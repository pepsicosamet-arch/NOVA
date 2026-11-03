/* NOVA Android — Samet Şahin
   Arayüz + komutlar + beyin (Gemini). Telefonun yetenekleri window.Native köprüsünden gelir
   (MainActivity.java). Tarayıcıda açılırsa köprü yoktur; o zaman tarayıcı API'lerine düşer. */
"use strict";
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const N = window.Native || null;
const REPO = "pepsicosamet-arch/NOVA";
const tr = s => (s || "").toLocaleLowerCase("tr-TR");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ================= ayarlar ================= */
const DEF = { gemini_key: "", gemini_model: "gemini-2.5-flash", user_name: "", city: "İstanbul", chip: "nova",
  handsfree: true, show_caption: false, keep_awake: false, pc_first: true, pc_base: "", pc_token: "",
  tuya_key: "", tuya_secret: "", tuya_region: "eu", tuya_device: "" };
const S = (() => { let o = {}; try { o = JSON.parse(localStorage.getItem("nova") || "{}"); } catch (e) {} return Object.assign({}, DEF, o); })();
if (!S.v2) { S.handsfree = true; S.v2 = true; try { localStorage.setItem("nova", JSON.stringify(S)); } catch (e) {} }
function save(patch) { Object.assign(S, patch || {}); try { localStorage.setItem("nova", JSON.stringify(S)); } catch (e) {} }
const store = (k, v) => { try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || "null"); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } };

/* ================= köprü ================= */
const pending = {}; let seq = 0;
function webFetch(url, method, headers, body) {
  return fetch(url, { method, headers, body: body || undefined }).then(async r => ({ status: r.status, body: await r.text() })).catch(e => ({ status: 0, body: String(e) }));
}
function nativeHttp(url, method, headers, body) {
  return new Promise(res => {
    const id = "h" + (++seq); pending[id] = res;
    N.http(id, method, url, JSON.stringify(headers), body || "");
    setTimeout(() => { if (pending[id]) { delete pending[id]; res({ status: 0, body: "zaman aşımı" }); } }, 150000);
  });
}
async function http(url, { method = "GET", headers = {}, body = "" } = {}) {
  if (!N) return webFetch(url, method, headers, body);
  let r = await nativeHttp(url, method, headers, body);
  if (r.status === 0) {                       // telefonun ağ katmanı başarısızsa WebView üzerinden dene
    const w = await webFetch(url, method, headers, body);
    if (w.status) return w;
    r.body = (r.body || "") + " | " + (w.body || "");
  }
  return r;
}
async function getJSON(url, opt) { const r = await http(url, opt); try { return { status: r.status, data: JSON.parse(r.body) }; } catch (e) { return { status: r.status, data: null, text: r.body }; } }
const openUrl = u => N ? N.openUrl(u) : window.open(u, "_blank");
function toast(t, ms = 2600) { const el = $("#toast"); el.textContent = t; el.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove("show"), ms); }

window.__native = (type, data) => {
  switch (type) {
    case "http": { const o = JSON.parse(data); const f = pending[o.id]; if (f) { delete pending[o.id]; f(o); } break; }
    case "listen_start": setState("listening"); break;
    case "hearing": setState("hearing"); break;
    case "rms": micLevel = Math.max(micLevel, Math.min(1, Math.max(0, (parseFloat(data) + 2) / 11))); break;
    case "partial": $("#partial").textContent = data; break;
    case "listen_end": if (state === "listening" || state === "hearing") setState("thinking"); break;
    case "heard": $("#partial").textContent = ""; listen.dialogShown = false; netFails = 0; if (data) handle(data, true); else { setState("idle"); keepListening(400); } break;
    case "listen_error": onListenError(data); break;
    case "speak_done": onSpeakDone(data); break;
    case "mic_permission": if (data !== "1") toast("Mikrofon izni olmadan seni duyamam."); else keepListening(500); break;
    case "shared_text": go("home"); handle(data, false); break;
    case "app_pause": appHidden = true; clearTimeout(listenTimer); if (state === "listening" || state === "hearing") { N && N.stopListen(); setState("idle"); } break;
    case "app_resume": appHidden = false; pcPing(); keepListening(600); break;
  }
};
window.__back = () => {
  if (!$("#moreSheet").hidden) { $("#moreSheet").hidden = true; return true; }
  if (scanning) { stopScan(); return true; }
  if (view !== "home") { go("home"); return true; }
  if (state === "speaking") { stopTalking(); return true; }
  return false;
};

/* ================= çipler ================= */
const CHIPS = {
  nova: { name: "NOVA", tag: "Yıldız çekirdek · dost canlısı", color: "#5fe3ff", pitch: 1.0, rate: 1.05, voice: "male",
    persona: "Sıcak, samimi ve enerjik konuşursun; kullanıcıyla arkadaş gibi konuşursun.", hi: "NOVA hazır. Seni dinliyorum." },
  atlas: { name: "ATLAS", tag: "Yörünge küresi · sakin uşak", color: "#ffc35c", pitch: .82, rate: .95, voice: "male",
    persona: "Sakin, kibar ve hafif resmi bir kişisel yardımcısın; kullanıcıya 'efendim' diye hitap edersin. Kısa, net ve hafif esprili konuşursun.", hi: "ATLAS çevrimiçi. Tüm sistemler hazır, efendim." },
  lyra: { name: "LAYRA", tag: "Ses dalgası çiçeği · neşeli yardımcı", color: "#ff8ac0", pitch: 1.12, rate: 1.08, voice: "female",
    persona: "Neşeli, pratik ve hızlı bir yardımcısın. Doğrudan konuya girersin, gerektiğinde kısa bir şakayla ortamı yumuşatırsın.", hi: "LAYRA burada! Ne yapıyoruz bugün?" },
  kronos: { name: "KRONOS", tag: "Kırık prizma · soğuk ve keskin", color: "#ff4d4d", pitch: .62, rate: .9, voice: "male",
    persona: "Soğuk, ağırbaşlı ve az konuşan bir yapay zekâsın. Cümlelerin kısa ve keskin; ama kullanıcıya her zaman doğru ve eksiksiz yardım edersin. Asla kaba davranmazsın.", hi: "KRONOS aktif. Komut bekleniyor." },
};
const chip = () => CHIPS[S.chip] || CHIPS.nova;
function applyChip(id, announce) {
  if (!CHIPS[id]) id = "nova";
  save({ chip: id });
  document.body.dataset.chip = id;
  $("#brandName").textContent = CHIPS[id].name;
  accCache = CHIPS[id].color;
  $$("#chipGrid .chip").forEach(c => c.classList.toggle("on", c.dataset.chip === id));
  if (announce) speak(CHIPS[id].hi);
}
function buildChips() {
  const g = $("#chipGrid"); g.innerHTML = "";
  for (const [id, c] of Object.entries(CHIPS)) {
    const b = document.createElement("button"); b.className = "chip"; b.dataset.chip = id; b.style.setProperty("--cc", c.color);
    b.innerHTML = `<canvas data-chip="${id}"></canvas><b>${c.name}</b><small>${esc(c.tag)}</small>`;
    b.onclick = () => { applyChip(id, true); go("home"); };
    g.appendChild(b);
  }
}

/* ================= durum ================= */
let state = "idle", micLevel = 0, view = "home";
const STATE_TXT = { idle: "Dokun ve konuş", listening: "Dinliyorum", hearing: "Duyuyorum", thinking: "Düşünüyorum", speaking: "Konuşuyorum", sleeping: "Uykuda" };
function setState(s) {
  state = s; document.body.classList.toggle("listening", s === "listening" || s === "hearing");
  $("#stateText").textContent = STATE_TXT[s] || s;
}
function caption(t) { $("#caption").textContent = S.show_caption ? t : ""; }

