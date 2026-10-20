let state,
  page = "Home",
  run = null,
  step = -1,
  mode = "team",
  selected = 0,
  executionMode = "real",
  connectionState = { ready: false },
  busy = false,
  activeTeamId = "",
  selectedAgentId = null,
  goalDraft = "Explain how a team can plan a picnic.";
const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
async function api(path, data) {
  if (path === "state" && data) data = { ...data, runs: [] };
  const r = await fetch(
    "/api/" + path,
    data
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }
      : {},
  );
  const v = await r.json();
  if (!r.ok) throw Error(v.error);
  return v;
}
function toast(t) {
  $("#toast").textContent = t;
  $("#toast").style.display = "block";
  setTimeout(() => ($("#toast").style.display = "none"), 4500);
}
function modal(html) {
  $("#dialogBody").innerHTML = html;
  $("#dialog").showModal();
}
async function persist() {
  try {
    state = await api("state", state);
    render();
  } catch (e) {
    toast(e.message);
  }
}
function nav() {
  const icons = ["⌂", "▷", "♙", "♟", "⚒", "ϟ", "♧", "◇"];
  $("#nav").innerHTML = [
    "Home",
    "Watch & run",
    "Agents",
    "Teams",
    "Tools",
    "Skills",
    "MCP Connections",
    "Architecture",
  ]
    .map(
      (n, i) =>
        `<button class="${page === n ? "active" : ""}" data-page="${n}">${icons[i]}　${n}</button>`,
    )
    .join("");
  document.querySelectorAll("[data-page]").forEach(
    (b) =>
      (b.onclick = () => {
        page = b.dataset.page;
        render();
        if (page === "Home")
          refreshConnection().then(() => {
            if (!connectionState.ready) connection();
          });
      }),
  );
}
function render() {
  nav();
  if (page === "Home") dashboard();
  else if (page === "Watch & run") home();
  else if (page === "Agents" || page === "Teams") catalog();
  else if (page === "Architecture") architecture();
  else resources();
}
function avatarClass(value) {
  return (
    {
      researcher: "portrait portrait-0",
      writer: "portrait portrait-1",
      reviewer: "portrait portrait-2",
      robot: "portrait robot-agent",
    }[value] || "portrait robot-agent"
  );
}
function dashboard() {
  const exampleCount = state.agents.filter((a) => a.example).length;
  const cards = [
    ["Agents", "Give each agent one clear job.", state.agents.length],
    ["Teams", "Choose which agents work together.", state.teams.length],
    ["Tools", "Small actions a agent may use.", state.catalog.tools.length],
    [
      "Skills",
      "Instructions that help a agent do its job.",
      state.catalog.skills.length,
    ],
    [
      "MCP Connections",
      "Connect a server and choose its tools.",
      state.catalog.mcp.length,
    ],
    [
      "Watch & run",
      "Set a goal and see each agent work.",
      state.runs.length + " saved runs",
    ],
  ];
  $("#main").innerHTML =
    `<h1>Your AI workshop</h1><p class="subtitle">Build a team. Give it a goal. Learn one step at a time.</p><section class="panel"><h2>Start here</h2><p>${state.agents.length ? `You have ${state.agents.length} saved agents. ${exampleCount} ${exampleCount === 1 ? "is an example configuration" : "are example configurations"}. A saved agent is a setup, not proof that AI has run.` : "This workspace is empty. Start with your own agent, or load a small example team."}</p><div class="toolbar"><button class="primary" id="ownSetup">${state.agents.length ? "Open my agents" : "Start empty · create my first agent"}</button><button id="examples">${exampleCount ? "View example agents" : "Load example team"}</button><button id="goWatch">Watch & run →</button><button id="educationalDemo">Educational samples (optional)</button></div><small>Saved on this computer in a persistent SQLite database (agentsim.db). Account credentials stay in protected local files and are never part of setup exports.</small></section><div class="list dashboard-cards">${cards.map(([name, description, count]) => `<button class="panel dashboard-card" data-open="${name}"><span class="dashboard-count">${esc(count)}</span><h2>${name}</h2><p>${description}</p><span>Open →</span></button>`).join("")}</div><section class="panel" style="margin-top:20px"><h2>Your next steps</h2><p>1. Create a agent or load examples. 2. Choose its job and permissions. 3. Pick a team in Watch & run. Demo shows samples. Real AI needs your own connection.</p><button id="dashboardConnect">Connection setup</button></section>`;
  document.querySelectorAll("[data-open]").forEach(
    (b) =>
      (b.onclick = () => {
        page = b.dataset.open;
        render();
      }),
  );
  $("#ownSetup").onclick = () => {
    page = "Agents";
    render();
    if (!state.agents.length) editor("agents");
  };
  $("#examples").onclick = async () => {
    try {
      if (!exampleCount) state = await api("examples", {});
      page = "Agents";
      render();
    } catch (e) {
      toast(e.message);
    }
  };
  $("#educationalDemo").onclick = () => {
    executionMode = "demo";
    page = "Watch & run";
    render();
  };
  $("#goWatch").onclick = () => {
    page = "Watch & run";
    render();
  };
  $("#dashboardConnect").onclick = connection;
}
function usageLabel(r, until = Infinity) {
  if (!r) return executionMode === "demo" ? "0 sample tokens" : "Not reported";
  const steps = r.steps.slice(0, until + 1);
  if (!steps.length) return "Not reported";
  if (
    r.provider !== "demo" &&
    steps.some((s) => s.inputTokens == null || s.outputTokens == null)
  )
    return "Not reported";
  return (
    steps.reduce(
      (n, s) =>
        n +
        (s.sampleInput ?? s.inputTokens ?? 0) +
        (s.sampleOutput ?? s.outputTokens ?? 0),
      0,
    ) + " tokens"
  );
}
function agentActivity(id) {
  let status = "idle";
  for (const event of run?.events || []) {
    const d = event.data;
    if (d.agentId !== id) continue;
    if (
      ["agent_started", "agent_resumed", "model_started"].includes(event.type)
    )
      status = "active";
    if (event.type === "agent_waiting") status = "waiting";
    if (event.type === "agent_completed") status = "done";
    if (event.type === "agent_failed") status = "failed";
  }
  if (run?.failed && ["active", "waiting"].includes(status)) status = "failed";
  if (run?.completed && ["active", "waiting"].includes(status)) status = "done";
  return status;
}
function liveAgentCard(a, managerId) {
  const id = a.agentId,
    status = agentActivity(id);
  const labels = {
    idle: "Not assigned yet",
    active: "Working now",
    waiting: "Waiting for a reply",
    done: "Result shared",
    failed: "Failed",
  };
  const usage = (run?.steps || []).filter((s) => s.agentId === id);
  const known =
    usage.length &&
    usage.every((s) => s.inputTokens != null && s.outputTokens != null);
  return `<article class="agent live-agent activity-${status} ${selectedAgentId === id ? "selected" : ""}" data-agent="${esc(id)}" tabindex="0" role="button" aria-label="Inspect ${esc(a.agent)}"><span class="agent-kind">${id === managerId ? "Team manager" : "Agent"}</span><div class="live-avatar"><div class="avatar ${avatarClass(a.avatar)}" aria-hidden="true"></div></div><h2>${esc(a.agent)}</h2><span class="badge"><span class="activity-dot" aria-hidden="true"></span>${labels[status]}</span><p>${esc(state.agents.find((x) => x.id === id)?.role || "Saved agent")}</p><small>${usage.length} completed task${usage.length === 1 ? "" : "s"}${known ? ` · ${usage.reduce((n, s) => n + s.inputTokens + s.outputTokens, 0)} tokens` : ""}</small></article>`;
}
function interactionTimeline() {
  const events = (run?.events || []).filter((e) =>
    [
      "delegation",
      "reply",
      "agent_started",
      "agent_completed",
      "agent_failed",
      "tool_started",
      "tool_completed",
      "tool_failed",
    ].includes(e.type),
  );
  if (!events.length)
    return '<p class="muted">Start a real run. Requests, replies and tool activity will appear here as they happen.</p>';
  return events
    .map((e, i) => {
      const d = e.data,
        time = new Date(e.time * 1000).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
      if (["delegation", "reply"].includes(e.type))
        return `<article class="dialogue-message ${e.type}"><small>${esc(time)} · ${e.type === "reply" ? "Reply" : d.kind === "question" ? "Question" : "Delegated task"}</small><h3>${esc(d.from)} <span aria-label="to">→</span> ${esc(d.to)}</h3><p>${esc(d.message)}</p>${d.context && e.type === "delegation" ? `<details><summary>Shared context</summary><p>${esc(d.context)}</p></details>` : ""}</article>`;
      if (e.type === "agent_completed" && d.manager)
        return `<article class="dialogue-message final-answer"><small>${esc(time)} · Final answer</small><h3>${esc(d.agent)}</h3><p>${esc(d.output)}</p></article>`;
      if (e.type === "agent_started")
        return `<div class="activity-event"><small>${esc(time)}</small><b>${esc(d.agent)} started a task</b><details><summary>Task received</summary><p>${esc(d.task)}</p></details></div>`;
      if (e.type === "agent_completed")
        return `<div class="activity-event"><small>${esc(time)}</small><b>${esc(d.agent)} shared a result</b>${run?.orchestration !== "managed" ? `<p>${esc(d.output)}</p>` : ""}</div>`;
      if (e.type === "agent_failed")
        return `<div class="activity-event danger"><b>${esc(d.agent)} could not complete the task</b></div>`;
      return `<div class="activity-event"><small>${esc(time)}</small><b>Tool ${e.type === "tool_started" ? "started" : e.type === "tool_failed" ? "failed" : "completed"}: ${esc(d.name)}</b>${e.type === "tool_completed" ? `<p>${esc(d.output)}</p>` : ""}</div>`;
    })
    .join("");
}
function realWatch() {
  const team = state.teams.find((t) => t.id === activeTeamId) || state.teams[0];
  activeTeamId = team?.id || "";
  const managerId = run?.managerId ?? (mode === "team" ? team?.manager : null);
  const members =
    run?.roster ||
    (team?.agents || [])
      .slice(0, mode === "one" ? 1 : 100)
      .map((id) => state.agents.find((a) => a.id === id))
      .filter(Boolean)
      .map((a) => ({ agentId: a.id, agent: a.name, avatar: a.avatar }));
  const manager = members.find((a) => a.agentId === managerId);
  const workers = members.filter((a) => a.agentId !== managerId);
  const inspected =
    members.find((a) => a.agentId === selectedAgentId) ||
    members.find((a) => agentActivity(a.agentId) === "active") ||
    manager ||
    members[0];
  const history = (run?.steps || []).filter(
    (s) => s.agentId === inspected?.agentId,
  );
  const last = history.at(-1);
  const currentTask = (run?.events || []).findLast(
    (e) => e.type === "agent_started" && e.data.agentId === inspected?.agentId,
  )?.data;
  const activity = inspected && agentActivity(inspected.agentId);
  const scroll = $("#conversation")?.scrollTop || 0;
  const follow =
    !$("#conversation") ||
    $("#conversation").scrollHeight - scroll - $("#conversation").clientHeight <
      90;
  const route = (run?.events || []).findLast((e) =>
    ["delegation", "reply"].includes(e.type),
  );
  $("#main").innerHTML =
    `<h1>Watch your team work</h1><p class="subtitle">Follow the manager's decisions and the agents' conversations live.</p>${run?.failed ? `<section class="panel danger" role="alert">${esc(run.error)}</section>` : ""}<div class="toolbar"><select aria-label="Run type" id="executionMode" ${busy ? "disabled" : ""}><option value="real">Real AI · live</option><option value="demo">Educational samples · optional</option></select><select aria-label="Team" id="team" ${busy ? "disabled" : ""}>${state.teams.map((t) => `<option value="${esc(t.id)}" ${t.id === activeTeamId ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select><button id="teamMode" class="${mode === "team" ? "primary" : ""}" ${busy ? "disabled" : ""}>Team</button><button id="one" class="${mode === "one" ? "primary" : ""}" ${busy ? "disabled" : ""}>One agent</button><button id="configureTeam" ${busy ? "disabled" : ""}>Configure manager</button></div><div class="panel goal-panel"><label for="goal">Your goal</label><div class="goal-actions"><input id="goal" maxlength="500" value="${esc(run?.goal || goalDraft)}" ${busy ? "disabled" : ""}><button class="orange" id="start" ${busy || !members.length ? "disabled" : ""}>${busy ? "Running…" : run ? "Run again" : "Run with AI"}</button></div></div><div class="layout live-layout"><div><section class="panel orchestration-panel"><div class="section-heading"><div><h2>${manager ? "Manager-led orchestration" : mode === "one" ? "Single agent" : "Choose your team manager"}</h2><p class="muted">${manager ? "The manager chooses who to involve and when. Agents can be called more than once." : mode === "one" ? "Watch this agent complete your goal." : "Open Configure manager to select who coordinates this team."}</p></div><span class="badge ${busy ? "working" : ""}">${busy ? "● Live" : run?.failed ? "Failed" : run?.completed ? "Complete" : "Ready"}</span></div>${manager ? `<div class="delegation-route ${busy && route ? "live-route" : ""}">${route ? `${esc(route.data.from)} → ${esc(route.data.to)} · ${route.type === "reply" ? "reply" : "task / question"}` : "↕ The manager chooses assignments; agents return their results"}</div>` : ""}<div class="orchestration-board">${manager ? liveAgentCard(manager, managerId) : ""}${workers.map((a) => liveAgentCard(a, managerId)).join("")}</div><p class="legend"><span class="activity-dot"></span> A pulsing card is executing. “Waiting for a reply” means work was delegated. Agents not selected by the manager stay idle.</p></section><section class="panel"><div class="section-heading"><h2>Live conversation</h2><span>${run?.events?.filter((e) => e.type === "delegation").length || 0} delegations</span></div><div id="conversation" class="conversation" role="log" aria-live="polite" aria-relevant="additions">${interactionTimeline()}</div><small>Actual tasks, questions and replies. Internal model reasoning is never displayed.</small>${run?.completed ? '<p class="run-complete">✓ Run complete. The final answer and conversation are saved.</p>' : ""}</section></div><div class="inspector"><section class="panel"><h2>Inspect an agent</h2><h3>${esc(inspected?.agent || "Choose an agent")}</h3><p>${esc(inspected?.agentId === managerId ? "Coordinates the team and combines its results." : "Select a card to inspect the task and answer.")}</p><details open><summary>Task received</summary><p>${esc((inspected?.agentId === managerId ? run?.goal || goalDraft : currentTask?.task || last?.input) || "No task assigned yet.")}</p></details><details open><summary>Answer</summary><p>${esc(activity === "active" ? "Working on the current task…" : last?.output || "No completed answer yet.")}</p></details><small>Model: ${esc(last?.model || state.agents.find((a) => a.id === inspected?.agentId)?.model?.name || "Choose in agent settings")}</small></section><section class="panel"><h2>Provider usage</h2><p>${usageLabel(run, run?.steps.length || 0)}</p><p>${run?.events?.filter((e) => e.type === "tool_completed").length || 0} tool calls completed</p><small>Usage comes from the provider. Missing usage stays unavailable.</small></section></div></div>`;
  const conversation = $("#conversation");
  conversation.scrollTop = follow ? conversation.scrollHeight : scroll;
  $("#goal").oninput = (e) => (goalDraft = e.target.value);
  $("#team").onchange = (e) => {
    activeTeamId = e.target.value;
    run = null;
    selectedAgentId = null;
    realWatch();
  };
  $("#one").onclick = () => {
    mode = "one";
    run = null;
    realWatch();
  };
  $("#teamMode").onclick = () => {
    mode = "team";
    run = null;
    realWatch();
  };
  $("#executionMode").onchange = (e) => {
    executionMode = e.target.value;
    run = null;
    step = -1;
    home();
  };
  $("#configureTeam").onclick = () =>
    team ? editor("teams", team.id) : editor("teams");
  document.querySelectorAll("[data-agent]").forEach((card) => {
    const inspect = () => {
      selectedAgentId = card.dataset.agent;
      realWatch();
    };
    card.onclick = inspect;
    card.onkeydown = (e) => {
      if (["Enter", " "].includes(e.key)) {
        e.preventDefault();
        inspect();
      }
    };
  });
  $("#start").onclick = async () => {
    if (mode === "team" && !team?.manager) {
      toast("Choose the team's manager first.");
      editor("teams", team?.id);
      return;
    }
    goalDraft = $("#goal").value;
    await refreshConnection();
    if (!connectionState.ready) {
      await connection();
      return;
    }
    await realRun({ goal: goalDraft, team: team.id, mode });
  };
}
function architecture() {
  const team = state.teams.find((t) => t.id === activeTeamId) || state.teams[0];
  const manager = state.agents.find((a) => a.id === team?.manager);
  const node = (x, y, w, title, sub) =>
    `<g><rect x="${x}" y="${y}" width="${w}" height="76" rx="12"/><text x="${x + w / 2}" y="${y + 29}" text-anchor="middle" class="node-title">${esc(title)}</text><text x="${x + w / 2}" y="${y + 53}" text-anchor="middle">${esc(sub)}</text></g>`;
  $("#main").innerHTML =
    `<h1>Architecture</h1><p class="subtitle">The components behind the current AgentSim application.</p><section class="panel"><h2>Application and execution</h2><svg class="architecture-diagram" viewBox="0 0 920 510" role="img" aria-label="Browser connects to the Python API. CrewAI runs the manager and agents, calls Responses models and authorized tools. SQLite stores configuration and completed runs. Live events return to the browser."><defs><marker id="arch-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8" fill="#8b79fa"/></marker></defs><g class="diagram-lines"><path d="M210 80H340"/><path d="M470 118V190"/><path d="M600 80H730V190"/><path d="M340 228H210"/><path d="M600 228H660"/><path d="M470 266V365"/><path d="M210 228V118"/></g>${node(30, 42, 180, "Browser UI", "HTML · CSS · JavaScript")}${node(340, 42, 260, "Python HTTP API", "Loopback · background jobs")}${node(340, 190, 260, "CrewAI", "Manager → selected agents")}${node(30, 190, 180, "Live events", "SSE → cards + conversation")}${node(660, 190, 230, "SQLite", "Profiles · teams · saved runs")}${node(340, 365, 260, "Responses API", "Each agent's chosen model")}${node(35, 365, 230, "Tools and MCP", "Explicit per-agent permissions")}<path class="diagram-lines" d="M340 243H290V403H265" marker-end="url(#arch-arrow)"/><text x="470" y="310" text-anchor="middle">Tasks, delegation and replies</text></svg><p class="muted">Credentials stay in protected local files. CrewAI coordinates execution; the model makes delegation choices. The browser receives public activity events, not private reasoning.</p></section><section class="panel"><h2>Selected team: ${esc(team?.name || "No team configured")}</h2><select id="architectureTeam" aria-label="Architecture team" ${busy ? "disabled" : ""}>${state.teams.map((t) => `<option value="${esc(t.id)}" ${t.id === team?.id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select><div class="architecture-team"><div class="architecture-manager">${manager ? `<b>${esc(manager.name)}</b><span>Manager · decides assignments and combines replies</span>` : "<b>No manager selected</b><span>Configure a manager to enable dynamic orchestration.</span>"}</div><div class="architecture-links">↕ Delegation, questions and replies · no fixed agent order</div><div class="architecture-workers">${(
      team?.agents || []
    )
      .filter((id) => id !== team?.manager)
      .map((id) => state.agents.find((a) => a.id === id))
      .filter(Boolean)
      .map(
        (a) =>
          `<div><b>${esc(a.name)}</b><span>${esc(a.role)}</span><small>${esc(a.model.name || "Model not selected")}</small></div>`,
      )
      .join(
        "",
      )}</div></div><p class="muted">This diagram describes the saved configuration. Watch & run shows which agents are actually involved in each execution. Single-agent mode bypasses team management.</p><button id="architectureWatch" class="primary">Watch & run →</button></section>`;
  $("#architectureTeam").onchange = (e) => {
    activeTeamId = e.target.value;
    run = null;
    selectedAgentId = null;
    architecture();
  };
  $("#architectureWatch").onclick = () => {
    page = "Watch & run";
    render();
  };
}

function home() {
  if (executionMode === "real") return realWatch();
  const teamId = $("#team")?.value || state.teams[0]?.id;
  const members = run
    ? run.steps
    : (state.teams.find((t) => t.id === teamId)?.agents || [])
        .map((id) => state.agents.find((a) => a.id === id))
        .filter(Boolean)
        .slice(0, mode === "one" ? 1 : 100)
        .map((a) => ({ agent: a.name, agentId: a.id, avatar: a.avatar }));
  const current =
    run?.steps[Math.max(0, Math.min(selected, run.steps.length - 1))];
  $("#main").innerHTML =
    `<h1>Watch your team work</h1>${run?.failed ? `<section class="panel danger" role="alert">${esc(run.error)}</section>` : ""}<p class="subtitle">See who does what, one step at a time.</p><div class="layout"><div><div class="toolbar"><select aria-label="Run type" id="executionMode"><option value="real">Real AI · automatic</option><option value="demo">Educational samples · optional</option></select><select aria-label="Team" id="team">${state.teams.map((t) => `<option value="${esc(t.id)}" ${t.id === teamId ? "selected" : ""}>♟ Team: ${esc(t.name)}</option>`).join("")}</select><div><button id="one" class="${mode === "one" ? "primary" : ""}">One agent</button><button id="teamMode" class="${mode === "team" ? "primary" : ""}">Team</button></div><button class="orange" id="start" ${busy ? "disabled" : ""}>▶ ${busy ? "Working…" : run ? "Run again" : executionMode === "demo" ? "Start demo" : "Run with AI"}</button></div><div class="steps"><span><b class="circle">1</b>Set a goal</span>→<span><b class="circle">2</b>Pick agents</span>→<span><b class="circle">3</b>Watch & learn</span></div><div class="panel"><label for="goal">Your goal</label><input id="goal" maxlength="500" value="${esc(run?.goal || "Explain how a team can plan a picnic.")}" style="margin:8px 0 18px"><div class="cards">${members.map((a, i) => `${i ? `<span class="handoff">${run && i <= step ? `<small>${esc(run.provider === "demo" ? "Here are the sample facts." : run.steps[i - 1]?.output.slice(0, 65))}</small>` : ""}<span class="arrow">→</span></span>` : ""}<article class="agent ${i === selected ? "selected" : ""}" data-step="${i}" tabindex="0" role="button" aria-label="Learn about ${esc(a.agent)}"><div class="avatar ${avatarClass(a.avatar || state.agents.find((x) => x.id === a.agentId)?.avatar)}" aria-hidden="true"></div><h2>${esc(a.agent)}</h2>${state.agents.find((x) => x.id === a.agentId)?.example ? '<small class="muted">Example configuration</small>' : ""}<span class="badge ${i < step ? "done" : i === step ? "working" : ""}">${i < step ? "✓ Done" : run?.failed && i === step ? "× Failed" : i === step ? "● Working" : "◷ Waiting"}</span><p>${esc(state.agents.find((x) => x.id === a.agentId)?.job || "Saved agent")}</p><div class="tokens">${run && i <= step ? (run.provider === "demo" ? `Sample input ${run.steps[i].sampleInput} · output ${run.steps[i].sampleOutput}` : `Input ${run.steps[i].inputTokens ?? "—"} · output ${run.steps[i].outputTokens ?? "—"} tokens`) : "Tokens: no provider usage"}</div></article>`).join("") || "<p>Add agents to a team to begin.</p>"}</div></div><div class="panel usage"><span>▤ ${(run?.provider || executionMode) === "demo" ? "Sample usage" : "Provider usage"}: <b>${usageLabel(run, step)}</b></span><span>${run?.events?.filter((e) => e.type === "tool_completed").length || 0} real tool calls</span><span>${esc(run?.provider || executionMode)} ${busy ? "• Working…" : ""}</span></div><div class="panel"><h2>What is happening?</h2>${
      run
        ? run.steps
            .slice(0, step + 1)
            .map(
              (s, i) =>
                `<div class="event"><b>Step ${i + 1} · ${esc(s.agent)} ${i === step ? "is working" : run.provider === "demo" ? "shared a sample" : "shared a result"}</b><p>${esc(i === step ? (run.provider === "demo" ? "Press Next step to pass the result along." : "This agent is working. Results appear automatically.") : s.output)}</p></div>`,
            )
            .join("")
        : '<p class="muted">Choose a team and a goal. Real work advances automatically; the optional sample lesson has its own controls.</p>'
    }${
      run?.events
        ?.filter((e) => e.type === "tool_completed")
        .map(
          (e) =>
            `<div class="event"><b>Tool: ${esc(e.data.name)}</b><p>${esc(e.data.output)}</p></div>`,
        )
        .join("") || ""
    }${run && step >= run.steps.length ? `<b>✓ ${run.provider === "demo" ? "Sample lesson complete." : "Real run complete."} Everyone has shared their result.</b>` : ""}</div></div><div class="inspector"><section class="panel"><h2>Learn this step</h2>${[
      ["What went in", current?.input],
      [
        "What came out",
        current && selected <= step
          ? current.output
          : "This step has not completed its answer yet.",
      ],
      [
        "Why this step?",
        current?.why ||
          "Teaching explanation: agents share small jobs and pass results to each other. This describes the setup, not private thoughts.",
      ],
    ]
      .map(
        ([title, text], i) =>
          `<details ${i === 2 ? "open" : ""}><summary>${title}</summary><p>${esc(text || "Run the team to inspect this step.")}</p></details>`,
      )
      .join(
        "",
      )}<small>Outputs and teaching explanations. No private internal thoughts.</small></section><section class="panel"><h2>Give your agent a job</h2><h3>${esc(current?.agent || members[0]?.agent || "Your agent")}</h3><p class="muted">${esc(state.agents.find((a) => a.id === (current?.agentId || members[0]?.agentId))?.job || "Choose a agent to begin.")}</p><p class="muted">Model: ${esc(current?.model || state.agents.find((a) => a.id === (current?.agentId || members[0]?.agentId))?.model?.name || "Choose in Profile")}</p><button id="editAgents">Edit job & permissions</button><p>${current ? `Tools: ${esc(current.assignments?.tools?.join(", ") || "None")}<br>Skills: ${esc(current.assignments?.skills?.join(", ") || "None")}<br>MCP: ${esc(current.assignments?.mcp?.join(", ") || "None")}` : "Choose tools, skills and MCP tools in Agents."}</p>${executionMode === "demo" ? `<button class="purple" id="next" ${!run || busy || step >= run.steps.length ? "disabled" : ""}>Next step →</button>` : '<p class="muted">Real AI runs automatically. Watch completed steps appear here.</p>'}<button id="compare" style="width:100%;margin-top:12px">◫ Compare runs</button></section></div></div>`;
  $("#executionMode").value = executionMode;
  $("#executionMode").onchange = () => {
    executionMode = $("#executionMode").value;
    run = null;
    step = -1;
    home();
  };
  $("#one").onclick = () => {
    mode = "one";
    run = null;
    step = -1;
    home();
  };
  $("#teamMode").onclick = () => {
    mode = "team";
    run = null;
    step = -1;
    home();
  };
  $("#team").onchange = () => {
    run = null;
    step = -1;
    home();
  };
  $("#start").onclick = async () => {
    try {
      const body = { goal: $("#goal").value, team: $("#team").value, mode };
      if (executionMode !== "demo") {
        await refreshConnection();
        if (!connectionState.ready) {
          await connection();
          return;
        }
        await realRun(body);
        return;
      }
      run = await api("run", body);
      state = await api("state");
      step = 0;
      selected = 0;
      home();
    } catch (e) {
      toast(e.message);
    }
  };
  if ($("#next"))
    $("#next").onclick = () => {
      step++;
      selected = Math.min(step, run.steps.length - 1);
      home();
    };
  $("#editAgents").onclick = () => {
    page = "Agents";
    render();
  };
  $("#compare").onclick = compare;
  document.querySelectorAll("[data-step]").forEach((el) => {
    el.onclick = () => {
      selected = +el.dataset.step;
      home();
    };
    el.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        el.click();
      }
    };
  });
}
function catalog() {
  const agents = page === "Agents",
    key = agents ? "agents" : "teams";
  $("#main").innerHTML =
    `<h1>${page}</h1><p class="subtitle">${agents ? "Give each agent a clear job." : "Choose a manager and the agents who work with it."}</p><div class="toolbar"><button class="primary" id="add">+ Add ${agents ? "agent" : "team"}</button><button id="export">Export setup</button><label><button id="importButton">Import setup</button><input hidden type="file" accept="application/json,.json" id="import"></label></div><div class="list">${state[key].map((a) => `<section class="panel">${agents ? `<div class="avatar ${avatarClass(a.avatar)}" aria-hidden="true"></div>` : ""}<h2>${esc(a.name)}</h2>${a.example ? '<span class="badge">Example configuration</span>' : '<span class="badge">Your saved configuration</span>'}<p>${esc(agents ? a.job : `${a.manager ? `Manager: ${state.agents.find((x) => x.id === a.manager)?.name} · ` : "Choose a manager · "}${a.agents.map((id) => state.agents.find((x) => x.id === id)?.name).join(" · ")}`)}</p><button data-edit="${esc(a.id)}">Edit</button> <button class="danger" data-delete="${esc(a.id)}">Delete</button></section>`).join("")}</div>`;
  $("#add").onclick = () => editor(key);
  document
    .querySelectorAll("[data-edit]")
    .forEach((b) => (b.onclick = () => editor(key, b.dataset.edit)));
  document.querySelectorAll("[data-delete]").forEach(
    (b) =>
      (b.onclick = async () => {
        state[key] = state[key].filter((a) => a.id !== b.dataset.delete);
        if (agents)
          state.teams.forEach((t) => {
            t.agents = t.agents.filter((id) => id !== b.dataset.delete);
            if (t.manager === b.dataset.delete || t.agents.length < 2)
              delete t.manager;
          });
        await persist();
      }),
  );
  $("#export").onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(
      new Blob([JSON.stringify({ ...state, runs: [] }, null, 2)], {
        type: "application/json",
      }),
    );
    a.download = "agentsim-setup.json";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  $("#importButton").onclick = () => $("#import").click();
  $("#import").onchange = async (e) => {
    try {
      const f = e.target.files[0];
      if (f.size > 200000) throw Error("File limit: 200 KB.");
      const data = JSON.parse(await f.text());
      state = await api("state", data);
      render();
      toast("Setup imported. Saved runs were kept.");
    } catch (err) {
      toast(err.message);
    }
  };
}
function checks(key, values, items) {
  return items
    .map(
      (x) =>
        `<label class="check"><input type="checkbox" name="${key}" value="${esc(x.id)}" ${values.includes(x.id) ? "checked" : ""}>${esc(x.name)}</label>`,
    )
    .join("");
}
function agentEditor(id) {
  const a = state.agents.find((a) => a.id === id) || {
    name: "",
    role: "",
    goal: "",
    backstory: "",
    instructions: "",
    purpose: "",
    exampleInput: "",
    exampleOutput: "",
    expectedOutput: "A short, helpful answer in plain English.",
    tools: [],
    skills: [],
    mcp: [],
    model: {
      mode: "inherit",
      name: "",
      temperature: null,
      maxOutputTokens: null,
      contextWindow: 32000,
    },
    behavior: {
      maxIterations: 6,
      maxRetries: 0,
      maxExecutionSeconds: 120,
      maxRequestsPerMinute: 0,
      respectContextWindow: true,
    },
  };
  const field = (name, label, help = "", multi = false) =>
    `<label class="field">${label}${multi ? `<textarea aria-label="${label}" name="${name}" rows="3">${esc(a[name])}</textarea>` : `<input aria-label="${label}" name="${name}" value="${esc(a[name])}">`}${help ? `<small>${help}</small>` : ""}</label>`;
  modal(
    `<h2>${id ? "Edit" : "Create"} agent</h2><p>${a.example ? "Example configuration. You can edit it or save it as your own." : "Give this agent a clear identity, job and boundaries."}</p><div class="editor-tabs" role="tablist">${[
      ["profile", "1 · Identity"],
      ["job", "2 · Job"],
      ["settings", "3 · Model & settings"],
      ["tools", "4 · Tools"],
      ["skills", "5 · Skills"],
      ["mcps", "6 · MCPs"],
    ]
      .map(
        ([key, label], i) =>
          `<button type="button" role="tab" id="tab-${key}" data-tab="${key}" aria-controls="panel-${key}" aria-selected="${i === 0}">${label}</button>`,
      )
      .join(
        "",
      )}</div><form id="agentForm" novalidate><section id="panel-profile" role="tabpanel" aria-labelledby="tab-profile"><fieldset class="avatar-choices"><legend>Choose a character</legend>${["researcher", "writer", "reviewer", "robot"].map((v) => `<label class="avatar-choice"><input type="radio" name="avatar" value="${v}" ${(a.avatar || "robot") === v ? "checked" : ""}><span class="avatar ${avatarClass(v)}" aria-hidden="true"></span><span>${v[0].toUpperCase() + v.slice(1)}</span></label>`).join("")}</fieldset><div class="form-grid">${field("name", "Name", "A short label, such as Picnic researcher.")}${field("role", "Role or specialty", "What is this agent good at? Used as CrewAI role.")}</div></section><section id="panel-job" role="tabpanel" aria-labelledby="tab-job" hidden><h3>What should this agent do?</h3>${field("goal", "Goal", "The job this agent should achieve. Used as CrewAI goal.", true)}${field("purpose", "What is this agent for?", "Helps the agent understand its purpose.", true)}${field("backstory", "Context and characteristics", "Background, audience and expertise. Used in CrewAI backstory.", true)}${field("instructions", "Instructions and boundaries", "How should it work? Be concrete. These instructions are sent with its task.", true)}${field("expectedOutput", "Expected result", "Describe the answer you want. Used as the task expected output.", true)}</section><section id="panel-settings" role="tabpanel" aria-labelledby="tab-settings" hidden><section class="panel"><h3>This agent's model</h3><label class="field">Model<select name="modelName" id="agentModel" aria-describedby="agentModelStatus"><option value="">Choose an available model</option>${a.model.name ? `<option value="${esc(a.model.name)}" selected>${esc(a.model.name)} · saved, availability not checked</option>` : ""}</select></label><p id="agentModelStatus" class="muted" role="status" aria-live="polite">Models load automatically from your connected account.</p><button type="button" id="agentModels">Refresh models</button><small class="model-hint">Each agent keeps its own model. A blank model is allowed in a saved draft, but real execution will ask you to select one.</small></section><details><summary>Teaching examples</summary><p>Examples show a style. They are clearly marked as examples, not the current goal or verified facts.</p>${field("exampleInput", "Example input", "", true)}${field("exampleOutput", "Example answer", "", true)}</details><details><summary>Advanced: model and behavior</summary><p>Optional model parameters are sent only when set. Model selection belongs to this agent.</p><div class="form-grid"><label class="field">Temperature (optional)<input type="number" step="0.1" min="0" max="2" name="temperature" value="${a.model.temperature ?? ""}"><small>Blank leaves the provider default. Some models reject temperature; a failed request is shown, never silently changed.</small></label><label class="field">Output token limit (optional)<input type="number" min="16" max="16000" name="maxOutputTokens" value="${a.model.maxOutputTokens ?? ""}"><small>Sent as max_output_tokens only when set. Check your model's supported limits.</small></label><label class="field">CrewAI context budget<input type="number" name="contextWindow" min="4096" max="2000000" value="${a.model.contextWindow ?? 32000}"><small>Used by CrewAI to manage long conversations. Set it to your model's actual capacity; this does not enlarge the model.</small></label>${[
      [
        "maxIterations",
        "Maximum work cycles",
        1,
        20,
        "How many model/tool cycles may this agent use?",
      ],
      [
        "maxRetries",
        "Task retries",
        0,
        2,
        "Retries may use more provider tokens.",
      ],
      [
        "maxExecutionSeconds",
        "Time limit (seconds)",
        10,
        600,
        "CrewAI execution limit for this agent.",
      ],
      [
        "maxRequestsPerMinute",
        "Requests per minute",
        0,
        120,
        "0 means no extra CrewAI rate limit.",
      ],
    ]
      .map(
        ([k, label, min, max, help]) =>
          `<label class="field">${label}<input type="number" name="${k}" min="${min}" max="${max}" value="${a.behavior[k]}"><small>${help}</small></label>`,
      )
      .join(
        "",
      )}</div><label class="check"><input type="checkbox" name="respectContextWindow" ${a.behavior.respectContextWindow ? "checked" : ""}>Let CrewAI manage the context budget</label><small>Private reasoning, automatic delegation and arbitrary code execution are not enabled by these settings.</small></details><button type="button" id="previewProfile">Preview profile and task inputs</button><pre id="profilePreview" hidden></pre></section><section id="panel-tools" role="tabpanel" aria-labelledby="tab-tools" hidden><h3>Tools this agent may use</h3><p>Each choice is a permission. Tools are only called when the agent requests them.</p>${checks("tools", a.tools, state.catalog.tools)}</section><section id="panel-skills" role="tabpanel" aria-labelledby="tab-skills" hidden><h3>Skills and instructions</h3><p>Skills add instructions. They never turn on a tool.</p>${checks("skills", a.skills, state.catalog.skills)}${state.catalog.skills
      .filter((s) => s.requires.length)
      .map(
        (s) =>
          `<p class="muted">${esc(s.name)} needs: ${esc(s.requires.join(", "))}</p>`,
      )
      .join(
        "",
      )}</section><section id="panel-mcps" role="tabpanel" aria-labelledby="tab-mcps" hidden><h3>MCP tools this agent may use</h3><p>A connection can offer many tools. Choose only the tools this agent needs.</p>${state.catalog.mcp
      .map(
        (c) =>
          `<div class="panel"><h3>${esc(c.name)}</h3>${checks(
            "mcp",
            a.mcp,
            c.tools.map((t) => ({
              id: c.id + ":" + t.id,
              name: t.name + " (" + t.id + ")",
            })),
          )}${!c.tools.length ? "<p>Discover this connection’s tools in MCP Connections first.</p>" : ""}</div>`,
      )
      .join(
        "",
      )}</section><div class="editor-footer">${a.example ? '<label class="check"><input type="checkbox" name="makeOwn">Save as my own configuration</label>' : ""}<div class="editor-navigation"><button type="button" id="agentPrevious">← Back</button><button type="button" id="agentNext">Next →</button><button class="primary">Save agent</button></div></div></form>`,
  );
  const stepKeys = ["profile", "job", "settings", "tools", "skills", "mcps"];
  let activeStep = 0,
    modelRequest = 0,
    activeConnection = null;
  const modelCache = new Map(),
    selectedModels = new Map([
      [a.model.connection || "chatgpt", a.model.name || ""],
    ]);
  const modelPicker = $("#agentModel"),
    modelStatus = $("#agentModelStatus");
  const showModels = (models, connection) => {
    const saved = selectedModels.get(connection) || "";
    const hasSaved = models.some((m) => m.id === saved);
    modelPicker.innerHTML =
      '<option value="">Choose an available model</option>' +
      models
        .map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`)
        .join("") +
      (!hasSaved && saved
        ? `<option value="${esc(saved)}">${esc(saved)} · saved, not returned by this connection</option>`
        : "");
    modelPicker.value = saved;
    modelStatus.textContent = models.length
      ? `${models.length} available model${models.length === 1 ? "" : "s"} loaded from this connection.${saved && !hasSaved ? " The saved model was not returned; choose an available model before running." : ""}`
      : "This connection returned no available models.";
    modelStatus.className = "muted";
  };
  const loadModels = async (force = false) => {
    const request = ++modelRequest;
    if (!force && activeConnection && modelCache.has(activeConnection)) {
      showModels(modelCache.get(activeConnection), activeConnection);
      modelPicker.removeAttribute("aria-busy");
      $("#agentModels").disabled = false;
      return;
    }
    modelStatus.textContent = "Loading available models…";
    modelStatus.className = "muted";
    modelPicker.setAttribute("aria-busy", "true");
    $("#agentModels").disabled = true;
    try {
      const settings = await api("settings");
      if (request !== modelRequest || $("#agentModel") !== modelPicker) return;
      const connection = settings.provider;
      const response = await api("models", { connection });
      if (request !== modelRequest || $("#agentModel") !== modelPicker) return;
      const models = response.models.filter(
        (m, i, all) =>
          typeof m.id === "string" && all.findIndex((x) => x.id === m.id) === i,
      );
      activeConnection = connection;
      modelCache.set(connection, models);
      showModels(models, connection);
    } catch (e) {
      if (request !== modelRequest || $("#agentModel") !== modelPicker) return;
      const saved =
        selectedModels.get(activeConnection || a.model.connection) || "";
      modelPicker.innerHTML =
        '<option value="">Connect your account to load models</option>' +
        (saved
          ? `<option value="${esc(saved)}">${esc(saved)} · saved, availability not checked</option>`
          : "");
      modelPicker.value = saved;
      modelStatus.textContent =
        e.message +
        (saved
          ? " Your saved model has been kept."
          : " Open Connection setup, then refresh this list.");
      modelStatus.className = "danger";
    } finally {
      if (request === modelRequest && $("#agentModel") === modelPicker) {
        modelPicker.removeAttribute("aria-busy");
        $("#agentModels").disabled = false;
      }
    }
  };
  modelPicker.onchange = () =>
    selectedModels.set(
      activeConnection || a.model.connection,
      modelPicker.value,
    );
  $("#agentModels").onclick = () => loadModels(true);
  const switchTab = (key) => {
    activeStep = stepKeys.indexOf(key);
    document.querySelectorAll("[data-tab]").forEach((b) => {
      b.setAttribute("aria-selected", String(b.dataset.tab === key));
      b.tabIndex = b.dataset.tab === key ? 0 : -1;
    });
    stepKeys.forEach((k) => ($("#panel-" + k).hidden = k !== key));
    $("#agentPrevious").disabled = activeStep === 0;
    $("#agentNext").hidden = activeStep === stepKeys.length - 1;
    if (key === "settings") loadModels();
    $("#dialog").scrollTop = 0;
  };
  document.querySelectorAll("[data-tab]").forEach((b, i) => {
    b.onclick = () => switchTab(b.dataset.tab);
    b.onkeydown = (e) => {
      if (["ArrowRight", "ArrowLeft"].includes(e.key)) {
        e.preventDefault();
        const keys = stepKeys;
        const next =
          keys[
            (i + (e.key === "ArrowRight" ? 1 : keys.length - 1)) % keys.length
          ];
        switchTab(next);
        $("#tab-" + next).focus();
      }
    };
  });
  $("#agentPrevious").onclick = () =>
    switchTab(stepKeys[Math.max(0, activeStep - 1)]);
  $("#agentNext").onclick = () =>
    switchTab(stepKeys[Math.min(stepKeys.length - 1, activeStep + 1)]);
  switchTab("profile");
  const collect = () => {
    const f = new FormData($("#agentForm"));
    const obj = {
      id: id || crypto.randomUUID(),
      name: f.get("name"),
      job: f.get("goal"),
      avatar: f.get("avatar"),
      tools: f.getAll("tools"),
      skills: f.getAll("skills"),
      mcp: f.getAll("mcp"),
      profileVersion: 1,
    };
    [
      "role",
      "goal",
      "backstory",
      "instructions",
      "purpose",
      "exampleInput",
      "exampleOutput",
      "expectedOutput",
    ].forEach((k) => (obj[k] = f.get(k)));
    obj.model = {
      mode: "custom",
      connection: activeConnection || a.model.connection || "chatgpt",
      name: modelPicker.value,
      temperature:
        f.get("temperature") === "" ? null : Number(f.get("temperature")),
      maxOutputTokens:
        f.get("maxOutputTokens") === ""
          ? null
          : Number(f.get("maxOutputTokens")),
      contextWindow: Number(f.get("contextWindow")),
    };
    obj.behavior = { respectContextWindow: f.has("respectContextWindow") };
    [
      "maxIterations",
      "maxRetries",
      "maxExecutionSeconds",
      "maxRequestsPerMinute",
    ].forEach((k) => (obj.behavior[k] = Number(f.get(k))));
    if (a.example) obj.example = !f.has("makeOwn");
    return obj;
  };
  $("#previewProfile").onclick = () => {
    const o = collect();
    $("#profilePreview").hidden = false;
    $("#profilePreview").textContent =
      "Your configured inputs. CrewAI also adds its own framework and task instructions. No credentials are included.\n\n" +
      JSON.stringify(o, null, 2);
  };
  $("#agentForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const obj = collect();
      const next = structuredClone(state);
      if (id) next.agents = next.agents.map((x) => (x.id === id ? obj : x));
      else next.agents.push(obj);
      state = await api("state", next);
      $("#dialog").close();
      render();
      toast("Agent profile and permissions saved.");
    } catch (e) {
      const form = $("#agentForm");
      if (!form.elements.name.value.trim() || !form.elements.role.value.trim())
        switchTab("profile");
      else if (!form.elements.goal.value.trim()) switchTab("job");
      else switchTab("settings");
      toast(e.message);
    }
  };
}
function editor(key, id) {
  if (key === "agents") return agentEditor(id);
  const team = state.teams.find((t) => t.id === id) || { name: "", agents: [] };
  modal(
    `<h2>${id ? "Edit" : "Create"} team</h2><form id="teamForm"><label class="field">Name<input name="name" maxlength="80" value="${esc(team.name)}" required></label><label class="field">Team manager<select name="manager" id="teamManager" aria-label="Team manager" required><option value="">Choose the agent who coordinates this team</option>${state.agents.map((a) => `<option value="${esc(a.id)}" ${a.id === team.manager ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select><small>The manager decides which agents to call and in what order. It coordinates through delegation; the other agents use their own tools and MCP permissions.</small></label><p>Select the manager and at least one other agent. The order below is not an execution sequence.</p>${checks("agents", team.agents, state.agents)}${team.example ? '<label class="check"><input type="checkbox" name="makeOwn">Save as my own configuration</label>' : ""}<button class="primary">Save team</button></form>`,
  );
  $("#teamManager").onchange = (e) => {
    const checkbox = [
      ...document.querySelectorAll('#teamForm input[name="agents"]'),
    ].find((c) => c.value === e.target.value);
    if (checkbox) checkbox.checked = true;
  };
  $("#teamForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const f = new FormData(e.target);
      const result = {
        id: id || crypto.randomUUID(),
        name: f.get("name"),
        agents: f.getAll("agents"),
        manager: f.get("manager"),
      };
      if (team.example) result.example = !f.has("makeOwn");
      const next = structuredClone(state);
      if (id) next.teams = next.teams.map((t) => (t.id === id ? result : t));
      else next.teams.push(result);
      state = await api("state", next);
      $("#dialog").close();
      render();
      toast("Team saved.");
    } catch (e) {
      toast(e.message);
    }
  };
}
function importSkill() {
  modal(
    `<h2>Import a skill</h2><p>Paste a plain JSON skill. This adds instructions only. It never installs or runs code.</p><form id="skillForm"><label class="field">Skill JSON<textarea id="skillJson" rows="12">${esc(JSON.stringify({ id: "friendly-plan", name: "Friendly plan", description: "Write a plan that is easy to follow.", instructions: "Use three short steps. Explain new words. Give one example.", requires: [] }, null, 2))}</textarea></label><button class="primary">Validate and import</button></form>`,
  );
  $("#skillForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      state = await api("skills", JSON.parse($("#skillJson").value));
      $("#dialog").close();
      render();
      toast("Skill imported. Assign it to an agent when ready.");
    } catch (e) {
      toast(e.message);
    }
  };
}
function mcpEditor(id) {
  const c = state.catalog.mcp.find((c) => c.id === id) || {
    id: "",
    name: "",
    url: "",
    authType: "none",
    headerName: "X-API-Key",
  };
  modal(
    `<h2>${id ? "Edit" : "Add"} MCP connection</h2><p>Use a server you trust. Saving or changing a connection clears its tool grants. Discover its tools, then choose each permission in Agents.</p><form id="mcpForm"><label class="field">Connection id<input required pattern="[a-z0-9-]+" name="id" value="${esc(c.id)}" ${id ? "readonly" : ""}></label><label class="field">Name<input required maxlength="80" name="name" value="${esc(c.name)}"></label><label class="field">Streamable HTTP endpoint<input required type="url" name="url" value="${esc(c.url)}" placeholder="https://your-server.example/mcp"></label><label class="field">Authentication<select name="authType" id="mcpAuth"><option value="none">No authentication</option><option value="bearer">Bearer token</option><option value="header">Custom header</option></select></label><details open><summary>Local credential</summary><p>Saved only on this computer. Never included in exports or timeline logs. Changing the endpoint needs a new credential.</p><label class="field">Header name (custom header only)<input name="headerName" value="${esc(c.headerName || "X-API-Key")}"></label><label class="field">Credential<input type="password" autocomplete="off" name="credential" placeholder="${c.hasCredential ? "Saved · leave blank to keep for this endpoint" : "Enter locally"}"></label></details><button class="primary">Save connection</button></form>`,
  );
  $("#mcpAuth").value = c.authType;
  $("#mcpForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      state = await api("mcp/save", Object.fromEntries(new FormData(e.target)));
      $("#dialog").close();
      render();
      toast("Saved. Discover tools, then choose agent permissions.");
    } catch (e) {
      toast(e.message);
    }
  };
}
function resources() {
  const k = { Tools: "tools", Skills: "skills", "MCP Connections": "mcp" }[
    page
  ];
  $("#main").innerHTML =
    `<h1>${page}</h1><p class="subtitle">Small building blocks for your agents.</p>${k === "skills" ? '<button id="importSkill">Import a skill</button><p class="muted">Only plain instructions are imported. No scripts or plugins.</p>' : ""}${k === "mcp" ? '<button class="primary" id="addMcp">+ Add HTTP connection</button><p class="muted">Connect → Discover tools → Choose permissions in Agents. New tools always start off.</p>' : ""}<div class="panel"><b>Tools run only when assigned and requested.</b><p>Assign or remove each item in Agents → Edit. MCP permissions are selected one tool at a time.</p></div><div class="list">${state.catalog[k].map((x) => `<section class="panel"><h2>${esc(x.name)}</h2><p>${esc(x.description || (x.id === "documents" ? "Built-in teaching documents. No private files are read." : x.url))}</p>${x.transport ? `<span class="badge">${esc(x.status)}</span><p class="muted">${esc(x.authType)} authentication · ${x.hasCredential ? "credential saved" : "no credential saved"}</p>` : ""}${x.tools ? x.tools.map((t) => `<p>□ ${esc(t.name)} <small>(${esc(t.id)})</small></p>`).join("") : ""}${x.requires?.length ? "<small>Tool dependencies require your explicit choice.</small>" : ""}<div class="toolbar"><button data-assign>Choose agents</button>${k === "mcp" ? `<button data-discover="${esc(x.id)}">${x.id === "documents" ? "Check connection" : "Discover tools"}</button>${x.id !== "documents" ? `<button data-mcp-edit="${esc(x.id)}">Edit</button><button class="danger" data-mcp-remove="${esc(x.id)}">Remove</button>` : ""}` : ""}</div></section>`).join("")}</div>`;
  if ($("#importSkill")) $("#importSkill").onclick = importSkill;
  if ($("#addMcp")) $("#addMcp").onclick = () => mcpEditor();
  document.querySelectorAll("[data-assign]").forEach(
    (b) =>
      (b.onclick = () => {
        page = "Agents";
        render();
      }),
  );
  document
    .querySelectorAll("[data-mcp-edit]")
    .forEach((b) => (b.onclick = () => mcpEditor(b.dataset.mcpEdit)));
  document.querySelectorAll("[data-mcp-remove]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          state = await api("mcp/remove", { id: b.dataset.mcpRemove });
          render();
          toast("Connection removed. Its tool permissions were removed too.");
        } catch (e) {
          toast(e.message);
        }
      }),
  );
  document.querySelectorAll("[data-discover]").forEach(
    (b) =>
      (b.onclick = async () => {
        b.disabled = true;
        try {
          if (b.dataset.discover === "documents") {
            const r = await api("mcp/check", {});
            toast("MCP connected · " + r.tools.map((t) => t.name).join(", "));
          } else {
            state = await api("mcp/discover", { id: b.dataset.discover });
            render();
            toast("Discovery complete. Choose each tool permission in Agents.");
          }
        } catch (e) {
          toast(e.message);
        } finally {
          b.disabled = false;
        }
      }),
  );
}
function compare() {
  if (state.runs.length < 2)
    return modal(
      "<h2>Compare runs</h2><p>Make two runs first. Try one agent, then a team with the same goal.</p>",
    );
  modal(
    `<h2>Compare runs</h2><p>Choose two saved samples. More steps means more handoffs, not a promise of a better answer.</p><div class="compare">${[0, 1].map((_, i) => `<div><select id="compare${i}">${state.runs.map((r, j) => `<option value="${j}" ${j === state.runs.length - 2 + i ? "selected" : ""}>${j + 1}. ${esc(r.mode)} · ${esc(r.goal.slice(0, 35))}</option>`).join("")}</select><div id="result${i}"></div></div>`).join("")}</div>`,
  );
  const update = () =>
    [0, 1].forEach((i) => {
      const r = state.runs[$("#compare" + i).value];
      $("#result" + i).innerHTML =
        `<h3>${esc(r.team)}</h3><p>${r.steps.length} agent(s) · ${esc(r.provider)} provider</p><p>${r.provider === "demo" ? "Sample run · no real tokens" : "Provider tokens: " + usageLabel(r)}</p><p>${esc(r.steps.at(-1)?.output)}</p>`;
    });
  [0, 1].forEach((i) => ($("#compare" + i).onchange = update));
  update();
}
async function connection() {
  try {
    const [c, status] = await Promise.all([
      api("settings"),
      api("connection/status"),
    ]);
    connectionState = status;
    modal(
      `<h2>Connect your account</h2><p>Real AI is the main workspace. Your account must pass a backend access check before a real run can start.</p><button class="primary" id="oauth">Continue with ChatGPT</button> <button id="logout">Sign out locally</button><p>${esc(status.chatgpt.message)}</p><p><small>If OpenAI shows a browser check or HTTP 403, complete sign-in in your regular browser. No connection is assumed until the callback and provider check succeed.</small></p><div id="signInLink"></div><details><summary>Alternative: your API connection</summary><p>Choose this alternative deliberately. Credentials are shared only as a connection; each agent selects its own model in Profile. Use a provider with streaming Responses support.</p><form id="settings"><label class="field">API base URL<input type="url" name="base_url" value="${esc(c.base_url)}"></label><label class="field">API key<input type="password" autocomplete="off" name="api_key" placeholder="${c.has_key ? "Saved · leave blank to keep" : "Enter locally, never in chat"}"></label><button class="primary">Save and check API connection</button></form><p>${esc(status.api.message)}</p></details><button id="recheck">Check connection again</button><p class="muted">Models are selected in Agents → Profile. Closing this pop-up keeps real execution unavailable until a connection is verified. Educational samples are optional and must be chosen explicitly.</p>`,
    );
    $("#oauth").onclick = async () => {
      try {
        const result = await api("oauth/start", {});
        $("#signInLink").innerHTML =
          `<p><a class="signin-link" href="${esc(result.url)}" target="_blank" rel="noreferrer">Open the official sign-in page →</a></p><p>Keep AgentSim running. Complete the browser sign-in, then return and check the connection.</p>`;
        window.open(result.url, "_blank", "noopener");
      } catch (e) {
        toast(e.message);
      }
    };
    $("#logout").onclick = async () => {
      await api("oauth/logout", {});
      await refreshConnection();
      connection();
    };
    $("#settings").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api("settings", {
          ...Object.fromEntries(new FormData(e.target)),
          provider: "api",
        });
        await refreshConnection();
        if (connectionState.api.valid) {
          $("#dialog").close();
          render();
          toast(
            "API connection verified. Choose each agent’s model in Profile.",
          );
        } else {
          toast(connectionState.api.message);
          connection();
        }
      } catch (e) {
        toast(e.message);
      }
    };
    $("#recheck").onclick = async () => {
      await refreshConnection();
      if (connectionState.ready) {
        $("#dialog").close();
        render();
        toast("Connection verified. Choose the model for each agent.");
      } else connection();
    };
  } catch (e) {
    toast(e.message);
  }
}
async function refreshConnection() {
  connectionState = await api("connection/status");
  $("#connection").textContent = connectionState.ready
    ? "◉ Account access verified"
    : "○ Connection required";
  $(".tag").textContent =
    executionMode === "demo" ? "Educational samples" : "Real AI workspace";
  return connectionState;
}
async function realRun(body) {
  busy = true;
  run = null;
  home();
  try {
    const job = await api("real-run", body);
    const team = state.teams.find((t) => t.id === body.team);
    const agents = (
      body.mode === "one" ? team.agents.slice(0, 1) : team.agents
    ).map((id) => state.agents.find((a) => a.id === id));
    const managerId = body.mode === "one" ? null : team.manager;
    const result = await new Promise((resolve, reject) => {
      const stream = new EventSource("/api/jobs/" + job.id + "/events");
      stream.onmessage = (event) => {
        const snapshot = JSON.parse(event.data);
        const completed = snapshot.events.filter(
          (e) => e.type === "step_completed",
        );
        run = {
          goal: body.goal,
          provider: "real",
          managerId,
          orchestration: managerId ? "managed" : "sequential",
          roster: agents.map((a) => ({
            agentId: a.id,
            agent: a.name,
            avatar: a.avatar,
          })),
          steps: completed.map((e) => e.data.result),
          events: snapshot.events,
          completed: snapshot.status === "completed",
        };
        step = completed.length;
        if (page === "Watch & run") home();
        if (snapshot.status === "completed") {
          stream.close();
          resolve(snapshot);
        } else if (snapshot.status === "failed") {
          stream.close();
          reject(Error(snapshot.error));
        }
      };
      stream.onerror = () => {
        stream.close();
        reject(
          Error(
            "The live event connection was lost. Check the saved run status; no sample result was substituted.",
          ),
        );
      };
    });
    run = result.run;
    state = await api("state");
    step = run.steps.length;
    selected = run.steps.length - 1;
    toast("Real run complete. Outputs and provider usage are saved.");
  } catch (e) {
    if (run) {
      run.failed = true;
      run.error = e.message;
    }
    toast(e.message);
  } finally {
    (busy = false),
      (activeTeamId = ""),
      (selectedAgentId = null),
      (goalDraft = "Explain how a team can plan a picnic.");
    if (page === "Home") dashboard();
    else if (page === "Watch & run") home();
  }
}
$("#connect").onclick = connection;
$("#connection").onclick = connection;
$("#help").onclick = () =>
  modal(
    "<h2>A team of small jobs</h2><p>Goal: plan a picnic. The Researcher finds things to bring. The Writer makes a short plan. The Reviewer checks whether the plan is easy to follow.</p><p>A tool helps do one task. A skill gives instructions. An MCP connection can offer several tools. You choose each permission.</p><p>Tokens are small pieces of text. Demo counts are sample numbers. Real AI counts come only from your provider.</p>",
  );
api("state")
  .then(async (s) => {
    state = s;
    render();
    await refreshConnection();
    if (!connectionState.ready) await connection();
  })
  .catch((e) => {
    $("#main").textContent =
      "Could not load AgentSim. Start the Python server and refresh.";
  });
