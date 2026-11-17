let brains = [];
let quoteMode = false;
let quoteDraft = {};
let quoteExecutionTab = "current";
let previousQuoteId = "";
let previousQuote = null;

function brainPage() {
  $("#main").innerHTML = `<div class="section-heading"><div><h1>Brain</h1><p class="subtitle">Edit shared Markdown knowledge. Grant each agent access in its profile.</p></div><button class="primary" id="newBrain">New Brain</button></div>
    <div class="list">${brains.map(b => `<article class="panel"><h2>${esc(b.name)}</h2><p>Revision ${b.revision} · ${1 + (b.files?.length || 0)} Markdown files · ${b.vehicles.length} vehicles · ${b.partners.length} partners</p><button data-edit-brain="${esc(b.id)}">Open Markdown</button></article>`).join("")}</div>
    ${brains.some(b => b.id === "motor-pricing-demo") ? "" : '<section class="panel"><h2>Motor insurance example</h2><p>Load a fictional price list and two quote crews for Yuzzu and ING.</p><button id="loadQuoteDemo">Load quote example</button></section>'}`;
  $("#newBrain").onclick = () => editBrain().catch(e => toast(e.message));
  document.querySelectorAll("[data-edit-brain]").forEach(button => {
    button.onclick = () => editBrain(brains.find(b => b.id === button.dataset.editBrain)).catch(e => toast(e.message));
  });
  if ($("#loadQuoteDemo")) $("#loadQuoteDemo").onclick = loadQuoteDemo;
}

async function loadQuoteDemo(event) {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const status = await api("connection/status");
    const connection = ["chatgpt", "api"].find(kind => status[kind].valid);
    if (!connection) throw Error("Connect a model before loading the quote crews.");
    const { models } = await api("models", { connection });
    if (!models.length) throw Error("This connection has no available models.");
    const model = models.find(m => m.id === "gpt-6-luna") || models[0];
    await api("brains/pricing-demo", { connection, model: model.id });
    [state, brains] = await Promise.all([api("state"), api("brains")]);
    render();
  } catch (e) {
    toast(e.message);
  } finally {
    button.disabled = false;
  }
}

