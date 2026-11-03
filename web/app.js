/* NOVA arayüzü — Samet Şahin */
(() => {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const LABELS = {
  idle: ["Beklemede", "Mikrofon kapalı · yazabilirsin"],
  listening: ["Dinliyor", "Dinliyorum"],
  hearing: ["Duyuyor", "Anlıyorum"],
  thinking: ["Düşünüyor", "Düşünüyorum"],
  speaking: ["Konuşuyor", "Konuşuyorum"],
  sleeping: ["Uyku modu", "Uyandırmak için “Nova uyan”"],
};
const DAYS = ["Pazar","Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi"];
const MONTHS = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"];

let api = null;
let info = null;
let state = "idle";
let micLevel = 0, outLevel = 0;

/* ================= köprü ================= */
function whenReady() {
  return new Promise(res => {
    if (location.search.includes("demo")) return setTimeout(() => res(demoApi()), 200);
    const token = (location.hash.match(/t=([\w-]+)/) || [])[1] || "";
    // Python'daki fonksiyonları çağırmak için köprü: api.ad(...) → POST /api/ad
    const bridge = new Proxy({}, {
      get: (_, name) => name === "then" ? undefined : (...args) => fetch("/api/" + String(name), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Nova-Token": token },
        body: JSON.stringify(args),
      }).then(r => r.json()).catch(e => { console.error(e); return null; }),
    });
    // Python'dan gelen olaylar (otomatik yeniden bağlanır)
    const es = new EventSource("/events?t=" + encodeURIComponent(token));
    es.onmessage = m => { try { window.novaEvent(JSON.parse(m.data)); } catch (e) { console.error(e); } };
    es.onopen = () => { if (api) $("#statusText").textContent = LABELS[state][0]; };
    es.onerror = () => { $("#statusText").textContent = "Bağlantı bekleniyor"; };
    window.addEventListener("error", e => bridge.log_js(e.message + " @" + e.filename + ":" + e.lineno));
    res(bridge);
  });
}

/* ================= saat ================= */
function tickClock() {
  const d = new Date();
  $("#clock").textContent = d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  $("#date").textContent = `${d.getDate()} ${MONTHS[d.getMonth()]} ${DAYS[d.getDay()]}`;
}
tickClock(); setInterval(tickClock, 5000);

/* ================= durum ================= */
function setState(s, label) {
  state = s;
  document.body.dataset.state = s;
  const [chip, core] = LABELS[s] || LABELS.idle;
  $("#statusText").textContent = chip;
  $("#coreLabel").textContent = label || core;
}
function setMic(on) {
  $("#btnMic").classList.toggle("on", !!on);
  $("#fListen").textContent = on ? "Sürekli" : "Kapalı";
}

/* ================= sohbet ================= */
function addMsg(who, text) {
  const t = $("#transcript");
  const el = document.createElement("div");
  el.className = "msg " + who;
  el.textContent = text;
  t.appendChild(el);
  while (t.children.length > 40) t.firstChild.remove();
  t.scrollTop = t.scrollHeight;
}
let toastTimer;
function toast(text, kind) {
  const el = $("#toast");
  el.textContent = text;
  el.className = "toast show " + (kind || "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = "toast " + (kind || ""), 4200);
}

/* ================= ses çalma ================= */
let actx = null, analyser = null, current = null, levelBuf = null;
function audioCtx() {
  if (!actx) {
    actx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = actx.createAnalyser();
    analyser.fftSize = 512;
    levelBuf = new Uint8Array(analyser.fftSize);
    analyser.connect(actx.destination);
  }
  if (actx.state === "suspended") actx.resume();
  return actx;
}
/* Python cümle cümle ses gönderir; burada sırayla çalınır. */
let speechQueue = [], playing = false, finalSeen = true;
function finishAll() { current = null; playing = false; outLevel = 0; api && api.speech_done(); }
function chunkEnded() {
  current = null; playing = false;
  if (speechQueue.length) playNext();
  else if (finalSeen) finishAll();
}
function stopAudio() {
  speechQueue = []; finalSeen = true;
  if (current) { try { current.pause(); } catch (e) {} current = null; }
  if (window.speechSynthesis) speechSynthesis.cancel();
  playing = false; outLevel = 0;
}
function speak(ev) {
  if (ev.first) stopAudio();
  finalSeen = ev.final !== false;
  speechQueue.push(ev);
  if (!playing) playNext();
}
function playNext() {
  const ev = speechQueue.shift();
  if (!ev) return;
  playing = true;
  if (ev.audio) {
    const plain = () => {                      // yedek: düz <audio> ile çal
      const a = new Audio("data:audio/mpeg;base64," + ev.audio);
      current = { pause: () => { a.onended = null; a.pause(); } };
      a.onended = chunkEnded; a.onerror = chunkEnded;
      a.play().catch(() => { toast("Sesi duymak için pencereye bir kez tıkla."); chunkEnded(); });
    };
    const ctx = audioCtx();
    if (ctx.state !== "running") { plain(); return; }
    const bytes = Uint8Array.from(atob(ev.audio), ch => ch.charCodeAt(0));
    ctx.decodeAudioData(bytes.buffer).then(buf => {
      if (!playing) return;                    // bu arada durduruldu
      const src = ctx.createBufferSource();
      src.buffer = buf; src.connect(analyser);
      src.onended = chunkEnded;
      current = { analysed: true, pause: () => { src.onended = null; try { src.stop(); } catch (e) {} } };
      src.start();
    }).catch(plain);
    return;
  }
  if (window.speechSynthesis) {               // yedek: Windows'un kendi sesi
    const u = new SpeechSynthesisUtterance(ev.text);
    u.lang = ev.lang || "tr-TR";
    u.onend = chunkEnded; u.onerror = chunkEnded;
    current = { pause: () => { u.onend = null; speechSynthesis.cancel(); } };
    speechSynthesis.speak(u);
    return;
  }
  chunkEnded();
}
function readOutLevel() {
  if (!analyser || !current || !current.analysed) return outLevel * 0.85;
  analyser.getByteTimeDomainData(levelBuf);
  let sum = 0;
  for (const v of levelBuf) { const x = (v - 128) / 128; sum += x * x; }
  return Math.min(1, Math.sqrt(sum / levelBuf.length) * 3.2);
}
document.addEventListener("pointerdown", () => audioCtx(), { once: true });

/* ================= Python olayları ================= */
window.novaEvent = ev => {
  switch (ev.type) {
    case "state": setState(ev.state, ev.label); setMic(ev.mic); $("#btnSleep").classList.toggle("on", !ev.awake); break;
    case "level": micLevel = ev.value; break;
    case "user": addMsg("user", ev.text); break;
    case "nova": addMsg("nova", ev.text); break;
    case "speak": speak(ev); break;
    case "stop_audio": stopAudio(); break;
    case "clear": $("#transcript").innerHTML = ""; break;
    case "toast": toast(ev.text, ev.kind); break;
    case "needs_setup": openDrawer("settings"); $("#setupNotice").hidden = false; break;
    case "stats": showStats(ev); break;
    case "timers": timers = ev.items || []; renderTimers(); break;
    case "alarm": toast("⏰ " + ev.text); chime(); break;
    case "panel": showPanel(ev); break;
    case "calendar": calEvents = ev.events || []; if (ev.focus) calSelect(ev.focus); renderCal(); break;
    case "rates": showRates(ev); break;
    case "update": showUpdate(ev); break;
    case "update_progress": $("#updProg").textContent = "%" + ev.value; break;
  }
};
function bar(id, v) { $("#" + id + "V").textContent = v == null ? "--" : v + "%"; $("#" + id + "B").style.width = (v || 0) + "%"; }
function showStats(s) {
  bar("cpu", s.cpu); bar("ram", s.ram);
  if (s.battery == null) $("#batRow").hidden = true;
  else { bar("bat", s.battery); if (s.plugged) $("#batV").textContent = s.battery + "% ⚡"; }
}

/* ================= zamanlayıcılar ================= */
let timers = [];
function fmtLeft(ms) {
  const t = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
}
function renderTimers() {
  const box = $("#timers");
  const badge = $("#timerBadge");
  badge.hidden = !timers.length; badge.textContent = timers.length;
  box.innerHTML = timers.length ? "" : '<li class="empty">Kurulu zamanlayıcı yok.</li>';
  for (const t of timers) {
    const li = document.createElement("li");
    li.innerHTML = '<span class="tl"></span><b class="tv"></b><button class="x" title="İptal">×</button>';
    li.querySelector(".tl").textContent = t.label || "Zamanlayıcı";
    li.querySelector(".tv").dataset.end = t.end;
    li.querySelector(".x").onclick = () => api.cancel_timer(t.id);
    box.appendChild(li);
  }
  tickTimers();
}
function tickTimers() {
  $$("#timers .tv").forEach(el => el.textContent = fmtLeft(+el.dataset.end - Date.now()));
}
setInterval(tickTimers, 1000);
function chime() {
  try {
    const ctx = audioCtx(), now = ctx.currentTime;
    [880, 1175, 1568].forEach((f, i) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f; o.type = "sine";
      g.gain.setValueAtTime(0, now + i * .18);
      g.gain.linearRampToValueAtTime(.18, now + i * .18 + .02);
      g.gain.exponentialRampToValueAtTime(.001, now + i * .18 + .5);
      o.connect(g).connect(ctx.destination); o.start(now + i * .18); o.stop(now + i * .18 + .55);
    });
  } catch (e) {}
}


/* =====================================================================
   PANELLER: haberler, takvim, zamanlayıcı, harita, notlar, hava, piyasa
   ===================================================================== */
const TR_MONTHS = MONTHS, TR_DOW = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let activeTab = "news";
function selectTab(name) {
  activeTab = name;
  try { localStorage.setItem("nova.tab", name); } catch (e) {}
  $$(".tabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  $$(".pane").forEach(p => p.classList.toggle("active", p.dataset.pane === name));
  if (name === "news" && !newsLoaded[newsCat]) loadNews(newsCat);
  if (name === "calendar") renderCal();
  if (name === "notes") loadNotes();
  if (name === "map") initMap();
}
$$(".tabs button").forEach(b => b.onclick = () => selectTab(b.dataset.tab));
$("#btnDock").onclick = () => document.body.classList.toggle("dock-open");
function showPanel(ev) {
  document.body.classList.add("dock-open");
  if (ev.name === "news" && ev.category) { newsCat = ev.category; newsLoaded[newsCat] = false; }
  if (ev.name === "calendar" && ev.focus) calSelect(ev.focus);
  selectTab(ev.name);
  if (ev.name === "map" && ev.place) setTimeout(() => mapShow(ev.place), 150);
}
function ago(ts) {
  if (!ts) return "";
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  if (m < 1) return "şimdi"; if (m < 60) return m + " dk önce";
  const h = Math.round(m / 60); if (h < 24) return h + " sa önce";
  return Math.round(h / 24) + " gün önce";
}

/* ---------- haberler ---------- */
let newsCat = "gundem"; const newsLoaded = {};
async function loadNews(cat) {
  newsCat = cat;
  $$("#newsCats button").forEach(b => b.classList.toggle("on", b.dataset.cat === cat));
  const list = $("#newsList");
  list.innerHTML = '<li class="empty">Yükleniyor…</li>';
  const d = await api.get_news(cat);
  if (!d || !d.items || !d.items.length) { list.innerHTML = '<li class="empty">Haberlere şu an ulaşılamadı. İnternet bağlantını kontrol et.</li>'; return; }
  newsLoaded[cat] = true;
  list.innerHTML = "";
  for (const n of d.items) {
    const li = document.createElement("li");
    li.className = "item"; li.title = n.desc || "";
    li.innerHTML = (n.img ? `<img src="${esc(n.img)}" alt="" loading="lazy" onerror="this.remove()">` : "") +
      `<span><span class="nt">${esc(n.title)}</span><span class="nm">${esc(n.source)} · ${esc(ago(n.ts))}</span></span>`;
    li.onclick = () => api.open_url(n.link);
    list.appendChild(li);
  }
}
$$("#newsCats button").forEach(b => b.onclick = () => loadNews(b.dataset.cat));
$("#newsRefresh").onclick = () => loadNews(newsCat);
$("#newsRead").onclick = () => { audioCtx(); api.read_news(newsCat); };

/* ---------- takvim ---------- */
let calEvents = [], calView = new Date(), calSel = isoDate(new Date());
function isoDate(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
function calSelect(iso) { calSel = iso; const [y, m] = iso.split("-").map(Number); calView = new Date(y, m - 1, 1); }
function renderCal() {
  const y = calView.getFullYear(), m = calView.getMonth();
  $("#calTitle").textContent = `${TR_MONTHS[m]} ${y}`;
  const grid = $("#calGrid"); grid.innerHTML = TR_DOW.map(d => `<span class="dow">${d}</span>`).join("");
  const first = new Date(y, m, 1), start = new Date(y, m, 1 - ((first.getDay() + 6) % 7));
  const today = isoDate(new Date()), has = new Set(calEvents.map(e => e.date));
  for (let i = 0; i < 42; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    const iso = isoDate(d), b = document.createElement("button");
    b.textContent = d.getDate(); b.type = "button";
    b.className = [d.getMonth() !== m && "out", iso === today && "today", iso === calSel && "sel", has.has(iso) && "has"].filter(Boolean).join(" ");
    b.onclick = () => { calSel = iso; renderCal(); };
    grid.appendChild(b);
  }
  const [sy, sm, sd] = calSel.split("-").map(Number);
  const sdate = new Date(sy, sm - 1, sd);
  $("#calDayTitle").textContent = `${sd} ${TR_MONTHS[sm - 1]} ${DAYS[sdate.getDay()]}`;
  const list = $("#calEvents"), evs = calEvents.filter(e => e.date === calSel);
  list.innerHTML = evs.length ? "" : '<li class="empty">Bu gün için etkinlik yok.</li>';
  for (const e of evs) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="tm">${esc(e.time || "—")}</span><span class="tt">${esc(e.title)}</span><button class="x" title="Sil">×</button>`;
    li.querySelector(".x").onclick = async () => { calEvents = await api.cal_delete(e.id); renderCal(); };
    list.appendChild(li);
  }
}
$("#calPrev").onclick = () => { calView = new Date(calView.getFullYear(), calView.getMonth() - 1, 1); renderCal(); };
$("#calNext").onclick = () => { calView = new Date(calView.getFullYear(), calView.getMonth() + 1, 1); renderCal(); };
$("#calToday").onclick = () => { calSelect(isoDate(new Date())); renderCal(); };
$("#calForm").onsubmit = async e => {
  e.preventDefault();
  const f = e.target;
  const r = await api.cal_add({ title: f.title.value, date: calSel, time: f.time.value, remind: +f.remind.value });
  if (r && r.ok) { calEvents = r.events; f.title.value = ""; f.time.value = ""; renderCal(); toast("Takvime eklendi."); }
};

/* ---------- zamanlayıcı formları ---------- */
$$("#quickTimers button").forEach(b => b.onclick = () => { audioCtx(); api.add_timer(+b.dataset.min * 60, ""); toast(b.textContent + " zamanlayıcı kuruldu."); });
$("#timerForm").onsubmit = e => {
  e.preventDefault(); audioCtx();
  const f = e.target, min = +f.min.value;
  if (!min) return;
  api.add_timer(min * 60, f.label.value); f.min.value = ""; f.label.value = "";
  toast("Hatırlatıcı kuruldu.");
};
$("#alarmForm").onsubmit = async e => {
  e.preventDefault(); audioCtx();
  const f = e.target;
  const msg = await api.add_alarm(f.time.value, f.label.value);
  f.label.value = ""; if (msg) toast(msg);
};

/* ---------- harita ---------- */
let map = null, mapMarker = null, mapPlace = null;
async function initMap() {
  if (map) { setTimeout(() => map.invalidateSize(), 60); return; }
  if (!window.L) { $("#map").innerHTML = '<p class="empty">Harita yüklenemedi. İnternet bağlantını kontrol et.</p>'; return; }
  $("#map").innerHTML = "";
  map = L.map("map", { zoomControl: true, attributionControl: true }).setView([39.0, 35.0], 5);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    maxZoom: 19, subdomains: "abcd",
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(map);
  setTimeout(() => map.invalidateSize(), 60);
  if (!mapPlace && info && info.settings.city) { const p = await api.geocode(info.settings.city); if (p) mapShow(p, 11); }
}
function mapShow(p, zoom) {
  if (!map) { initMap().then(() => mapShow(p, zoom)); return; }
  mapPlace = p;
  map.setView([p.lat, p.lon], zoom || 13);
  if (mapMarker) mapMarker.remove();
  mapMarker = L.marker([p.lat, p.lon]).addTo(map).bindPopup(esc(p.label || p.name)).openPopup();
  $("#mapLabel").textContent = p.label || p.name;
}
$("#mapForm").onsubmit = async e => {
  e.preventDefault();
  const q = e.target.q.value.trim(); if (!q) return;
  const p = await api.geocode(q);
  if (p) mapShow(p); else toast(q + " bulunamadı.", "error");
};
$("#mapRoute").onclick = () => {
  if (!mapPlace) return toast("Önce bir yer ara.");
  api.open_url(`https://www.google.com/maps/dir/?api=1&destination=${mapPlace.lat},${mapPlace.lon}`);
};

/* ---------- notlar ---------- */
function renderNotes(list) {
  const ul = $("#notesList");
  ul.innerHTML = list && list.length ? "" : '<li class="empty">Henüz not yok. Yaz ya da “Not al: …” de.</li>';
  (list || []).map((n, i) => [n, i]).reverse().forEach(([n, i]) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="tt">${esc(n.text)}<small>${esc(n.time)}</small></span><button class="x" title="Sil">×</button>`;
    li.querySelector(".x").onclick = async () => renderNotes(await api.note_delete(i));
    ul.appendChild(li);
  });
}
async function loadNotes() { renderNotes(await api.notes_list()); }
$("#noteForm").onsubmit = async e => {
  e.preventDefault();
  const t = e.target.text; if (!t.value.trim()) return;
  renderNotes(await api.note_add(t.value)); t.value = "";
};
$("#noteForm textarea").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#noteForm").requestSubmit(); } });

/* ---------- hava ve piyasa ---------- */
async function loadWeather() {
  const w = await api.get_weather();
  if (!w || !w.ok) { $("#wxDesc").textContent = (w && w.error) || "Ulaşılamadı"; return; }
  $("#wxCity").textContent = w.city; $("#wxIcon").textContent = w.icon;
  $("#wxTemp").textContent = w.temp + "°"; $("#wxDesc").textContent = w.desc;
  $("#wxMeta").textContent = `Hissedilen ${w.feels}° · Rüzgâr ${w.wind} km/s`;
  $("#wxDays").innerHTML = w.days.map(d => `<li title="${esc(d.desc)}${d.rain != null ? " · yağış %" + d.rain : ""}">${esc(d.day)}<span>${d.icon}</span><b>${d.max}°</b>${d.min}°</li>`).join("");
}
const fmtTL = v => v.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
function showRates(r) {
  if (!r || !r.ok) { $("#fxGrid").innerHTML = '<span class="empty">Kurlara ulaşılamadı</span>'; return; }
  const names = { USD: "DOLAR", EUR: "EURO", GBP: "STERLİN", ALTIN: "GRAM ALTIN" };
  $("#fxGrid").innerHTML = Object.entries(r.rates).map(([k, v]) => `<div><dt>${names[k] || k}</dt><dd>₺${fmtTL(v)}</dd></div>`).join("");
  $("#fxTime").textContent = "· " + r.time;
}
async function loadRates() { showRates(await api.get_rates()); }

/* ---------- güncelleme ---------- */
let updInfo = null;
function showUpdate(u) {
  updInfo = u;
  const chip = $("#updateChip");
  chip.hidden = !(u && u.available);
  if (u && u.available) { $("#updVer").textContent = "v" + u.latest; $("#updProg").textContent = "Güncelle"; }
}
$("#updateChip").onclick = async () => {
  if (!updInfo) return;
  $("#updProg").textContent = "İndiriliyor…";
  const r = await api.install_update();
  if (!r || !r.ok) { toast((r && r.error) || "Güncelleme başlatılamadı", "error"); $("#updProg").textContent = "Güncelle"; }
};
$("#btnUpd").onclick = async () => {
  await api.save_settings(readForm());
  $("#updOut").textContent = "Denetleniyor…";
  const u = await api.check_update();
  if (!u || !u.ok) { $("#updOut").textContent = (u && u.error) || "Denetlenemedi"; return; }
  $("#updOut").textContent = u.available ? `Yeni sürüm: v${u.latest}` : (u.note || `NOVA güncel (v${u.current})`);
  showUpdate(u);
};

/* ================= çekmeceler ================= */
function openDrawer(id) {
  $$(".drawer").forEach(d => d.classList.toggle("open", d.id === id));
  document.body.classList.add("drawer-open");
  if (id === "settings") fillForm();
}
function closeDrawers() {
  $$(".drawer").forEach(d => d.classList.remove("open"));
  document.body.classList.remove("drawer-open");
  $("#askInput").focus();
}
$$("[data-open]").forEach(b => b.onclick = () => openDrawer(b.dataset.open));
$$("[data-close]").forEach(b => b.onclick = closeDrawers);

/* ================= ayarlar ================= */
const form = $("#setForm");
function fillForm() {
  const s = info.settings;
  for (const el of form.elements) {
    if (!el.name || !(el.name in s)) continue;
    if (el.type === "checkbox") el.checked = !!s[el.name];
    else if (el.type === "radio") el.checked = s[el.name] === el.value;
    else el.value = s[el.name];
  }
  showRanges();
  showProvider();
}
function showProvider() {
  const p = (form.querySelector("[name=provider]:checked") || {}).value || "gemini";
  $$("[data-prov]", form).forEach(el => el.hidden = !el.dataset.prov.split(" ").includes(p));
}
form.addEventListener("change", e => { if (e.target.name === "provider") showProvider(); });
function showRanges() {
  const r = +form.rate.value;
  $("#rateV").textContent = (r > 0 ? "+" : "") + r + "%";
  $("#sensV").textContent = (+form.sensitivity.value).toFixed(1) + "×";
}
form.addEventListener("input", showRanges);
function readForm() {
  const out = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === "checkbox") out[el.name] = el.checked;
    else if (el.type === "radio") { if (el.checked) out[el.name] = el.value; }
    else out[el.name] = el.value;
  }
  return out;
}
form.onsubmit = async e => {
  e.preventDefault();
  const r = await api.save_settings(readForm());
  info.settings = r.settings; info.ready = r.ready;
  if (r.about) { info.about = r.about; renderAbout(r.about); }
  loadWeather();
  $("#setupNotice").hidden = r.ready;
  showFacts();
  toast("Ayarlar kaydedildi.");
  if (r.ready) closeDrawers();
};
$("#btnTest").onclick = async () => {
  const r0 = await api.save_settings(readForm());
  info.settings = r0.settings;
  $("#testOut").textContent = "Deneniyor…";
  const r = await api.test_brain();
  $("#testOut").textContent = (r.ok ? "✓ " : "✕ ") + r.text;
};
$$("[data-url]").forEach(a => a.onclick = () => api.open_url(a.dataset.url));

function showFacts() {
  const s = info.settings;
  $("#fBrain").textContent = s.provider === "openai" ? "ChatGPT · " + s.openai_model
    : s.provider === "custom" ? "Kendi YZ · " + s.custom_model : "Gemini · " + s.gemini_model;
  const v = (info.voices || []).find(v => v.id === s.voice);
  $("#fVoice").textContent = v ? v.name.split(" (")[0] : s.voice;
}

/* ================= hakkında ================= */
const SOCIAL_ICONS = {
  instagram: ["#ff5fa2", '<rect x="4" y="4" width="16" height="16" rx="5"/><circle cx="12" cy="12" r="3.6"/><circle cx="16.8" cy="7.2" r=".6" fill="currentColor"/>'],
  tiktok: ["#5fe3ff", '<path d="M14 4v10.5a3.5 3.5 0 1 1-3.5-3.5"/><path d="M14 4c.4 2.4 2 4 4.5 4.2"/>'],
  youtube: ["#ff6f61", '<rect x="3" y="6" width="18" height="12" rx="4"/><path d="M10.5 9.5v5l4.2-2.5z" fill="currentColor"/>'],
  github: ["#c9d1e6", '<path d="M8.5 8 4.5 12l4 4M15.5 8l4 4-4 4M13.2 6.5l-2.4 11"/>'],
};
function renderAbout(a) {
  $("#abApp").textContent = a.app;
  $("#abVer").textContent = "Sürüm " + a.version;
  $("#abMaker").textContent = a.maker;
  $("#abRole").textContent = a.role;
  $("#abBio").textContent = a.bio;
  $("#abHandle").textContent = a.handle;
  $("#abCopy").textContent = a.copyright;
  const box = $("#abSocials");
  box.innerHTML = "";
  for (const s of a.socials) {
    const [color, path] = SOCIAL_ICONS[s.id] || ["#9fb0d6", '<circle cx="12" cy="12" r="8"/>'];
    const b = document.createElement("button");
    b.type = "button"; b.className = "social"; b.style.setProperty("--sc", color);
    b.innerHTML = `<span class="si"><svg viewBox="0 0 24 24">${path}</svg></span><span><b></b><small></small></span><span class="go"></span>`;
    b.querySelector("b").textContent = s.name;
    b.querySelector("small").textContent = s.note;
    b.querySelector(".go").textContent = (s.user || a.handle) + " ↗";
    b.onclick = () => api.open_url(s.url);
    box.appendChild(b);
  }
}

/* ================= kontroller ================= */
$("#btnMic").onclick = async () => setMic(await api.toggle_mic());
$("#btnSleep").onclick = () => api.set_awake(state === "sleeping");
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else document.documentElement.requestFullscreen().catch(() => toast("Tam ekran için F11'e bas."));
}
$("#btnFull").onclick = toggleFullscreen;
$("#btnMin").onclick = () => api.minimize();
$("#btnQuit").onclick = () => { api.quit(); setTimeout(() => window.close(), 300); };
$("#core").onclick = () => { if (state === "speaking") api.stop_speaking(); };
$("#ask").onsubmit = e => {
  e.preventDefault();
  const v = $("#askInput").value.trim();
  if (!v) return;
  $("#askInput").value = "";
  audioCtx();
  api.send_text(v);
};
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { if (document.body.classList.contains("drawer-open")) closeDrawers(); else api.stop_speaking(); }
  if (e.key === "F11") { e.preventDefault(); toggleFullscreen(); }
  if ((e.key || "").toLowerCase() === "m" && e.ctrlKey) { e.preventDefault(); $("#btnMic").click(); }
});

/* ================= yıldız gökyüzü ================= */
const sky = $("#sky"), sg = sky.getContext("2d");
let stars = [];
function resizeSky() {
  const dpr = devicePixelRatio || 1;
  sky.width = innerWidth * dpr; sky.height = innerHeight * dpr;
  sg.setTransform(dpr, 0, 0, dpr, 0, 0);
  stars = Array.from({ length: Math.round(innerWidth * innerHeight / 5200) }, () => ({
    x: Math.random() * innerWidth, y: Math.random() * innerHeight,
    r: Math.random() * 1.1 + .2, a: Math.random() * .6 + .15, p: Math.random() * 6.28, v: Math.random() * .06 + .01,
  }));
}
addEventListener("resize", resizeSky); resizeSky();

/* ================= çekirdek ================= */
const core = $("#core"), g = core.getContext("2d");
const RAYS = 120;
const seeds = Array.from({ length: RAYS }, () => Math.random());
let t0 = performance.now(), smooth = 0;
function accent() { return getComputedStyle(document.body).getPropertyValue("--acc").trim() || "#5fe3ff"; }
function hexA(hex, a) {
  const m = hex.match(/^#?([0-9a-f]{6})$/i);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}
let accCache = "", accFrame = 0;

function frame(now) {
  const t = (now - t0) / 1000;
  // gökyüzü
  sg.clearRect(0, 0, innerWidth, innerHeight);
  for (const s of stars) {
    s.y -= s.v; if (s.y < 0) { s.y = innerHeight; s.x = Math.random() * innerWidth; }
    sg.globalAlpha = s.a * (.6 + .4 * Math.sin(t * 1.3 + s.p));
    sg.fillStyle = "#cfd8ff";
    sg.beginPath(); sg.arc(s.x, s.y, s.r, 0, 6.283); sg.fill();
  }
  sg.globalAlpha = 1;

  // çekirdek boyutu
  const dpr = devicePixelRatio || 1;
  const size = core.clientWidth;
  if (core.width !== Math.round(size * dpr)) { core.width = core.height = Math.round(size * dpr); }
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, size, size);
  if (accFrame++ % 15 === 0) accCache = accent();
  const acc = accCache;
  const c = size / 2;
  const R = size * .2;

  let target = 0;
  if (state === "speaking") target = (outLevel = readOutLevel());
  else if (state === "listening" || state === "hearing") target = micLevel;
  else if (state === "thinking") target = .25 + .15 * Math.sin(t * 6);
  smooth += (target - smooth) * .22;
  const sleeping = state === "sleeping";
  const breathe = sleeping ? .5 + .5 * Math.sin(t * .9) : 1;

  // dış halkalar
  g.lineWidth = 1;
  for (let i = 0; i < 3; i++) {
    const rr = R * (1.95 + i * .32);
    const rot = t * (i % 2 ? -.06 : .09) * (sleeping ? .3 : 1);
    g.strokeStyle = hexA(acc, .10 + i * .03);
    g.setLineDash(i === 1 ? [2, 10] : i === 2 ? [40, 14, 4, 14] : []);
    g.beginPath(); g.arc(c, c, rr, rot, rot + 6.283); g.stroke();
  }
  g.setLineDash([]);
  // ölçek çizgileri
  const tickR = R * 1.72;
  for (let i = 0; i < 72; i++) {
    const a = i / 72 * 6.283 + t * .05;
    const long = i % 6 === 0;
    g.strokeStyle = hexA(acc, long ? .45 : .16);
    g.beginPath();
    g.moveTo(c + Math.cos(a) * tickR, c + Math.sin(a) * tickR);
    g.lineTo(c + Math.cos(a) * (tickR + (long ? 9 : 4)), c + Math.sin(a) * (tickR + (long ? 9 : 4)));
    g.stroke();
  }
  // düşünürken dönen yaylar
  if (state === "thinking") {
    g.lineWidth = 2.5; g.strokeStyle = hexA(acc, .85);
    for (let k = 0; k < 3; k++) {
      const a = t * 2.4 + k * 2.094;
      g.beginPath(); g.arc(c, c, R * 1.45, a, a + .7); g.stroke();
    }
  }
  // ışınlar (yıldız patlaması)
  g.lineCap = "round";
  for (let i = 0; i < RAYS; i++) {
    const a = i / RAYS * 6.283;
    const wob = Math.sin(t * 2.2 + seeds[i] * 12) * .5 + .5;
    const spike = i % 30 === 0 ? 1.8 : i % 10 === 0 ? 1.25 : 1;
    const len = (R * .12 + R * .55 * smooth * (0.45 + wob * .9)) * spike * (sleeping ? .35 : 1);
    const r0 = R * 1.08;
    g.strokeStyle = hexA(acc, (.25 + .6 * smooth * wob) * breathe + .05);
    g.lineWidth = spike > 1.5 ? 2 : 1.2;
    g.beginPath();
    g.moveTo(c + Math.cos(a) * r0, c + Math.sin(a) * r0);
    g.lineTo(c + Math.cos(a) * (r0 + len), c + Math.sin(a) * (r0 + len));
    g.stroke();
  }
  // parıltı
  const glowR = R * (1.6 + smooth * .5);
  const glow = g.createRadialGradient(c, c, R * .2, c, c, glowR);
  glow.addColorStop(0, hexA(acc, .55 * breathe));
  glow.addColorStop(.5, hexA(acc, .12 * breathe));
  glow.addColorStop(1, hexA(acc, 0));
  g.fillStyle = glow; g.beginPath(); g.arc(c, c, glowR, 0, 6.283); g.fill();
  // çekirdek küre
  const pr = R * (.86 + smooth * .12);
  const body = g.createRadialGradient(c - pr * .3, c - pr * .35, pr * .1, c, c, pr);
  body.addColorStop(0, "#ffffff");
  body.addColorStop(.35, hexA(acc, .95));
  body.addColorStop(1, hexA(acc, .15));
  g.globalAlpha = sleeping ? .45 + .25 * breathe : 1;
  g.fillStyle = body; g.beginPath(); g.arc(c, c, pr, 0, 6.283); g.fill();
  g.globalAlpha = 1;
  // iç halka
  g.strokeStyle = "rgba(255,255,255,.35)"; g.lineWidth = 1;
  g.beginPath(); g.arc(c, c, pr * 1.06, 0, 6.283); g.stroke();
  // dört köşeli yıldız parlaması
  g.fillStyle = `rgba(255,255,255,${.55 * breathe})`;
  const f = pr * (1.5 + smooth * .8);
  g.beginPath();
  g.moveTo(c, c - f); g.quadraticCurveTo(c, c, c + f, c); g.quadraticCurveTo(c, c, c, c + f);
  g.quadraticCurveTo(c, c, c - f, c); g.quadraticCurveTo(c, c, c, c - f); g.fill();

  micLevel *= .92;
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

/* ================= başlat ================= */
whenReady().then(async a => {
  api = a;
  info = await api.init();
  $("#ver").textContent = "Kişisel asistan · v" + info.version;
  const sel = $("#voiceSel");
  sel.innerHTML = "";
  for (const v of info.voices) sel.add(new Option(v.name, v.id));
  renderAbout(info.about);
  showFacts();
  setMic(info.mic);
  setState(info.awake ? (info.mic ? "listening" : "idle") : "sleeping");
  if (!info.ready) $("#setupNotice").hidden = false;
  timers = info.timers || []; renderTimers();
  if (info.update) showUpdate(info.update);
  let tab = "news"; try { tab = localStorage.getItem("nova.tab") || "news"; } catch (e) {}
  selectTab(tab);
  calEvents = await api.cal_list() || []; renderCal();
  loadWeather(); loadRates();
  setInterval(loadWeather, 15 * 60 * 1000);
  setInterval(loadRates, 10 * 60 * 1000);
  setInterval(() => { if (activeTab === "news") loadNews(newsCat); }, 10 * 60 * 1000);
  $("#askInput").focus();
});

/* ================= tarayıcıda önizleme (?demo) ================= */
function demoApi() {
  const settings = { user_name: "Samet", provider: "gemini", custom_url: "http://localhost:11434/v1", custom_key: "", custom_model: "llama3.1",
    instagram_user: "xsametsahinx", tiktok_user: "xsametsahinx", youtube_user: "xsametsahinx", github_user: "pepsicosamet-arch", gemini_key: "", gemini_model: "gemini-3.8-flash",
    openai_key: "", openai_model: "gpt-4o-mini", web_search: true, voice: "tr-TR-AhmetNeural", rate: 0, speak: true,
    continuous: true, sensitivity: 1, language: "tr-TR", city: "İstanbul", fullscreen: true,
    wake_words: "nova, uyan", sleep_words: "uyu, uyku moduna geç, beklemeye geç" };
  const about = {"app":"NOVA","version":"1.3.0","maker":"Samet Şahin","role":"NOVA'yı tasarlayan ve geliştiren kişi","bio":"NOVA'yı sıfırdan tasarlayıp geliştirdim. Yeni özellikleri, geliştirme sürecini ve perde arkasını sosyal medya hesaplarımda paylaşıyorum.","handle":"@xsametsahinx","socials":[{"id":"instagram","name":"Instagram","url":"https://www.instagram.com/xsametsahinx/","note":"Yeni özellikler ve perde arkası"},{"id":"tiktok","name":"TikTok","url":"https://www.tiktok.com/@xsametsahinx","note":"Kısa videolar ve denemeler"},{"id":"youtube","name":"YouTube","url":"https://www.youtube.com/@xsametsahinx","note":"Uzun videolar ve anlatımlar"},{"id":"github","name":"GitHub","url":"https://github.com/xsametsahinx","note":"Projeler ve kaynak kod"}],"copyright":"© 2026 Samet Şahin. Tüm hakları saklıdır."};
  let mic = true;
  setInterval(() => { if (state === "listening") micLevel = Math.max(micLevel, Math.random() ** 3); }, 120);
  setTimeout(() => window.novaEvent({ type: "stats", cpu: 18, ram: 46, battery: 82, plugged: true }), 300);
  return {
    init: async () => ({ app: "NOVA", version: "1.3.0", about, settings, voices: [{ id: "tr-TR-AhmetNeural", name: "Ahmet (Türkçe, erkek)" }, { id: "tr-TR-EmelNeural", name: "Emel (Türkçe, kadın)" }], state: "listening", awake: true, mic, ready: true, timers: [{ id: 1, label: "Çay", end: Date.now() + 540000 }], update: { available: true, latest: "1.3.1" } }),
    send_text: async t => { addMsg("user", t); setState("thinking"); setTimeout(() => { addMsg("nova", "Bu bir önizleme. Gerçek uygulamada yanıtı Gemini ya da ChatGPT verir."); setState("listening"); }, 1200); },
    speech_done: async () => {}, stop_speaking: async () => {}, cancel_timer: async () => {},
    toggle_mic: async () => (mic = !mic), set_awake: async a => setState(a ? "listening" : "sleeping"),
    save_settings: async v => ({ settings: Object.assign(settings, v), ready: true }),
    test_brain: async () => ({ ok: true, text: "Önizleme modu." }),
    open_url: async u => window.open(u, "_blank"), minimize: async () => {}, quit: async () => {}, log_js: async () => {},
    get_news: async c => ({ ok: true, items: [
      { title: "Merkez Bankası faiz kararını açıkladı", source: "NTV", ts: Date.now() / 1000 - 900, link: "#" },
      { title: "Yeni nesil yapay zekâ modelleri tanıtıldı", source: "TRT Haber", ts: Date.now() / 1000 - 3600, link: "#" },
      { title: "Meteoroloji'den Ege için sağanak uyarısı", source: "NTV", ts: Date.now() / 1000 - 7200, link: "#" },
      { title: "Milli takımın aday kadrosu belli oldu", source: "TRT Haber", ts: Date.now() / 1000 - 11000, link: "#" },
      { title: "Uzay teleskobundan yeni galaksi görüntüleri", source: "BBC Türkçe", ts: Date.now() / 1000 - 20000, link: "#" }] }),
    read_news: async () => true,
    get_weather: async () => ({ ok: true, city: "Manisa", temp: 17, feels: 15, desc: "Parçalı bulutlu", icon: "⛅", wind: 12,
      days: [["Bugün","⛅",19,9],["Çar","🌦",17,10],["Per","☀",21,8],["Cum","☀",22,9],["Cmt","🌧",16,11]].map(([day, icon, max, min]) => ({ day, icon, max, min })) }),
    get_rates: async () => ({ ok: true, time: "03:20", rates: { USD: 41.92, EUR: 48.35, GBP: 55.1, ALTIN: 5612.4 } }),
    geocode: async q => null,
    cal_list: async () => [{ id: "a", title: "Dişçi randevusu", date: isoDate(new Date()), time: "15:30" }, { id: "b", title: "Toplantı", date: isoDate(new Date(Date.now() + 2 * 864e5)), time: "09:00" }],
    cal_add: async e => ({ ok: true, events: [...calEvents, { ...e, id: String(Math.random()) }] }),
    cal_delete: async id => calEvents.filter(e => e.id !== id),
    add_timer: async () => true, add_alarm: async (t, l) => "Alarm kuruldu",
    notes_list: async () => [{ time: "03.11.2026 02:10", text: "Markete git" }], note_add: async t => [{ time: "", text: t }], note_delete: async () => [],
    check_update: async () => ({ ok: true, available: true, latest: "1.3.1", current: "1.3.0" }), install_update: async () => ({ ok: true }),
  };
}
})();
