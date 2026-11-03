package com.sametsahin.nova;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * NOVA Android — Samet Şahin.
 * Arayüz assets/www içindeki web sayfasıdır; bu sınıf ona telefonun yeteneklerini (konuşma tanıma,
 * sesli okuma, ağ, uygulama açma, paylaşma) "Native" adlı köprüyle verir.
 */
public class MainActivity extends Activity {
    static final String HOST = "appassets.androidplatform.net";
    static final String START = "https://" + HOST + "/www/index.html";
    static final int REQ_MIC = 11, REQ_CAM = 12;

    WebView web;
    final Handler ui = new Handler(Looper.getMainLooper());
    final ExecutorService pool = Executors.newFixedThreadPool(4);
    SpeechRecognizer recognizer;
    TextToSpeech tts;
    boolean ttsReady = false;
    String pendingShare = null;
    PermissionRequest pendingCam = null;
    String pendingListenLang = null;
    long lastRms = 0;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        web = new WebView(this);
        web.setBackgroundColor(0xFF05070F);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setTextZoom(100);
        s.setUserAgentString(s.getUserAgentString() + " NOVA-Android/" + version());

        web.addJavascriptInterface(new Bridge(), "Native");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (!HOST.equals(u.getHost())) return null;
                String path = u.getPath() == null ? "" : u.getPath();
                if (path.startsWith("/")) path = path.substring(1);
                try {
                    InputStream in = getAssets().open(path);
                    WebResourceResponse res = new WebResourceResponse(mime(path), "utf-8", in);
                    java.util.Map<String, String> h = new java.util.HashMap<>();
                    h.put("Cache-Control", "no-cache");
                    res.setResponseHeaders(h);
                    return res;
                } catch (Exception e) {
                    return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", null, null);
                }
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (HOST.equals(u.getHost())) return false;
                openExternal(u.toString());
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest req) {
                if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    req.grant(req.getResources());
                } else {
                    pendingCam = req;
                    requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAM);
                }
            }
        });

        tts = new TextToSpeech(this, st -> {
            if (st == TextToSpeech.SUCCESS) {
                tts.setLanguage(new Locale("tr", "TR"));
                ttsReady = true;
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String id) { emit("speak_start", id); }
                    @Override public void onDone(String id) { emit("speak_done", id); }
                    @Override public void onError(String id) { emit("speak_done", id); }
                });
                emit("tts_ready", "1");
            }
        });

        handleIntent(getIntent());
        web.loadUrl(START);
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
        }
    }

    @Override
    protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        handleIntent(i);
        if (pendingShare != null) flushShare();
    }

    void handleIntent(Intent i) {
        if (i != null && Intent.ACTION_SEND.equals(i.getAction())) {
            pendingShare = i.getStringExtra(Intent.EXTRA_TEXT);
        }
    }

    void flushShare() {
        if (pendingShare == null) return;
        emit("shared_text", pendingShare);
        pendingShare = null;
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] perms, int[] res) {
        boolean ok = res.length > 0 && res[0] == PackageManager.PERMISSION_GRANTED;
        if (req == REQ_CAM && pendingCam != null) {
            if (ok) pendingCam.grant(pendingCam.getResources()); else pendingCam.deny();
            pendingCam = null;
        }
        if (req == REQ_MIC) {
            emit("mic_permission", ok ? "1" : "0");
            if (ok && pendingListenLang != null) { String l = pendingListenLang; pendingListenLang = null; startListen(l); }
        }
    }

    @Override
    public boolean onKeyDown(int code, KeyEvent e) {
        if (code == KeyEvent.KEYCODE_BACK) {
            web.evaluateJavascript("window.__back ? window.__back() : false", v -> {
                if (!"true".equals(v)) moveTaskToBack(true);
            });
            return true;
        }
        return super.onKeyDown(code, e);
    }

    @Override
    protected void onPause() {
        super.onPause();
        emit("app_pause", "1");
    }

    @Override
    protected void onResume() {
        super.onResume();
        emit("app_resume", "1");
    }

    @Override
    protected void onDestroy() {
        if (recognizer != null) recognizer.destroy();
        if (tts != null) tts.shutdown();
        pool.shutdownNow();
        super.onDestroy();
    }

    // ---------------- yardımcılar ----------------
    String version() {
        try { return getPackageManager().getPackageInfo(getPackageName(), 0).versionName; }
        catch (Exception e) { return "?"; }
    }

    static String mime(String p) {
        String l = p.toLowerCase(Locale.ROOT);
        if (l.endsWith(".html")) return "text/html";
        if (l.endsWith(".js")) return "application/javascript";
        if (l.endsWith(".css")) return "text/css";
        if (l.endsWith(".png")) return "image/png";
        if (l.endsWith(".jpg") || l.endsWith(".jpeg")) return "image/jpeg";
        if (l.endsWith(".svg")) return "image/svg+xml";
        if (l.endsWith(".json")) return "application/json";
        if (l.endsWith(".woff2")) return "font/woff2";
        return "application/octet-stream";
    }

    /** JS tarafına olay gönder: window.__native(type, data) */
    void emit(String type, String data) {
        final String js = "window.__native && window.__native(" + JSONObject.quote(type) + "," + JSONObject.quote(data == null ? "" : data) + ")";
        ui.post(() -> { if (web != null) web.evaluateJavascript(js, null); });
    }

    boolean openExternal(String url) {
        try {
            Intent i;
            if (url.startsWith("intent:")) {
                i = Intent.parseUri(url, Intent.URI_INTENT_SCHEME);
            } else {
                i = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            }
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
            return true;
        } catch (ActivityNotFoundException e) {
            return false;
        } catch (Exception e) {
            return false;
        }
    }

    void startListen(String lang) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            pendingListenLang = lang;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
            return;
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            emit("listen_error", "unavailable");
            return;
        }
        if (tts != null && tts.isSpeaking()) tts.stop();
        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(this);
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle p) { emit("listen_start", ""); }
                @Override public void onBeginningOfSpeech() { emit("hearing", ""); }
                @Override public void onRmsChanged(float db) {
                    long now = System.currentTimeMillis();
                    if (now - lastRms > 60) { lastRms = now; emit("rms", String.valueOf(db)); }
                }
                @Override public void onBufferReceived(byte[] buf) {}
                @Override public void onEndOfSpeech() { emit("listen_end", ""); }
                @Override public void onError(int err) { emit("listen_error", String.valueOf(err)); }
                @Override public void onResults(Bundle r) {
                    ArrayList<String> l = r.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    emit("heard", l != null && !l.isEmpty() ? l.get(0) : "");
                }
                @Override public void onPartialResults(Bundle r) {
                    ArrayList<String> l = r.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (l != null && !l.isEmpty()) emit("partial", l.get(0));
                }
                @Override public void onEvent(int t, Bundle p) {}
            });
        }
        Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang == null || lang.isEmpty() ? "tr-TR" : lang);
        i.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        i.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getPackageName());
        try { recognizer.cancel(); } catch (Exception ignored) {}
        recognizer.startListening(i);
    }

    static String hex(byte[] b, boolean upper) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format(upper ? "%02X" : "%02x", x));
        return sb.toString();
    }

    // ---------------- JS köprüsü ----------------
    class Bridge {
        @JavascriptInterface public String version() { return MainActivity.this.version(); }

        @JavascriptInterface public String device() {
            boolean tablet = getResources().getConfiguration().smallestScreenWidthDp >= 600;
            return (tablet ? "tablet" : "phone") + "|" + Build.MANUFACTURER + " " + Build.MODEL + "|" + Build.VERSION.SDK_INT;
        }

        @JavascriptInterface public void ready() { ui.post(MainActivity.this::flushShare); }

        /** Ağ isteği (CORS yok). Sonuç: __native("http", {id,status,body}) */
        @JavascriptInterface
        public void http(final String id, final String method, final String url, final String headers, final String body) {
            pool.execute(() -> {
                JSONObject out = new JSONObject();
                try {
                    out.put("id", id);
                    HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                    c.setRequestMethod(method == null || method.isEmpty() ? "GET" : method);
                    c.setConnectTimeout(12000);
                    c.setReadTimeout(45000);
                    c.setInstanceFollowRedirects(true);
                    c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android " + Build.VERSION.RELEASE + ") NOVA-Android/" + MainActivity.this.version());
                    c.setRequestProperty("Accept-Language", "tr-TR,tr;q=0.9");
                    if (headers != null && !headers.isEmpty()) {
                        JSONObject h = new JSONObject(headers);
                        Iterator<String> it = h.keys();
                        while (it.hasNext()) { String k = it.next(); c.setRequestProperty(k, h.getString(k)); }
                    }
                    if (body != null && !body.isEmpty()) {
                        c.setDoOutput(true);
                        byte[] data = body.getBytes(StandardCharsets.UTF_8);
                        c.setFixedLengthStreamingMode(data.length);
                        try (OutputStream os = c.getOutputStream()) { os.write(data); }
                    }
                    int code = c.getResponseCode();
                    InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
                    ByteArrayOutputStream bo = new ByteArrayOutputStream();
                    if (in != null) {
                        byte[] buf = new byte[16384]; int n;
                        while ((n = in.read(buf)) > 0) { bo.write(buf, 0, n); if (bo.size() > 6_000_000) break; }
                        in.close();
                    }
                    String ct = c.getContentType() == null ? "" : c.getContentType().toLowerCase(Locale.ROOT);
                    String charset = ct.contains("charset=iso-8859-9") ? "ISO-8859-9" : ct.contains("windows-1254") ? "windows-1254" : "UTF-8";
                    out.put("status", code);
                    out.put("body", new String(bo.toByteArray(), charset));
                    c.disconnect();
                } catch (Exception e) {
                    try { out.put("status", 0); out.put("body", String.valueOf(e.getMessage())); } catch (Exception ignored) {}
                }
                emit("http", out.toString());
            });
        }

        @JavascriptInterface public void listen(final String lang) { ui.post(() -> startListen(lang)); }

        @JavascriptInterface public void stopListen() {
            ui.post(() -> { if (recognizer != null) try { recognizer.cancel(); } catch (Exception ignored) {} });
        }

        @JavascriptInterface public boolean ttsReady() { return ttsReady; }

        /** Sesli oku. voiceHint: "female" | "male" | "" */
        @JavascriptInterface
        public void speak(final String text, final float pitch, final float rate, final String id, final String voiceHint, final boolean flush) {
            ui.post(() -> {
                if (!ttsReady) { emit("speak_done", id); return; }
                tts.setPitch(pitch <= 0 ? 1f : pitch);
                tts.setSpeechRate(rate <= 0 ? 1f : rate);
                try {
                    if (voiceHint != null && !voiceHint.isEmpty() && tts.getVoices() != null) {
                        Voice best = null;
                        for (Voice v : tts.getVoices()) {
                            if (v.getLocale() == null || !"tr".equals(v.getLocale().getLanguage())) continue;
                            if (v.isNetworkConnectionRequired()) continue;
                            String n = v.getName().toLowerCase(Locale.ROOT);
                            boolean male = n.contains("male") && !n.contains("female") || n.contains("-tmc") || n.contains("-ama") || n.contains("#male");
                            if ("male".equals(voiceHint) == male) { best = v; break; }
                            if (best == null) best = v;
                        }
                        if (best != null) tts.setVoice(best);
                    }
                } catch (Exception ignored) {}
                Bundle p = new Bundle();
                p.putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_MUSIC);
                tts.speak(text, flush ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD, p, id);
            });
        }

        @JavascriptInterface public void stopSpeak() { ui.post(() -> { if (tts != null) tts.stop(); }); }

        @JavascriptInterface public boolean openUrl(String url) { return openExternal(url); }

        /** Yüklü bir uygulamayı adıyla aç. Bulunan uygulamanın adını döndürür, yoksa "". */
        @JavascriptInterface
        public String openApp(String name) {
            PackageManager pm = getPackageManager();
            Intent q = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
            List<ResolveInfo> apps = pm.queryIntentActivities(q, 0);
            String want = name.toLowerCase(new Locale("tr")).trim();
            ResolveInfo best = null; int bestScore = 0;
            for (ResolveInfo r : apps) {
                String label = String.valueOf(r.loadLabel(pm)).toLowerCase(new Locale("tr"));
                String pkg = r.activityInfo.packageName.toLowerCase(Locale.ROOT);
                int score = label.equals(want) ? 100 : label.startsWith(want) ? 80 : label.contains(want) ? 60
                        : pkg.contains(want.replace(" ", "")) ? 40 : 0;
                if (score > bestScore) { bestScore = score; best = r; }
            }
            if (best == null) return "";
            Intent i = pm.getLaunchIntentForPackage(best.activityInfo.packageName);
            if (i == null) return "";
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
            return String.valueOf(best.loadLabel(pm));
        }

        @JavascriptInterface
        public String apps() {
            PackageManager pm = getPackageManager();
            Intent q = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
            JSONArray a = new JSONArray();
            for (ResolveInfo r : pm.queryIntentActivities(q, 0)) a.put(String.valueOf(r.loadLabel(pm)));
            return a.toString();
        }

        @JavascriptInterface public boolean hasApp(String pkg) {
            try { getPackageManager().getPackageInfo(pkg, 0); return true; } catch (Exception e) { return false; }
        }

        /** Metni paylaş. pkg boşsa seçim ekranı açılır (örn. com.whatsapp, org.telegram.messenger). */
        @JavascriptInterface
        public boolean share(String text, String pkg) {
            Intent i = new Intent(Intent.ACTION_SEND);
            i.setType("text/plain");
            i.putExtra(Intent.EXTRA_TEXT, text);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                if (pkg != null && !pkg.isEmpty()) { i.setPackage(pkg); startActivity(i); }
                else startActivity(Intent.createChooser(i, "Paylaş").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                return true;
            } catch (Exception e) { return false; }
        }

        @JavascriptInterface public void copy(String text) {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            cm.setPrimaryClip(ClipData.newPlainText("NOVA", text));
        }

        @JavascriptInterface public String paste() {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (!cm.hasPrimaryClip() || cm.getPrimaryClip().getItemCount() == 0) return "";
            CharSequence t = cm.getPrimaryClip().getItemAt(0).getText();
            return t == null ? "" : t.toString();
        }

        @JavascriptInterface public void vibrate(int ms) {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v == null) return;
            if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
            else v.vibrate(ms);
        }

        @JavascriptInterface public void toast(String t) { ui.post(() -> Toast.makeText(MainActivity.this, t, Toast.LENGTH_SHORT).show()); }

        @JavascriptInterface public void keepAwake(boolean on) {
            ui.post(() -> {
                if (on) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            });
        }

        @JavascriptInterface public void volume(String dir) {
            AudioManager am = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
            int d = "up".equals(dir) ? AudioManager.ADJUST_RAISE : "down".equals(dir) ? AudioManager.ADJUST_LOWER
                    : "mute".equals(dir) ? AudioManager.ADJUST_TOGGLE_MUTE : AudioManager.ADJUST_SAME;
            am.adjustStreamVolume(AudioManager.STREAM_MUSIC, d, AudioManager.FLAG_SHOW_UI);
        }

        @JavascriptInterface public void media(String key) {
            AudioManager am = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
            int k = "next".equals(key) ? KeyEvent.KEYCODE_MEDIA_NEXT : "prev".equals(key) ? KeyEvent.KEYCODE_MEDIA_PREVIOUS
                    : "pause".equals(key) ? KeyEvent.KEYCODE_MEDIA_PAUSE : "play".equals(key) ? KeyEvent.KEYCODE_MEDIA_PLAY
                    : KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE;
            am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, k));
            am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, k));
        }

        @JavascriptInterface public void call(String number) {
            openExternal("tel:" + number);
        }

        @JavascriptInterface public String sha256(String s) {
            try { return hex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)), false); }
            catch (Exception e) { return ""; }
        }

        @JavascriptInterface public String hmacSha256(String key, String msg) {
            try {
                Mac m = Mac.getInstance("HmacSHA256");
                m.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
                return hex(m.doFinal(msg.getBytes(StandardCharsets.UTF_8)), true);
            } catch (Exception e) { return ""; }
        }

        @JavascriptInterface public void immersive(boolean on) {
            ui.post(() -> {
                int f = on ? (View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE) : 0;
                getWindow().getDecorView().setSystemUiVisibility(f);
            });
        }
    }
}
