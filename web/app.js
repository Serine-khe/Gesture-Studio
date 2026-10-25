"use strict";
/* Gesture Studio interface.
   Python does all the work (camera, hands, music). This script only:
     - receives the live state ~30x per second from /events and draws it
     - sends clicks, slider moves and key presses to /api/action          */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

let INIT = null;          // menus and catalogs (loaded once)
let S = null;             // latest live state from Python
let view = "synth";       // synth | free | songs | settings
let songOpen = false;     // in the My Songs tab: playing a song (true) or browsing (false)
let songsRev = null;      // version of the song list we have (reloaded when it changes)
let editing = null;       // id of the song open in the editor ("" = a new song)
let lastToast = null;
let lastHeadline = null;
let lastHandSeen = performance.now();
let lastMessage = performance.now();
let scanning = false;
const dragging = new Set();

const HAND_CONNECTIONS = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10],
  [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
const FINGERS = ["thumb", "index", "middle", "ring", "pinky"];
const FINGER_TIPS = { thumb: 4, index: 8, middle: 12, ring: 16, pinky: 20 };
const COLORS = { harmony: "255,138,92", sound: "124,196,255" };

/* ------------------------------------------------------------- helpers */
function send(type, value, extra = {}) {
  return fetch("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Gesture-Studio": "1" },
    body: JSON.stringify({ type, value, ...extra }),
  }).catch(() => {});
}

function throttle(fn, ms) {
  let last = 0, timer = null, pending;
  return (...args) => {
    pending = args;
    const wait = ms - (performance.now() - last);
    if (wait <= 0) { last = performance.now(); fn(...pending); return; }
    clearTimeout(timer);
    timer = setTimeout(() => { last = performance.now(); fn(...pending); }, wait);
  };
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* Only touch the page when something actually changed (keeps it smooth). */
function setHTML(el, html) { if (el._html !== html) { el.innerHTML = html; el._html = html; } }
function setText(el, text) { if (el.textContent !== text) el.textContent = text; }
function setPressed(el, on) { const v = String(!!on); if (el.getAttribute("aria-pressed") !== v) el.setAttribute("aria-pressed", v); }

/* Little five-bar hand icon: tall bar = finger up (thumb first). */
function glyph(gesture) {
  const info = INIT && INIT.gestures[gesture];
  const pattern = info ? info.pattern : [0, 0, 0, 0, 0];
  return `<span class="glyph" aria-hidden="true">${pattern
    .map((v) => `<i class="${v === 1 ? "up" : v === 2 ? "either" : ""}"></i>`).join("")}</span>`;
}

function paintRange(input) {
  const min = Number(input.min || 0), max = Number(input.max || 1);
  input.style.setProperty("--fill", `${((Number(input.value) - min) / (max - min)) * 100}%`);
}

function setRange(input, value) {
  if (value === undefined || value === null || dragging.has(input)) return;
  if (Number(input.value) !== Number(value)) input.value = value;
  paintRange(input);
}

function setSelect(select, value) {
  if (document.activeElement === select) return;
  if (select.value !== String(value)) select.value = String(value);
}

function bindSlider(input, onValue) {
  const sendLater = throttle(onValue, 40);
  const release = () => setTimeout(() => dragging.delete(input), 300);
  input.addEventListener("pointerdown", () => dragging.add(input));
  input.addEventListener("pointerup", release);
  input.addEventListener("pointercancel", release);
  input.addEventListener("keydown", () => { dragging.add(input); release(); });
  input.addEventListener("input", () => { paintRange(input); sendLater(Number(input.value)); });
}

/* --------------------------------------------------------------- start */
async function boot() {
  try {
    INIT = await (await fetch("/api/init")).json();
  } catch {
    setTimeout(boot, 1000);
    return;
  }
  // Sound menu, grouped: "Synths" and "Instruments" (piano, guitar, strings...).
  const groups = [...new Set(INIT.presets.map((p) => p.group))];
  const presetOptions = groups.map((g) => `<optgroup label="${esc(g)}">${INIT.presets.filter((p) => p.group === g)
    .map((p) => `<option value="${p.id}" title="${esc(p.description)}">${esc(p.label)}</option>`).join("")}</optgroup>`).join("");
  $("#preset").innerHTML = presetOptions;
  $("#set-preset").innerHTML = presetOptions;
  $("#key").innerHTML = INIT.keys.map((k) => `<option value="${k}">${k}</option>`).join("");
  $("#voicing").innerHTML = INIT.voicings.map((v) => `<option value="${v.id}">${esc(v.label)}</option>`).join("");
  buildSongCards();
  buildHelp();
  wire();
  wireEditor();
  connect();
  try {
    if (!localStorage.getItem("gs-help-seen")) {
      $("#help").showModal();
      localStorage.setItem("gs-help-seen", "1");
    }
  } catch { /* private mode: fine */ }
}

function buildSongCards() {
  const cards = INIT.songs.map((s) => {
    const initials = s.title.replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean).slice(0, 2)
      .map((w) => w[0].toUpperCase()).join("") || "♪";
    const chords = [...new Set(s.sections.flatMap((sec) => sec.chords))];
    return `<div class="song-card" role="button" tabindex="0" data-song="${esc(s.id)}">
      <span class="song-top"><span class="monogram" aria-hidden="true">${esc(initials)}</span>
        <span><h3>${esc(s.title)}</h3><span class="artist">${esc(s.artist)}</span></span>
        <button class="card-edit" data-edit="${esc(s.id)}" title="Edit" aria-label="Edit ${esc(s.title)}">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4"/></svg></button></span>
      <span class="chords">${chords.map(esc).join("  ·  ")}</span>
      ${s.sections.length > 1 ? `<span class="sections">${s.sections.map((sec) => esc(sec.name)).join(" · ")}</span>` : ""}
      ${s.unmapped.length ? `<span class="sections warn">More than 7 chords: ${s.unmapped.map(esc).join(", ")} skipped</span>` : ""}
    </div>`;
  });
  cards.push(`<button class="song-card new-card" id="new-song"><span class="plus" aria-hidden="true">+</span>
    <h3>New song</h3><span class="artist">Type in the chords of any song</span></button>`);
  setHTML($("#song-grid"), cards.join(""));
}

