function officeSprite(avatar) {
  const column = {robot: 0, researcher: 1, writer: 2, reviewer: 3}[avatar] ?? 0;
  const centers = [210, 185, 192, 191];
  const center = column * 384 + centers[column];
  return [0, 1].map(row => `<svg class="office-${row ? "step" : "idle"}" x="-31" y="-82" width="62" height="106"
    viewBox="${center - 135} ${26 + row * 512} 270 458" preserveAspectRatio="xMidYMax meet" overflow="hidden">
    <image href="/office-characters.png" width="1536" height="1024"></image></svg>`).join("");
}

function officeExchanges(record) {
  const events = record?.events || [];
  const exchanges = events.filter(e => ["delegation", "reply"].includes(e.type));
  const final = record?.completed && events.findLast(e => e.type === "agent_completed" &&
    e.data.agentId === record.managerId && e.data.manager);
  if (final) {
    exchanges.push({sequence: final.sequence, type: "final", data: {
      fromId: final.data.agentId, from: final.data.agent, to: "You", message: final.data.output,
    }});
  }
  return exchanges;
}

let officePlayback = {};

function showCrewOffice(office, record, isLive) {
  const exchanges = officeExchanges(record);
  if (officePlayback.runId !== record?.id) {
    clearTimeout(officePlayback.timer);
    officePlayback = {runId: record?.id, queue: [], seen: 0, exchange: null};
  }
  if (!officePlayback.queue) officePlayback.queue = [];
  if (isLive || officePlayback.wasLive) {
    officePlayback.queue.push(...exchanges.filter(e => e.sequence > (officePlayback.seen || 0)));
  } else if (!officePlayback.exchange) {
    officePlayback.exchange = exchanges.at(-1);
  }
  officePlayback.seen = exchanges.at(-1)?.sequence || 0;
  officePlayback.wasLive = isLive;
  officePlayback.record = record;
  officePlayback.host = office;
  if ($("#replayOffice")) $("#replayOffice").disabled = isLive || !exchanges.length || Boolean(officePlayback.timer);
  nextOfficeExchange();
}

function replayOfficeDialogue() {
  if (officePlayback.wasLive || officePlayback.timer) return;
  officePlayback.queue = officeExchanges(officePlayback.record);
  unlockOfficeAudio();
  lastOfficeExchange = null;
  nextOfficeExchange();
}

function firstOfficeStatus(record) {
  if (record?.failed) return "The quote could not be completed.";
  const events = record?.events || [];
  if (events.some(e => e.data.agentId === record.managerId && e.type === "tool_completed" &&
    e.data.implementation === "brain.tools.read_brain")) return "I found the pricing rules. I’m preparing the first task.";
  if (events.some(e => e.data.agentId === record.managerId && e.type === "agent_started")) {
    return "I’m reviewing the quote and checking the pricing rules.";
  }
  return "I’m opening the quote.";
}

function updateOfficeResult(record, exchange, presenting, isLive) {
  const link = $("#quotePdf");
  const result = $("#quoteResult");
  if (!link || !result) return;
  const settled = !isLive && !presenting && !officePlayback.queue.length;
  const announced = exchange?.type === "final";
  const showResult = record?.completed && (settled || announced);
  const pdf = showResult ? officePdf(record) : null;
  const href = pdf?.url || "";
  if (link.dataset.url !== href) {
    link.dataset.url = href;
    link.innerHTML = officePdfLink(pdf);
  }
  const markup = showResult ? quoteResultMarkup(record) : "";
  if (result.dataset.markup !== markup) {
    result.dataset.markup = markup;
    result.innerHTML = markup;
  }
}

function nextOfficeExchange() {
  if (!officePlayback.timer && officePlayback.queue.length && officePlayback.host?.isConnected) {
    officePlayback.exchange = officePlayback.queue.shift();
    officePlayback.timer = setTimeout(() => {
      officePlayback.timer = null;
      nextOfficeExchange();
    }, 2800);
  }
  const {host, record, exchange, timer, wasLive} = officePlayback;
  if (!host?.isConnected) return;
  const roster = record?.roster || [];
  const manager = roster.find(a => a.agentId === record.managerId);
  const status = !exchange && (wasLive || record?.failed) ? firstOfficeStatus(record) : "";
  const shown = status && manager ? {type: "status", data: {
    from: manager.agent, fromId: manager.agentId, message: status,
  }} : exchange;
  const key = `${record?.id}:${exchange?.sequence}:${Boolean(timer)}:${status}`;
  if (host.dataset.key !== key) {
    host.dataset.key = key;
    host.innerHTML = manager ? officeMarkup(record, manager, shown, Boolean(timer))
      : '<p class="office-empty">Run a quote to open the crew office.</p>';
  }
  updateOfficeAudio(record, exchange, Boolean(timer), wasLive);
  updateOfficeResult(record, exchange, Boolean(timer), wasLive);
  for (const station of host.querySelectorAll("[data-office-agent]")) {
    const status = agentActivity(station.dataset.officeAgent, record);
    station.dataset.activity = status;
    station.querySelector(".office-agent-status").textContent = {
      idle: "Ready", active: "Working", waiting: "Waiting", done: "Done", failed: "Failed",
    }[status];
  }
  if ($("#replayOffice")) {
    $("#replayOffice").disabled = Boolean(timer || wasLive || !exchange);
  }
}