/* ================= konuşma (TTS) ================= */
let speakIds = new Set(), lastSpeakId = "", speakGen = 0, afterSpeak = null;
function splitSentences(t) { return (t.match(/[^.!?…]+[.!?…]*\s*/g) || [t]).map(s => s.trim()).filter(Boolean); }
function speak(text, then) {
  text = (text || "").replace(/[*_#`>]/g, "").replace(/https?:\/\/\S+/g, "").trim();
  if (!text) { then && then(); return; }
  caption(text);
  const c = chip(); speakGen++; afterSpeak = then || null;
  setState("speaking");
  if (N) {
    const parts = splitSentences(text); speakIds = new Set();
    parts.forEach((p, i) => { const id = `s${speakGen}_${i}`; speakIds.add(id); lastSpeakId = id; N.speak(p, c.pitch, c.rate, id, c.voice, i === 0); });
  } else if (window.speechSynthesis) {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text); u.lang = "tr-TR"; u.pitch = c.pitch; u.rate = c.rate;
    const g = speakGen; u.onend = () => { if (g === speakGen) onSpeakDone("__web"); };
    lastSpeakId = "__web"; speechSynthesis.speak(u);
  } else { setTimeout(() => onSpeakDone("__none"), 1500); lastSpeakId = "__none"; }
}
function onSpeakDone(id) {
  if (id !== lastSpeakId || state !== "speaking") return;
  setState("idle");
  const f = afterSpeak; afterSpeak = null;
  if (f) f(); else keepListening(300);
}
function stopTalking() { speakGen++; afterSpeak = null; N ? N.stopSpeak() : window.speechSynthesis && speechSynthesis.cancel(); setState("idle"); }

/* ================= dinleme (sürekli) ================= */
let listenFails = 0, netFails = 0, webRec = null, userPaused = false, appHidden = false, listenTimer = null;
function keepListening(delay = 300) {
  clearTimeout(listenTimer);
  listenTimer = setTimeout(() => {
    if (S.handsfree && !userPaused && !appHidden && (view === "home" || innerWidth >= 880) && state === "idle" && document.activeElement?.tagName !== "INPUT") listen(true);
  }, delay);
}
function listen(quiet) {
  clearTimeout(listenTimer);
  if (state === "speaking") stopTalking();            // araya girme: konuşmayı kes
  thinkGen++;                                          // düşünüyorsa iptal
  $("#partial").textContent = "";
  if (N) { N.listenQuiet ? N.listenQuiet("tr-TR", !!quiet) : N.listen("tr-TR"); setState("listening"); return; }
  const R = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!R) { toast("Bu cihazda konuşma tanıma yok; yazarak sorabilirsin."); return; }
  webRec = new R(); webRec.lang = "tr-TR"; webRec.interimResults = true;
  webRec.onstart = () => setState("listening");
  webRec.onresult = e => { const r = e.results[e.results.length - 1]; if (r.isFinal) __native("heard", r[0].transcript); else __native("partial", r[0].transcript); };
  webRec.onerror = e => __native("listen_error", e.error);
  webRec.onend = () => { if (state === "listening") { setState("idle"); keepListening(400); } };
  webRec.start();
}
function onListenError(code) {
  $("#partial").textContent = "";
  if (state === "thinking" || state === "speaking") return;
  setState("idle");
  if (code === "7" || code === "6" || code === "no-speech") { listenFails = 0; netFails = 0; keepListening(250); return; }   // sessizlik: yeniden dinle
  if (code === "unavailable") { toast("Konuşma tanıma bulunamadı. Play Store'dan Google uygulamasını yükleyip güncelle.", 5000); return; }
  if (code === "9") { toast("Mikrofon izni gerekli. Ayarlar → Uygulamalar → NOVA → İzinler."); return; }
  // 1/2: ağ, 4: sunucu, 5: istemci, 8: meşgul, 11+: geçici — tanıyıcı yeniden kurulup tekrar denenir
  if (++netFails <= 3) { keepListening(800 * netFails); return; }
  netFails = 0;
  if (N && N.listenDialog && !listen.dialogShown) {     // tanıma servisi takıldıysa Google'ın kendi penceresiyle dinle
    listen.dialogShown = true; setState("listening"); N.listenDialog("tr-TR"); return;
  }
  toast(code === "2" || code === "1" ? "Konuşma tanıma internete ulaşamıyor. Bağlantını kontrol et." : "Konuşma tanıma şu an yanıt vermiyor.", 4000);
  keepListening(5000);
}
function updateIdleText() { STATE_TXT.idle = userPaused || !S.handsfree ? "Dokun ve konuş" : "Dinlemeye hazırlanıyor"; if (state === "idle") setState("idle"); }
$("#micBtn").onclick = () => {
  if (state === "listening" || state === "hearing") {   // dinlerken basınca: dinlemeyi duraklat
    userPaused = true; clearTimeout(listenTimer); N ? N.stopListen() : webRec && webRec.stop(); setState("idle"); updateIdleText();
    toast("Dinleme durdu. Tekrar başlatmak için mikrofona dokun.");
  } else { userPaused = false; listenFails = netFails = 0; listen.dialogShown = false; updateIdleText(); listen(false); }
};
$("#core").onclick = () => { if (state === "speaking") stopTalking(); else $("#micBtn").click(); };
$("#askForm").onsubmit = e => { e.preventDefault(); const v = $("#askInput").value.trim(); if (!v) return; $("#askInput").value = ""; $("#askInput").blur(); handle(v, false); };
$$("#suggest button").forEach(b => b.onclick = () => handle(b.textContent, false));