async function reloadSongs() {
  try {
    INIT.songs = await (await fetch("/api/songs")).json();
    buildSongCards();
  } catch { songsRev = null; /* try again on the next update */ }
}

/* ------------------------------------------------------------ song editor */
function sectionRow(name = "", chords = "") {
  const li = document.createElement("li");
  li.innerHTML = `<input type="text" class="ed-name" maxlength="80" placeholder="Verse" aria-label="Section name">
    <input type="text" class="ed-chords" placeholder="C G Am F" aria-label="Chords" autocomplete="off" spellcheck="false">
    <button type="button" class="ed-remove" title="Remove section" aria-label="Remove section">×</button>`;
  $(".ed-name", li).value = name;
  $(".ed-chords", li).value = chords;
  return li;
}

function openEditor(id) {
  const song = id ? INIT.songs.find((s) => s.id === id) : null;
  editing = song ? song.id : "";
  setText($("#editor-title"), song ? "Edit song" : "New song");
  $("#ed-title").value = song ? song.title : "";
  $("#ed-artist").value = song ? song.artist : "";
  const list = $("#ed-sections");
  list.innerHTML = "";
  const sections = song ? song.sections : [{ name: "Verse", chords: [] }, { name: "Chorus", chords: [] }];
  sections.forEach((sec) => list.append(sectionRow(sec.name, sec.chords.join(" "))));
  $("#ed-delete").hidden = !song;
  $("#ed-preview").innerHTML = "";
  $("#editor").showModal();
  checkEditor();
  (song ? $(".ed-chords", list) : $("#ed-title")).focus();
}

function editorEntry() {
  return {
    id: editing || "",
    title: $("#ed-title").value,
    artist: $("#ed-artist").value,
    sections: $$("#ed-sections li").map((li) => ({ name: $(".ed-name", li).value, chords: $(".ed-chords", li).value }))
      .filter((sec) => sec.chords.trim()),
  };
}