async function editBrain(brain) {
  modal(`<h2>${brain ? "Edit Brain" : "New Brain"}</h2><p>For motor quotes, keep the Vehicles and Partners table headings and edit the rows. Other Brains can contain any Markdown reference text.</p>
    <form id="brainForm"><label class="field">Name<input name="name" maxlength="80" required value="${esc(brain?.name)}"></label>
    <div class="toolbar"><label class="field">Upload Markdown<input type="file" id="brainFile" accept=".md,.markdown,text/markdown" multiple></label><button type="button" id="brainTemplate">Load pricing template</button></div>
    <label class="field">Markdown<textarea class="brain-markdown" name="markdown" rows="16" maxlength="16000" required spellcheck="false">${esc(brain?.markdown)}</textarea></label><div id="brainFiles"></div><button type="button" id="addBrainFile">Add Markdown file</button> <button class="primary">Save Brain</button></form>`);
  const form = $("#brainForm");
  function addFile(file = {}) {
    if ($("#brainFiles").childElementCount >= 9) return toast("A Brain can contain up to ten files.");
    const fields = document.createElement("fieldset");
    fields.className = "panel brain-file";
    fields.innerHTML = `<label class="field">File name<input name="fileName" maxlength="120" required value="${esc(file.name)}"></label>
      <label class="field">File Markdown<textarea class="brain-markdown" name="fileMarkdown" rows="8" maxlength="16000" required>${esc(file.markdown)}</textarea></label>
      <button type="button">Remove this file</button>`;
    fields.querySelector("button").onclick = () => fields.remove();
    $("#brainFiles").append(fields);
  }
  for (const file of brain?.files || []) addFile(file);
  $("#addBrainFile").onclick = () => addFile();
  $("#brainFile").onchange = async ({target}) => {
    try {
      for (const file of target.files) {
        if (file.size > 64000) throw Error("Choose a smaller Markdown file.");
        const markdown = await file.text();
        if (!markdown.trim() || markdown.length > 16000) throw Error("Files need 1–16,000 Markdown characters.");
        if (!form.elements.markdown.value.trim()) {
          form.elements.markdown.value = markdown;
          if (!form.elements.name.value) form.elements.name.value = file.name.replace(/\.[^.]+$/, "").slice(0, 80);
        } else {
          addFile({name: file.name, markdown});
        }
      }
    } catch (e) {
      toast(e.message);
    } finally {
      target.value = "";
    }
  };
  $("#brainTemplate").onclick = async () => {
    try {
      form.elements.markdown.value = (await api("brains/pricing-template")).markdown;
    } catch (e) {
      toast(e.message);
    }
  };
  form.onsubmit = async e => {
    e.preventDefault();
    const button = form.querySelector("button.primary");
    button.disabled = true;
    try {
      const values = new FormData(form);
      const files = values.getAll("fileName").map((name, i) => ({name, markdown: values.getAll("fileMarkdown")[i]}));
      await api("brains/save", {
        id: brain?.id, revision: brain?.revision, name: values.get("name"), markdown: values.get("markdown"), files,
      });
      brains = await api("brains");
      $("#dialog").close();
      render();
      toast("Brain saved.");
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  };
}

function watchModePicker() {
  return `<div class="toolbar watch-mode" role="group" aria-label="Run type">
    <button id="watchChat" aria-pressed="${!quoteMode}" ${busy ? "disabled" : ""}>Chat</button>
    <button id="watchQuote" aria-pressed="${quoteMode}" ${busy ? "disabled" : ""}>Motor Coach</button>
  </div>`;
}

function bindWatchMode() {
  $("#watchChat").onclick = () => { quoteMode = false; realWatch(); };
  $("#watchQuote").onclick = () => { quoteMode = true; realWatch(); };
}

function motorQuoteMarkup() {
  const teams = state.teams.filter(t => t.quotePartner);
  const team = teams.find(t => t.id === quoteDraft.team) || teams[0];
  if (!team) return '<section class="panel"><p>Load the quote example or set the Motor Coach partner on a team.</p><button id="openQuoteBrain">Open Brain</button></section>';
  const manager = state.agents.find(a => a.id === team.manager);
  const documents = brains.filter(b =>
    b.vehicles.length && b.partners.some(p => p.toLowerCase() === team.quotePartner.toLowerCase()) &&
    manager?.brains?.includes(b.id) && state.agents.some(a =>
      a.id !== team.manager && team.agents.includes(a.id) &&
      a.brains?.includes(b.id) && a.tools.includes("calculator")
    )
  );
  const vehicles = documents.length === 1 ? documents[0].vehicles : [];
  return `<form id="quoteForm" class="panel quote-form"><fieldset ${busy ? "disabled" : ""}>
    <label class="field">Team<select name="team" required>${teams.map(t => `<option value="${esc(t.id)}" ${t.id === team.id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></label>
    <label class="field">Vehicle<select name="vehicle" required>${vehicles.map(v => `<option value="${esc(v)}" ${v === quoteDraft.vehicle ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
    <button class="primary" ${!vehicles.length ? "disabled" : ""}>${busy ? "Working…" : "Run quote"}</button>
  </fieldset>${vehicles.length ? "" : '<p>Give the manager and a pricing analyst with Calculator access to one Brain with this partner and vehicle prices.</p>'}</form>`;

}

function bindMotorQuote() {
  const form = $("#quoteForm");
  if (!form) {
    $("#openQuoteBrain").onclick = () => { page = "Brain"; render(); };
    return;
  }
  form.onchange = event => {
    quoteDraft = Object.fromEntries(new FormData(form));
    if (event.target.name === "team") delete quoteDraft.vehicle;
    realWatch();
  };
  form.onsubmit = async event => {
    event.preventDefault();
    if (busy) return;
    unlockOfficeAudio(true);
    quoteDraft = Object.fromEntries(new FormData(form));
    const { team, ...quote } = quoteDraft;
    quoteExecutionTab = "current";
    run = null;
    busy = true;
    realWatch();
    try {
      activeConversation = await api("conversations", { mode: "team", team });
      mode = "team";
      activeTeamId = team;
      localStorage.setItem("agentsim-conversation", activeConversation.id);
      await realRun({ conversationId: activeConversation.id, goal: "Simulate a motor insurance quote.", quote });
    } catch (e) {
      busy = false;
      toast(e.message);
      realWatch();
    }
  };
}

function quoteResultMarkup(record = run) {
  const result = record?.events?.findLast(e => e.type === "tool_completed" && e.data.implementation === "brain.quote")?.data.output;
  if (!result) return "";
  return `<div class="quote-result"><div><strong>${esc(result.partner)} · ${esc(result.vehicle)}</strong><p>${esc(result.formula)} · Brain revision ${esc(result.revision)}</p></div>
    <strong>€${esc(result.total)}</strong></div>`;
}
