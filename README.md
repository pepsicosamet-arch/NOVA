# NOVA

**NOVA**, Samet Şahin'in tasarlayıp geliştirdiği kişisel, sesli bir masaüstü asistanıdır.
Beyni Google Gemini, OpenAI ChatGPT ya da kendi yapay zekandır. Mikrofona basmadan sürekli dinler,
Türkçe konuşur, bilgisayarda komut uygular ve kendini GitHub üzerinden günceller.

Instagram · TikTok · YouTube: **@xsametsahinx**

## İndir
En son sürümün kurulum dosyası **Releases** sayfasında: `NOVA-x.y.z-Windows-Setup.exe`.
Kurduktan sonra NOVA yeni sürümleri kendisi bulur. Üst çubukta **"Yeni sürüm · Güncelle"** çıkınca tıklaman yeterli.

## Özellikler
**Arayüz panelleri** (sağdaki panel)
- **Haberler:** Gündem, son dakika, dünya, ekonomi, spor ve teknoloji haberleri. Kaynaklar NTV, TRT Haber ve BBC Türkçe. NOVA başlıkları sesli de okur.
- **Takvim:** Aylık görünüm. Etkinlik ekleyip silebilirsin. Etkinlikten önce hatırlatma yapar.
- **Zaman:** Hızlı zamanlayıcılar, dakika ile hatırlatıcı ve saat ile alarm. Geri sayım canlı görünür.
- **Harita:** Yer arama ve işaretleme. Tek tıkla Google Haritalar'da yol tarifi açar.
- **Notlar:** Not yazma, okuma ve silme.
- **Sol panel:** 5 günlük hava durumu, döviz ve gram altın, sistem durumu (işlemci, bellek, pil).

**Sesli komut örnekleri**
- "Nova uyan" · "uyu"
- "Son dakika haberlerini oku" · "spor haberlerini göster"
- "Yarın saat 15:30 dişçi randevusu takvime ekle" · "Bugün takvimimde ne var?"
- "10 dakika sonra çayı hatırlat" · "Saat 7'de alarm kur" · "Ne kadar kaldı?"
- "Haritada Galata Kulesi'ni göster"
- "Dolar kaç?" · "Altın ne kadar?"
- "Manisa'da hava nasıl?"
- "Ekranda ne var?" (ekranına bakıp yorumlar)
- "Not al: yarın markete git" · "Notlarımı oku"
- "YouTube'da lofi aç" · "Google'da uzay haberleri ara" · "Hesap makinesini aç"
- "Sesi kıs" · "Müziği durdur"
- "Güncelleme var mı?"
- "Seni kim yaptı?"

**Beyin:** Gemini, ChatGPT ya da kendi yapay zekan seçilebilir. Kendi yapay zekan için OpenAI uyumlu her sunucu olur: Ollama, LM Studio ya da kendi API'n. Biri çalışmazsa NOVA diğerine geçer. Google eski bir Gemini modelini kapatırsa NOVA önerilen yeni modele kendiliğinden geçer.

## Güncelleme yayınlamak (geliştirici için)
1. Kodda değişikliği yap ve GitHub'a gönder (push).
2. `novaapp/__init__.py` dosyasındaki `VERSION` değerini artır (örneğin `"1.3.1"`) ve main dalına gönder. İstersen `v1.3.1` gibi bir etiket (tag) de gönderebilirsin.
3. GitHub Actions EXE'yi ve kurulum dosyasını derler, ardından **Releases**'e ekler. Bu yaklaşık 5-10 dakika sürer.
4. NOVA kullanan herkes açılışta "Yeni sürüm" uyarısını görür. Tek tıkla indirip sessizce kurar ve NOVA yeniden açılır.

Güncellemelerin hangi depodan alınacağı Ayarlar → Güncelleme bölümünde yazar (`pepsicosamet-arch/nova`).

## Bilgisayarda derleme
- `build.bat` dosyasına çift tıkla. Gerekirse Python 3.12'yi kendisi kurar.
  - EXE şuraya çıkar: `dist\NOVA\NOVA.exe`
  - Inno Setup 6 kuruluysa kurulum dosyası şuraya çıkar: `Output\`
- NOVA'yı **`NOVA Baslat.bat`** ile aç. `main.py`'ye doğrudan çift tıklama.

## İlk açılış
Ayarlar'a bir API anahtarı gir:
- Gemini için ücretsiz anahtar: https://aistudio.google.com/apikey
- ChatGPT için anahtar: https://platform.openai.com/api-keys

Ayarlar, takvim ve kayıtlar `%APPDATA%\NOVA\` klasöründe tutulur. API anahtarların yalnızca bu klasörde durur, GitHub'a gitmez.

## Sorun giderme
- Hata kaydı: `%APPDATA%\NOVA\nova.log`. Program çökerse ayrıca `nova-cokme.log` oluşur.
- NOVA'nın penceresi Microsoft Edge'in uygulama modunda açılır, Edge her Windows'ta kuruludur.
- NOVA seni duymuyorsa: Windows Ayarlar → Gizlilik ve güvenlik → Mikrofon → "Masaüstü uygulamalarının mikrofona erişmesine izin ver" seçeneğini aç.

## Lisanslar
- Harita: [Leaflet](https://leafletjs.com) (BSD-2). Harita görselleri © OpenStreetMap katkıcıları, © CARTO.
- Hava durumu: Open-Meteo. Kurlar: Truncgil Finans ve TCMB.

© 2026 Samet Şahin