/* Ask Python to read the chords (same rules as saving) and show which hand sign plays each one. */
let checkId = 0;
async function checkEditor() {
  const id = ++checkId;
  const entry = editorEntry();
  if (!entry.title.trim()) entry.title = "Untitled";   // the title is checked when saving
  let result;
  try {
    result = await (await fetch("/api/song_check", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Gesture-Studio": "1" },
      body: JSON.stringify(entry),
    })).json();
  } catch { return null; }
  if (id !== checkId) return null;   // a newer check is on its way
  const box = $("#ed-preview");
  if (!entry.sections.length) {
    box.innerHTML = `<p class="note">Type the chords of a section to see which hand sign plays each one.</p>`;
  } else if (!result.ok) {
    box.innerHTML = `<p class="ed-error">${esc(result.error)}</p>`;
  } else {
    box.innerHTML = `<div class="ed-gestures">${result.gestures.map((g) => `<span title="${esc(INIT.gestures[g.gesture].label)}">${glyph(g.gesture)}<b>${esc(g.chord)}</b>${
      g.also.length ? `<small>${g.also.map(esc).join(" ")}</small>` : ""}</span>`).join("")}</div>${
      result.unmapped.length ? `<p class="ed-warn">Only 7 hand signs: ${result.unmapped.map(esc).join(", ")} will be skipped. Similar chords (F, Fmaj7, F/A) share a sign.</p>` : ""}`;
  }
  return entry.sections.length ? result : null;
}
const checkLater = throttle(checkEditor, 250);

function wireEditor() {
  const form = $("#editor-form");
  form.addEventListener("input", checkLater);
  $("#ed-add").addEventListener("click", () => {
    const li = sectionRow(["Verse", "Chorus", "Bridge"][$$("#ed-sections li").length % 3]);
    $("#ed-sections").append(li);
    $(".ed-chords", li).focus();
  });
  $("#ed-sections").addEventListener("click", (e) => {
    const b = e.target.closest(".ed-remove");
    if (!b) return;
    if ($$("#ed-sections li").length > 1) b.closest("li").remove();
    else { $(".ed-chords", b.closest("li")).value = ""; }
    checkEditor();
  });
  $("#ed-cancel").addEventListener("click", () => $("#editor").close());
  $("#ed-delete").addEventListener("click", () => {
    const song = INIT.songs.find((s) => s.id === editing);
    if (!song || !confirm(`Delete "${song.title}"? This can't be undone.`)) return;
    send("song_delete", song.id);
    $("#editor").close();
    songOpen = false;
    render();
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const entry = editorEntry();
    if (!entry.sections.length) {
      $("#ed-preview").innerHTML = `<p class="ed-error">Add the chords of at least one section.</p>`;
      return;
    }
    const result = await checkEditor();
    if (!result || !result.ok) return;   // the problem is shown under the chords
    send("song_save", entry);
    $("#editor").close();
    songOpen = true;
    view = "songs";
    render();
  });
}

function buildHelp() {
  const order = ["one", "two", "three", "four", "palm", "rock", "shaka", "fist"];
  $("#help-gestures").innerHTML = order.map((g) => {
    const info = INIT.gestures[g];
    return `<div>${glyph(g)}<b>${esc(info.label)}</b><span>${esc(info.how)}</span></div>`;
  }).join("");
}

/* -------------------------------------------------------- user actions */
function setView(next) {
  view = next;
  if (next === "synth" || next === "free") send("mode", next);
  if (next === "songs" && songOpen) send("mode", "songs");
  try { localStorage.setItem("gs-view", next); } catch { /* ignore */ }
  render();
}

