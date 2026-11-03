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
      src.buffer = buf; connectFx(ctx, src, ev.fx);
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
/* Çip ses efektleri: "ai" (yapay zekâ tınısı), "soft" (parlak), "dark" (metalik, karanlık) */
function connectFx(ctx, src, fx) {
  if (!fx || fx === "none") { src.connect(analyser); return; }
  const out = ctx.createGain(); out.connect(analyser);
  const dry = ctx.createGain(); dry.gain.value = fx === "dark" ? .75 : .9;
  const delay = (ms, gain, from = src) => {
    const d = ctx.createDelay(.1); d.delayTime.value = ms / 1000;
    const g = ctx.createGain(); g.gain.value = gain;
    from.connect(d); d.connect(g); g.connect(out); return d;
  };
  if (fx === "ai") {
    const hp = ctx.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 110;
    const pk = ctx.createBiquadFilter(); pk.type = "peaking"; pk.frequency.value = 2600; pk.Q.value = 1.2; pk.gain.value = 4;
    src.connect(hp); hp.connect(pk); pk.connect(dry); dry.connect(out);
    delay(14, .28, pk); delay(31, .14, pk);           // hafif "dijital" çift ses
  } else if (fx === "soft") {
    const hs = ctx.createBiquadFilter(); hs.type = "highshelf"; hs.frequency.value = 4500; hs.gain.value = 4;
    src.connect(hs); hs.connect(dry); dry.connect(out);
    delay(9, .16, hs);
  } else if (fx === "dark") {
    const ws = ctx.createWaveShaper(); const curve = new Float32Array(1024);
    for (let i = 0; i < 1024; i++) { const x = i / 512 - 1; curve[i] = Math.tanh(x * 2.4) * .9; }
    ws.curve = curve; ws.oversample = "2x";
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 3800;
    const ring = ctx.createGain(); const osc = ctx.createOscillator(); osc.frequency.value = 38; osc.type = "sine";
    const depth = ctx.createGain(); depth.gain.value = .35; osc.connect(depth); depth.connect(ring.gain); osc.start();
    src.connect(ws); ws.connect(lp); lp.connect(dry); dry.connect(out);
    lp.connect(ring); ring.connect(out);                // metalik titreşim
    delay(22, .3, lp); delay(47, .18, lp);
    src.addEventListener("ended", () => { try { osc.stop(); } catch (e) {} });
  } else { src.connect(analyser); }
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
    case "chip": applyChip(ev.chip, ev.chips); break;
    case "msg_preview": showMsgPreview(ev); break;
    case "camera":
      if (ev.action === "open") camOpen();
      else if (ev.action === "close") camStop();
      else if (ev.action === "photo") camPhoto();
      else if (ev.action === "ask") camAsk(ev.question);
      break;
    case "msg_sent": toast((ev.ok ? "✓ " : "✕ ") + (PLAT_NAME[ev.platform] || "") + (ev.to ? " · " + ev.to : "")); break;
    case "news_show": showBulletin(ev); break;
    case "news_focus": bulletinFocus(ev.index); break;
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
  const b2 = $("#timerBadge2"); if (b2) { b2.hidden = !timers.length; b2.textContent = timers.length; }
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
  if (name === "messages") loadContacts();
  if (name === "phone") loadPhone();
  if (name !== "camera" && camStream) camStop();
  $$("#menubar [data-menu]").forEach(b => b.classList.toggle("on", b.dataset.menu === name));
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
$("#newsShow").onclick = async () => {
  const d = await api.get_news(newsCat);
  if (d && d.items && d.items.length) showBulletin({ category: newsCat, name: d.name, items: d.items.slice(0, 12) });
};

/* ---------- haber bülteni (ekranda büyük sunum) ---------- */
let bl = { items: [], i: 0, cat: "gundem", reading: false, timer: null };
const BL_STEP = 9000;
function showBulletin(ev) {
  bl.items = ev.items || []; bl.cat = ev.category || "gundem"; bl.i = 0; bl.reading = false;
  if (!bl.items.length) return;
  $("#blName").textContent = ev.name || "Gündem";
  $$("#blCats button").forEach(b => b.classList.toggle("on", b.dataset.cat === bl.cat));
  const list = $("#blList"); list.innerHTML = "";
  bl.items.slice(0, 6).forEach((n, k) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="n">${String(k + 1).padStart(2, "0")}</span><span><span class="t"></span><span class="s"></span></span>`;
    li.querySelector(".t").textContent = n.title;
    li.querySelector(".s").textContent = `${n.source} · ${ago(n.ts)}`;
    li.onclick = () => { bl.reading = false; blShow(k); };
    list.appendChild(li);
  });
  document.body.classList.add("bulletin-on");
  blShow(0);
}
function blShow(k) {
  if (!bl.items.length) return;
  bl.i = (k + bl.items.length) % bl.items.length;
  const n = bl.items[bl.i];
  $("#blTitle").textContent = n.title;
  $("#blDesc").textContent = n.desc || "";
  $("#blMeta").textContent = `${n.source} · ${ago(n.ts)}`;
  $("#blMark").textContent = n.img ? "" : (n.source || "").toUpperCase();
  const img = $("#blImg");
  img.querySelectorAll(".kb").forEach(e => e.remove());
  if (n.img) { const kb = document.createElement("div"); kb.className = "kb"; kb.style.backgroundImage = `url("${n.img.replace(/"/g, "%22")}")`; img.prepend(kb); }
  let num = $("#blHero .bl-num"); if (!num) { num = document.createElement("span"); num.className = "bl-num"; $("#blHero").appendChild(num); }
  num.textContent = String(bl.i + 1).padStart(2, "0");
  const hero = $("#blHero"); hero.classList.remove("swap"); void hero.offsetWidth; hero.classList.add("swap");
  $$("#blList li").forEach((li, j) => li.classList.toggle("on", j === bl.i));
  const prog = $("#blProg");
  prog.classList.remove("run"); prog.style.width = "0";
  clearTimeout(bl.timer);
  if (!bl.reading) {                            // okunmuyorsa kendiliğinden ilerle
    requestAnimationFrame(() => { prog.style.transitionDuration = BL_STEP + "ms"; prog.classList.add("run"); prog.style.width = "100%"; });
    bl.timer = setTimeout(() => blShow(bl.i + 1), BL_STEP);
  }
}
function bulletinFocus(idx) {
  if (idx < 0) { bl.reading = false; blShow(bl.i); return; }
  if (!document.body.classList.contains("bulletin-on")) return;
  bl.reading = true; blShow(idx);
}
function closeBulletin() { document.body.classList.remove("bulletin-on"); clearTimeout(bl.timer); }
$("#blClose").onclick = closeBulletin;
$("#blPrev").onclick = () => { bl.reading = false; blShow(bl.i - 1); };
$("#blNext").onclick = () => { bl.reading = false; blShow(bl.i + 1); };
$("#blRead").onclick = () => { audioCtx(); api.read_news(bl.cat); };
$("#blHero").onclick = e => {
  const sh = e.target.closest("[data-share]");
  const n = bl.items[bl.i]; if (!n) return;
  if (sh) { e.stopPropagation(); api.share(sh.dataset.share, n.title, n.link); return; }
  api.open_url(n.link);
};
async function openBrief(cat = "gundem") {
  const d = await api.get_news(cat);
  if (d && d.items && d.items.length) showBulletin({ category: cat, name: d.name, items: d.items.slice(0, 12) });
  else toast("Haberlere şu an ulaşılamadı.");
}
$$("#blCats button").forEach(b => b.onclick = () => { bl.reading = false; openBrief(b.dataset.cat); });

/* ---------- üst menü ---------- */
$$("#menubar [data-menu]").forEach(b => b.onclick = () => {
  const m = b.dataset.menu;
  if (m === "brief") { document.body.classList.contains("bulletin-on") && bl.cat === "gundem" ? closeBulletin() : openBrief("gundem"); return; }
  closeBulletin();
  document.body.classList.add("dock-open");
  selectTab(m);
});

/* ---------- mesajlaşma ---------- */
let contacts = [];
const PLAT_COLOR = { whatsapp: "#25d366", telegram: "#2aabee", x: "#e7e9ea" };
const PLAT_NAME = { whatsapp: "WhatsApp", telegram: "Telegram", x: "X" };
function msgPlat() { return (document.querySelector("[name=mplat]:checked") || {}).value || "whatsapp"; }
let apps = {};
async function loadContacts() {
  apps = await api.apps() || {};
  const names = { whatsapp: "WhatsApp", telegram: "Telegram", x: "X" };
  $("#appsInfo").textContent = "Bu bilgisayarda: " + Object.keys(names).map(k => `${names[k]} ${apps[k] ? "uygulaması ✓" : "(web)"}`).join(" · ");
  msgPlatChanged();
}
function msgPlatChanged() {
  const p = msgPlat();
  $("#msgTo").hidden = p === "x";
  $("#msgBtn").textContent = p === "x" ? "Paylaş" : "Gönder";
  const where = apps[p] ? "PC uygulaması ✓" : (p === "x" ? "tarayıcıda X" : "web sürümü");
  const auto = info && info.settings.msg_auto_send;
  $("#msgHint").textContent = where + " · " + (p === "x" ? (auto ? "otomatik paylaşır" : "gönderi hazır açılır") : (auto ? "otomatik gönderir" : "sohbet hazır açılır"));
}
$$("[name=mplat]").forEach(r => r.onchange = msgPlatChanged);
$("#msgForm").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, text = f.text.value.trim();
  if (!text) return;
  const r = await api.msg_send(msgPlat(), f.to.value, text);
  toast(r ? r.text : "Gönderilemedi.", r && r.ok ? "" : "error");
  if (r && r.ok) f.text.value = "";
};
function showMsgPreview(ev) {
  const card = $("#msgCard");
  if (ev.hide) { card.hidden = true; return; }
  $("#mcPlat").textContent = (ev.platform_name || PLAT_NAME[ev.platform] || "").toUpperCase();
  $("#mcPlat").style.setProperty("--pc", PLAT_COLOR[ev.platform] || "var(--acc)");
  $("#mcTo").textContent = ev.to ? ev.to + " kişisine" : (ev.platform === "x" ? "Herkese açık gönderi" : "");
  $("#mcText").textContent = ev.text;
  card.hidden = false;
}
$("#mcYes").onclick = () => { $("#msgCard").hidden = true; api.msg_confirm(true); };
$("#mcNo").onclick = () => { $("#msgCard").hidden = true; api.msg_confirm(false); };

