let state,
  page = "Home",
  run = null,
  step = -1,
  mode = "team",
  selected = 0,
  provider = "demo",
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
  const icons = ["⌂", "♙", "♟", "⚒", "ϟ", "♧"];
  $("#nav").innerHTML = [
    "Home",
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
      }),
  );
}
function render() {
  nav();
  if (page === "Home") home();
  else if (page === "Agents" || page === "Teams") catalog();
  else resources();
}
function usageLabel(r, until = Infinity) {
  if (!r) return "0 tokens";
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
        .map((a) => ({ agent: a.name, agentId: a.id }));
  const current =
    run?.steps[Math.max(0, Math.min(selected, run.steps.length - 1))];
  $("#main").innerHTML =
    `<h1>Watch your team work</h1><p class="subtitle">See who does what, one step at a time.</p><div class="layout"><div><div class="toolbar"><select aria-label="Team" id="team">${state.teams.map((t) => `<option value="${esc(t.id)}" ${t.id === teamId ? "selected" : ""}>♟ Team: ${esc(t.name)}</option>`).join("")}</select><div><button id="one" class="${mode === "one" ? "primary" : ""}">One agent</button><button id="teamMode" class="${mode === "team" ? "primary" : ""}">Team</button></div><button class="orange" id="start" ${busy ? "disabled" : ""}>▶ ${busy ? "Working…" : run ? "Run again" : provider === "demo" ? "Start demo" : "Run with AI"}</button></div><div class="steps"><span><b class="circle">1</b>Set a goal</span>→<span><b class="circle">2</b>Pick helpers</span>→<span><b class="circle">3</b>Watch & learn</span></div><div class="panel"><label for="goal">Your goal</label><input id="goal" maxlength="500" value="${esc(run?.goal || "Explain how a team can plan a picnic.")}" style="margin:8px 0 18px"><div class="cards">${members.map((a, i) => `${i ? `<span class="handoff">${run && i <= step ? `<small>${esc(run.provider === "demo" ? "Here are the sample facts." : run.steps[i - 1]?.output.slice(0, 65))}</small>` : ""}<span class="arrow">→</span></span>` : ""}<article class="agent ${i === selected ? "selected" : ""}" data-step="${i}" tabindex="0" role="button" aria-label="Learn about ${esc(a.agent)}"><div class="avatar portrait portrait-${i % 3}" aria-hidden="true"></div><h2>${esc(a.agent)}</h2><span class="badge ${i < step ? "done" : i === step ? "working" : ""}">${i < step ? "✓ Done" : i === step ? "● Working" : "◷ Waiting"}</span><p>${esc(state.agents.find((x) => x.id === a.agentId)?.job || "Saved helper")}</p><div class="tokens">${run && i <= step ? (run.provider === "demo" ? `Sample input ${run.steps[i].sampleInput} · output ${run.steps[i].sampleOutput}` : `Input ${run.steps[i].inputTokens ?? "—"} · output ${run.steps[i].outputTokens ?? "—"} tokens`) : "Tokens: no provider usage"}</div></article>`).join("") || "<p>Add helpers to a team to begin.</p>"}</div></div><div class="panel usage"><span>▤ ${run?.provider === "demo" || !run ? "Sample usage" : "Provider usage"}: <b>${usageLabel(run, step)}</b></span><span>${run?.events?.filter((e) => e.type === "tool_completed").length || 0} real tool calls</span><span>${esc(run?.provider || provider)} ${busy ? "• Working…" : ""}</span></div><div class="panel"><h2>What is happening?</h2>${
      run
        ? run.steps
            .slice(0, step + 1)
            .map(
              (s, i) =>
                `<div class="event"><b>Step ${i + 1} · ${esc(s.agent)} ${i === step ? "is working" : run.provider === "demo" ? "shared a sample" : "shared a result"}</b><p>${esc(i === step ? "Press Next step to pass the result along." : s.output)}</p></div>`,
            )
            .join("")
        : '<p class="muted">Start the demo. Each click shows one helper receiving and sharing a sample.</p>'
    }${
      run?.events
        ?.filter((e) => e.type === "tool_completed")
        .map(
          (e) =>
            `<div class="event"><b>Tool: ${esc(e.data.name)}</b><p>${esc(e.data.output)}</p></div>`,
        )
        .join("") || ""
    }${run && step >= run.steps.length ? "<b>✓ Demo complete. Everyone has shared their result.</b>" : ""}</div></div><div class="inspector"><section class="panel"><h2>Learn this step</h2>${[
      ["What went in", current?.input],
      [
        "What came out",
        current && selected <= step
          ? current.output
          : "Advance to this step to see its sample output.",
      ],
      [
        "Why this step?",
        current?.why ||
          "Teaching explanation: helpers share small jobs. This demo shows the handoff, not private thoughts.",
      ],
    ]
      .map(
        ([title, text], i) =>
          `<details ${i === 2 ? "open" : ""}><summary>${title}</summary><p>${esc(text || "Start a demo to see an example.")}</p></details>`,
      )
      .join(
        "",
      )}<small>Outputs and teaching explanations. No private internal thoughts.</small></section><section class="panel"><h2>Give your agent a job</h2><h3>${esc(current?.agent || members[0]?.agent || "Your helper")}</h3><p class="muted">${esc(state.agents.find((a) => a.id === (current?.agentId || members[0]?.agentId))?.job || "Choose a helper to begin.")}</p><button id="editHelpers">Edit job & permissions</button><p>${current ? `Tools: ${esc(current.assignments?.tools?.join(", ") || "None")}<br>Skills: ${esc(current.assignments?.skills?.join(", ") || "None")}<br>MCP: ${esc(current.assignments?.mcp?.join(", ") || "None")}` : "Choose tools, skills and MCP tools in Agents."}</p><button class="purple" id="next" ${!run || busy || step >= run.steps.length ? "disabled" : ""}>Next step →</button><button id="compare" style="width:100%;margin-top:12px">◫ Compare runs</button></section></div></div>`;
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
      if (provider !== "demo") {
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
    `<h1>${page}</h1><p class="subtitle">${agents ? "Give each helper a clear job." : "Choose who works together, in order."}</p><div class="toolbar"><button class="primary" id="add">+ Add ${agents ? "agent" : "team"}</button><button id="export">Export setup</button><label><button id="importButton">Import setup</button><input hidden type="file" accept="application/json,.json" id="import"></label></div><div class="list">${state[key].map((a) => `<section class="panel"><h2>${esc(a.name)}</h2><p>${esc(agents ? a.job : a.agents.map((id) => state.agents.find((x) => x.id === id)?.name).join(" → "))}</p><button data-edit="${esc(a.id)}">Edit</button> <button class="danger" data-delete="${esc(a.id)}">Delete</button></section>`).join("")}</div>`;
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
function editor(key, id) {
  const a = state[key].find((a) => a.id === id) || {
    name: "",
    job: "",
    tools: [],
    skills: [],
    mcp: [],
    agents: [],
  };
  modal(
    `<h2>${id ? "Edit" : "Add"} ${key === "agents" ? "agent" : "team"}</h2><form id="editor"><label class="field">Name<input required maxlength="80" name="name" value="${esc(a.name)}"></label>${
      key === "agents"
        ? `<label class="field">Job<textarea name="job" maxlength="500">${esc(a.job)}</textarea></label><h3>Tools</h3>${checks("tools", a.tools, state.catalog.tools)}<h3>Skills</h3>${checks("skills", a.skills, state.catalog.skills)}<small>Skills give instructions. Any tool dependency needs your explicit permission; nothing is enabled automatically.</small><h3>MCP tool permissions</h3>${checks(
            "mcp",
            a.mcp,
            state.catalog.mcp.flatMap((m) =>
              m.tools.map((t) => ({
                id: m.id + ":" + t.id,
                name: m.name + " / " + t.name,
              })),
            ),
          )}`
        : `<p>Helpers run in the order shown below. Edit a team by checking its members.</p>${checks("agents", a.agents, state.agents)}`
    }<button class="primary">Save</button></form>`,
  );
  $("#editor").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target),
      obj = { id: id || crypto.randomUUID(), name: f.get("name") };
    if (key === "agents") {
      obj.job = f.get("job");
      ["tools", "skills", "mcp"].forEach((k) => (obj[k] = f.getAll(k)));
    } else obj.agents = f.getAll("agents");
    if (id) state[key] = state[key].map((x) => (x.id === id ? obj : x));
    else state[key].push(obj);
    $("#dialog").close();
    await persist();
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
function resources() {
  const k = { Tools: "tools", Skills: "skills", "MCP Connections": "mcp" }[
    page
  ];
  $("#main").innerHTML =
    `<h1>${page}</h1><p class="subtitle">Small building blocks for your helpers.</p>${k === "skills" ? '<button id="importSkill">Import a skill</button><p class="muted">Only plain instructions are imported. No scripts or plugins.</p>' : ""}<div class="panel"><b>Allowlisted catalog · Real tools run only when assigned and requested.</b><p>Assign or remove each item in Agents → Edit. MCP permissions are selected one tool at a time.</p></div><div class="list">${state.catalog[k].map((x) => `<section class="panel"><h2>${esc(x.name)}</h2><p>${esc(x.description || "A real MCP server with bundled teaching documents. No private files are read.")}</p>${x.tools ? x.tools.map((t) => `<p>□ ${esc(t.name)}</p>`).join("") : ""}${x.requires?.length ? "<small>Tool dependencies require your explicit choice.</small>" : ""}<button data-assign>Choose agents</button>${k === "mcp" ? '<button id="checkMcp">Check connection</button>' : ""}</section>`).join("")}</div>`;
  if ($("#importSkill")) $("#importSkill").onclick = importSkill;
  if ($("#checkMcp"))
    $("#checkMcp").onclick = async () => {
      try {
        const r = await api("mcp/check", {});
        toast("MCP connected · " + r.tools.map((t) => t.name).join(", "));
      } catch (e) {
        toast(e.message);
      }
    };
  document.querySelectorAll("[data-assign]").forEach(
    (b) =>
      (b.onclick = () => {
        page = "Agents";
        render();
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
    const c = await api("settings");
    modal(
      `<h2>Connect your account</h2><p>Choose how your helpers work. Demo uses samples. A real connection sends your goal to your chosen provider.</p><button class="primary" id="oauth">Continue with ChatGPT</button> <button id="logout">Sign out</button><p>${c.oauth_connected ? "ChatGPT permission saved on this computer." : "ChatGPT is not connected. Sign-in opens your browser for permission."}</p><form id="settings"><label class="field">Connection<select name="provider" id="provider"><option value="demo">Demo · no AI calls</option><option value="chatgpt">ChatGPT · your authorized plan</option><option value="api">API provider · your own key</option></select></label><label class="field">Model<input name="model" value="${esc(c.model)}" placeholder="Choose a model from your provider"></label><button type="button" id="models">Load my models</button><div id="modelList"></div><details><summary>Advanced: API connection</summary><p>Use a provider that supports the Responses API. Your key stays in a protected file on this computer. It is never included in exports.</p><label class="field">API base URL<input type="url" name="base_url" value="${esc(c.base_url)}"></label><label class="field">API key<input type="password" autocomplete="off" name="api_key" placeholder="${c.has_key ? "Saved · leave blank to keep" : "Enter locally, never in chat"}"></label></details><button class="primary">Save connection</button></form><p><small>No connection is shown as working until its real request succeeds.</small></p>`,
    );
    $("#provider").value = c.provider;
    $("#oauth").onclick = async () => {
      try {
        const result = await api("oauth/start", {});
        location.href = result.url;
      } catch (e) {
        toast(e.message);
      }
    };
    $("#logout").onclick = async () => {
      await api("oauth/logout", {});
      toast("Signed out locally. You can also revoke app access in ChatGPT.");
      connection();
    };
    const saveSettings = async () => {
      const f = new FormData($("#settings"));
      const result = await api("settings", Object.fromEntries(f));
      provider = result.provider;
      return result;
    };
    $("#settings").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await saveSettings();
        $("#dialog").close();
        refreshConnection();
        render();
        toast("Connection settings saved.");
      } catch (e) {
        toast(e.message);
      }
    };
    $("#models").onclick = async () => {
      try {
        await saveSettings();
        const data = await api("models", {});
        $("#modelList").innerHTML = data.models
          .map(
            (m) =>
              `<button type="button" data-model="${esc(m.id)}">${esc(m.name)}</button>`,
          )
          .join("");
        document
          .querySelectorAll("[data-model]")
          .forEach(
            (b) =>
              (b.onclick = () =>
                ($('#settings [name="model"]').value = b.dataset.model)),
          );
      } catch (e) {
        toast(e.message);
      }
    };
  } catch (e) {
    toast(e.message);
  }
}
async function refreshConnection() {
  const c = await api("settings");
  provider = c.provider;
  $("#connection").textContent =
    c.provider === "demo"
      ? "○ Demo · no account needed"
      : c.provider === "chatgpt"
        ? c.oauth_connected
          ? "◉ ChatGPT authorized"
          : "○ ChatGPT sign-in needed"
        : c.has_key
          ? "◉ API key saved · test with a run"
          : "○ API key needed";
  $(".tag").textContent =
    c.provider === "demo" ? "Demo • Sample data" : "Real AI • " + c.provider;
}
async function realRun(body) {
  busy = true;
  run = null;
  home();
  try {
    const job = await api("real-run", body);
    let result;
    do {
      await new Promise((r) => setTimeout(r, 1000));
      result = await api("jobs/" + job.id);
      const completed = result.events.filter(
        (e) => e.type === "step_completed",
      );
      if (completed.length) {
        run = {
          goal: body.goal,
          provider,
          steps: completed.map((e) => e.data.result),
          events: result.events,
        };
        step = run.steps.length;
        selected = Math.max(0, step - 1);
      }
      if (page === "Home") home();
    } while (result.status === "running");
    if (result.status === "failed") throw Error(result.error);
    run = result.run;
    state = await api("state");
    step = run.steps.length;
    selected = run.steps.length - 1;
    toast("Real run complete. Outputs and provider usage are saved.");
  } catch (e) {
    toast(e.message);
  } finally {
    busy = false;
    if (page === "Home") home();
  }
}
$("#connect").onclick = connection;
$("#connection").onclick = connection;
$("#help").onclick = () =>
  modal(
    "<h2>A team of small jobs</h2><p>Goal: plan a picnic. The Researcher finds things to bring. The Writer makes a short plan. The Reviewer checks whether the plan is easy to follow.</p><p>A tool helps do one task. A skill gives instructions. An MCP connection can offer several tools. You choose each permission.</p><p>Tokens are small pieces of text. Demo counts are sample numbers. Real AI counts come only from your provider.</p>",
  );
api("state")
  .then((s) => {
    state = s;
    refreshConnection();
    render();
  })
  .catch((e) => {
    $("#main").textContent =
      "Could not load the app. Start the Python server and refresh.";
  });