function wire() {
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  $("#mute-btn").addEventListener("click", () => send("mute"));
  $("#help-btn").addEventListener("click", () => $("#help").showModal());
  $("#open-calibration").addEventListener("click", () => {
    $("#help").close();
    setView("settings");
    requestAnimationFrame(() => $("#calibration").scrollIntoView({ behavior: "smooth", block: "start" }));
  });

  $("#preset").addEventListener("change", (e) => send("preset", e.target.value));
  $("#key").addEventListener("change", (e) => send("key", e.target.value));
  $("#voicing").addEventListener("change", (e) => send("voicing", e.target.value));
  $$(".segmented").forEach((seg) => seg.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    const action = seg.dataset.action;
    send(action, action === "register" ? Number(button.dataset.value) : button.dataset.value);
  }));
  $("#octave").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b && S) send("octave", S.octave + Number(b.dataset.step));
  });
  $("#set-octave").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b && S) send("setting", S.settings.default_octave + Number(b.dataset.step), { key: "default_octave" });
  });

  $$("[data-volume]").forEach((input) => bindSlider(input, (v) => send("volume", v)));
  bindSlider($("#brightness"), (v) => send("brightness", v));
  $$("input[type=range][data-setting]").forEach((input) =>
    bindSlider(input, (v) => send("setting", v, { key: input.dataset.setting })));
  $$("select[data-setting]").forEach((select) =>
    select.addEventListener("change", () => send("setting", select.value, { key: select.dataset.setting })));
  $$(".switch").forEach((sw) => sw.addEventListener("click", () =>
    send("setting", sw.getAttribute("aria-checked") !== "true", { key: sw.dataset.setting })));

  $("#set-camera").addEventListener("change", (e) => send("camera", Number(e.target.value)));
  $("#scan-cameras").addEventListener("click", () => { scanning = true; send("scan_cameras"); render(); });
  $("#camera-retry").addEventListener("click", () => send("camera", S ? S.settings.camera_index : 0));
  $("#restart-audio").addEventListener("click", () => send("restart_audio"));

  const openSong = (e) => {
    const edit = e.target.closest("[data-edit]");
    if (edit) { e.stopPropagation(); openEditor(edit.dataset.edit); return; }
    if (e.target.closest("#new-song")) { openEditor(null); return; }
    const card = e.target.closest(".song-card[data-song]");
    if (!card) return;
    songOpen = true;
    send("song_select", card.dataset.song);
    render();
  };
  $("#song-grid").addEventListener("click", openSong);
  $("#song-grid").addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches(".song-card[data-song]")) { e.preventDefault(); openSong(e); }
  });
  $("#song-back").addEventListener("click", () => { songOpen = false; render(); });
  $("#song-restart").addEventListener("click", () => send("song_restart"));
  $("#song-edit").addEventListener("click", () => S && S.song && openEditor(S.song.id));
  $("#song-sections").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) send("song_section", Number(b.dataset.index));
  });
  $("#song-key").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) send("song_transpose", Number(b.dataset.step));
  });

  document.addEventListener("keydown", onKey);
  window.addEventListener("resize", () => render());
  $("#video").addEventListener("load", () => render());
}

function onKey(e) {
  if (!S || $("#help").open || $("#editor").open) return;
  const typing = e.target.closest("input, select, textarea");
  if (typing && e.key !== "Escape") return;
  switch (e.key) {
    case " ": e.preventDefault(); send("mute"); break;
    case "Escape": send("stop"); break;
    case "1": setView("synth"); break;
    case "2": setView("free"); break;
    case "3": setView("songs"); break;
    case "4": setView("settings"); break;
    case "ArrowUp": e.preventDefault(); send("volume", Math.min(1, S.volume + 0.05)); break;
    case "ArrowDown": e.preventDefault(); send("volume", Math.max(0, S.volume - 0.05)); break;
    case "[": send("octave", S.octave - 1); break;
    case "]": send("octave", S.octave + 1); break;
    case "r": case "R": if (S.mode === "songs") send("song_restart"); break;
    default: break;
  }
}

/* ----------------------------------------------------------- live data */
function connect() {
  const events = new EventSource("/events");
  let first = true;
  events.onmessage = (e) => {
    S = JSON.parse(e.data);
    lastMessage = performance.now();
    if (S.songs_rev !== songsRev) {   // a song was saved or deleted
      if (songsRev !== null) reloadSongs();
      songsRev = S.songs_rev;
    }
    document.body.classList.remove("offline");
    if (first) {
      first = false;
      lastToast = S.toast.id;
      let saved = null;
      try { saved = localStorage.getItem("gs-view"); } catch { /* ignore */ }
      if (S.mode === "songs") { view = "songs"; songOpen = true; } else view = S.mode;
      if (saved === "settings") view = "settings";
    }
    scheduleRender();
  };
  setInterval(() => {
    if (performance.now() - lastMessage > 4000) document.body.classList.add("offline");
  }, 1000);
}

let frameRequested = false;
function scheduleRender() {
  if (frameRequested) return;
  frameRequested = true;
  requestAnimationFrame(() => { frameRequested = false; render(); });
}

