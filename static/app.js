let state,
  page = "Home",
  run = null,
  mode = "team",
  connectionState = { ready: false },
  busy = false,
  activeTeamId = "",
  architectureTeamId = "",
  selectedAgentId = null,
  activeAgentId = "",
  activeConversation = null,
  conversationList = [],
  messageDraft = "",
  streamJobId = null;
const expandedExecutionDetails = new Set();
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
  if (!r.ok) {
    const error = Error(v.error);
    error.executionId = v.id;
    throw error;
  }
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
  const icons = ["⌂", "▷", "♙", "♟", "⚒", "ϟ", "♧", "◇", "◷"];
  $("#nav").innerHTML = [
    "Home",
    "Watch & run",
    "Agents",
    "Teams",
    "Tools",
    "Skills",
    "MCP Connections",
    "Architecture",
    "Execution history",
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
  $("#main").classList.toggle("chat-page", page === "Watch & run");
  nav();
  if (page === "Home") dashboard();
  else if (page === "Watch & run") home();
  else if (page === "Agents" || page === "Teams") catalog();
  else if (page === "Architecture") architecture();
  else if (page === "Execution history")
    executionHistory().catch((e) => toast(e.message));
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
function dashboardArt(name) {
  if (name === "Watch & run")
    return '<span class="dashboard-art dashboard-art-watch" aria-hidden="true"><span class="robot"></span><span class="dashboard-play">▶</span></span>';
  const image = {
    Agents: "agents",
    Teams: "teams",
    Tools: "tools",
    Skills: "skills",
    "MCP Connections": "mcp",
  }[name];
  return `<span class="dashboard-art" aria-hidden="true"><img src="/card-${image}.png" alt="" width="1536" height="1024"></span>`;
}
function dashboard() {
  const exampleCount = state.agents.filter((a) => a.example).length;
  const cards = [
    ["Agents", "Give each agent one clear job.", state.agents.length],
    ["Teams", "Choose which agents work together.", state.teams.length],
    ["Tools", "Small actions an agent may use.", state.catalog.tools.length],
    [
      "Skills",
      "Instructions that help an agent do its job.",
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
    `<h1>Your AI workshop</h1><p class="subtitle">Build a team. Give it a goal. Learn one step at a time.</p><section class="panel"><h2>Start here</h2><p>${state.agents.length ? `You have ${state.agents.length} saved agents. ${exampleCount} ${exampleCount === 1 ? "is an example configuration" : "are example configurations"}. A saved agent is a setup, not proof that AI has run.` : "This workspace is empty. Start with your own agent, or load a small example team."}</p><div class="toolbar"><button class="primary" id="ownSetup">${state.agents.length ? "Open my agents" : "Start empty · create my first agent"}</button><button id="examples">${exampleCount ? "View example agents" : "Load example team"}</button><button id="goWatch">Watch & run →</button></div><small>Saved on this computer in a persistent SQLite database (agentsim.db). Account credentials stay in protected local files and are never part of setup exports.</small></section><div class="list dashboard-cards">${cards.map(([name, description, count]) => `<button class="panel dashboard-card" data-open="${name}">${dashboardArt(name)}<span class="dashboard-count">${esc(count)}</span><h2>${name}</h2><p>${description}</p><span>Open →</span></button>`).join("")}</div><section class="panel" style="margin-top:20px"><h2>Your next steps</h2><p>1. Create an agent or load examples. 2. Choose its job and permissions. 3. Choose a team or agent in Watch & run and start a conversation.</p><button id="dashboardConnect">Connection setup</button></section>`;
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
  $("#goWatch").onclick = () => {
    page = "Watch & run";
    render();
  };
  $("#dashboardConnect").onclick = connection;
}
function usageLabel(r, until = Infinity) {
  if (!r) return "Not reported";
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
function chatTarget() {
  return mode === "one"
    ? state.agents.find((a) => a.id === activeAgentId)
    : state.teams.find((t) => t.id === activeTeamId);
}
function conversationTurns() {
  return (activeConversation?.messages || []).filter((m) => m.role === "user");
}
function resetConversation() {
  activeConversation = null;
  run = null;
  selectedAgentId = null;
  messageDraft = "";
  localStorage.removeItem("agentsim-conversation");
  realWatch();
}
function realWatch() {
  const target = chatTarget();
  const options = mode === "one" ? state.agents : state.teams;
  const targetId = mode === "one" ? activeAgentId : activeTeamId;
  $("#main").classList.add("chat-page");
  $("#main").innerHTML =
    `<h1>Watch & run</h1><p class="subtitle">Chat with your team or agent. Follow each execution on the right.</p>
    <section class="panel chat-setup"><div class="target-mode" role="group" aria-label="Who to call"><button id="teamMode" aria-pressed="${mode === "team"}" class="${mode === "team" ? "primary" : ""}" ${busy ? "disabled" : ""}>Team</button><button id="one" aria-pressed="${mode === "one"}" class="${mode === "one" ? "primary" : ""}" ${busy ? "disabled" : ""}>One agent</button></div>
    <label class="target-label">${mode === "one" ? "Agent" : "Team"}<select id="executionTarget" aria-label="${mode === "one" ? "Agent to call" : "Team to call"}" ${busy ? "disabled" : ""}><option value="">Choose ${mode === "one" ? "an agent" : "a team"}</option>${options.map((t) => `<option value="${esc(t.id)}" ${t.id === targetId ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></label>
    <button id="openChat" ${busy || !target ? "disabled" : ""}>${activeConversation ? "New chat" : "Open chat"}</button>
    ${mode === "team" && target && !target.manager ? '<button id="configureTeam">Choose manager</button>' : ""}
    ${conversationList.length ? `<label class="saved-chat-label">Saved chats<select id="savedChat" aria-label="Saved chats" ${busy ? "disabled" : ""}><option value="">Open a conversation</option>${conversationList.map((c) => `<option value="${esc(c.id)}" ${c.id === activeConversation?.id ? "selected" : ""}>${esc(c.name)} · ${esc(new Date(c.updatedAt * 1000).toLocaleString())}</option>`).join("")}</select></label>` : ""}</section>
    <div class="chat-workspace"><section class="panel user-chat" aria-label="Conversation"><div class="section-heading"><div><h2>${esc(activeConversation?.name || target?.name || "Your conversation")}</h2><small>${activeConversation ? "Messages are saved. Follow-up messages retain conversation context." : "Choose Team or One agent, select a name and open the chat."}</small></div></div>
    <div id="chatMessages" class="chat-messages" role="log" aria-label="Chat messages" aria-live="polite"></div>
    <form id="chatForm" class="chat-composer"><label for="chatMessage">Message</label><textarea id="chatMessage" placeholder="What would you like to do?" maxlength="8000" rows="3" ${!activeConversation || busy ? "disabled" : ""}>${esc(messageDraft)}</textarea><div><small>Enter to send · Shift+Enter for a new line</small><button class="orange" id="sendMessage" ${!activeConversation || busy ? "disabled" : ""}>${busy ? "Working…" : "Send"}</button></div></form></section>
    <section class="panel execution-column" aria-label="Execution details"><div class="section-heading"><h2>Execution</h2><span class="badge ${busy ? "working" : ""}" id="executionStatus">${busy ? "● Live" : run?.failed ? "Failed" : run?.completed ? "Complete" : "Ready"}</span></div><div id="turnPicker"></div><div id="liveAgents" class="chat-agent-strip"></div><div id="executionScroll" class="execution-scroll" tabindex="0" aria-label="Scrollable execution steps"><div id="executionSteps"></div><div id="executionArtifacts"></div></div><small id="executionUsage"></small></section></div>`;
  $("#teamMode").onclick = () => {
    if (mode !== "team") {
      mode = "team";
      resetConversation();
    }
  };
  $("#one").onclick = () => {
    if (mode !== "one") {
      mode = "one";
      resetConversation();
    }
  };
  $("#executionTarget").onchange = (e) => {
    if (mode === "one") activeAgentId = e.target.value;
    else activeTeamId = e.target.value;
    resetConversation();
  };
  if ($("#configureTeam"))
    $("#configureTeam").onclick = () => editor("teams", target.id);
  $("#openChat").onclick = async () => {
    try {
      activeConversation = await api("conversations", {
        mode,
        team: activeTeamId,
        agent: activeAgentId,
      });
      localStorage.setItem("agentsim-conversation", activeConversation.id);
      conversationList = await api("conversations");
      run = null;
      messageDraft = "";
      realWatch();
      $("#chatMessage").focus();
    } catch (e) {
      toast(e.message);
    }
  };
  if ($("#savedChat"))
    $("#savedChat").onchange = (e) => {
      if (e.target.value)
        loadConversation(e.target.value).catch((err) => toast(err.message));
    };
  $("#chatMessage").oninput = (e) => {
    messageDraft = e.target.value;
  };
  $("#chatMessage").onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("#chatForm").requestSubmit();
    }
  };
  $("#chatForm").onsubmit = async (e) => {
    e.preventDefault();
    if (busy || !activeConversation || !messageDraft.trim()) return;
    await realRun({
      conversationId: activeConversation.id,
      goal: messageDraft.trim(),
    });
  };
  renderChatMessages();
  renderTurnPicker();
  updateExecution();
}
function renderChatMessages() {
  const el = $("#chatMessages");
  if (!el) return;
  const old = el.scrollTop,
    follow = el.scrollHeight - old - el.clientHeight < 90;
  el.innerHTML =
    (activeConversation?.messages || [])
      .map(
        (m) =>
          `<article class="chat-bubble ${m.role === "user" ? "from-user" : "from-agent"} ${["failed", "interrupted", "rejected"].includes(m.status) ? "chat-error" : ""}"><b>${esc(m.role === "user" ? "You" : m.name || activeConversation.name)}</b><p>${esc(m.content)}</p>${m.role === "assistant" ? `${artifactCards({ artifacts: m.artifacts || [] })}<button class="message-evidence" data-turn="${esc(m.runId)}">Inspect this execution →</button>` : ""}</article>`,
      )
      .join("") ||
    '<div class="chat-empty"><h3>Start a conversation</h3><p>Send a message. The selected agent or team will reply here, while actions and results appear alongside.</p></div>';
  if (busy)
    el.innerHTML += `<div class="chat-bubble from-agent" role="status">Working on your message… Follow the execution on the right.${run?.conversationId === activeConversation?.id && run?.id === activeConversation?.activeRunId ? artifactCards(run) : ""}</div>`;
  el.scrollTop = follow ? el.scrollHeight : old;
  el.querySelectorAll("[data-turn]").forEach(
    (b) => (b.onclick = () => selectExecution(b.dataset.turn)),
  );
}
function renderTurnPicker() {
  const turns = conversationTurns();
  if (!$("#turnPicker")) return;
  $("#turnPicker").innerHTML = turns.length
    ? `<label class="turn-label">Message execution<select id="executionTurn" aria-label="Message execution">${turns.map((m, i) => `<option value="${esc(m.runId)}" ${m.runId === run?.id ? "selected" : ""}>${i + 1}. ${esc(m.content.slice(0, 65))}</option>`).join("")}</select></label>`
    : "";
  if ($("#executionTurn"))
    $("#executionTurn").onchange = (e) => selectExecution(e.target.value);
}
async function selectExecution(id) {
  try {
    const job = await api("jobs/" + id);
    run = {
      ...job.run,
      failed: ["failed", "interrupted", "rejected"].includes(job.status),
      error: job.error,
    };
    renderTurnPicker();
    updateExecution(true);
  } catch (e) {
    toast(e.message);
  }
}
function updateExecution(resetScroll = false) {
  if (!$("#executionSteps")) return;
  const box = $("#executionScroll"),
    old = box.scrollTop;
  const follow = resetScroll || box.scrollHeight - old - box.clientHeight < 90;
  const contentKey = `${run?.id}:${run?.events?.length || 0}`;
  $("#executionStatus").textContent = run?.failed
    ? "Failed"
    : run?.completed
      ? "Complete"
      : busy
        ? "● Live"
        : "Ready";
  const roster = run?.roster || [];
  $("#liveAgents").innerHTML = roster
    .map((a) => liveAgentCard(a, run?.managerId))
    .join("");
  if ($("#executionSteps").dataset.contentKey !== contentKey) {
    $("#executionSteps").innerHTML = interactionTimeline(run);
    $("#executionSteps").dataset.contentKey = contentKey;
    $("#executionSteps")
      .querySelectorAll("details")
      .forEach((d, i) => {
        const key = `${run?.id}:${i}`;
        d.open = expandedExecutionDetails.has(key);
        d.ontoggle = () => {
          if (d.open) expandedExecutionDetails.add(key);
          else expandedExecutionDetails.delete(key);
        };
      });
  }
  const artifactsKey = (run?.events || [])
    .filter((e) => e.type === "artifact_created")
    .map((e) => e.data.id)
    .join();
  if ($("#executionArtifacts").dataset.contentKey !== artifactsKey) {
    $("#executionArtifacts").innerHTML = artifactCards(run);
    $("#executionArtifacts").dataset.contentKey = artifactsKey;
    if (busy) renderChatMessages();
  }
  $("#executionUsage").textContent =
    `Provider usage: ${usageLabel(run)} · ${(run?.events || []).filter((e) => e.type === "tool_completed").length} completed tool calls`;
  box.scrollTop = follow ? box.scrollHeight : old;
  document.querySelectorAll("[data-agent]").forEach(
    (b) =>
      (b.onclick = () => {
        const events = [
          ...$("#executionSteps").querySelectorAll(".trace-event"),
        ];
        const index = (run?.events || []).findLastIndex(
          (e) => e.data.agentId === b.dataset.agent,
        );
        if (index >= 0)
          events[index]?.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
          });
      }),
  );
}
async function loadConversation(id) {
  activeConversation = await api("conversations/" + id);
  mode = activeConversation.mode;
  if (mode === "one") activeAgentId = activeConversation.targetId;
  else activeTeamId = activeConversation.targetId;
  localStorage.setItem("agentsim-conversation", id);
  const latest =
    activeConversation.activeRunId || conversationTurns().at(-1)?.runId;
  run = latest ? (await api("jobs/" + latest)).run : null;
  messageDraft = "";
  if (page === "Watch & run") realWatch();
  if (activeConversation.activeRunId && streamJobId !== latest) {
    busy = true;
    if (page === "Watch & run") realWatch();
    followExecution(latest).catch((e) => toast(e.message));
  }
}
function architecture() {
  const team =
    state.teams.find((t) => t.id === (architectureTeamId || activeTeamId)) ||
    state.teams[0];
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
    architectureTeamId = e.target.value;
    architecture();
  };
  $("#architectureWatch").onclick = () => {
    page = "Watch & run";
    render();
  };
}

function home() {
  realWatch();
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
    `<h1>${page}</h1><p class="subtitle">Small building blocks for your agents.</p>${k === "skills" ? '<button id="importSkill">Import a skill</button><p class="muted">Codex SKILL.md format. The manager can choose skills when needed; every choice appears in the execution history.</p>' : ""}${k === "mcp" ? '<button class="primary" id="addMcp">+ Add HTTP connection</button> <button id="importPlugin">Import plugin ZIP</button><p class="muted">Connect → Discover tools → Choose permissions in Agents. New tools always start off.</p>' : ""}<div class="panel"><b>Tools run only when assigned and requested.</b><p>Assign or remove each item in Agents → Edit. MCP permissions are selected one tool at a time.</p></div><div class="list">${state.catalog[k].map((x) => `<section class="panel"><h2>${esc(x.name)}</h2><p>${esc(x.description || (x.id === "documents" ? "Built-in teaching documents. No private files are read." : x.url))}</p>${x.transport ? `<span class="badge">${esc(x.status)}</span><p class="muted">${esc(x.authType)} authentication · ${x.hasCredential ? "credential saved" : "no credential saved"}</p>` : ""}${x.tools ? x.tools.map((t) => `<p>□ ${esc(t.name)} <small>(${esc(t.id)})</small></p>`).join("") : ""}${x.requires?.length ? "<small>Tool dependencies require your explicit choice.</small>" : ""}${k === "tools" && x.id === "image-generator" ? `<button id="configureImages">ChatGPT image connection</button><p class="muted">Generates images through the native ChatGPT runtime using your plan. No API key required.</p>` : ""}${k === "skills" ? `<button data-skill-view="${esc(x.id)}">View SKILL.md</button> <button class="danger" data-skill-remove="${esc(x.id)}">Remove skill</button>` : ""}<div class="toolbar"><button data-assign>Choose agents</button>${k === "mcp" ? `<button data-discover="${esc(x.id)}">${x.id === "documents" ? "Check connection" : "Discover tools"}</button>${x.id !== "documents" ? `${x.transport !== "stdio" ? `<button data-mcp-edit="${esc(x.id)}">Edit</button>` : ""}<button class="danger" data-mcp-remove="${esc(x.id)}">Remove</button>` : ""}` : ""}</div></section>`).join("")}</div>`;
  if ($("#importSkill")) $("#importSkill").onclick = importSkill;
  if ($("#configureImages"))
    $("#configureImages").onclick = configureImageProvider;
  if ($("#importPlugin")) $("#importPlugin").onclick = pluginImport;
  document.querySelectorAll("[data-skill-view]").forEach(
    (b) =>
      (b.onclick = () => {
        const skill = state.catalog.skills.find(
          (s) => s.id === b.dataset.skillView,
        );
        modal(
          `<h2>${esc(skill.name)}</h2><pre class="skill-source">${esc(skill.markdown || `---\nname: ${skill.id}\ndescription: ${skill.description}\n---\n${skill.instructions}`)}</pre>`,
        );
      }),
  );
  document.querySelectorAll("[data-skill-remove]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          state = await api("skills/remove", { id: b.dataset.skillRemove });
          render();
          toast("Skill removed from the registry and agent assignments.");
        } catch (e) {
          toast(e.message);
        }
      }),
  );
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
      `<h2>Connect your account</h2><p>Real AI is the main workspace. Your account must pass a backend access check before a real run can start.</p><button class="primary" id="oauth">Continue with ChatGPT</button> <button id="logout">Sign out locally</button><p>${esc(status.chatgpt.message)}</p><p><small>If OpenAI shows a browser check or HTTP 403, complete sign-in in your regular browser. No connection is assumed until the callback and provider check succeed.</small></p><div id="signInLink"></div><details><summary>Alternative: your API connection</summary><p>Choose this alternative deliberately. Credentials are shared only as a connection; each agent selects its own model in Profile. Use a provider with streaming Responses support.</p><form id="settings"><label class="field">API base URL<input type="url" name="base_url" value="${esc(c.base_url)}"></label><label class="field">API key<input type="password" autocomplete="off" name="api_key" placeholder="${c.has_key ? "Saved · leave blank to keep" : "Enter locally, never in chat"}"></label><button class="primary">Save and check API connection</button></form><p>${esc(status.api.message)}</p></details><button id="recheck">Check connection again</button><p class="muted">Models are selected in Agents → Profile. Closing this pop-up keeps real execution unavailable until a connection is verified. Execution always uses the connected models.</p>`,
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
  $(".tag").textContent = "Real AI workspace";
  return connectionState;
}
async function realRun(body) {
  busy = true;
  if (page === "Watch & run") realWatch();
  try {
    const job = await api("real-run", body);
    messageDraft = "";
    activeConversation = await api("conversations/" + body.conversationId);
    run = (await api("jobs/" + job.id)).run;
    if (page === "Watch & run") realWatch();
    await followExecution(job.id);
  } catch (e) {
    busy = false;
    if (e.executionId) {
      run = (await api("jobs/" + e.executionId)).run;
      run.failed = true;
      run.error = e.message;
      activeConversation = await api("conversations/" + activeConversation.id);
      if (activeConversation.messages.some((m) => m.runId === e.executionId))
        messageDraft = "";
    }
    toast(e.message);
    if (page === "Watch & run") realWatch();
  }
}
async function followExecution(id) {
  streamJobId = id;
  try {
    await new Promise((resolve, reject) => {
      const stream = new EventSource("/api/jobs/" + id + "/events");
      stream.onmessage = (event) => {
        const snapshot = JSON.parse(event.data);
        if (!run || run.id === id || !busy) {
          run = {
            ...snapshot.run,
            failed: ["failed", "interrupted", "rejected"].includes(
              snapshot.status,
            ),
            error: snapshot.error,
          };
          if (page === "Watch & run") updateExecution();
        }
        if (snapshot.status !== "running") {
          stream.close();
          resolve(snapshot);
        }
      };
      stream.onerror = () => {
        stream.close();
        reject(
          Error(
            "Live connection lost. Reopen this saved chat to reconnect; its execution continues on the server.",
          ),
        );
      };
    });
  } catch (e) {
    toast(e.message);
  } finally {
    busy = false;
    streamJobId = null;
    activeConversation = await api("conversations/" + activeConversation.id);
    conversationList = await api("conversations");
    state = await api("state");
    if (page === "Watch & run") {
      realWatch();
      $("#chatMessage")?.focus();
    }
  }
}
$("#connection").onclick = connection;
$("#help").onclick = () =>
  modal(
    "<h2>A team of small jobs</h2><p>Goal: plan a picnic. The Researcher finds things to bring. The Writer makes a short plan. The Reviewer checks whether the plan is easy to follow.</p><p>A tool helps do one task. A skill gives instructions. An MCP connection can offer several tools. You choose each permission.</p><p>Choose Team or One agent, select a name and open the chat. Each message triggers an automatic execution. Inspect the steps on the right. Token counts come from your provider.</p>",
  );
api("state")
  .then(async (s) => {
    state = s;
    conversationList = await api("conversations");
    const savedConversation = localStorage.getItem("agentsim-conversation");
    if (savedConversation) {
      try {
        await loadConversation(savedConversation);
      } catch {
        localStorage.removeItem("agentsim-conversation");
      }
    }
    render();
    await refreshConnection();
    if (!connectionState.ready) await connection();
  })
  .catch((e) => {
    $("#main").textContent =
      "Could not load AgentSim. Start the Python server and refresh.";
  });

function artifactCards(record = run) {
  const items =
    record?.artifacts ||
    (record?.events || [])
      .filter((e) => e.type === "artifact_created")
      .map((e) => e.data);
  if (!items.length) return "";
  return `<section class="panel"><h2>Generated results</h2><div class="artifact-grid">${items.map((a) => `<article class="artifact-card"><h3>${esc(a.title)}</h3><small>${esc(a.agent)} · ${esc(a.extension.toUpperCase())} · ${esc(a.bytes)} bytes</small>${a.extension === "png" ? `<img src="${esc(a.url)}" alt="${esc(a.title)}" loading="lazy">` : a.extension === "html" ? `<iframe src="${esc(a.url)}" sandbox="allow-scripts" title="${esc(a.title)}" loading="lazy"></iframe>` : a.extension === "pdf" ? `<div class="pdf-attachment"><span aria-hidden="true">▤</span><b>PDF document</b><p>Open the report to view its pages.</p></div>` : ""}<a href="${esc(a.url)}" target="_blank" rel="noopener">Open ${esc(a.extension.toUpperCase())}</a> · <a href="${esc(a.url)}" download>Download</a></article>`).join("")}</div></section>`;
}
function interactionTimeline(record = run) {
  const events = record?.events || [];
  if (!events.length) {
    if (record?.steps?.length)
      return (
        '<p class="muted">Legacy saved run: per-event class/location metadata was not recorded.</p>' +
        record.steps
          .map(
            (s, i) =>
              `<article class="dialogue-message"><small>Saved step ${i + 1} · ${esc(record.provider === "demo" ? "Educational sample" : "Legacy result")}</small><h3>${esc(s.agent)}</h3><p>${esc(s.output)}</p></article>`,
          )
          .join("")
      );
    return '<p class="muted">Start a run to follow its actual steps, decisions, skills, tools and outputs.</p>';
  }
  return events
    .map((e, i) => {
      const d = e.data,
        time = new Date(e.time * 1000).toLocaleTimeString();
      const label = e.type.replaceAll("_", " ");
      let body = "";
      if (["delegation", "reply"].includes(e.type))
        body = `<h3>${esc(d.from)} → ${esc(d.to)}</h3><p>${esc(d.message)}</p>${d.context ? `<details><summary>Shared context</summary><p>${esc(d.context)}</p></details>` : ""}`;
      else if (e.type === "skill_selected")
        body = `<h3>Skill chosen: ${esc(d.skill)}</h3><p>${esc(d.selectedBy)} selected this skill for ${esc(d.agent)}.</p><p><b>Why:</b> ${esc(d.reason)}</p>`;
      else if (e.type === "skill_applied")
        body = `<h3>${esc(d.agent)} · ${esc(d.skill)}</h3><p>${esc(d.explanation)}</p>`;
      else if (e.type === "agent_started")
        body = `<h3>${esc(d.agent)} started</h3><details><summary>Task received</summary><p>${esc(d.task)}</p></details>`;
      else if (e.type === "agent_completed")
        body = `<h3>${esc(d.agent)} · ${d.manager ? "Final answer" : "Result"}</h3><p>${esc(d.output)}</p>`;
      else if (e.type === "artifact_created")
        body = `<h3>${esc(d.title)}</h3><a href="${esc(d.url)}" target="_blank" rel="noopener">View generated ${esc(d.extension.toUpperCase())}</a>`;
      else if (e.type === "tool_completed") {
        const out = d.output;
        body = `<h3>${esc(d.name)} completed</h3><p>${esc(typeof out === "string" ? out : out?.text || "Results returned to the agent.")}</p>${
          out?.sources?.length
            ? `<ul>${out.sources
                .filter((s) => /^https?:\/\//.test(s.url))
                .map(
                  (s) =>
                    `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`,
                )
                .join("")}</ul>`
            : ""
        }`;
      } else if (e.type === "usage")
        body = `<h3>Provider usage</h3><p>Input: ${esc(d.input ?? "unavailable")} · Output: ${esc(d.output ?? "unavailable")} tokens</p>`;
      else if (e.type === "model_started")
        body = `<h3>${esc(d.agent)} · ${esc(d.model)}</h3><p>${esc(d.explanation)}</p>`;
      else
        body = `<h3>${esc(d.name || d.agent || record?.roster?.find((a) => a.agentId === d.agentId)?.agent || label)}</h3><p>${esc(d.explanation || d.error || label)}</p>`;
      const detail = JSON.stringify(d, null, 2);
      return `<article class="dialogue-message trace-event event-${e.type}"><small>Step ${e.sequence || i + 1} · ${esc(time)} · ${esc(label)}</small>${body}<details class="provenance"><summary>Where it ran · implementation · evidence</summary><p><b>Where:</b> ${esc(d.where || "Local harness")}<br><b>Class / function:</b> <code>${esc(d.implementation || "Legacy event")}</code></p><p>${esc(d.explanation || "Recorded execution event.")}</p><pre>${esc(detail)}</pre></details></article>`;
    })
    .join("");
}
let historySelectedId = null,
  historyTimer = null;
async function executionHistory() {
  clearTimeout(historyTimer);
  const items = await api("executions");
  if (page !== "Execution history") return;
  $("#main").innerHTML =
    `<h1>Execution history</h1><p class="subtitle">All recorded runs, including failures and interrupted work. Open a run to inspect every public step.</p><button id="refreshHistory">Refresh</button><div class="history-layout"><div class="list">${items.map((j) => `<button class="panel history-run" data-history="${esc(j.id)}"><span class="badge">${esc(j.status)}</span><h3>${esc(j.team)}</h3><p>${esc(j.goal)}</p><small>${j.eventCount} events${j.startedAt ? " · " + esc(new Date(j.startedAt * 1000).toLocaleString()) : ""}</small></button>`).join("") || "<p>No recorded runs yet.</p>"}</div><div id="historyDetail"></div></div>`;
  $("#refreshHistory").onclick = () => executionHistory();
  async function show(id) {
    historySelectedId = id;
    const job = await api("jobs/" + id);
    if (page !== "Execution history") return;
    const record = { ...job.run, events: job.events };
    $("#historyDetail").innerHTML =
      `<section class="panel"><h2>${esc(record.goal)}</h2><p>${esc(job.status)} · ${esc(record.team)}</p>${job.error ? `<p class="danger">${esc(job.error)}</p>` : ""}<p>Each step identifies what ran, where it ran and which class handled it. This is public execution evidence, not hidden model reasoning.</p><div class="conversation history-conversation">${interactionTimeline(record)}</div></section>${artifactCards(record)}`;
  }
  document
    .querySelectorAll("[data-history]")
    .forEach((b) => (b.onclick = () => show(b.dataset.history)));
  if (historySelectedId && items.some((j) => j.id === historySelectedId))
    await show(historySelectedId);
  if (items.some((j) => j.status === "running"))
    historyTimer = setTimeout(() => {
      if (page === "Execution history")
        executionHistory().catch((e) => toast(e.message));
    }, 1500);
}
function importSkill() {
  modal(
    `<h2>Import Codex SKILL.md</h2><p>Upload a Markdown file with YAML name and description, followed by the skill instructions. Instructions become available to the orchestrator; uploaded scripts are not executed as skills.</p><form id="skillForm"><label class="field">Markdown file<input type="file" id="skillFile" accept=".md,.markdown,text/markdown"></label><label class="field">SKILL.md<textarea id="skillMarkdown" rows="15">---\nname: clear-report\ndescription: Use when preparing a clear report with cited sources.\n---\n# Clear report\nExplain the result, cite sources and state limitations.</textarea></label><button class="primary">Import skill</button></form>`,
  );
  $("#skillFile").onchange = async (e) => {
    const file = e.target.files[0];
    if (file) $("#skillMarkdown").value = await file.text();
  };
  $("#skillForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      state = await api("skills/import", {
        markdown: $("#skillMarkdown").value,
      });
      $("#dialog").close();
      render();
      toast("Skill imported. The manager can select it when relevant.");
    } catch (e) {
      toast(e.message);
    }
  };
}
function pluginImport() {
  let encoded = "",
    preview = null;
  modal(
    `<h2>Import MCP plugin ZIP</h2><p>Choose a ZIP containing .mcp.json or mcp.json. <a href="/example-mcp-plugin.zip" download>Download the local MCP example</a>. The manifest is inspected before import. HTTP servers and packaged Python/Node stdio entry points are supported; dependency installers are not run.</p><form id="pluginForm"><label class="field">Plugin ZIP<input id="pluginZip" type="file" accept=".zip,application/zip" required></label><div id="pluginPreview"></div><label class="field">Access key<input id="pluginKey" type="password" autocomplete="off"><small>Stored in protected local credentials; never included in exports or execution logs.</small></label><label class="check" id="pluginTrustLabel" hidden><input type="checkbox" id="pluginTrust">I reviewed this package and trust its code to run with my local user permissions.</label><button class="primary" id="installPlugin" disabled>Import and discover tools</button></form>`,
  );
  $("#pluginZip").onchange = async (e) => {
    try {
      const file = e.target.files[0];
      if (!file) return;
      if (file.size > 10000000) throw Error("ZIP limit is 10 MB.");
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let i = 0; i < bytes.length; i += 32768)
        binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
      encoded = btoa(binary);
      preview = await api("plugins/inspect", { zip: encoded });
      $("#pluginPreview").innerHTML =
        `<h3>Plugin contents</h3>${preview.connections.map((c) => `<p><b>${esc(c.name)}</b> · ${esc(c.transport)}<br>${esc(c.url)}</p>${c.sourcePreview ? `<details><summary>Entry-point source (first 20 KB)</summary><pre>${esc(c.sourcePreview)}</pre></details>` : ""}`).join("")}<p>${preview.skills.length} skills · ${preview.files.length} packaged files</p><details><summary>Files</summary><pre>${esc(preview.files.join("\n"))}</pre></details>`;
      $("#pluginTrustLabel").hidden = !preview.runsLocalCode;
      $("#installPlugin").disabled = false;
    } catch (e) {
      $("#installPlugin").disabled = true;
      toast(e.message);
    }
  };
  $("#pluginForm").onsubmit = async (e) => {
    e.preventDefault();
    const button = $("#installPlugin");
    button.disabled = true;
    try {
      const result = await api("plugins/import", {
        zip: encoded,
        accessKey: $("#pluginKey").value,
        trustLocal: $("#pluginTrust").checked,
      });
      state = result.state;
      $("#dialog").close();
      render();
      toast(result.discovery.map((x) => x.id + ": " + x.status).join(" · "));
    } catch (e) {
      button.disabled = false;
      toast(e.message);
    }
  };
}