/* ---------- kamera ---------- */
let camStream = null, camMirror = true;
async function camStart(deviceId) {
  if (camStream) return true;
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: deviceId ? { deviceId: { exact: deviceId } } : { width: { ideal: 1280 } }, audio: false });
    const v = $("#camVideo"); v.srcObject = camStream; v.classList.toggle("mirror", camMirror);
    $("#camMsg").hidden = true; $("#camToggle").textContent = "■ Kamerayı kapat";
    const devs = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "videoinput");
    const sel = $("#camSel"); sel.hidden = devs.length < 2; sel.innerHTML = "";
    devs.forEach((d, i) => sel.add(new Option(d.label || "Kamera " + (i + 1), d.deviceId)));
    return true;
  } catch (e) {
    $("#camMsg").hidden = false;
    $("#camMsg").textContent = e.name === "NotAllowedError" ? "Kamera izni verilmedi. Adres çubuğundaki kamera simgesinden izin ver." : "Kamera bulunamadı ya da başka bir uygulama kullanıyor.";
    return false;
  }
}
function camStop() {
  if (camStream) camStream.getTracks().forEach(t => t.stop());
  camStream = null; $("#camVideo").srcObject = null;
  $("#camMsg").hidden = false; $("#camMsg").textContent = "Kamera kapalı."; $("#camToggle").textContent = "▶ Kamerayı aç";
}
function camFrame() {
  const v = $("#camVideo"), c = $("#camCanvas");
  if (!v.videoWidth) return null;
  const w = Math.min(1280, v.videoWidth), h = Math.round(v.videoHeight * w / v.videoWidth);
  c.width = w; c.height = h;
  const g2 = c.getContext("2d");
  if (camMirror) { g2.translate(w, 0); g2.scale(-1, 1); }
  g2.drawImage(v, 0, 0, w, h);
  return c.toDataURL("image/png");
}
async function camOpen() { document.body.classList.add("dock-open"); selectTab("camera"); return camStart(); }
async function camPhoto() {
  if (!await camOpen()) return;
  await new Promise(r => setTimeout(r, camStream && $("#camVideo").videoWidth ? 50 : 1200));
  const d = camFrame(); if (!d) return toast("Görüntü alınamadı.");
  const f = $("#camFlash"); f.classList.add("on"); setTimeout(() => f.classList.remove("on"), 60);
  const r = await api.save_photo(d); toast(r && r.ok ? "📸 Kaydedildi: Resimler\\NOVA" : "Kaydedilemedi.");
}
async function camAsk(q) {
  if (!await camOpen()) return;
  await new Promise(r => setTimeout(r, $("#camVideo").videoWidth ? 50 : 1500));
  const d = camFrame(); if (!d) return toast("Görüntü alınamadı.");
  api.camera_vision(d, q || "");
}
$("#camToggle").onclick = () => camStream ? camStop() : camStart();
$("#camShot").onclick = camPhoto;
$("#camAsk").onclick = () => camAsk("");
$("#camMirror").onclick = () => { camMirror = !camMirror; $("#camVideo").classList.toggle("mirror", camMirror); };
$("#camSel").onchange = e => { camStop(); camStart(e.target.value); };