/* -------------------------------------------------------------- render */
function render() {
  if (!S) return;
  $$(".tabs button").forEach((b) => {
    const v = String(b.dataset.view === view);
    if (b.getAttribute("aria-selected") !== v) b.setAttribute("aria-selected", v);
  });
  const inSong = view === "songs" && songOpen && S.mode === "songs";
  const playing = view === "synth" || view === "free" || inSong;
  $("#play-view").hidden = !playing;
  $("#songs-view").hidden = !(view === "songs" && !inSong);
  $("#settings-view").hidden = view !== "settings";
  $("#dock").hidden = !playing;

  renderStatus();
  if (playing) {
    renderGuides();
    renderNow();
    renderSong();
    renderDock();
    fitStage();
    renderVideoState();
    renderOverlay();
  }
  if (view === "settings") renderSettings();
  renderToast();
}

function fitStage() {
  // The camera fills the window and the panels float over it (see styles.css).
  // Keep the chord display just above the control bar, however tall the bar is.
  const bottom = `${$("#dock").offsetHeight + 14}px`;
  const stage = $(".stage");
  if (stage.style.bottom !== bottom) stage.style.bottom = bottom;
}

function renderStatus() {
  const cam = $("#cam-status");
  const camState = { ok: "ok", starting: "warn", warning: "warn", error: "err" }[S.camera.status] || "warn";
  cam.className = `status ${camState}`;
  setText($("span", cam), S.camera.status === "error" ? "No camera" : "Camera");
  cam.title = S.camera.message || "Camera";

  const audio = $("#audio-status");
  const audioState = { ok: "ok", starting: "warn" }[S.audio.status] || "err";
  audio.className = `status ${audioState}`;
  setText($("span", audio), audioState === "err" ? "No sound" : "Sound");
  audio.title = S.audio.message || (audioState === "ok" ? "Sound engine running" : "Starting sound engine");

  const mute = $("#mute-btn");
  setPressed(mute, S.muted);
  setText($("span", mute), S.muted ? "Muted" : "Mute");
}

function renderGuides() {
  const swap = S.settings.swap_hands;
  for (const role of ["harmony", "sound"]) {
    const el = $(role === "harmony" ? "#guide-harmony" : "#guide-sound");
    const guide = S.guides[role];
    const wanted = role === "harmony" ? S.settings.show_left_guide : S.settings.show_right_guide;
    el.hidden = !wanted || !guide;
    if (!guide) continue;
    const tag = $(".hand-tag", el);
    setText(tag, (role === "harmony") !== swap ? "Left hand" : "Right hand");
    tag.classList.toggle("seen", Boolean(S.hands[role]));
    setText($("h2", el), guide.title);
    setHTML($(".rows", el), guide.rows.map((r) => `
      <li class="${r.active ? "active " : ""}${r.now ? "live " : ""}${r.next ? "next" : ""}">
        ${glyph(r.gesture)}<span class="label">${esc(r.label)}</span>
        <span class="value">${esc(r.value)}${r.sub ? `<small>${esc(r.sub)}</small>` : ""}</span>
      </li>`).join(""));
    let foot = guide.footer || "";
    if (role === "sound" && S.shaping.manual && S.mode !== "free") foot = "Manual mode: use the controls below";
    setText($(".guide-foot", el), foot);
  }
  const shaping = S.mode !== "free";
  $("#guide-sound").classList.toggle("dimmed", shaping && S.shaping.manual);
  $("#sound-meters").hidden = !shaping;
  $("#meter-volume").style.width = `${Math.round(S.shaping.volume * 100)}%`;
  $("#meter-bright").style.width = `${Math.round(S.shaping.brightness * 100)}%`;
  $("#play-view").classList.toggle("no-harmony", $("#guide-harmony").hidden);
  $("#play-view").classList.toggle("no-sound", $("#guide-sound").hidden);
}

function renderNow() {
  const d = S.display;
  const headline = $("#headline");
  const text = d.headline || "–";
  if (text !== lastHeadline) {
    headline.classList.remove("pop");
    if (d.headline) { void headline.offsetWidth; headline.classList.add("pop"); }
    lastHeadline = text;
  }
  setText(headline, text);
  headline.classList.toggle("idle", !d.headline);
  setText($("#now-title"), d.title || "");
  let caption = esc(d.caption || "");
  const song = S.song;
  if (S.mode === "songs" && song && song.next_gesture && d.caption) {
    caption += ` &nbsp;${glyph(song.next_gesture)}`;
  }
  setHTML($("#now-caption"), caption);
  setText($("#now-detail"), d.detail || "");
  const notes = S.mode === "songs" ? [] : (d.notes || []);   // songs: keep the display minimal
  setHTML($("#now-notes"), notes.map((n) => `<span>${esc(n)}</span>`).join(""));
  $("#now").classList.toggle("active", Boolean(d.active));
}