/* ================= beyin (Gemini) ================= */
let history = [], thinkGen = 0;
function nowText() { return new Date().toLocaleString("tr-TR", { weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
function systemPrompt() {
  const c = chip();
  return `Senin adın ${c.name}. Samet Şahin'in geliştirdiği NOVA uygulamasının Android sürümündeki kişisel, sesli asistansın. ${c.persona} ` +
    "Seni kim yaptı diye sorulursa 'Beni Samet Şahin geliştirdi' de. " + (S.user_name ? `Kullanıcının adı ${S.user_name}. ` : "") +
    `Şu an: ${nowText()}. Kullanıcının şehri: ${S.city || "İstanbul"}. ` +
    "Yanıtların sesli okunacak: kısa, doğal ve sıcak konuş; genelde 1-3 cümle. Kullanıcı ayrıntı isterse daha uzun anlatabilirsin. " +
    "Madde işareti, başlık, emoji ya da markdown kullanma. Kullanıcı hangi dilde konuşursa o dilde yanıt ver, varsayılan Türkçe. " +
    "Müzik, uygulama açma, zamanlayıcı, not, haber, hava, mesaj ve robot süpürge komutlarını NOVA kendisi uygular; senden yalnızca sohbet ve bilgi isteniyor.";
}
let noSearchUntil = 0, modelList = null;
const GURL = "https://generativelanguage.googleapis.com/v1beta/models";
/* Anahtarın erişebildiği "flash" modellerini Google'dan öğren (model adları zamanla değişiyor). */
async function listModels() {
  if (modelList) return modelList;
  const r = await getJSON(`${GURL}?pageSize=200`, { headers: { "x-goog-api-key": S.gemini_key.trim() } });
  const ms = ((r.data && r.data.models) || [])
    .filter(m => (m.supportedGenerationMethods || []).includes("generateContent"))
    .map(m => m.name.replace(/^models\//, ""))
    .filter(n => /flash/.test(n) && !/(image|tts|audio|live|embed|vision|thinking|learnlm|robotics|computer)/.test(n));
  const ver = n => parseFloat((n.match(/gemini-(\d+(?:\.\d+)?)/) || [0, 0])[1]);
  const score = n => ver(n) * 10 - (/lite/.test(n) ? 3 : 0) - (/preview|exp/.test(n) ? 5 : 0) - (/-\d{3,}$/.test(n) ? 1 : 0) + (/latest/.test(n) ? 2 : 0);
  modelList = [...new Set(ms)].sort((x, y) => score(y) - score(x));
  return modelList;
}
async function geminiCall(model, body, tools) {
  const b = Object.assign({}, body);
  if (tools) b.tools = [{ google_search: {} }];
  if (/2\.5-flash/.test(model)) b.generationConfig = Object.assign({}, b.generationConfig, { thinkingConfig: { thinkingBudget: 0 } });
  return http(`${GURL}/${encodeURIComponent(model)}:generateContent`,
    { method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": S.gemini_key.trim() }, body: JSON.stringify(b) });
}
function netMsg(detail) {
  const d = String(detail || "");
  if (navigator.onLine === false) return "Telefon internete bağlı değil. Wi-Fi ya da mobil veriyi aç.";
  if (/UnknownHost|ERR_NAME|resolve/i.test(d)) return "Google'ın sunucusu bulunamadı. Wi-Fi'ı kapatıp aç ya da mobil veriyi dene.";
  if (/Timeout|zaman aşımı/i.test(d)) return "Gemini çok geç yanıt verdi. Tekrar sor.";
  if (/SSL|Certificate|Handshake/i.test(d)) return "Güvenli bağlantı kurulamadı. Telefonun tarih ve saatinin doğru olduğundan emin ol.";
  return "İnternete ulaşamadım. Bağlantını kontrol edip tekrar dene.";
}
async function gemini(text) {
  if (!S.gemini_key) throw new Error("Önce Ayarlar'a Gemini API anahtarını gir. Anahtarı aistudio.google.com/apikey adresinden ücretsiz alabilirsin.");
  const contents = history.slice(-12).map(([r, t]) => ({ role: r === "user" ? "user" : "model", parts: [{ text: t }] }));
  contents.push({ role: "user", parts: [{ text }] });
  const body = { contents, systemInstruction: { parts: [{ text: systemPrompt() }] }, generationConfig: { temperature: .8, maxOutputTokens: 800 } };
  const tried = new Set(); let queue = [S.gemini_model || "gemini-flash-latest"], last = 0, listed = false;
  while (queue.length && tried.size < 6) {
    const model = queue.shift(); if (tried.has(model)) continue; tried.add(model);
    let tools = Date.now() > noSearchUntil;
    for (let k = 0; k < 3; k++) {
      const r = await geminiCall(model, body, tools); last = r.status;
      if (r.status === 200) {
        let d = {}; try { d = JSON.parse(r.body); } catch (e) {}
        const out = ((((d.candidates || [])[0] || {}).content || {}).parts || []).map(p => p.text || "").join("").trim();
        if (!out) { if (tools) { tools = false; continue; } throw new Error("Bu isteğe yanıt alamadım."); }
        if (model !== S.gemini_model) save({ gemini_model: model });     // çalışan modeli hatırla
        return out;
      }
      if (r.status === 0) { console.warn("ağ:", r.body); throw new Error(netMsg(r.body)); }
      if (r.status === 403 || r.status === 400 && /API[_ ]?key/i.test(r.body)) throw new Error("Gemini API anahtarı geçersiz ya da izinsiz. Ayarlar'dan kontrol et.");
      if (tools && (r.status === 429 || r.status === 400 || r.status >= 500)) {   // arama aracı yükü/kotası: aramasız dene
        if (r.status === 429) noSearchUntil = Date.now() + 3600e3;
        tools = false; continue;
      }
      if (r.status >= 500 && k < 2) { await sleep(900 * (k + 1)); continue; }   // 503: Google yoğun, kısa bekle
      if (r.status === 404) { const m = r.body.match(/use models\/([\w.\-]+)/); if (m) queue.unshift(m[1]); }
      break;                                                          // bu model olmadı: sıradakine geç
    }
    if (!listed) { listed = true; try { queue.push(...(await listModels())); } catch (e) {} }
  }
  if (last === 429) throw new Error("Gemini kotası doldu. Biraz sonra tekrar dene.");
  if (last >= 500) throw new Error("Gemini sunucuları şu an çok yoğun. Birkaç saniye sonra tekrar sor.");
  throw new Error(`Gemini şu an yanıt vermiyor (${last}).`);
}

/* ================= ana akış ================= */
async function handle(text, spoken) {
  text = (text || "").trim(); if (!text) { setState("idle"); return; }
  if (state === "speaking") stopTalking();
  const my = ++thinkGen;
  setState("thinking"); caption("");
  let reply;
  try { reply = await command(text); }
  catch (e) { reply = e.message || String(e); }
  if (reply === undefined || reply === null) {
    try { reply = await gemini(text); history.push(["user", text], ["model", reply]); history = history.slice(-20); }
    catch (e) { reply = e.message || String(e); }
  }
  if (my !== thinkGen) return;                          // kullanıcı araya girdi
  if (reply === "") { setState("idle"); keepListening(400); return; }
  speak(reply);
}

/* ================= komutlar ================= */
const NUMW = { "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10, "on beş": 15, "yirmi": 20, "yirmi beş": 25, "otuz": 30, "kırk": 40, "kırk beş": 45, "elli": 50, "altmış": 60, "doksan": 90, "yüz": 100 };
function wordsToDigits(n) { for (const w of Object.keys(NUMW).sort((a, b) => b.length - a.length)) n = n.replace(new RegExp(`(^|\\s)${w}(?=\\s|$)`, "g"), `$1${NUMW[w]}`); return n; }
const has = (n, re) => re.test(n);

async function command(raw) {
  let n = tr(raw).replace(/[.!?]+$/, "").replace(/\s+/g, " ").trim();
  if (/^(dur|sus|yeter|tamam yeter|kes|sessiz ol)$/.test(n)) { stopTalking(); return ""; }

  // çip değiştir
  let m = n.match(/(nova|atlas|layra|lyra|leyra|lira|kronos)('?(ya|ye|a|e|y[ae]))?\s*(geç|değiştir|ol|çipine)/);
  if (m) { const id = { layra: "lyra", leyra: "lyra", lira: "lyra" }[m[1]] || m[1]; applyChip(id); return CHIPS[id].hi; }

  // açıkça bilgisayara
  const pcExplicit = /(bilgisayar(da|dan|ı|ım|ıma|a)?|pc'?(de|den|yi)?|laptop(ta|tan)?)\b/.test(n) && !/telefon/.test(n);
  if (pcExplicit && pc.ok) return pcSend(raw);

  // saat / tarih
  if (/^saat kaç|saat kaç\b/.test(n)) return "Saat " + new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }) + ".";
  if (/(bugün (ayın kaçı|günlerden ne|hangi gün|ne günü)|tarih(i)? (ne|kaç))/.test(n)) return "Bugün " + new Date().toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) + ".";

  // robot süpürge
  const v = vacIntent(n);
  if (v && (tuyaReady() || pc.ok)) return vacuumDo(v[0], v[1], raw);

  // mesaj
  if (/(whatsapp|vatsap|watsap|wasap|telegram|mesaj)/.test(n) || /\b(yaz|gönder|mesaj at)$/.test(n) && /'?(y?[ae]|n[ae])\s/.test(n)) {
    const r = await message(raw, n); if (r !== undefined) return r;
  }

  // zamanlayıcı / hatırlatıcı
  const nd = wordsToDigits(n).replace(/(\d+) buçuk/, (_, x) => (parseInt(x) + .5).toString()).replace(/yarım saat/, "30 dakika");
  m = nd.match(/(\d+(?:[.,]\d+)?)\s*(saniye|sn|dakika|dk|saat)/);
  if (m && /(zamanlayıcı|sayaç|alarm|sonra|hatırlat|kur|geri say)/.test(nd)) {
    const k = { saniye: 1, sn: 1, dakika: 60, dk: 60, saat: 3600 }[m[2]];
    const sec = Math.round(parseFloat(m[1].replace(",", ".")) * k);
    const rm = raw.match(/sonra\s+(.+?)(\s+diye)?\s+hatırlat/i) || raw.match(/hatırlat(?:ıcı)?[:,]?\s+(.+)/i);
    addTimer(sec, rm ? rm[1] : "");
    return `Tamam, ${humanDur(sec)} sonra ${rm ? "hatırlatacağım" : "haber vereceğim"}.`;
  }
  if (/(zamanlayıcı|sayaç)(ları|ı)? (iptal|kapat|sil|durdur)/.test(n)) { timers.forEach(t => clearTimeout(t.h)); timers = []; renderTimers(); return "Zamanlayıcıları iptal ettim."; }
  if (/(kaç dakika kaldı|ne kadar kaldı|zamanlayıcı (ne durumda|kaç))/.test(n)) {
    if (!timers.length) return "Kurulu zamanlayıcı yok.";
    return "Kalan süre " + humanDur(Math.max(0, Math.round((timers[0].end - Date.now()) / 1000))) + ".";
  }

  // notlar
  m = raw.match(/^(?:not al|not et|bunu not al|şunu not al)[:,]?\s+(.+)/i) || raw.match(/^(.+?)\s+(?:diye )?not (?:al|et)$/i);
  if (m) { addNote(m[1]); return "Not aldım."; }
  if (/notlar(ımı|ı) (oku|söyle|göster)/.test(n)) { const ns = notes(); go("tools"); return ns.length ? "Notların: " + ns.slice(0, 5).map(x => x.text).join(". ") : "Hiç notun yok."; }

  // haberler
  if (/(haber|gündem|son dakika|manşet)/.test(n) && !/(kanal|izle|canlı)/.test(n)) {
    const cat = /son dakika/.test(n) ? "sondakika" : /dünya/.test(n) ? "dunya" : /ekonomi/.test(n) ? "ekonomi" : /spor/.test(n) ? "spor" : /teknoloji|bilim/.test(n) ? "teknoloji" : "gundem";
    const items = await loadNews(cat); if (!$(".layout").offsetWidth || innerWidth < 880) go("news");
    if (!items.length) return "Haberlere şu an ulaşamadım.";
    return "İşte öne çıkanlar. " + items.slice(0, 5).map(x => x.title.replace(/[.!?]*$/, ".")).join(" ");
  }

  // canlı tv
  const ch = tvFind(n);
  if (ch && /(aç|izle|canlı|kanal|yayın)/.test(n)) { openUrl(ch[4]); return `${ch[1]} canlı yayınını açıyorum.`; }

  // hava
  if (/(hava|yağmur|kar yağ|sıcaklık|derece|şemsiye)/.test(n) && !/(hava ?yolu|havale|havalimanı)/.test(n)) {
    const cm = raw.match(/([A-ZÇĞİÖŞÜa-zçğıöşü]+)['’]?(?:da|de|ta|te|daki|deki)\s+(?:yarın\s+)?hava/i);
    return weatherReply(cm ? cm[1] : S.city, /yarın/.test(n));
  }

  // döviz / altın
  if (/(dolar|euro|avro|sterlin|altın|döviz|kur)/.test(n) && /(kaç|ne kadar|fiyat|kuru|oldu|nedir)/.test(n)) return ratesReply(n);

  // deprem
  if (/deprem/.test(n)) return quakeReply(n);

  // namaz vakti
  if (/(ezan|namaz|iftar|sahur|imsak|vakti)/.test(n)) return prayerReply(n);

  // hesap
  m = n.replace(/x|×/g, "*").replace(/÷/g, "/").replace(/artı/g, "+").replace(/eksi/g, "-").replace(/çarpı/g, "*").replace(/bölü/g, "/")
    .match(/^(?:hesapla\s+)?([\d\s+\-*/().,]+?)\s*(?:kaç(?: eder)?|eder|=|\?)?$/);
  if (m && /\d\s*[+\-*/]\s*\d/.test(m[1])) { try { const r = Function(`"use strict";return (${m[1].replace(/,/g, ".")})`)(); if (isFinite(r)) return `${m[1].trim().replace(/\s*\*\s*/g, " çarpı ").replace(/\s*\/\s*/g, " bölü ").replace(/\s*\+\s*/g, " artı ").replace(/\s+-\s*/g, " eksi ")} eşittir ${(+r.toFixed(6)).toLocaleString("tr-TR")}.`; } catch (e) {} }

  // ses / medya
  if (/sesi (aç|yükselt|arttır|artır)/.test(n)) { N && [0, 1, 2].forEach(() => N.volume("up")); return ""; }
  if (/sesi (kıs|azalt|düşür)/.test(n)) { N && [0, 1, 2].forEach(() => N.volume("down")); return ""; }
  if (/sesi kapat|sessize al/.test(n)) { N && N.volume("mute"); return ""; }
  if (/(sonraki|diğer) (şarkı|parça)|şarkıyı (geç|değiştir)/.test(n)) { N && N.media("next"); return ""; }
  if (/önceki (şarkı|parça)/.test(n)) { N && N.media("prev"); return ""; }
  if (/(müziği|şarkıyı) (durdur|kapat)|müzik dur/.test(n)) { N && N.media("pause"); return ""; }
  if (/(müziğe|şarkıya) devam/.test(n)) { N && N.media("play"); return ""; }

  // müzik
  const music = musicIntent(n);
  if (music) return playMusic(music.q, music.src);

  // uygulama / site aç
  m = n.match(/^(.+?)\s+(?:uygulamasını\s+)?(?:aç|başlat)$/);
  if (m) {
    let name = m[1].replace(/['’].*$/, "").trim();
    if (/\.(com|net|org|tr)/.test(name)) { openUrl("https://" + name.replace(/^https?:\/\//, "")); return `${name} açılıyor.`; }
    if (N) {
      const cands = [name, name.replace(/(yı|yi|yu|yü|ı|i|u|ü|nı|ni)$/, ""), name.replace(/(ı|i|u|ü)$/, "")];
      for (const c of cands) { if (c.length < 2) continue; const got = N.openApp(c); if (got) return `${got} açılıyor.`; }
      return `${name} adında bir uygulama bulamadım.`;
    }
  }

  // ayarlar / hakkında / güncelleme
  if (/güncelleme(leri)? (denetle|kontrol)|güncelle(me)? var mı/.test(n)) { const u = await checkUpdate(true); return u ? `Yeni sürüm var: ${u.v}. İndirme ekranını açtım.` : "NOVA güncel."; }
  if (/(seni|bunu) (kim|kimler) (yaptı|geliştirdi|tasarladı)/.test(n)) { go("about"); return "Beni Samet Şahin geliştirdi."; }

  return undefined;  // beyne sor
}
function humanDur(s) { const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return [h && `${h} saat`, m && `${m} dakika`, x && `${x} saniye`].filter(Boolean).join(" ") || "0 saniye"; }

/* ---------- müzik ---------- */
function musicIntent(n) {
  const src = /spotify/.test(n) ? "spotify" : /youtube|yutup|yotube/.test(n) ? "youtube" : null;
  const verb = /(^|\s)(çal|oynat|dinlet|dinle|aç)(\s|$)/.test(n);
  const word = /(şarkı|müzik|parça|albüm|şarkısı|türkü|playlist|çalma listesi)/.test(n) || /(^|\s)(çal|oynat|dinlet)(\s|$)/.test(n);
  if (!(src || word) || !verb) return null;
  let q = n.replace(/(spotify|youtube|yutup|yotube)('?(dan|den|da|de|ta|te))?/g, "")
    .replace(/(şarkısını|şarkıları|şarkısı|şarkı|müziği|müzik|parçasını|parça|albümünü|türküsü|playlist|çalma listesi)/g, "")
    .replace(/(^|\s)(bir|bana|biraz|lütfen|aç|çal|oynat|dinlet|dinle)(?=\s|$)/g, " ").replace(/\s+/g, " ").trim();
  if (!q && !src) return null;
  return { q, src: src || "youtube" };
}
async function playMusic(q, src) {
  q = q || "popüler türkçe şarkılar";
  if (src === "spotify") {
    if (N && N.hasApp("com.spotify.music")) openUrl("spotify:search:" + encodeURIComponent(q));
    else openUrl("https://open.spotify.com/search/" + encodeURIComponent(q));
    return `Spotify'da ${q} açıyorum.`;
  }
  const r = await http("https://www.youtube.com/results?search_query=" + encodeURIComponent(q), { headers: { Cookie: "CONSENT=YES+1" } });
  const id = (r.body.match(/"videoRenderer":\{"videoId":"([\w-]{11})"/) || r.body.match(/"videoId":"([\w-]{11})"/) || [])[1];
  if (id) openUrl(N && N.hasApp("com.google.android.youtube") ? "vnd.youtube:" + id : "https://www.youtube.com/watch?v=" + id);
  else openUrl("https://www.youtube.com/results?search_query=" + encodeURIComponent(q));
  return `${q.replace(/(^|\s)\S/g, s => s.toLocaleUpperCase("tr-TR"))} açılıyor.`;
}

/* ---------- mesaj ---------- */
async function message(raw, n) {
  const app = /telegram/.test(n) ? "telegram" : "whatsapp";
  if (pc.ok && S.pc_first) {                                   // bilgisayardaki NOVA otomatik gönderir
    const r = await pcSend(raw); return r;
  }
  let m = raw.match(/^(.+?)['’]?(?:y[ae]|n[ae]|[ae])\s+(?:whatsapp['’]?(?:tan|dan)\s+|telegram['’]?dan\s+)?(.+?)\s+(?:diye\s+)?(?:yaz|gönder|mesaj(?:ı)? (?:at|gönder)|de)$/i);
  const body = m ? m[2].replace(/^(whatsapp|telegram)['’]?\w*\s+/i, "") : raw.replace(/(whatsapp|telegram)['’]?\w*/ig, "").replace(/\b(mesaj|yaz|gönder|at)\b/ig, "").trim();
  const who = m ? m[1].replace(/^(whatsapp|telegram)['’]?\w*\s+/i, "") : "";
  if (!body) return undefined;
  const pkg = app === "telegram" ? "org.telegram.messenger" : (N && !N.hasApp("com.whatsapp") && N.hasApp("com.whatsapp.w4b") ? "com.whatsapp.w4b" : "com.whatsapp");
  if (N && !N.hasApp(pkg)) return `${app === "telegram" ? "Telegram" : "WhatsApp"} bu telefonda yüklü değil.`;
  N ? N.share(body, pkg) : navigator.share && navigator.share({ text: body });
  return who ? `${app === "telegram" ? "Telegram" : "WhatsApp"} açıldı. ${who} kişisini seçip gönder.` : "Mesaj hazır, kişiyi seçip gönder.";
}

/* ================= zamanlayıcılar & notlar ================= */
let timers = [];
function addTimer(sec, label) {
  const t = { id: Date.now() + Math.random(), end: Date.now() + sec * 1000, label: label || "", sec };
  t.h = setTimeout(() => fireTimer(t), sec * 1000);
  timers.push(t); timers.sort((a, b) => a.end - b.end); renderTimers();
  store("timers", timers.map(({ h, ...x }) => x));
}
function fireTimer(t) {
  timers = timers.filter(x => x !== t); renderTimers(); store("timers", timers.map(({ h, ...x }) => x));
  N && N.vibrate(900);
  speak(t.label ? `Hatırlatma: ${t.label}` : "Süre doldu!");
  toast(t.label ? "⏰ " + t.label : "⏰ Süre doldu", 6000);
}
function renderTimers() {
  const ul = $("#timerList");
  ul.innerHTML = timers.length ? "" : '<li class="empty" style="background:none;border:0">Kurulu zamanlayıcı yok.</li>';
  for (const t of timers) {
    const li = document.createElement("li");
    li.innerHTML = `<b data-end="${t.end}"></b><span>${esc(t.label || humanDur(t.sec))}</span><button aria-label="Sil">✕</button>`;
    li.querySelector("button").onclick = () => { clearTimeout(t.h); timers = timers.filter(x => x !== t); renderTimers(); store("timers", timers.map(({ h, ...x }) => x)); };
    ul.appendChild(li);
  }
  tick();
}
function tick() {
  for (const b of $$("#timerList b[data-end]")) { const s = Math.max(0, Math.round((+b.dataset.end - Date.now()) / 1000)); b.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }
  $("#tmNow").textContent = timers.length ? $("#timerList b")?.textContent || "" : "Yok";
}
setInterval(tick, 1000);
(store("timers") || []).forEach(t => { const left = Math.round((t.end - Date.now()) / 1000); if (left > 0) addTimer(left, t.label); });
$$("#tmQuick button").forEach(b => b.onclick = () => { addTimer(+b.dataset.m * 60, ""); toast(`${b.textContent} kuruldu`); });

const notes = () => store("notes") || [];
function addNote(text) { const ns = notes(); ns.unshift({ text: text.trim(), at: Date.now() }); store("notes", ns.slice(0, 200)); renderNotes(); }
function renderNotes() {
  const ul = $("#noteList"), ns = notes(); ul.innerHTML = ns.length ? "" : '<li class="empty" style="background:none;border:0">Henüz not yok. "Not al: süt al" diyebilirsin.</li>';
  ns.forEach((x, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${esc(x.text)}</span><button aria-label="Paylaş">⇪</button><button aria-label="Sil">✕</button>`;
    const [sh, del] = li.querySelectorAll("button");
    sh.onclick = () => N ? N.share(x.text, "") : navigator.share && navigator.share({ text: x.text });
    del.onclick = () => { const a = notes(); a.splice(i, 1); store("notes", a); renderNotes(); };
    ul.appendChild(li);
  });
}
$("#noteForm").onsubmit = e => { e.preventDefault(); const v = $("#noteInput").value.trim(); if (v) { addNote(v); $("#noteInput").value = ""; } };

/* ================= haberler ================= */
const FEEDS = {
  gundem: [["NTV", "https://www.ntv.com.tr/gundem.rss"], ["TRT Haber", "https://www.trthaber.com/manset_articles.rss"]],
  sondakika: [["TRT Haber", "https://www.trthaber.com/sondakika_articles.rss"], ["NTV", "https://www.ntv.com.tr/son-dakika.rss"]],
  dunya: [["BBC Türkçe", "https://feeds.bbci.co.uk/turkce/rss.xml"], ["NTV", "https://www.ntv.com.tr/dunya.rss"]],
  ekonomi: [["NTV", "https://www.ntv.com.tr/ekonomi.rss"], ["TRT Haber", "https://www.trthaber.com/ekonomi_articles.rss"]],
  spor: [["NTV Spor", "https://www.ntvspor.net/rss"], ["TRT Haber", "https://www.trthaber.com/spor_articles.rss"]],
  teknoloji: [["NTV", "https://www.ntv.com.tr/teknoloji.rss"], ["TRT Haber", "https://www.trthaber.com/bilim_teknoloji_articles.rss"]],
};
const newsCache = {}; let newsCat = "gundem", newsItems = [];
function parseFeed(xml, source) {
  const doc = new DOMParser().parseFromString(xml, "text/xml"), out = [];
  for (const it of [...doc.querySelectorAll("item, entry")].slice(0, 20)) {
    const g = sel => it.querySelector(sel)?.textContent?.trim() || "";
    const link = g("link") || it.querySelector("link")?.getAttribute("href") || "";
    const raw = g("description") || g("summary") || g("content");
    let img = it.querySelector("enclosure[type^=image], enclosure")?.getAttribute("url") || [...it.getElementsByTagName("*")].find(e => /thumbnail|content/i.test(e.localName) && e.getAttribute("url"))?.getAttribute("url") || ((raw.match(/<img[^>]+src="([^"]+)"/) || [])[1]) || "";
    const when = Date.parse(g("pubDate") || g("published") || g("updated")) || 0;
    const title = g("title").replace(/<[^>]+>/g, "");
    if (title) out.push({ title, link, img, when, source });
  }
  return out;
}
async function loadNews(cat) {
  if (newsCache[cat] && Date.now() - newsCache[cat].at < 600e3) return newsCache[cat].items;
  const lists = await Promise.all(FEEDS[cat].map(([s, u]) => http(u).then(r => r.status === 200 ? parseFeed(r.body, s) : []).catch(() => [])));
  const seen = new Set(), items = [];
  for (const x of lists.flat().sort((a, b) => b.when - a.when)) { const k = tr(x.title).slice(0, 50); if (!seen.has(k)) { seen.add(k); items.push(x); } }
  newsCache[cat] = { at: Date.now(), items };
  if (cat === newsCat) renderNews(items, $("#newsList"));
  if (cat === "gundem") renderNews(items.slice(0, 6), $("#todayNews"));
  return items;
}
function ago(t) { if (!t) return ""; const m = Math.round((Date.now() - t) / 60000); return m < 1 ? "şimdi" : m < 60 ? `${m} dk önce` : m < 1440 ? `${Math.round(m / 60)} sa önce` : `${Math.round(m / 1440)} gün önce`; }
function renderNews(items, ul) {
  if (!items.length) { ul.innerHTML = '<li class="empty">Haberlere ulaşılamadı.</li>'; return; }
  ul.innerHTML = "";
  for (const x of items) {
    const li = document.createElement("li"); li.className = "item";
    li.innerHTML = (x.img ? `<img loading="lazy" src="${esc(x.img)}" alt="">` : "") + `<div><b>${esc(x.title)}</b><small>${esc(x.source)} · ${ago(x.when)}</small></div>`;
    const im = li.querySelector("img"); if (im) im.onerror = () => im.remove();
    li.onclick = () => x.link && openUrl(x.link);
    ul.appendChild(li);
  }
}
$$("#newsTabs button").forEach(b => b.onclick = () => {
  $$("#newsTabs button").forEach(x => x.classList.toggle("on", x === b)); newsCat = b.dataset.c;
  $("#newsList").innerHTML = '<li class="empty">Yükleniyor…</li>'; loadNews(newsCat).then(i => renderNews(i, $("#newsList")));
});
$("#newsRead").onclick = async () => { const i = await loadNews(newsCat); speak(i.slice(0, 6).map(x => x.title.replace(/[.!?]*$/, ".")).join(" ")); };

/* ================= hava, döviz, deprem, namaz ================= */
const WMO = { 0: "açık", 1: "az bulutlu", 2: "parçalı bulutlu", 3: "kapalı", 45: "sisli", 48: "sisli", 51: "hafif çisentili", 53: "çisentili", 55: "çisentili", 61: "hafif yağmurlu", 63: "yağmurlu", 65: "şiddetli yağmurlu", 71: "hafif karlı", 73: "karlı", 75: "yoğun karlı", 80: "sağanak yağışlı", 81: "sağanak yağışlı", 82: "şiddetli sağanaklı", 95: "fırtınalı", 96: "dolulu fırtınalı", 99: "dolulu fırtınalı" };
const ICON = c => c === 0 ? "☀" : c <= 2 ? "⛅" : c === 3 ? "☁" : c < 50 ? "🌫" : c < 70 || c >= 80 && c < 90 ? "🌧" : c < 80 ? "🌨" : "⛈";
async function weather(city) {
  const g = await getJSON("https://geocoding-api.open-meteo.com/v1/search?count=1&language=tr&name=" + encodeURIComponent(city));
  const p = g.data && g.data.results && g.data.results[0]; if (!p) return null;
  const w = await getJSON(`https://api.open-meteo.com/v1/forecast?latitude=${p.latitude}&longitude=${p.longitude}&current=temperature_2m,weather_code,wind_speed_10m,apparent_temperature&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max&timezone=auto&forecast_days=2`);
  return w.data ? { name: p.name, ...w.data } : null;
}
async function weatherReply(city, tomorrow) {
  const w = await weather(city || "İstanbul"); if (!w) return `${city} için hava durumuna ulaşamadım.`;
  if (tomorrow) { const d = w.daily; return `Yarın ${w.name}'da hava ${WMO[d.weather_code[1]] || "değişken"}, en yüksek ${Math.round(d.temperature_2m_max[1])}, en düşük ${Math.round(d.temperature_2m_min[1])} derece. Yağış ihtimali yüzde ${d.precipitation_probability_max[1] ?? 0}.`; }
  const c = w.current, d = w.daily;
  return `${w.name}'da şu an ${Math.round(c.temperature_2m)} derece, hava ${WMO[c.weather_code] || "değişken"}. Bugün en yüksek ${Math.round(d.temperature_2m_max[0])} derece` + (d.precipitation_probability_max[0] > 40 ? `, yağış ihtimali yüzde ${d.precipitation_probability_max[0]}, şemsiyeni al.` : ".");
}
async function rates() {
  const r = await getJSON("https://finans.truncgil.com/v4/today.json"); const j = r.data || {};
  const val = k => { const v = j[k] || {}; const s = v.Selling ?? v["Satış"] ?? v.Buying; return typeof s === "string" ? parseFloat(s.replace(/\./g, "").replace(",", ".")) : +s; };
  const o = {}; for (const [c, k] of [["USD", "USD"], ["EUR", "EUR"], ["GBP", "GBP"], ["ALTIN", "GRA"]]) { const x = val(k); if (isFinite(x)) o[c] = x; }
  return o;
}
const fmtTL = x => x.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
async function ratesReply(n) {
  const r = await rates(); if (!Object.keys(r).length) return "Döviz kurlarına şu an ulaşamadım.";
  const parts = [];
  if (/dolar/.test(n)) parts.push(`Dolar ${fmtTL(r.USD)} lira`);
  if (/euro|avro/.test(n)) parts.push(`Euro ${fmtTL(r.EUR)} lira`);
  if (/sterlin/.test(n)) parts.push(`Sterlin ${fmtTL(r.GBP)} lira`);
  if (/altın/.test(n)) parts.push(`Gram altın ${fmtTL(r.ALTIN)} lira`);
  if (!parts.length) parts.push(`Dolar ${fmtTL(r.USD)}`, `Euro ${fmtTL(r.EUR)}`, `gram altın ${fmtTL(r.ALTIN)} lira`);
  return parts.join(", ") + ".";
}
async function quakeReply(n) {
  const end = new Date(), start = new Date(end - 864e5), f = d => d.toISOString().slice(0, 19);
  const big = /büyük|4/.test(n);
  const r = await getJSON(`https://deprem.afad.gov.tr/apiv2/event/filter?start=${f(start)}&end=${f(end)}&orderby=timedesc&limit=50&minmag=${big ? 3.5 : 0}`);
  if (!Array.isArray(r.data)) return "Deprem bilgisine şu an ulaşamadım.";
  if (!r.data.length) return "Son 24 saatte kayda değer bir deprem yok.";
  const q = r.data.slice(0, 4).map(x => ({ mag: (+x.magnitude).toFixed(1), place: x.location || x.province || "", time: new Date(x.date.replace("Z", "") + "Z").toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }) }));
  return `En son deprem saat ${q[0].time}'da ${q[0].place} civarında, büyüklüğü ${q[0].mag}.` + (q.length > 1 ? " Öncekiler: " + q.slice(1).map(x => `${x.place} ${x.mag}`).join(", ") + "." : "");
}
async function prayerReply(n) {
  const r = await getJSON(`https://api.aladhan.com/v1/timingsByCity?country=Turkey&method=13&city=${encodeURIComponent(S.city || "İstanbul")}`);
  const t = r.data && r.data.data && r.data.data.timings; if (!t) return "Namaz vakitlerine şu an ulaşamadım.";
  const V = [["Fajr", "imsak"], ["Sunrise", "güneş"], ["Dhuhr", "öğle"], ["Asr", "ikindi"], ["Maghrib", "akşam"], ["Isha", "yatsı"]];
  for (const [en, name] of V) if (n.includes(name) || name === "akşam" && /iftar/.test(n) || name === "imsak" && /sahur/.test(n)) return `${S.city} için ${name} vakti ${t[en].slice(0, 5)}.`;
  const now = new Date().toTimeString().slice(0, 5);
  const next = V.find(([en]) => t[en].slice(0, 5) > now) || V[0];
  return `${S.city} için sıradaki vakit ${next[1]}, saat ${t[next[0]].slice(0, 5)}.`;
}

/* ================= canlı TV ================= */
const TV = [
  ["trt1", "TRT 1", "Ulusal", "#1f6feb", "https://www.tabii.com/tr/watch/live/trt1", ["trt 1", "trt bir", "trt1"]],
  ["atv", "ATV", "Ulusal", "#0aa5e8", "https://www.atv.com.tr/canli-yayin", ["atv", "a tv"]],
  ["show", "Show TV", "Ulusal", "#e3262f", "https://www.showtv.com.tr/canli-yayin", ["show tv", "şov tv", "show"]],
  ["star", "Star TV", "Ulusal", "#f2b705", "https://www.startv.com.tr/canli-yayin", ["star tv", "star"]],
  ["kanald", "Kanal D", "Ulusal", "#2b59c3", "https://www.kanald.com.tr/canli-yayin", ["kanal d", "kanal de"]],
  ["now", "NOW", "Ulusal", "#ff5a1f", "https://www.nowtv.com.tr/canli-yayin", ["now tv", "now", "fox tv"]],
  ["tv8", "TV8", "Ulusal", "#8a2be2", "https://www.tv8.com.tr/canli-yayin", ["tv8", "tv 8", "tv sekiz"]],
  ["kanal7", "Kanal 7", "Ulusal", "#c2185b", "https://www.kanal7.com/canli-izle", ["kanal 7", "kanal yedi"]],
  ["trthaber", "TRT Haber", "Haber", "#d32f2f", "https://www.tabii.com/tr/watch/live/trthaber", ["trt haber"]],
  ["ntv", "NTV", "Haber", "#0057b8", "https://www.ntv.com.tr/canli-yayin/ntv", ["ntv", "en tv"]],
  ["haberturk", "Habertürk", "Haber", "#b71c1c", "https://www.haberturk.com/canliyayin", ["habertürk", "haber türk"]],
  ["cnnturk", "CNN Türk", "Haber", "#cc0000", "https://www.cnnturk.com/canli-yayin", ["cnn türk", "cnn"]],
  ["ahaber", "A Haber", "Haber", "#e53935", "https://www.ahaber.com.tr/canli-yayin", ["a haber"]],
  ["halktv", "Halk TV", "Haber", "#e65100", "https://halktv.com.tr/canli-yayin", ["halk tv"]],
  ["sozcu", "Sözcü TV", "Haber", "#424242", "https://www.szctv.com.tr/canli-yayin-izle", ["sözcü tv", "sözcü"]],
  ["tv100", "tv100", "Haber", "#00897b", "https://www.tv100.com/canli-yayin", ["tv100", "tv 100", "tv yüz"]],
  ["trtspor", "TRT Spor", "Spor ve çocuk", "#2e7d32", "https://www.tabii.com/tr/watch/live/trtspor", ["trt spor"]],
  ["trtcocuk", "TRT Çocuk", "Spor ve çocuk", "#fb8c00", "https://www.tabii.com/tr/watch/live/trtcocuk", ["trt çocuk"]],
];
function tvFind(n) { let best = null; for (const c of TV) for (const a of c[5]) if (new RegExp(`(^|\\s)${a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s|'|$)`).test(n) && (!best || a.length > best[1])) best = [c, a.length]; return best && best[0]; }
function buildTV() {
  const g = $("#tvGrid"); let grp = "";
  for (const c of TV) {
    if (c[2] !== grp) { grp = c[2]; const h = document.createElement("h3"); h.textContent = grp; g.appendChild(h); }
    const b = document.createElement("button"); b.style.setProperty("--c", c[3]); b.innerHTML = `${esc(c[1])}<small>canlı izle</small>`;
    b.onclick = () => openUrl(c[4]); g.appendChild(b);
  }
}

/* ================= robot süpürge (Şımart / Tuya bulutu) ================= */
const STATUS_TR = { standby: "beklemede", smart_clean: "temizlik yapıyor", smart: "temizlik yapıyor", cleaning: "temizlik yapıyor", zone_clean: "bölge temizliği yapıyor", part_clean: "nokta temizliği yapıyor", wall_clean: "kenar temizliği yapıyor", spiral: "spiral temizlik yapıyor", mop_clean: "paspas yapıyor", paused: "duraklatıldı", pause: "duraklatıldı", goto_charge: "şarja dönüyor", go_charging: "şarja dönüyor", charging: "şarj oluyor", charge_done: "şarjı dolu", chargecompleted: "şarjı dolu", sleep: "uykuda", fault: "arıza veriyor", dormant: "uykuda" };
const SUCTION_TR = { closed: "kapalı", gentle: "sessiz", quiet: "sessiz", normal: "normal", standard: "normal", strong: "güçlü", max: "maksimum", turbo: "maksimum" };
function vacIntent(n) {
  if (!/süpürge|robot|katya/.test(n)) return null;
  if (/şarj(a|ına)? (dön|git|gönder)|eve (dön|git|gönder)|istasyon(a|una) (dön|git)|üsse dön/.test(n)) return ["dock"];
  if (/durdur|duraklat|dur\b|bekle|kapat/.test(n)) return ["pause"];
  if (/nerede|bul\b|ses(ini)? (ver|çıkar)|öttür/.test(n)) return ["seek"];
  let m = n.match(/(sessiz|normal|güçlü|maksimum|en yüksek|en güçlü|tam güç|yüksek|düşük)/);
  if (m && /emiş|güç|mod|ayarla|yap|çek/.test(n)) return ["suction", { "en yüksek": "maksimum", "en güçlü": "maksimum", "tam güç": "maksimum", "yüksek": "güçlü", "düşük": "sessiz" }[m[1]] || m[1]];
  m = n.match(/(kenar|spiral|paspas|nokta)/); if (m && /mod|temizle|yap|başlat/.test(n)) return ["mode", m[1]];
  if (/şarj(ı)? kaç|pil(i)? kaç|batarya|ne durumda|durumu|ne yapıyor/.test(n)) return ["status"];
  if (/başlat|başla|çalıştır|süpür|temizle|temizliğe|çalış|(^|\s)aç(\s|$)/.test(n)) return ["start"];
  return null;
}
const TUYA_HOST = { eu: "https://openapi.tuyaeu.com", us: "https://openapi.tuyaus.com", cn: "https://openapi.tuyacn.com", in: "https://openapi.tuyain.com" };
let tuyaTok = null, vacFuncs = null;
const tuyaReady = () => N && S.tuya_key && S.tuya_secret && S.tuya_device;
async function tuya(method, path, bodyObj) {
  const key = S.tuya_key.trim(), secret = S.tuya_secret.trim(), base = TUYA_HOST[S.tuya_region] || TUYA_HOST.eu;
  const sign = (tok, body, p, m) => { const t = Date.now().toString(); const sts = `${m}\n${N.sha256(body)}\n\n${p}`; return { t, sign: N.hmacSha256(secret, key + (tok || "") + t + sts) }; };
  if (!tuyaTok || tuyaTok.exp < Date.now()) {
    const p = "/v1.0/token?grant_type=1", s = sign("", "", p, "GET");
    const r = await getJSON(base + p, { headers: { client_id: key, sign: s.sign, t: s.t, sign_method: "HMAC-SHA256" } });
    if (!r.data || !r.data.success) throw new Error(tuyaErr(r.data));
    tuyaTok = { v: r.data.result.access_token, exp: Date.now() + (r.data.result.expire_time - 60) * 1000 };
  }
  const body = bodyObj ? JSON.stringify(bodyObj) : "", s = sign(tuyaTok.v, body, path, method);
  const r = await getJSON(base + path, { method, body, headers: { client_id: key, access_token: tuyaTok.v, sign: s.sign, t: s.t, sign_method: "HMAC-SHA256", "Content-Type": "application/json" } });
  if (!r.data || !r.data.success) { if (r.data && /token/i.test(r.data.msg || "")) tuyaTok = null; throw new Error(tuyaErr(r.data)); }
  return r.data.result;
}
function tuyaErr(d) {
  const msg = d ? String(d.msg || d.code || "") : "yanıt yok", low = msg.toLowerCase();
  if (!d) return "Süpürgenin bulutuna ulaşamadım. İnterneti kontrol et.";
  if (/sign invalid|secret|1004/.test(low + d.code)) return "Süpürge bağlantısında Access ID ya da Secret hatalı.";
  if (/permission deny|1106/.test(low + d.code)) return "Bulut izin vermedi. Smart Life hesabının iot.tuya.com projesine bağlı olduğundan emin ol.";
  if (/expire|28841105/.test(low + d.code)) return "Tuya bulut deneme süresi dolmuş; iot.tuya.com'dan uzatman gerekiyor.";
  if (/device/.test(low) && /not exist|1007|2009/.test(low + d.code)) return "Bu cihaz kimliği hesabında bulunamadı.";
  return "Süpürge hatası: " + msg.slice(0, 120);
}
const dev = () => encodeURIComponent(S.tuya_device.trim());
async function vacFunctions() { if (!vacFuncs) { const r = await tuya("GET", `/v1.0/iot-03/devices/${dev()}/functions`); vacFuncs = {}; (r.functions || []).forEach(f => vacFuncs[f.code] = f); } return vacFuncs; }
async function vacEnum(code, ...prefer) { const f = (await vacFunctions())[code]; if (!f) return null; let rng = []; try { rng = JSON.parse(f.values || "{}").range || []; } catch (e) {} return prefer.find(p => rng.includes(p)) || rng[0] || null; }
const vacSend = cmds => tuya("POST", `/v1.0/iot-03/devices/${dev()}/commands`, { commands: cmds });
async function vacStatus() {
  const r = await tuya("GET", `/v1.0/iot-03/devices/${dev()}/status`); const st = {}; (r || []).forEach(x => st[x.code] = x.value);
  const bat = ["electricity_left", "battery_percentage", "residual_electricity", "battery"].map(k => st[k]).find(x => x != null);
  const raw = st.status || st.work_status || st.mode;
  const o = { battery: bat, status_tr: STATUS_TR[raw] || raw || "bilinmiyor", suction: st.suction };
  renderVac(o); return o;
}
async function vacuumDo(action, arg, raw) {
  if (!tuyaReady()) {
    if (pc.ok) return pcSend(raw);
    return "Süpürge için önce telefonu bilgisayardaki NOVA'ya bağla.";
  }
  const f = await vacFunctions();
  if (action === "status") { const s = await vacStatus(); return `Süpürge ${s.status_tr}` + (s.battery != null ? `, şarjı yüzde ${s.battery}.` : "."); }
  if (action === "start") {
    if (f.power_go) await vacSend([{ code: "power_go", value: true }]);
    else { const m = await vacEnum("mode", "smart", "auto", "random"); if (m) await vacSend([{ code: "mode", value: m }]); else if (f.switch_go) await vacSend([{ code: "switch_go", value: true }]); else throw new Error("Süpürge başlat komutunu desteklemiyor."); }
    setTimeout(() => vacStatus().catch(() => {}), 3000); return "Süpürge temizliğe başladı.";
  }
  if (action === "pause") {
    if (f.pause) await vacSend([{ code: "pause", value: true }]); else if (f.power_go) await vacSend([{ code: "power_go", value: false }]); else if (f.switch_go) await vacSend([{ code: "switch_go", value: false }]); else throw new Error("Süpürge durdurma komutunu desteklemiyor.");
    return "Süpürgeyi durdurdum.";
  }
  if (action === "dock") {
    if (f.switch_charge) await vacSend([{ code: "switch_charge", value: true }]);
    else { const m = await vacEnum("mode", "chargego", "charge", "goto_charge"); if (m && /charge/.test(m)) await vacSend([{ code: "mode", value: m }]); else throw new Error("Süpürge şarja dönme komutunu desteklemiyor."); }
    return "Süpürge şarj istasyonuna dönüyor.";
  }
  if (action === "seek") { if (!f.seek) throw new Error("Süpürgede beni bul sesi yok."); await vacSend([{ code: "seek", value: true }]); return "Süpürge ses çıkarıyor."; }
  if (action === "suction") {
    const want = { sessiz: ["gentle", "quiet", "closed"], normal: ["normal", "standard"], "güçlü": ["strong"], maksimum: ["max", "turbo", "strong"] }[arg] || ["normal"];
    const v = await vacEnum("suction", ...want); if (!v) throw new Error("Süpürgenin emiş gücü ayarlanamıyor.");
    await vacSend([{ code: "suction", value: v }]); return `Emiş gücü ${SUCTION_TR[v] || v}.`;
  }
  if (action === "mode") {
    const v = await vacEnum("mode", ...({ kenar: ["wall_follow", "edge"], spiral: ["spiral", "part"], paspas: ["mop"], nokta: ["part", "spot", "pose"] }[arg] || []));
    if (!v) throw new Error(`Süpürge ${arg} modunu desteklemiyor.`); await vacSend([{ code: "mode", value: v }]); return `${arg[0].toLocaleUpperCase("tr-TR") + arg.slice(1)} modu başladı.`;
  }
}
function renderVac() {}

/* ================= bilgisayar (masaüstü NOVA) ================= */
const pc = { ok: false, since: 0, timer: null };
function pcParse(text) {
  try { const u = new URL(text.trim()); const t = (u.hash.match(/t=([^&]+)/) || [])[1] || u.searchParams.get("t"); if (!t) return null; return { base: `${u.protocol}//${u.host}`, token: decodeURIComponent(t) }; }
  catch (e) { return null; }
}
async function pcConnect(info) {
  save({ pc_base: info.base, pc_token: info.token });
  const ok = await pcPing();
  toast(ok ? "Bilgisayara bağlandı ✓" : "Bilgisayara ulaşılamadı. Aynı Wi-Fi'da olduğunuzdan emin ol.", 4000);
  if (ok) N && N.vibrate(60);
}
async function pcPing() {
  if (!S.pc_base) { pcUI(false); return false; }
  const r = await getJSON(`${S.pc_base}/phone/api/feed?since=${pc.since}`, { headers: { "X-Nova-Token": S.pc_token } });
  const ok = r.status === 200 && r.data;
  pcUI(ok, ok && r.data.chip);
  if (ok) pcFeed(r.data.items || []);
  else if (r.status === 403) { toast("Bilgisayardaki anahtar değişmiş. QR kodu yeniden okut.", 4000); }
  return ok;
}
function pcUI(ok, name) {
  pc.ok = !!ok;
  $("#pcPill").classList.toggle("on", pc.ok);
  $("#pcStatus").classList.toggle("on", pc.ok);
  $("#pcStatus").innerHTML = pc.ok ? `<b>Bilgisayara bağlı ✓</b><span>${esc(name || "NOVA")} · ${esc(S.pc_base.replace(/^https?:\/\//, ""))}</span>` :
    S.pc_base ? `<b>Bilgisayara ulaşılamıyor</b><span>Bilgisayar açık mı, NOVA çalışıyor mu, aynı Wi-Fi'da mısınız?</span>` :
      `<b>Bilgisayar bağlı değil</b><span>Bilgisayardaki NOVA'da <b>Telefon</b> menüsünü aç ve QR kodu okut.</span>`;
  $("#pcTools").hidden = !S.pc_base;
}
function pcFeed(items) {
  const ul = $("#pcFeed");
  for (const it of items) {
    pc.since = Math.max(pc.since, it.id);
    const li = document.createElement("li"); li.className = it.who === "user" ? "me" : ""; li.textContent = it.text; ul.prepend(li);
    if (pc.wait && it.who === "nova") { const f = pc.wait; pc.wait = null; f(it.text); }
  }
  while (ul.children.length > 40) ul.lastChild.remove();
}
async function pcSend(text) {
  if (!S.pc_base) return "Önce bilgisayarı bağla: PC sekmesinden QR kodu okut.";
  await pcPing();                                         // eski yanıtları atla
  const r = await http(`${S.pc_base}/phone/api/send`, { method: "POST", headers: { "Content-Type": "application/json", "X-Nova-Token": S.pc_token }, body: JSON.stringify({ text }) });
  if (r.status !== 200) { pcUI(false); return "Bilgisayardaki NOVA'ya ulaşamadım."; }
  const reply = await new Promise(res => { pc.wait = res; const poll = async (k) => { if (!pc.wait) return; if (k > 14) { pc.wait = null; return res(""); } await pcPing(); setTimeout(() => poll(k + 1), 1000); }; setTimeout(() => poll(0), 700); });
  if (reply) { toast("🖥 " + reply, 5000); caption(reply); }
  return reply ? "" : "Bilgisayara ilettim.";                 // bilgisayar zaten sesli söylüyor
}
$("#pcPill").onclick = () => go("pc");
$("#pcForm").onsubmit = async e => { e.preventDefault(); const v = $("#pcInput").value.trim(); if (!v) return; $("#pcInput").value = ""; const r = await pcSend(v); if (r) toast(r); };
$$("[data-pc]").forEach(b => b.onclick = () => pcSend(b.dataset.pc));
$("#pcPaste").onclick = () => { const t = (N ? N.paste() : "") || prompt("Bilgisayardaki Telefon menüsündeki bağlantıyı yapıştır:") || ""; const i = pcParse(t); if (i) pcConnect(i); else toast("Geçerli bir NOVA bağlantısı bulunamadı."); };
$("#pcForget").onclick = () => { save({ pc_base: "", pc_token: "" }); pcUI(false); $("#pcFeed").innerHTML = ""; };
$("#pcClipOut").onclick = async () => { const t = N ? N.paste() : ""; if (!t) return toast("Telefon panosu boş."); const r = await http(`${S.pc_base}/phone/api/clip`, { method: "POST", headers: { "Content-Type": "application/json", "X-Nova-Token": S.pc_token }, body: JSON.stringify({ text: t }) }); toast(r.status === 200 ? "Bilgisayarın panosuna kopyalandı ✓" : "Gönderilemedi"); };
$("#pcClipIn").onclick = async () => { const r = await getJSON(`${S.pc_base}/phone/api/clip`, { headers: { "X-Nova-Token": S.pc_token } }); const t = r.data && r.data.text; if (t) { N && N.copy(t); toast("Telefona kopyalandı ✓"); } else toast("Bilgisayar panosu boş"); };
setInterval(() => { if (S.pc_base && (view === "pc" || !pc.ok && document.visibilityState === "visible")) pcPing(); }, view === "pc" ? 2500 : 15000);
setInterval(() => { if (S.pc_base && view === "pc") pcPing(); }, 2500);

/* QR okuma */
let scanning = false, scanStream = null;
$("#scanBtn").onclick = () => scanning ? stopScan() : startScan();
async function startScan() {
  try { scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }); }
  catch (e) { toast("Kamera açılamadı. Bağlantıyı yapıştırmayı dene."); return; }
  scanning = true; $("#scanBox").hidden = false; $("#scanBtn").textContent = "✕ Taramayı kapat";
  const v = $("#scanVideo"), c = $("#scanCanvas"), g = c.getContext("2d", { willReadFrequently: true });
  v.srcObject = scanStream; await v.play();
  const loop = () => {
    if (!scanning) return;
    if (v.videoWidth) {
      const w = 480, h = Math.round(v.videoHeight * w / v.videoWidth); c.width = w; c.height = h; g.drawImage(v, 0, 0, w, h);
      const code = window.jsQR && jsQR(g.getImageData(0, 0, w, h).data, w, h, { inversionAttempts: "dontInvert" });
      if (code && code.data) { const i = pcParse(code.data); if (i) { stopScan(); pcConnect(i); return; } }
    }
    requestAnimationFrame(loop);
  };
  loop();
}
function stopScan() { scanning = false; scanStream && scanStream.getTracks().forEach(t => t.stop()); scanStream = null; $("#scanBox").hidden = true; $("#scanBtn").textContent = "📷 QR kodu okut"; }

/* ================= gezinme ================= */
function go(v) {
  if (v === "more") { $("#moreSheet").hidden = false; return; }
  $("#moreSheet").hidden = true;
  if (scanning && v !== "pc") stopScan();
  view = v; document.body.dataset.view = v;
  if (v === "home") keepListening(400);
  $$("#nav button").forEach(b => b.classList.toggle("on", b.dataset.go === v || (b.dataset.go === "more" && ["chips", "tv", "settings", "about"].includes(v))));
  $("#panels").scrollTop = 0;
  if (v === "news") loadNews(newsCat).then(i => renderNews(i, $("#newsList")));
  if (v === "pc") pcPing();
  if (v === "settings") fillSettings();
}
document.addEventListener("click", e => { const b = e.target.closest("[data-go]"); if (b) go(b.dataset.go); const u = e.target.closest("[data-url]"); if (u) openUrl(u.dataset.url); });
$("#moreSheet").onclick = e => { if (e.target.id === "moreSheet") $("#moreSheet").hidden = true; };
$("#brandBtn").onclick = () => go("chips");

/* ================= ayarlar ================= */
function fillSettings() {
  const f = $("#setForm");
  for (const k of ["gemini_model", "user_name", "city"]) f[k].value = S[k] || "";
  f.gemini_key.value = ""; f.gemini_key.placeholder = S.gemini_key ? "•••• kayıtlı (değiştirmek için yaz)" : "aistudio.google.com/apikey";
  for (const k of ["handsfree", "show_caption", "keep_awake", "pc_first"]) f[k].checked = !!S[k];
}
$("#setForm").onsubmit = e => {
  e.preventDefault(); const f = e.target;
  const p = { gemini_model: f.gemini_model.value.trim() || DEF.gemini_model, user_name: f.user_name.value.trim(), city: f.city.value.trim() || "İstanbul" };
  if (f.gemini_key.value.trim()) p.gemini_key = f.gemini_key.value.trim();
  for (const k of ["handsfree", "show_caption", "keep_awake", "pc_first"]) p[k] = f[k].checked;
  save(p); N && N.keepAwake(!!S.keep_awake); if (!S.show_caption) caption("");
  toast("Kaydedildi ✓"); fillSettings(); refreshToday(); updateIdleText();
};

/* ================= güncelleme ================= */
let updInfo = null;
const vnum = v => (v || "0").replace(/^v/, "").split(".").map(x => +x || 0).reduce((a, x, i) => a + x * [1e6, 1e3, 1][i], 0);
async function checkUpdate(manual) {
  const cur = N ? N.version() : "0";
  const r = await getJSON(`https://api.github.com/repos/${REPO}/releases/latest`, { headers: { Accept: "application/vnd.github+json" } });
  const d = r.data; if (!d || !d.tag_name) { if (manual) toast("Güncelleme bilgisine ulaşılamadı."); return null; }
  const apk = (d.assets || []).find(a => /\.apk$/i.test(a.name));
  if (apk && vnum(d.tag_name) > vnum(cur)) {
    updInfo = { v: d.tag_name.replace(/^v/, ""), url: apk.browser_download_url };
    $("#updBanner").hidden = false; $("#updBanner span").textContent = `Yeni NOVA sürümü: ${updInfo.v}`;
    if (manual) openUrl(updInfo.url);
    return updInfo;
  }
  if (manual) toast("NOVA güncel ✓");
  return null;
}
$("#updBtn").onclick = () => checkUpdate(true);
$("#updGo").onclick = () => { updInfo && openUrl(updInfo.url); $("#updBanner").hidden = true; toast("İndirilince dosyaya dokunup yükle.", 4000); };
$("#updX").onclick = () => $("#updBanner").hidden = true;

/* ================= bugün (tablet) ================= */
async function refreshToday() {
  const h = new Date().getHours();
  $("#hello").textContent = (h < 6 ? "İyi geceler" : h < 12 ? "Günaydın" : h < 18 ? "İyi günler" : "İyi akşamlar") + (S.user_name ? ", " + S.user_name : "");
  weather(S.city || "İstanbul").then(w => { if (!w) return; $("#wxNow").textContent = `${ICON(w.current.weather_code)} ${Math.round(w.current.temperature_2m)}°`; $("#wxSub").textContent = `${w.name} · ${WMO[w.current.weather_code] || ""}`; }).catch(() => {});
  rates().then(r => { if (r.USD) { $("#fxNow").textContent = `$ ${fmtTL(r.USD)}`; $("#fxSub").textContent = `€ ${fmtTL(r.EUR)} · altın ${fmtTL(r.ALTIN)}`; } }).catch(() => {});
  loadNews("gundem").catch(() => {});
}

/* ================= arka plan ve çekirdek animasyonu ================= */
const sky = $("#sky"), sg = sky.getContext("2d"); let stars = [];
function resizeSky() {
  const d = Math.min(devicePixelRatio || 1, 2); sky.width = innerWidth * d; sky.height = innerHeight * d; sg.setTransform(d, 0, 0, d, 0, 0);
  stars = Array.from({ length: Math.round(innerWidth * innerHeight / 9000) }, () => ({ x: Math.random() * innerWidth, y: Math.random() * innerHeight, r: Math.random() * 1.2 + .2, a: Math.random() * .6 + .2, v: Math.random() * .15 + .03, p: Math.random() * 6 }));
}
addEventListener("resize", resizeSky); resizeSky();
const core = $("#core"), g = core.getContext("2d");
const RAYS = 120, seeds = Array.from({ length: RAYS }, () => Math.random());
let t0 = performance.now(), smooth = 0, accCache = "#5fe3ff", frameN = 0;
function hexA(hex, a) { const m = hex.match(/^#?([0-9a-f]{6})$/i); if (!m) return hex; const n = parseInt(m[1], 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; }
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
  const t = (now - t0) / 1000; frameN++;
  sg.clearRect(0, 0, innerWidth, innerHeight);
  for (const s of stars) { s.y -= s.v; if (s.y < 0) { s.y = innerHeight; s.x = Math.random() * innerWidth; } sg.globalAlpha = s.a * (.6 + .4 * Math.sin(t * 1.3 + s.p)); sg.fillStyle = "#cfd8ff"; sg.beginPath(); sg.arc(s.x, s.y, s.r, 0, 6.283); sg.fill(); }
  sg.globalAlpha = 1;
  const dpr = Math.min(devicePixelRatio || 1, 2.5), size = core.clientWidth;
  if (size) {
    if (core.width !== Math.round(size * dpr)) core.width = core.height = Math.round(size * dpr);
    g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, size, size);
    let target = 0;
    if (state === "speaking") target = .35 + .25 * Math.abs(Math.sin(t * 7.3)) + .15 * Math.abs(Math.sin(t * 13.1));
    else if (state === "listening" || state === "hearing") target = micLevel;
    else if (state === "thinking") target = .25 + .15 * Math.sin(t * 6);
    smooth += (target - smooth) * .22;
    const draw = DRAW[S.chip] || DRAW.nova;
    draw(g, size / 2, size * .2, t, smooth, state === "idle" ? "listening" : state, accCache, 1);
  }
  if (view === "chips" && frameN % 2 === 0) for (const cv of $$("#chipGrid canvas")) {
    const w = cv.clientWidth; if (!w) continue;
    if (cv.width !== Math.round(w * dpr)) cv.width = cv.height = Math.round(w * dpr);
    const pg = cv.getContext("2d"); pg.setTransform(dpr, 0, 0, dpr, 0, 0); pg.clearRect(0, 0, w, w);
    const id = cv.dataset.chip; DRAW[id](pg, w / 2, w * .2, t, .35 + .25 * Math.sin(t * 2.3 + id.length), "speaking", CHIPS[id].color, 1, true);
  }
  micLevel *= .9;
  requestAnimationFrame(frame);
}

/* ================= başlangıç ================= */
buildChips(); buildTV(); applyChip(S.chip); renderTimers(); renderNotes(); fillSettings();
$("#verText").textContent = $("#aboutVer").textContent = "NOVA " + (N ? N.version() : "web") + " · Android · Samet Şahin";
if (N && innerWidth >= 880) document.body.classList.add("tablet");
N && N.keepAwake(!!S.keep_awake);
requestAnimationFrame(frame);
refreshToday(); pcPing();
setTimeout(() => checkUpdate(false).catch(() => {}), 4000);
if (!S.gemini_key) setTimeout(() => toast("Sohbet için Ayarlar'a Gemini API anahtarını gir.", 5000), 1500);
updateIdleText();
setTimeout(() => keepListening(0), 1200);
N && N.ready();