/* ---------- telefon ---------- */
function showPhone(i) {
  if (!i) return;
  $("#phoneOn").checked = !!i.enabled;
  $("#qrBox").innerHTML = i.enabled && i.svg ? i.svg : '<p class="empty">Telefon bağlantısı kapalı. Açınca burada QR kod çıkar.</p>';
  $("#phoneUrl").textContent = i.enabled ? i.url.split("#")[0] : "";
}
async function loadPhone() { showPhone(await api.phone_info()); }
$("#phoneOn").onchange = async e => showPhone(await api.phone_toggle(e.target.checked));
$("#phoneReset").onclick = async () => { showPhone(await api.phone_reset()); toast("Yeni QR oluşturuldu; eski bağlantılar geçersiz."); };
$("#phoneLink").onclick = () => api.send_text("telefon bağlantısı uygulamasını aç");

/* ---------- canlı TV ---------- */
function renderTv(list) {
  const box = $("#tvGrid"); if (!box) return;
  box.innerHTML = "";
  const groups = [...new Set(list.map(c => c.group))];
  for (const g of groups) {
    const h = document.createElement("h3"); h.textContent = g; box.appendChild(h);
    const grid = document.createElement("div"); grid.className = "tv-grid";
    for (const c of list.filter(x => x.group === g)) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "tv-card"; b.style.setProperty("--tc", c.color);
      b.innerHTML = '<span class="tv-live">● CANLI</span><b></b>';
      b.querySelector("b").textContent = c.name;
      b.onclick = async () => { const r = await api.tv_open(c.id); toast(r && r.ok ? `📺 ${r.name} açılıyor` : "Kanal açılamadı.", r && r.ok ? "" : "error"); };
      grid.appendChild(b);
    }
    box.appendChild(grid);
  }
}