function renderSong() {
  const panel = $("#song-panel");
  const s = S.song;
  panel.hidden = !(S.mode === "songs" && s);
  if (panel.hidden) return;

  // A single row of 8 chords that follows the song (the one playing is highlighted).
  const n = s.chords.length;
  const focus = s.position >= 0 ? s.position : s.next_index;
  const count = Math.min(8, n);
  const chips = [];
  for (let k = 0; k < count; k++) {
    const i = (Math.max(focus - 1, 0) + k) % n;
    chips.push(`<span class="${i === s.position ? "current" : ""}${i === s.next_index ? " next" : ""}">${esc(s.chords[i])}</span>`);
  }
  setHTML($("#chord-strip"), chips.join(""));
  // Section buttons (Verse, Chorus...): start from there.
  setHTML($("#song-sections"), s.parts.length > 1 ? s.parts.map((p) =>
    `<button data-index="${p.index}" class="${p.index === s.part ? "current" : ""}">${esc(p.name)}</button>`).join("") : "");
  setText($("#song-key output"), s.key.split(" ")[0]);
}

function renderDock() {
  $$(".dock-group[data-modes]").forEach((g) => {
    let show = g.dataset.modes.split(" ").includes(S.mode);
    if (g.classList.contains("manual-only")) show = show && S.shaping.manual;
    g.hidden = !show;
  });
  setSelect($("#preset"), S.preset);
  setSelect($("#key"), S.key);
  setSelect($("#voicing"), S.shaping.voicing);
  setText($("#octave output"), String(S.octave));
  $$("[data-volume]").forEach((input) => setRange(input, S.volume));
  setRange($("#brightness"), S.shaping.brightness);
  const values = {
    scale: S.scale,
    expression: S.settings.expression,
    register: String(S.shaping.register),
  };
  $$(".segmented").forEach((seg) => {
    $$("button", seg).forEach((b) => setPressed(b, b.dataset.value === values[seg.dataset.action]));
  });
}

function renderVideoState() {
  const cam = S.camera;
  const empty = $("#video-empty");
  const problem = cam.status !== "ok";
  empty.hidden = !problem;
  if (problem) {
    const titles = { starting: "Starting camera…", warning: "Reconnecting to the camera…", error: "Camera not available" };
    setText($("#video-empty-title"), titles[cam.status] || "Camera");
    setText($("#video-empty-text"), cam.status === "error" ? cam.message || "" : "");
    setHTML($("#video-empty-help"), cam.status === "error" ? (cam.help || []).map((h) => `<li>${esc(h.replace(/^\s*-\s*/, ""))}</li>`).join("") : "");
    $("#camera-retry").hidden = cam.status !== "error";
  }
  const anyHand = Object.keys(S.hands).length > 0;
  if (anyHand) lastHandSeen = performance.now();
  $("#video-hint").classList.toggle("show", !problem && performance.now() - lastHandSeen > 1500);
}

