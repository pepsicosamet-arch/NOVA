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

**Çipler** (Çipler sekmesi)
- Dört ayrı kişilik var, her birinin kendi tasarımı, rengi, sesi, ses efekti ve konuşma tarzı var:
  - **NOVA:** Yıldız çekirdek, mavi, samimi.
  - **ATLAS:** Dönen tel kafes küre, altın rengi, sakin ve resmi uşak; derin ses ve yapay zekâ tınısı.
  - **LAYRA:** Ses dalgası çiçeği, pembe, neşeli; kadın sesi.
  - **KRONOS:** Kırık prizma ve keskin çokgenler, kırmızı, soğuk ve az konuşan; metalik ses.
- Sesle değiştirilebilir: "ATLAS'a geç", "LAYRA moduna geç". Adlar Ayarlar → Çipler'den değiştirilebilir.

**Mesajlaşma ve paylaşım** (Mesaj sekmesi)
- "WhatsApp'tan anneme geliyorum yaz" ya da "Ömrüm kişisine seni seviyorum diye mesaj gönder" → NOVA sormadan WhatsApp uygulamasını açar, Windows UI Otomasyonu ile kişiyi uygulamanın aramasında bulur ve mesajı gönderir.
- "Ahmet'e Telegram'dan yarın görüşürüz mesajı gönder" → Telegram'da sohbeti açıp gönderir. İstersen Telegram Bot ile tamamen arka planda gönderebilir.
- "X'te paylaş: NOVA 1.5 yayında" → X'te gönderi metni hazır açılır, Paylaş butonuna sen basarsın.
- PC'de WhatsApp, Telegram ya da X uygulaması kuruluysa NOVA onu kullanır; kurulu değilse web sürümünü açar.
- Numara gerekmez: NOVA uygulamayı açar, kişiyi uygulamanın kendi aramasında adıyla bulur ve mesajı gönderir.
- Haber bülteninden haberler tek tıkla X, WhatsApp ya da Telegram'da paylaşılabilir.

**Üst menü:** Gündem, Canlı TV, Takvim, Zaman, Harita, Notlar, Mesaj, Çipler, Komutlar, Ayarlar ve Hakkında. Hepsi yazılı ve her zaman görünür.

**Canlı TV:** TRT 1, ATV, Show TV, Star TV, Kanal D, NOW, TV8, Kanal 7, TRT Haber, NTV, Habertürk, CNN Türk, A Haber, Halk TV, Sözcü TV, tv100, TRT Spor ve TRT Çocuk. Kanallar kendi resmî canlı yayın sayfalarında, ayrı bir pencerede açılır. Sesle de olur: "TRT 1'i aç".

**Arka planda çalışma**
- Pencereyi kapatınca NOVA kapanmaz. Saatin yanındaki sistem tepsisinde durur ve dinlemeye devam eder; sesi doğrudan hoparlörden verir.
- "NOVA ekranı aç" dediğinde ya da tepsideki simgeye tıkladığında pencere geri gelir. "Arka plana geç" dediğinde pencere gizlenir.
- Ayarlar'dan "Windows açılınca arka planda başlasın" seçilebilir.
- Konuşma yazıları varsayılan olarak ekranda görünmez; Ayarlar'dan açılabilir.

**Kamera**
- "Kamerayı aç", "fotoğraf çek" ve "kamerada ne görüyorsun?" komutları var. NOVA kameradaki görüntüyü yapay zekâya gösterip anlatır.
- Fotoğraflar Resimler\NOVA klasörüne kaydedilir.

**Telefon bağlantısı**
- "Telefonumu bağla" dediğinde ya da Telefon menüsünü açtığında ekranda bir QR kod çıkar.
- Telefon aynı Wi-Fi'dayken QR kod okutulunca telefonda NOVA sayfası açılır.
- Bu sayfadan NOVA'ya yazılabilir, hızlı komut gönderilebilir, fotoğraf ve dosya yollanabilir (Resimler\NOVA\Telefon) ve iki yönlü pano paylaşılabilir.

**Söz kesme**
- NOVA konuşurken ya da düşünürken sen konuşmaya başlarsan hemen susar, düşünmeyi bırakır ve seni dinler. Ayarlar'dan kapatılabilir.

**Yapay zekâ ile mesaj yazdırma**
- "Bana aşk dolu bir mesaj hazırla ve ömrüm kişisine WhatsApp'tan gönder" → NOVA mesajı kendisi yazar ve gönderir.
- NOVA'ya bir şey yazdırdıktan sonra "ömrüm kişisine gönder" ya da "bunu gönder" dersen son yazdığını gönderir.

**Harita**
- Harita artık ortada büyük bir ekran olarak açılıyor. Koyu, sokak ve uydu görünümü var.
- "Konumum" düğmesi, araçla ya da yürüyerek yol tarifi ve WhatsApp'ta paylaşma da eklendi.

**Diğer**
- "100 dolar kaç TL", "Chrome'u kapat", "IP adresim ne", "tekrar et", "daha yavaş konuş", "tam ekran yap"
- "Son depremler" → AFAD verisinden son depremleri söyler.
- "Akşam ezanı ne zaman?" ya da "namaz vakitleri" → Diyanet hesabıyla bugünkü vakitleri söyler.
- "25 çarpı 4 kaç eder", "200'ün yüzde 15'i kaç" → hızlı hesap yapar.
- "Panodakini oku" → kopyaladığın metni sesli okur.
- "Bilgisayarı kapat / yeniden başlat / uyut" → önce onay ister; kapatmayı 15 saniye içinde "iptal" diyerek durdurabilirsin.

**Müzik**
- "YouTube'da Duman çal", "Sezen Aksu şarkısını çal" ve "biraz müzik aç" komutları ilk videoyu doğrudan oynatır.
- "Spotify'da Tarkan çal" komutu Spotify'da aramayı açar.
- Varsayılan kaynak Ayarlar'dan seçilir: YouTube, YouTube Music ya da Spotify.

**Haber bülteni**
- "Haberleri göster" ya da "son dakika haberlerini oku" dediğinde ekranda büyük, görselli bir bülten açılır.
- NOVA haberleri okurken okuduğu başlık öne çıkar.

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