/* ---------- çipler ---------- */
let chipId = "nova", chipList = [];
const CHIP_COLORS = { nova: "#5fe3ff", atlas: "#ffc35c", lyra: "#ff8ac0", kronos: "#ff4d4d" };
function applyChip(chip, list) {
  if (!chip) return;
  chipId = chip.id; if (list) chipList = list;
  document.body.dataset.chip = chip.id;
  $("#brandName").textContent = chip.name;
  document.title = chip.name;
  accFrame = 0;
  renderChips();
  if (info) showFacts();
}
function renderChips() {
  const box = $("#chipGrid"); if (!box) return;
  box.innerHTML = "";
  for (const c of chipList) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip-card" + (c.id === chipId ? " on" : "");
    b.style.setProperty("--cc", CHIP_COLORS[c.id] || "#9fb0d6");
    b.innerHTML = `<span class="on-badge">AKTİF</span><canvas data-chip="${c.id}"></canvas><b></b><small></small>`;
    b.querySelector("b").textContent = c.name;
    b.querySelector("small").textContent = c.tagline;
    b.onclick = async () => { audioCtx(); const r = await api.set_chip(c.id); if (r) applyChip(r.chip, r.chips); };
    box.appendChild(b);
  }
}

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
  document.body.classList.toggle("no-transcript", !info.settings.show_transcript);
  if (r.chips) { chipList = r.chips; const c = r.chips.find(x => x.id === chipId); if (c) applyChip({ ...c }, r.chips); }
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
  $("#fVoice").textContent = s.chip_voice ? ($("#brandName").textContent + " sesi") : (v ? v.name.split(" (")[0] : s.voice);
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
$("#btnBg").onclick = () => { toast("Arka plana geçiyorum, dinlemeye devam ediyorum."); setTimeout(() => api.hide(), 600); };
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
  if (e.key === "Escape" && document.body.classList.contains("bulletin-on")) { closeBulletin(); return; }
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