function renderOverlay() {
  const canvas = $("#overlay");
  const card = $("#video-card");
  const dpr = window.devicePixelRatio || 1;
  const w = card.clientWidth, h = card.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!S.settings.show_hand_outlines || S.camera.status !== "ok") return;

  // The picture is shown with "object-fit: cover": work out the same scaling.
  const img = $("#video");
  const iw = img.naturalWidth || 640, ih = img.naturalHeight || 480;
  const scale = Math.max(w / iw, h / ih);
  const ox = (w - iw * scale) / 2, oy = (h - ih * scale) / 2;
  const map = ([x, y]) => [ox + x * iw * scale, oy + y * ih * scale];

  for (const [role, hand] of Object.entries(S.hands)) {
    const rgb = COLORS[role];
    const pts = hand.points.map(map);
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.strokeStyle = `rgba(${rgb},0.55)`;
    ctx.beginPath();
    for (const [a, b] of HAND_CONNECTIONS) { ctx.moveTo(...pts[a]); ctx.lineTo(...pts[b]); }
    ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.7)";
    for (const [x, y] of pts) { ctx.beginPath(); ctx.arc(x, y, 2.2, 0, Math.PI * 2); ctx.fill(); }
    ctx.fillStyle = `rgb(${rgb})`;
    for (const f of FINGERS) {
      if (!hand.fingers[f]) continue;
      const [x, y] = pts[FINGER_TIPS[f]];
      ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
    }
    // Small label under the wrist: which job this hand has, and what it shows.
    const label = `${role === "harmony" ? "Chords" : "Sound"}${hand.label ? " · " + hand.label : ""}`;
    ctx.font = "600 12px 'Segoe UI', system-ui, sans-serif";
    const tw = ctx.measureText(label).width;
    let [lx, ly] = pts[0];
    lx = Math.min(Math.max(lx - tw / 2 - 10, 6), w - tw - 26);
    ly = Math.min(ly + 14, h - 30);
    ctx.fillStyle = "rgba(17,18,21,0.78)";
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(lx, ly, tw + 20, 24, 12); else ctx.rect(lx, ly, tw + 20, 24);
    ctx.fill();
    ctx.fillStyle = `rgb(${rgb})`;
    ctx.fillText(label, lx + 10, ly + 16);
  }
}

function renderSettings() {
  const st = S.settings;
  $$(".switch").forEach((sw) => {
    const v = String(Boolean(st[sw.dataset.setting]));
    if (sw.getAttribute("aria-checked") !== v) sw.setAttribute("aria-checked", v);
  });
  setRange($("#set-steadiness"), st.steadiness);
  setRange($("#set-thumb"), st.thumb_sensitivity);
  setRange($("#set-repeat"), st.piano_repeat);
  setText($("#repeat-value"), `${Number(st.piano_repeat).toFixed(2)} s`);
  setRange($("#set-volume"), S.volume);
  setSelect($("#set-preset"), st.default_preset);
  setText($("#set-octave output"), String(st.default_octave));
  $$("#settings-view .segmented[data-action=scale] button").forEach((b) => setPressed(b, b.dataset.value === st.scale));

  // Camera list
  if (S.camera.available) scanning = false;
  const list = S.camera.available || [S.camera.index ?? st.camera_index];
  const options = list.map((i) => `<option value="${i}">Camera ${i}${i === S.camera.index ? " (in use)" : ""}</option>`).join("");
  setHTML($("#set-camera"), options);
  setSelect($("#set-camera"), S.camera.index ?? st.camera_index);
  setText($("#scan-cameras"), scanning ? "Searching…" : "Find cameras");
  setText($("#camera-note"), S.camera.status === "ok"
    ? `Using camera ${S.camera.index} · ${S.fps ? Math.round(S.fps) + " fps" : ""}`
    : S.camera.message || "");

  const audioOk = S.audio.status === "ok";
  setText($("#audio-note"), audioOk ? "Sound engine running." : S.audio.message
    ? `Sound problem: ${S.audio.message}` : "Starting sound engine…");
  $("#restart-audio").hidden = audioOk || S.audio.status === "starting";

  // Gesture check
  for (const box of $$(".calib-hand")) {
    const role = box.dataset.role;
    const hand = S.hands[role];
    const handName = (role === "harmony") !== st.swap_hands ? "Left hand" : "Right hand";
    const job = role === "harmony" ? "chords" : "sound";
    const name = hand ? (hand.label || (hand.gesture === "unknown" ? "Not sure" : "…")) : "Not visible";
    setHTML(box, `
      <header><span class="hand-tag ${role}">${handName} · ${job}</span><span class="gesture-name">${esc(name)}</span></header>
      <div class="calib-fingers">${FINGERS.map((f) =>
        `<span class="${hand && hand.fingers[f] ? "up" : ""}">${f[0].toUpperCase() + f.slice(1)}</span>`).join("")}</div>
      <div class="calib-meta">${hand ? `Tilt ${Math.round(hand.tilt)}° · Height ${Math.round(hand.height * 100)}%` : "Hold this hand up to the camera"}</div>`);
  }
}

function renderToast() {
  const toast = $("#toast");
  if (lastToast === null || S.toast.id === lastToast) return;
  lastToast = S.toast.id;
  toast.textContent = S.toast.text;
  toast.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove("show"), 1800);
}

boot();