function officePdf(record, exchange) {
  if (["delegation", "status"].includes(exchange?.type)) return null;
  return record?.events?.findLast(({type, data, sequence}) =>
    type === "artifact_created" && data.extension === "pdf" &&
    /^\/artifacts\/[A-Za-z0-9-]+\/[a-f0-9]{32}\.pdf$/.test(data.url) &&
    (!exchange || exchange.type === "final" ||
      (sequence <= exchange.sequence && data.agentId === exchange.data.fromId))
  )?.data;
}

function officePdfLink(pdf) {
  return pdf ? `<a class="office-pdf-link" href="${esc(pdf.url)}" target="_blank" rel="noopener"><span class="office-pdf-icon" aria-hidden="true">PDF</span> Open PDF</a>` : "";
}

function officeMarkup(record, manager, exchange, isLive) {
  const workers = record.roster.filter(a => a !== manager);
  const palette = ["#126780", "#7245a7", "#bf6327", "#286745"];
  const agents = [
    { a: manager, x: 390, y: 257, color: "#00008f", manager: true },
    ...workers.map((a, index) => ({
      a, x: workers.length <= 4 ? [152, 628, 628, 152][index] : 115 + index * 550 / (workers.length - 1),
      y: workers.length <= 4 ? (index < 2 ? 177 : 330) : 175 + (index % 2) * 145,
      color: palette[index % palette.length],
    })),
  ];
  const from = agents.find(item => item.a.agentId === exchange?.data.fromId);
  const to = agents.find(item => item.a.agentId === exchange?.data.toId);
  const animate = isLive && from && to;
  const dx = animate ? (to.x - from.x) * .73 : 0;
  const dy = animate ? (to.y - from.y) * .73 : 0;
  const speakerX = from ? (from.x + dx) / 7.8 : 50;
  const speakerY = from ? (from.y + dy - 66) / 4.18 : 32;
  const short = officeSpeech(record, exchange);
  const pdf = exchange?.type === "final" ? officePdf(record) : null;
  return `<div class="office-stage" aria-label="Crew operations floor">
    <svg class="office-world" viewBox="0 0 780 418" role="img" aria-label="Crew office with walking robots">
      <defs>
        <pattern id="office-tiles" width="52" height="34" patternUnits="userSpaceOnUse">
          <rect width="52" height="34" fill="#eeebe4"/><path d="M0 34H52V0M26 0v34" fill="none" stroke="#d9d6cc" stroke-width="1"/>
        </pattern>
        <linearGradient id="office-oak" x2="0" y2="1"><stop stop-color="#e5d1b1"/><stop offset="1" stop-color="#bfa17c"/></linearGradient>
      </defs>
      <rect x="4" y="4" width="772" height="410" rx="15" fill="url(#office-tiles)" stroke="#9aafbd"/>
      <path d="M4 65V20Q4 4 20 4H760Q776 4 776 20V65Z" fill="#203a54"/>
      <path d="M28 17h237v36H28zM515 17h237v36H515z" fill="#c8e4ed" stroke="#8fb6c8" stroke-width="3"/>
      <path d="M105 17v36m80-36v36m407-36v36m80-36v36" stroke="#eef8ff" stroke-width="3"/>
      <text x="390" y="39" text-anchor="middle" fill="#fff" class="office-room-label">MOTOR COACH</text>
      <ellipse cx="390" cy="248" rx="175" ry="111" fill="#dbe9f7" stroke="#a6bfdc"/>
      <ellipse cx="390" cy="248" rx="164" ry="100" fill="none" stroke="#fff" opacity=".55"/>
      ${[35, 745].map(x => `<g transform="translate(${x} 372)"><rect x="-9" width="18" height="19" rx="3" fill="#a67859"/><ellipse cy="-8" rx="14" ry="19" fill="#5c9279"/></g>`).join("")}
      ${agents.map(({x, y, color, manager}) => manager
        ? `<g transform="translate(${x} ${y - 76})">
          <rect x="-87" y="-2" width="174" height="42" rx="10" fill="#243c65" opacity=".28" transform="translate(3 5)"/>
          <rect x="-87" y="-6" width="174" height="43" rx="10" fill="#244779" stroke="#507eb5" stroke-width="2"/>
          <rect x="-47" y="-22" width="94" height="31" rx="6" fill="#162b4a"/>
          <path d="M-35 -11h68m-68 6h48" stroke="#a8d4f3" stroke-width="2"/>
          <text x="0" y="26" text-anchor="middle" fill="white" class="office-desk-title">ORCHESTRATOR</text>
        </g>`
        : `<g transform="translate(${x} ${y - 53})">
        <rect x="-58" y="-1" width="118" height="33" rx="7" fill="#2c4053" opacity=".15" transform="translate(2 5)"/>
        <rect x="-58" y="-4" width="118" height="31" rx="7" fill="url(#office-oak)" stroke="#b29272"/>
        <rect x="13" y="-22" width="32" height="24" rx="3" fill="#243e56"/>
        <rect x="16" y="-19" width="26" height="17" rx="2" fill="#edf4f8"/>
        <path d="M21 -13h16m-16 5h9" stroke="${color}" stroke-width="2"/>
        <path d="M-36 6h17m-17 5h11" stroke="#f9f6ed" stroke-width="3"/>
      </g>`).join("")}
      ${animate ? `<path class="office-walk-route" d="M${from.x} ${from.y}L${to.x} ${to.y}"/>` : ""}
      ${agents.map(({a, x, y, color}) => {
        const walking = animate && a === from.a;
        // The sprite sheet faces right. Mirror only the artwork so labels stay readable.
        const facing = (walking && dx !== 0 ? dx < 0 : x > 390) ? -1 : 1;
        return `<g transform="translate(${x} ${y})"><g class="office-figure ${walking ? "office-walking" : ""}" data-office-agent="${esc(a.agentId)}"
          style="--suit:${color};--walk-x:${walking ? dx : 0}px;--walk-y:${walking ? dy : 0}px">
          <ellipse class="office-shadow" cx="0" cy="28" rx="25" ry="5" fill="#203448" fill-opacity=".19"/>
          <g class="office-character" transform="scale(${facing} 1)">${officeSprite(a.avatar)}</g>
          <text class="office-name" x="0" y="44" text-anchor="middle">${esc(a.agent)}</text>
          <text class="office-agent-status" x="0" y="57" text-anchor="middle"></text>
        </g></g>`;
      }).join("")}
    </svg>
    ${from ? `<div class="office-speech ${animate ? "office-speech-arrival" : ""}" style="--speech-x:${Math.max(24, Math.min(76, speakerX))}%;--speech-y:${Math.max(18, speakerY)}%">
      <strong>${esc(exchange.data.from)}</strong><span>${esc(short.length > 75 ? short.slice(0, 72) + "…" : short)}</span>${officePdfLink(pdf)}
    </div>` : ""}
  </div>
  <div class="office-dialogue" aria-live="polite">${exchange
    ? `<strong>${esc(exchange.data.from)}${exchange.data.to ? " → " + esc(exchange.data.to) : ""}</strong><p>${esc(short.slice(0, 320))}</p>`
    : '<p>Waiting for the first handoff.</p>'}</div>`;
}

