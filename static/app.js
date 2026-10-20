let state,
  page = "Home",
  run = null,
  step = -1,
  mode = "team",
  selected = 0,
  executionMode = "real",
  connectionState = { ready: false },
  busy = false;
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
  const icons = ["⌂", "▷", "♙", "♟", "⚒", "ϟ", "♧"];
  $("#nav").innerHTML = [
    "Home",
    "Watch & run",
    "Agents",
    "Teams",
    "Tools",
    "Skills",
    "MCP Connections",
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
    ["Agents", "Give each helper one clear job.", state.agents.length],
    ["Teams", "Choose which helpers work together.", state.teams.length],
    ["Tools", "Small actions a helper may use.", state.catalog.tools.length],
    [
      "Skills",
      "Instructions that help a helper do its job.",
      state.catalog.skills.length,
    ],
    [
      "MCP Connections",
      "Connect a server and choose its tools.",
      state.catalog.mcp.length,
    ],
    [
      "Watch & run",
      "Set a goal and see each helper work.",
      state.runs.length + " saved runs",
    ],
  ];
  $("#main").innerHTML =
    `<h1>Your AI workshop</h1><p class="subtitle">Build a team. Give it a goal. Learn one step at a time.</p><section class="panel"><h2>Start here</h2><p>${state.agents.length ? `You have ${state.agents.length} saved helpers. ${exampleCount} ${exampleCount === 1 ? "is an example configuration" : "are example configurations"}. A saved helper is a setup, not proof that AI has run.` : "This workspace is empty. Start with your own helper, or load a small example team."}</p><div class="toolbar"><button class="primary" id="ownSetup">${state.agents.length ? "Open my helpers" : "Start empty · create my first helper"}</button><button id="examples">${exampleCount ? "View example helpers" : "Load example team"}</button><button id="goWatch">Watch & run →</button><button id="educationalDemo">Educational samples (optional)</button></div><small>Saved on this computer in a persistent SQLite database (agentsim.db). Account credentials stay in protected local files and are never part of setup exports.</small></section><div class="list dashboard-cards">${cards.map(([name, description, count]) => `<button class="panel dashboard-card" data-open="${name}"><span class="dashboard-count">${esc(count)}</span><h2>${name}</h2><p>${description}</p><span>Open →</span></button>`).join("")}</div><section class="panel" style="margin-top:20px"><h2>Your next steps</h2><p>1. Create a helper or load examples. 2. Choose its job and permissions. 3. Pick a team in Watch & run. Demo shows samples. Real AI needs your own connection.</p><button id="dashboardConnect">Connection setup</button></section>`;
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
function home() {
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
    `<h1>Watch your team work</h1>${run?.failed ? `<section class="panel danger" role="alert">${esc(run.error)}</section>` : ""}<p class="subtitle">See who does what, one step at a time.</p><div class="layout"><div><div class="toolbar"><select aria-label="Run type" id="executionMode"><option value="real">Real AI · automatic</option><option value="demo">Educational samples · optional</option></select><select aria-label="Team" id="team">${state.teams.map((t) => `<option value="${esc(t.id)}" ${t.id === teamId ? "selected" : ""}>♟ Team: ${esc(t.name)}</option>`).join("")}</select><div><button id="one" class="${mode === "one" ? "primary" : ""}">One agent</button><button id="teamMode" class="${mode === "team" ? "primary" : ""}">Team</button></div><button class="orange" id="start" ${busy ? "disabled" : ""}>▶ ${busy ? "Working…" : run ? "Run again" : executionMode === "demo" ? "Start demo" : "Run with AI"}</button></div><div class="steps"><span><b class="circle">1</b>Set a goal</span>→<span><b class="circle">2</b>Pick helpers</span>→<span><b class="circle">3</b>Watch & learn</span></div><div class="panel"><label for="goal">Your goal</label><input id="goal" maxlength="500" value="${esc(run?.goal || "Explain how a team can plan a picnic.")}" style="margin:8px 0 18px"><div class="cards">${members.map((a, i) => `${i ? `<span class="handoff">${run && i <= step ? `<small>${esc(run.provider === "demo" ? "Here are the sample facts." : run.steps[i - 1]?.output.slice(0, 65))}</small>` : ""}<span class="arrow">→</span></span>` : ""}<article class="agent ${i === selected ? "selected" : ""}" data-step="${i}" tabindex="0" role="button" aria-label="Learn about ${esc(a.agent)}"><div class="avatar ${avatarClass(a.avatar || state.agents.find((x) => x.id === a.agentId)?.avatar)}" aria-hidden="true"></div><h2>${esc(a.agent)}</h2>${state.agents.find((x) => x.id === a.agentId)?.example ? '<small class="muted">Example configuration</small>' : ""}<span class="badge ${i < step ? "done" : i === step ? "working" : ""}">${i < step ? "✓ Done" : run?.failed && i === step ? "× Failed" : i === step ? "● Working" : "◷ Waiting"}</span><p>${esc(state.agents.find((x) => x.id === a.agentId)?.job || "Saved helper")}</p><div class="tokens">${run && i <= step ? (run.provider === "demo" ? `Sample input ${run.steps[i].sampleInput} · output ${run.steps[i].sampleOutput}` : `Input ${run.steps[i].inputTokens ?? "—"} · output ${run.steps[i].outputTokens ?? "—"} tokens`) : "Tokens: no provider usage"}</div></article>`).join("") || "<p>Add helpers to a team to begin.</p>"}</div></div><div class="panel usage"><span>▤ ${(run?.provider || executionMode) === "demo" ? "Sample usage" : "Provider usage"}: <b>${usageLabel(run, step)}</b></span><span>${run?.events?.filter((e) => e.type === "tool_completed").length || 0} real tool calls</span><span>${esc(run?.provider || executionMode)} ${busy ? "• Working…" : ""}</span></div><div class="panel"><h2>What is happening?</h2>${
      run
        ? run.steps
            .slice(0, step + 1)
            .map(
              (s, i) =>
                `<div class="event"><b>Step ${i + 1} · ${esc(s.agent)} ${i === step ? "is working" : run.provider === "demo" ? "shared a sample" : "shared a result"}</b><p>${esc(i === step ? (run.provider === "demo" ? "Press Next step to pass the result along." : "This helper is working. Results appear automatically.") : s.output)}</p></div>`,
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
          "Teaching explanation: helpers share small jobs and pass results to each other. This describes the setup, not private thoughts.",
      ],
    ]
      .map(
        ([title, text], i) =>
          `<details ${i === 2 ? "open" : ""}><summary>${title}</summary><p>${esc(text || "Run the team to inspect this step.")}</p></details>`,
      )
      .join(
        "",
      )}<small>Outputs and teaching explanations. No private internal thoughts.</small></section><section class="panel"><h2>Give your agent a job</h2><h3>${esc(current?.agent || members[0]?.agent || "Your helper")}</h3><p class="muted">${esc(state.agents.find((a) => a.id === (current?.agentId || members[0]?.agentId))?.job || "Choose a helper to begin.")}</p><p class="muted">Model: ${esc(current?.model || state.agents.find((a) => a.id === (current?.agentId || members[0]?.agentId))?.model?.name || "Choose in Profile")}</p><button id="editHelpers">Edit job & permissions</button><p>${current ? `Tools: ${esc(current.assignments?.tools?.join(", ") || "None")}<br>Skills: ${esc(current.assignments?.skills?.join(", ") || "None")}<br>MCP: ${esc(current.assignments?.mcp?.join(", ") || "None")}` : "Choose tools, skills and MCP tools in Agents."}</p>${executionMode === "demo" ? `<button class="purple" id="next" ${!run || busy || step >= run.steps.length ? "disabled" : ""}>Next step →</button>` : '<p class="muted">Real AI runs automatically. Watch completed steps appear here.</p>'}<button id="compare" style="width:100%;margin-top:12px">◫ Compare runs</button></section></div></div>`;
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
  $("#editHelpers").onclick = () => {
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
    `<h1>${page}</h1><p class="subtitle">${agents ? "Give each helper a clear job." : "Choose who works together, in order."}</p><div class="toolbar"><button class="primary" id="add">+ Add ${agents ? "agent" : "team"}</button><button id="export">Export setup</button><label><button id="importButton">Import setup</button><input hidden type="file" accept="application/json,.json" id="import"></label></div><div class="list">${state[key].map((a) => `<section class="panel">${agents ? `<div class="avatar ${avatarClass(a.avatar)}" aria-hidden="true"></div>` : ""}<h2>${esc(a.name)}</h2>${a.example ? '<span class="badge">Example configuration</span>' : '<span class="badge">Your saved configuration</span>'}<p>${esc(agents ? a.job : a.agents.map((id) => state.agents.find((x) => x.id === id)?.name).join(" → "))}</p><button data-edit="${esc(a.id)}">Edit</button> <button class="danger" data-delete="${esc(a.id)}">Delete</button></section>`).join("")}</div>`;
  $("#add").onclick = () => editor(key);
  document
    .querySelectorAll("[data-edit]")
    .forEach((b) => (b.onclick = () => editor(key, b.dataset.edit)));
  document.querySelectorAll("[data-delete]").forEach(
    (b) =>
      (b.onclick = async () => {
        state[key] = state[key].filter((a) => a.id !== b.dataset.delete);
        if (agents)
          state.teams.forEach(
            (t) =>
              (t.agents = t.agents.filter((id) => id !== b.dataset.delete)),
          );
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
    `<h2>${id ? "Edit" : "Create"} agent</h2><p>${a.example ? "Example configuration. You can edit it or save it as your own." : "Give this helper a clear identity, job and boundaries."}</p><div class="editor-tabs" role="tablist">${[
      ["profile", "1 · Profile"],
      ["tools", "2 · Tools"],
      ["skills", "3 · Skills"],
      ["mcps", "4 · MCPs"],
    ]
      .map(
        ([key, label], i) =>
          `<button type="button" role="tab" id="tab-${key}" data-tab="${key}" aria-controls="panel-${key}" aria-selected="${i === 0}">${label}</button>`,
      )
      .join(
        "",
      )}</div><form id="agentForm" novalidate><section id="panel-profile" role="tabpanel" aria-labelledby="tab-profile"><fieldset class="avatar-choices"><legend>Choose a character</legend>${["researcher", "writer", "reviewer", "robot"].map((v) => `<label class="avatar-choice"><input type="radio" name="avatar" value="${v}" ${(a.avatar || "robot") === v ? "checked" : ""}><span class="avatar ${avatarClass(v)}" aria-hidden="true"></span><span>${v[0].toUpperCase() + v.slice(1)}</span></label>`).join("")}</fieldset><div class="form-grid">${field("name", "Name", "A short label, such as Picnic researcher.")}${field("role", "Role or specialty", "What is this helper good at? Used as CrewAI role.")}</div>${field("goal", "Goal", "The job this helper should achieve. Used as CrewAI goal.", true)}${field("purpose", "What is this helper for?", "Helps the agent understand its purpose.", true)}${field("backstory", "Context and characteristics", "Background, audience and expertise. Used in CrewAI backstory.", true)}${field("instructions", "Instructions and boundaries", "How should it work? Be concrete. These instructions are sent with its task.", true)}${field("expectedOutput", "Expected result", "Describe the answer you want. Used as the task expected output.", true)}<section class="panel"><h3>This agent's model</h3><label class="field">Connection<select name="agentConnection" id="agentConnection"><option value="chatgpt">ChatGPT · own authorized account</option><option value="api">API · own saved provider credentials</option></select></label><label class="field">Model name<input name="modelName" value="${esc(a.model.name)}" placeholder="Choose a model for this helper"></label><button type="button" id="agentModels">Load models for this connection</button><div id="agentModelList"></div><small>Each helper keeps its own model. A blank model is allowed in a saved draft, but real execution will ask you to select one.</small></section><details><summary>Teaching examples</summary><p>Examples show a style. They are clearly marked as examples, not the current goal or verified facts.</p>${field("exampleInput", "Example input", "", true)}${field("exampleOutput", "Example answer", "", true)}</details><details><summary>Advanced: model and behavior</summary><p>Optional model parameters are sent only when set. Model selection belongs to this agent.</p><div class="form-grid"><label class="field">Temperature (optional)<input type="number" step="0.1" min="0" max="2" name="temperature" value="${a.model.temperature ?? ""}"><small>Blank leaves the provider default. Some models reject temperature; a failed request is shown, never silently changed.</small></label><label class="field">Output token limit (optional)<input type="number" min="16" max="16000" name="maxOutputTokens" value="${a.model.maxOutputTokens ?? ""}"><small>Sent as max_output_tokens only when set. Check your model's supported limits.</small></label><label class="field">CrewAI context budget<input type="number" name="contextWindow" min="4096" max="2000000" value="${a.model.contextWindow ?? 32000}"><small>Used by CrewAI to manage long conversations. Set it to your model's actual capacity; this does not enlarge the model.</small></label>${[
      [
        "maxIterations",
        "Maximum work cycles",
        1,
        20,
        "How many model/tool cycles may this helper use?",
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
        "CrewAI execution limit for this helper.",
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
      )}</div><label class="check"><input type="checkbox" name="respectContextWindow" ${a.behavior.respectContextWindow ? "checked" : ""}>Let CrewAI manage the context budget</label><small>Private reasoning, automatic delegation and arbitrary code execution are not enabled by these settings.</small></details><button type="button" id="previewProfile">Preview profile and task inputs</button><pre id="profilePreview" hidden></pre></section><section id="panel-tools" role="tabpanel" aria-labelledby="tab-tools" hidden><h3>Tools this helper may use</h3><p>Each choice is a permission. Tools are only called when the helper requests them.</p>${checks("tools", a.tools, state.catalog.tools)}</section><section id="panel-skills" role="tabpanel" aria-labelledby="tab-skills" hidden><h3>Skills and instructions</h3><p>Skills add instructions. They never turn on a tool.</p>${checks("skills", a.skills, state.catalog.skills)}${state.catalog.skills
      .filter((s) => s.requires.length)
      .map(
        (s) =>
          `<p class="muted">${esc(s.name)} needs: ${esc(s.requires.join(", "))}</p>`,
      )
      .join(
        "",
      )}</section><section id="panel-mcps" role="tabpanel" aria-labelledby="tab-mcps" hidden><h3>MCP tools this helper may use</h3><p>A connection can offer many tools. Choose only the tools this helper needs.</p>${state.catalog.mcp
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
      )}</section><div class="editor-footer">${a.example ? '<label class="check"><input type="checkbox" name="makeOwn">Save as my own configuration</label>' : ""}<button class="primary">Save agent</button></div></form>`,
  );
  $("#agentConnection").value = a.model.connection || "chatgpt";
  $("#agentModels").onclick = async () => {
    try {
      const r = await api("models", {
        connection: $("#agentConnection").value,
      });
      $("#agentModelList").innerHTML = r.models
        .map(
          (m) =>
            `<button type="button" data-agent-model="${esc(m.id)}">${esc(m.name)}</button>`,
        )
        .join("");
      document
        .querySelectorAll("[data-agent-model]")
        .forEach(
          (b) =>
            (b.onclick = () =>
              ($('#agentForm [name="modelName"]').value =
                b.dataset.agentModel)),
        );
    } catch (e) {
      toast(e.message);
    }
  };
  const switchTab = (key) => {
    document.querySelectorAll("[data-tab]").forEach((b) => {
      b.setAttribute("aria-selected", String(b.dataset.tab === key));
      b.tabIndex = b.dataset.tab === key ? 0 : -1;
    });
    ["profile", "tools", "skills", "mcps"].forEach(
      (k) => ($("#panel-" + k).hidden = k !== key),
    );
  };
  document.querySelectorAll("[data-tab]").forEach((b, i) => {
    b.onclick = () => switchTab(b.dataset.tab);
    b.onkeydown = (e) => {
      if (["ArrowRight", "ArrowLeft"].includes(e.key)) {
        e.preventDefault();
        const keys = ["profile", "tools", "skills", "mcps"];
        const next = keys[(i + (e.key === "ArrowRight" ? 1 : 3)) % 4];
        switchTab(next);
        $("#tab-" + next).focus();
      }
    };
  });
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
      connection: f.get("agentConnection"),
      name: f.get("modelName"),
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
      switchTab("profile");
      toast(e.message);
    }
  };
}
function editor(key, id) {
  if (key === "agents") return agentEditor(id);
  const team = state.teams.find((t) => t.id === id) || { name: "", agents: [] };
  modal(
    `<h2>${id ? "Edit" : "Create"} team</h2><form id="teamForm"><label class="field">Name<input name="name" maxlength="80" value="${esc(team.name)}" required></label><p>Choose the helpers. They run in the order shown below.</p>${checks("agents", team.agents, state.agents)}${team.example ? '<label class="check"><input type="checkbox" name="makeOwn">Save as my own configuration</label>' : ""}<button class="primary">Save team</button></form>`,
  );
  $("#teamForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const f = new FormData(e.target);
      const result = {
        id: id || crypto.randomUUID(),
        name: f.get("name"),
        agents: f.getAll("agents"),
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
    `<h1>${page}</h1><p class="subtitle">Small building blocks for your helpers.</p>${k === "skills" ? '<button id="importSkill">Import a skill</button><p class="muted">Only plain instructions are imported. No scripts or plugins.</p>' : ""}${k === "mcp" ? '<button class="primary" id="addMcp">+ Add HTTP connection</button><p class="muted">Connect → Discover tools → Choose permissions in Agents. New tools always start off.</p>' : ""}<div class="panel"><b>Tools run only when assigned and requested.</b><p>Assign or remove each item in Agents → Edit. MCP permissions are selected one tool at a time.</p></div><div class="list">${state.catalog[k].map((x) => `<section class="panel"><h2>${esc(x.name)}</h2><p>${esc(x.description || (x.id === "documents" ? "Built-in teaching documents. No private files are read." : x.url))}</p>${x.transport ? `<span class="badge">${esc(x.status)}</span><p class="muted">${esc(x.authType)} authentication · ${x.hasCredential ? "credential saved" : "no credential saved"}</p>` : ""}${x.tools ? x.tools.map((t) => `<p>□ ${esc(t.name)} <small>(${esc(t.id)})</small></p>`).join("") : ""}${x.requires?.length ? "<small>Tool dependencies require your explicit choice.</small>" : ""}<div class="toolbar"><button data-assign>Choose agents</button>${k === "mcp" ? `<button data-discover="${esc(x.id)}">${x.id === "documents" ? "Check connection" : "Discover tools"}</button>${x.id !== "documents" ? `<button data-mcp-edit="${esc(x.id)}">Edit</button><button class="danger" data-mcp-remove="${esc(x.id)}">Remove</button>` : ""}` : ""}</div></section>`).join("")}</div>`;
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
      "<h2>Compare runs</h2><p>Make two runs first. Try one helper, then a team with the same goal.</p>",
    );
  modal(
    `<h2>Compare runs</h2><p>Choose two saved samples. More steps means more handoffs, not a promise of a better answer.</p><div class="compare">${[0, 1].map((_, i) => `<div><select id="compare${i}">${state.runs.map((r, j) => `<option value="${j}" ${j === state.runs.length - 2 + i ? "selected" : ""}>${j + 1}. ${esc(r.mode)} · ${esc(r.goal.slice(0, 35))}</option>`).join("")}</select><div id="result${i}"></div></div>`).join("")}</div>`,
  );
  const update = () =>
    [0, 1].forEach((i) => {
      const r = state.runs[$("#compare" + i).value];
      $("#result" + i).innerHTML =
        `<h3>${esc(r.team)}</h3><p>${r.steps.length} helper(s) · ${esc(r.provider)} provider</p><p>${r.provider === "demo" ? "Sample run · no real tokens" : "Provider tokens: " + usageLabel(r)}</p><p>${esc(r.steps.at(-1)?.output)}</p>`;
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
    const helpers = (
      body.mode === "one" ? team.agents.slice(0, 1) : team.agents
    ).map((id) => state.agents.find((a) => a.id === id));
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
          steps: helpers.map(
            (a, i) =>
              completed.find((e) => e.data.index === i)?.data.result || {
                agent: a.name,
                agentId: a.id,
                avatar: a.avatar,
                input: i === 0 ? body.goal : "Waiting for the previous helper.",
                output: "This helper has not completed its answer.",
                why:
                  "Teaching explanation: this helper was assigned the job “" +
                  a.goal +
                  "”.",
                assignments: { tools: a.tools, skills: a.skills, mcp: a.mcp },
                inputTokens: null,
                outputTokens: null,
              },
          ),
          events: snapshot.events,
        };
        step = completed.length;
        selected = Math.min(step, helpers.length - 1);
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
    busy = false;
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