/* ======== çip tasarımları: her biri kendi çekirdeğini çizer ======== */
const DRAW = {
  /* NOVA — yıldız çekirdek */
  nova(g, c, R, t, lv, st, acc, br, mini) {
    const sleeping = st === "sleeping";
    g.lineWidth = 1;
    for (let i = 0; i < 3; i++) {
      const rr = R * (1.95 + i * .32), rot = t * (i % 2 ? -.06 : .09) * (sleeping ? .3 : 1);
      g.strokeStyle = hexA(acc, .10 + i * .03);
      g.setLineDash(i === 1 ? [2, 10] : i === 2 ? [40, 14, 4, 14] : []);
      g.beginPath(); g.arc(c, c, rr, rot, rot + 6.283); g.stroke();
    }
    g.setLineDash([]);
    if (!mini) {
      const tickR = R * 1.72;
      for (let i = 0; i < 72; i++) {
        const a = i / 72 * 6.283 + t * .05, long = i % 6 === 0;
        g.strokeStyle = hexA(acc, long ? .45 : .16); g.beginPath();
        g.moveTo(c + Math.cos(a) * tickR, c + Math.sin(a) * tickR);
        g.lineTo(c + Math.cos(a) * (tickR + (long ? 9 : 4)), c + Math.sin(a) * (tickR + (long ? 9 : 4))); g.stroke();
      }
    }
    if (st === "thinking") {
      g.lineWidth = 2.5; g.strokeStyle = hexA(acc, .85);
      for (let k = 0; k < 3; k++) { const a = t * 2.4 + k * 2.094; g.beginPath(); g.arc(c, c, R * 1.45, a, a + .7); g.stroke(); }
    }
    g.lineCap = "round";
    for (let i = 0; i < RAYS; i += mini ? 2 : 1) {
      const a = i / RAYS * 6.283, wob = Math.sin(t * 2.2 + seeds[i] * 12) * .5 + .5;
      const spike = i % 30 === 0 ? 1.8 : i % 10 === 0 ? 1.25 : 1;
      const len = (R * .12 + R * .55 * lv * (0.45 + wob * .9)) * spike * (sleeping ? .35 : 1), r0 = R * 1.08;
      g.strokeStyle = hexA(acc, (.25 + .6 * lv * wob) * br + .05); g.lineWidth = spike > 1.5 ? 2 : 1.2;
      g.beginPath(); g.moveTo(c + Math.cos(a) * r0, c + Math.sin(a) * r0);
      g.lineTo(c + Math.cos(a) * (r0 + len), c + Math.sin(a) * (r0 + len)); g.stroke();
    }
    glowAndOrb(g, c, R, lv, acc, br, sleeping);
    g.fillStyle = `rgba(255,255,255,${.55 * br})`;
    const f = R * (.86 + lv * .12) * (1.5 + lv * .8);
    g.beginPath(); g.moveTo(c, c - f); g.quadraticCurveTo(c, c, c + f, c); g.quadraticCurveTo(c, c, c, c + f);
    g.quadraticCurveTo(c, c, c - f, c); g.quadraticCurveTo(c, c, c, c - f); g.fill();
  },

  /* ATLAS — dönen tel kafes küre ve yörünge halkaları */
  atlas(g, c, R, t, lv, st, acc, br, mini) {
    const sleeping = st === "sleeping", sp = sleeping ? .25 : 1;
    // yörünge halkaları (parçalı yaylar)
    const rings = [[1.75, .35, 6], [2.05, -.22, 3], [2.35, .12, 9]];
    rings.forEach(([rr, speed, seg], k) => {
      g.lineWidth = k === 0 ? 2.2 : 1.2; g.strokeStyle = hexA(acc, (k === 0 ? .55 : .25) * br);
      for (let i = 0; i < seg; i++) {
        const a = t * speed * sp + i / seg * 6.283, len = 6.283 / seg * (k === 0 ? .55 : .7);
        g.beginPath(); g.arc(c, c, R * rr * (1 + lv * .05), a, a + len); g.stroke();
      }
    });
    // ekolayzır çubukları
    if (!mini || true) {
      const n = mini ? 48 : 96, r0 = R * 1.25;
      for (let i = 0; i < n; i++) {
        const a = i / n * 6.283 - t * .1 * sp;
        const h = R * (.04 + lv * .32 * (.5 + .5 * Math.sin(i * 1.7 + t * 6)));
        g.strokeStyle = hexA(acc, .35 + lv * .5); g.lineWidth = mini ? 1.4 : 2.2;
        g.beginPath(); g.moveTo(c + Math.cos(a) * r0, c + Math.sin(a) * r0);
        g.lineTo(c + Math.cos(a) * (r0 + h), c + Math.sin(a) * (r0 + h)); g.stroke();
      }
    }
    // tel kafes küre
    const r = R * (.95 + lv * .08), rot = t * .45 * sp;
    const bodyG = g.createRadialGradient(c - r * .3, c - r * .3, r * .1, c, c, r);
    bodyG.addColorStop(0, hexA(acc, .35 * br)); bodyG.addColorStop(1, hexA(acc, .04));
    g.fillStyle = bodyG; g.beginPath(); g.arc(c, c, r, 0, 6.283); g.fill();
    g.lineWidth = 1; g.strokeStyle = hexA(acc, .7 * br);
    for (let m = 0; m < 8; m++) {                   // boylamlar
      const ph = rot + m / 8 * Math.PI, rx = Math.abs(Math.cos(ph)) * r;
      g.globalAlpha = Math.sin(ph) > 0 ? 1 : .35;
      g.beginPath(); g.ellipse(c, c, Math.max(rx, .5), r, 0, 0, 6.283); g.stroke();
    }
    g.globalAlpha = 1;
    for (let l = -2; l <= 2; l++) {                 // enlemler
      const y = c + l * r / 3, w = Math.sqrt(Math.max(0, r * r - (l * r / 3) ** 2));
      g.beginPath(); g.ellipse(c, y, w, w * .22, 0, 0, 6.283); g.stroke();
    }
    g.strokeStyle = hexA(acc, .9 * br); g.lineWidth = 1.6; g.beginPath(); g.arc(c, c, r, 0, 6.283); g.stroke();
    // merkez ışık
    const glow = g.createRadialGradient(c, c, 0, c, c, R * (1.7 + lv));
    glow.addColorStop(0, hexA(acc, .35 * br)); glow.addColorStop(1, hexA(acc, 0));
    g.fillStyle = glow; g.beginPath(); g.arc(c, c, R * (1.7 + lv), 0, 6.283); g.fill();
    g.fillStyle = `rgba(255,248,230,${.9 * br})`; g.beginPath(); g.arc(c, c, R * (.08 + lv * .06), 0, 6.283); g.fill();
    if (st === "thinking") {
      g.strokeStyle = hexA(acc, .9); g.lineWidth = 3;
      const a = t * 3; g.beginPath(); g.arc(c, c, R * 1.5, a, a + 1.2); g.stroke();
      g.beginPath(); g.arc(c, c, R * 1.5, a + 3.14, a + 4.34); g.stroke();
    }
  },

  /* LYRA — ses dalgası çiçeği */
  lyra(g, c, R, t, lv, st, acc, br, mini) {
    const sleeping = st === "sleeping", sp = sleeping ? .3 : 1;
    // yayılan dalga halkaları
    for (let k = 0; k < 4; k++) {
      const ph = ((t * .35 * sp + k / 4) % 1), rr = R * (1.2 + ph * 1.4);
      g.strokeStyle = hexA(acc, (1 - ph) * .35 * br); g.lineWidth = 1.5;
      g.beginPath(); g.arc(c, c, rr, 0, 6.283); g.stroke();
    }
    // taç yapraklar: üst üste binen gül eğrileri
    const layers = [[5, .0, .55], [7, 1.3, .4], [9, 2.6, .28]];
    g.globalCompositeOperation = "lighter";
    layers.forEach(([k, off, alpha], li) => {
      g.beginPath();
      for (let i = 0; i <= 240; i++) {
        const a = i / 240 * 6.283;
        const amp = .22 + lv * .45 + (sleeping ? -.1 : 0);
        const rr = R * (1.0 + amp * Math.sin(k * a + t * (1.2 + li * .4) * sp + off));
        const x = c + Math.cos(a) * rr, y = c + Math.sin(a) * rr;
        i ? g.lineTo(x, y) : g.moveTo(x, y);
      }
      g.closePath();
      g.fillStyle = hexA(acc, alpha * .35 * br); g.fill();
      g.strokeStyle = hexA(acc, alpha * br); g.lineWidth = 1.3; g.stroke();
    });
    g.globalCompositeOperation = "source-over";
    // yumuşak çekirdek
    const r = R * (.42 + lv * .12);
    const body = g.createRadialGradient(c, c, 0, c, c, r * 2.2);
    body.addColorStop(0, `rgba(255,255,255,${.95 * br})`); body.addColorStop(.35, hexA(acc, .7 * br)); body.addColorStop(1, hexA(acc, 0));
    g.fillStyle = body; g.beginPath(); g.arc(c, c, r * 2.2, 0, 6.283); g.fill();
    if (st === "thinking") {
      for (let k = 0; k < 6; k++) {
        const a = t * 2 + k * 1.047; g.fillStyle = hexA(acc, .9);
        g.beginPath(); g.arc(c + Math.cos(a) * R * 1.55, c + Math.sin(a) * R * 1.55, 3.2, 0, 6.283); g.fill();
      }
    }
  },

  /* KRONOS — kırık prizma, keskin çokgenler */
  kronos(g, c, R, t, lv, st, acc, br, mini) {
    const sleeping = st === "sleeping", sp = sleeping ? .2 : 1;
    const poly = (n, r, rot, stroke, w, fill) => {
      g.beginPath();
      for (let i = 0; i <= n; i++) { const a = rot + i / n * 6.283; const x = c + Math.cos(a) * r, y = c + Math.sin(a) * r; i ? g.lineTo(x, y) : g.moveTo(x, y); }
      g.closePath(); if (fill) { g.fillStyle = fill; g.fill(); } g.strokeStyle = stroke; g.lineWidth = w; g.stroke();
    };
    // dış altıgenler
    poly(6, R * 2.3, t * .08 * sp, hexA(acc, .18 * br), 1);
    poly(6, R * 2.05, -t * .12 * sp + .52, hexA(acc, .28 * br), 1.2);
    // testere dişli kenar
    const n = mini ? 36 : 72;
    g.beginPath();
    for (let i = 0; i <= n; i++) {
      const a = i / n * 6.283 + t * .2 * sp;
      const glitch = st === "speaking" ? (seeds[i % RAYS] - .5) * lv * .5 : 0;
      const rr = R * (i % 2 ? 1.35 : 1.6 + lv * .7 + glitch);
      const x = c + Math.cos(a) * rr, y = c + Math.sin(a) * rr; i ? g.lineTo(x, y) : g.moveTo(x, y);
    }
    g.closePath(); g.fillStyle = hexA(acc, .07 * br); g.fill(); g.strokeStyle = hexA(acc, .65 * br); g.lineWidth = 1.2; g.stroke();
    // iç üçgenler
    poly(3, R * (1.12 + lv * .1), t * .5 * sp, hexA(acc, .85 * br), 2);
    poly(3, R * (1.12 + lv * .1), -t * .5 * sp + Math.PI, hexA(acc, .5 * br), 1.4);
    // kırık prizma çekirdek
    const r = R * (.55 + lv * .12);
    const body = g.createLinearGradient(c - r, c - r, c + r, c + r);
    body.addColorStop(0, hexA(acc, .95 * br)); body.addColorStop(1, hexA(acc, .25 * br));
    g.beginPath(); g.moveTo(c, c - r); g.lineTo(c + r * .7, c); g.lineTo(c, c + r); g.lineTo(c - r * .7, c); g.closePath();
    g.fillStyle = body; g.fill();
    g.strokeStyle = `rgba(255,235,230,${.7 * br})`; g.lineWidth = 1;
    g.beginPath(); g.moveTo(c - r * .35, c - r * .5); g.lineTo(c + r * .1, c + r * .05); g.lineTo(c - r * .05, c + r * .6); g.stroke();
    g.beginPath(); g.moveTo(c + r * .1, c + r * .05); g.lineTo(c + r * .5, c - r * .15); g.stroke();
    const glow = g.createRadialGradient(c, c, 0, c, c, R * (1.6 + lv));
    glow.addColorStop(0, hexA(acc, .3 * br)); glow.addColorStop(1, hexA(acc, 0));
    g.fillStyle = glow; g.beginPath(); g.arc(c, c, R * (1.6 + lv), 0, 6.283); g.fill();
    if (st === "thinking") { const a = t * 4; g.strokeStyle = hexA(acc, .95); g.lineWidth = 2.5; poly(3, R * 1.8, a, hexA(acc, .9), 2.5); }
  },
};
function glowAndOrb(g, c, R, lv, acc, br, sleeping) {
  const glowR = R * (1.6 + lv * .5);
  const glow = g.createRadialGradient(c, c, R * .2, c, c, glowR);
  glow.addColorStop(0, hexA(acc, .55 * br)); glow.addColorStop(.5, hexA(acc, .12 * br)); glow.addColorStop(1, hexA(acc, 0));
  g.fillStyle = glow; g.beginPath(); g.arc(c, c, glowR, 0, 6.283); g.fill();
  const pr = R * (.86 + lv * .12);
  const body = g.createRadialGradient(c - pr * .3, c - pr * .35, pr * .1, c, c, pr);
  body.addColorStop(0, "#ffffff"); body.addColorStop(.35, hexA(acc, .95)); body.addColorStop(1, hexA(acc, .15));
  g.globalAlpha = sleeping ? .45 + .25 * br : 1;
  g.fillStyle = body; g.beginPath(); g.arc(c, c, pr, 0, 6.283); g.fill();
  g.globalAlpha = 1;
  g.strokeStyle = "rgba(255,255,255,.35)"; g.lineWidth = 1; g.beginPath(); g.arc(c, c, pr * 1.06, 0, 6.283); g.stroke();
}

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

  DRAW[chipId] ? DRAW[chipId](g, c, R, t, smooth, state, acc, breathe) : DRAW.nova(g, c, R, t, smooth, state, acc, breathe);

  // çip kartlarındaki küçük önizlemeler
  if (activeTab === "chips" && accFrame % 2 === 0) {
    for (const cv of $$("#chipGrid canvas")) {
      const w = cv.clientWidth; if (!w) continue;
      if (cv.width !== Math.round(w * dpr)) { cv.width = cv.height = Math.round(w * dpr); }
      const pg = cv.getContext("2d"); pg.setTransform(dpr, 0, 0, dpr, 0, 0); pg.clearRect(0, 0, w, w);
      const id = cv.dataset.chip, col = CHIP_COLORS[id];
      const lv = .35 + .25 * Math.sin(t * 2.3 + id.length);
      DRAW[id](pg, w / 2, w * .2, t, lv, "speaking", col, 1, true);
    }
  }

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
  applyChip(info.chip, info.chips);
  document.body.classList.toggle("no-transcript", !info.settings.show_transcript);
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
  renderTv(info.tv || []);
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
    contacts: async () => [], apps: async () => ({ whatsapp: true }), phone_info: async () => ({ enabled: false }), hide: async () => {}, msg_send: async () => ({ ok: true, text: "Demo" }), msg_confirm: async () => true, share: async () => true,
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