function officeSpeech(record, exchange) {
  if (!exchange) return "";
  const message = String(exchange.data.message || "");
  if (exchange.type === "status") return message;
  if (exchange.type === "final") {
    const result = record.events.findLast(e => e.data.implementation === "brain.quote");
    const pdf = record.events.findLast(e => e.type === "artifact_created" && e.data.extension === "pdf");
    if (result && pdf) return `Quote complete. €${result.data.output.total} per year. PDF ready.`;
  }
  if (exchange.type === "delegation") {
    if (/calculate_quote|calculate the|call the pricing/i.test(message)) return "Please calculate the premium.";
    if (/publish_quote|publish the|assemble the pdf/i.test(message)) return "Please publish the quote PDF.";
    if (/illustration|saved.*png/i.test(message)) return "Please confirm the saved illustration.";
    if (/pdf|one.page/i.test(message)) return "Please publish the quote PDF.";
  } else {
    const events = record.events.filter(e => e.sequence <= exchange.sequence &&
      e.data.agentId === exchange.data.fromId);
    const pdf = events.findLast(e => e.type === "artifact_created" && e.data.extension === "pdf");
    if (pdf) return "The quote PDF is ready.";
    const result = events.findLast(e => e.data.implementation === "brain.quote");
    if (result) return "The premium calculation is ready.";
    if (/\.png\b/.test(message)) return "The saved illustration is ready.";
  }
  return message.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/(?:sandbox:)?\/artifacts\/[^\s)]+/g, "the generated file")
    .replace(/[*#`]/g, "").replace(/\s+/g, " ").trim().slice(0, 160);
}

// Presentation cues use the same notes as the SPARX Developer office.
let officeAudioContext;
let officeAudioLive = false;
let lastOfficeExchange;
const officeSoundEnabled = () => localStorage.getItem("agentsim-office-sound") !== "off";

async function unlockOfficeAudio(cue = false) {
  if (!officeSoundEnabled()) return;
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio) {
    if (cue) toast("This browser cannot play office sounds.");
    return;
  }
  try {
    officeAudioContext ||= new Audio();
    if (officeAudioContext.state !== "running") await officeAudioContext.resume();
    if (cue) officeTone([660, .14, 0, .09]);
  } catch {
    if (cue) toast("The browser blocked office sound. Try the sound control.");
  }
}