async function configureImageProvider() {
  try {
    const [settings, native] = await Promise.all([
      api("image-provider"),
      api("image-runtime"),
    ]);
    modal(
      `<h2>ChatGPT image generation</h2><section class="panel"><h3>Native ChatGPT runtime</h3><p>Your agent sends the image prompt to the native ChatGPT generator and brings the PNG back into this execution. Uses your ChatGPT plan; no API key is required.</p><p id="nativeImageStatus">${native.configured ? "Image session saved. Access is checked during generation." : native.available ? "Connect the image session once to start generating." : "Install the official Codex CLI to enable native images."}</p><button id="nativeImageLogin" ${native.available ? "" : "disabled"}>${native.configured ? "Reconnect ChatGPT images" : "Connect ChatGPT images"}</button> <button id="nativeImageRefresh">Check image session</button><div id="nativeImageLink"></div><small>This session is saved independently inside AgentSim. Other applications’ credentials are not copied.</small></section><details><summary>Optional API image provider</summary><form id="imageProviderForm"><label class="field">API base URL<input name="base_url" value="${esc(settings.base_url)}" required></label><label class="field">Image API key<input type="password" autocomplete="off" name="api_key" placeholder="${settings.configured ? "Saved · leave blank to keep" : "Enter locally"}"></label><button type="button" id="imageModels">Load available image models</button><label class="field">Image model<select name="model" id="imageProviderModel">${settings.model ? `<option value="${esc(settings.model)}">${esc(settings.model)}</option>` : '<option value="">Load models from your image account</option>'}</select></label><button class="primary">Save image provider</button>${settings.configured ? '<button type="button" id="clearImageProvider">Disconnect image model</button>' : ""}<p class="muted">The key is stored in protected local credentials and excluded from exports and execution logs.</p></form></details>`,
    );
    $("#nativeImageLogin").onclick = async () => {
      try {
        $("#nativeImageLogin").disabled = true;
        const login = await api("image-runtime/login", {});
        $("#nativeImageLink").innerHTML =
          `<p><a href="${esc(login.url)}" target="_blank" rel="noopener">Continue with ChatGPT →</a></p><p>After sign-in, click Check image session.</p>`;
      } catch (e) {
        toast(e.message);
      } finally {
        $("#nativeImageLogin").disabled = false;
      }
    };
    $("#nativeImageRefresh").onclick = async () => {
      try {
        const status = await api("image-runtime");
        $("#nativeImageStatus").textContent = status.configured
          ? "Image session saved. Ready to generate through ChatGPT."
          : "Image sign-in has not completed yet.";
      } catch (e) {
        toast(e.message);
      }
    };
    if ($("#clearImageProvider"))
      $("#clearImageProvider").onclick = async () => {
        try {
          await api("image-provider/clear", {});
          $("#dialog").close();
          toast("Image-provider credentials removed.");
        } catch (e) {
          toast(e.message);
        }
      };
    $("#imageModels").onclick = async () => {
      try {
        const response = await api(
          "image-provider/models",
          Object.fromEntries(new FormData($("#imageProviderForm"))),
        );
        $("#imageProviderModel").innerHTML = response.models
          .map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`)
          .join("");
        if (!response.models.length)
          toast("This key returned no compatible GPT Image models.");
      } catch (e) {
        toast(e.message);
      }
    };
    $("#imageProviderForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api(
          "image-provider/save",
          Object.fromEntries(new FormData(e.target)),
        );
        $("#dialog").close();
        toast(
          "Image model configured. The agent account connection is unchanged.",
        );
      } catch (e) {
        toast(e.message);
      }
    };
  } catch (e) {
    toast(e.message);
  }
}