function officeTone([frequency, duration, delay, volume, type = "sine"]) {
  if (!officeSoundEnabled() || officeAudioContext?.state !== "running") return;
  const start = officeAudioContext.currentTime + delay;
  const oscillator = officeAudioContext.createOscillator();
  const gain = officeAudioContext.createGain();
  oscillator.type = type;
  oscillator.frequency.value = frequency;
  gain.gain.setValueAtTime(.0001, start);
  gain.gain.exponentialRampToValueAtTime(volume, start + .008);
  gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
  oscillator.connect(gain).connect(officeAudioContext.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + .02);
}

let officeFootstep;

function playOfficeFootsteps() {
  if (!officeSoundEnabled() || officeAudioContext?.state !== "running") return;
  const context = officeAudioContext;
  if (!officeFootstep) {
    const length = Math.floor(context.sampleRate * .085);
    officeFootstep = context.createBuffer(1, length, context.sampleRate);
    const sample = officeFootstep.getChannelData(0);
    for (let i = 0; i < length; i++) {
      const t = i / context.sampleRate;
      sample[i] = (Math.sin(2 * Math.PI * 115 * t) * .55 + (Math.random() * 2 - 1) * .38)
        * Math.exp(-t * 58) * Math.min(1, t / .003);
    }
  }
  for (const [index, delay] of [.10, .34, .58, .82].entries()) {
    const step = context.createBufferSource();
    const filter = context.createBiquadFilter();
    const volume = context.createGain();
    step.buffer = officeFootstep;
    step.playbackRate.value = index % 2 ? 1.12 : .92;
    filter.type = "lowpass";
    filter.frequency.value = 800;
    volume.gain.value = index % 2 ? .13 : .16;
    step.connect(filter).connect(volume).connect(context.destination);
    step.start(context.currentTime + delay);
  }
}

function updateOfficeAudio(record, exchange, speaking, isLive) {
  const exchangeKey = exchange && `${record.id}:${exchange.sequence}`;
  if (speaking && exchangeKey && lastOfficeExchange !== exchangeKey) {
    lastOfficeExchange = exchangeKey;
    const walking = Boolean(exchange.data.fromId && exchange.data.toId &&
      exchange.data.fromId !== exchange.data.toId && record.roster?.some(a => a.agentId === exchange.data.toId));
    if (walking && !matchMedia("(prefers-reduced-motion: reduce)").matches) playOfficeFootsteps();
    const delay = walking ? 1.02 : 0;
    const tones = exchange.type === "delegation"
      ? [[1180,.04,0,.05,"square"], [920,.035,.10,.044,"square"], [1320,.04,.20,.044,"square"]]
      : [[880,.085,0,.10], [1180,.08,.09,.07]];
    tones.forEach(([frequency, duration, offset, volume, waveform]) =>
      officeTone([frequency, duration, offset + delay, volume, waveform]));
  }
  if (officeAudioLive && !isLive && record?.completed) {
    [[523,.11,0,.045], [659,.11,.1,.045], [784,.13,.2,.05], [659,.1,.36,.04], [1047,.28,.47,.055]].forEach(officeTone);
  }
  officeAudioLive = isLive;
}
