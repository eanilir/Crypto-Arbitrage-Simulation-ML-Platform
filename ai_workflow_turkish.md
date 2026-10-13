# AI Workflow Takip Listesi

> **Amaç:** Crypto Arbitrage Simulation & ML Platform projesinin geliştirme sürecini adım adım takip etmek, AI destekli kod geliştirmeyi kontrol altında tutmak ve tamamlanan işleri testlerle doğrulamak.
>
> **Proje modu:** Simulation / Backtesting / Paper Trading. Gerçek para kullanılmayacak ve gerçek emir gönderilmeyecek.
>
> **Araştırma odağı:** Piyasa verisinin eskiliği ve simüle edilen işlem gecikmesinin maliyet sonrası arbitraj kârlılığına etkisini incelemek ve ML filtresini kural tabanlı yöntemlerle karşılaştırmak.

## 1. Proje Temeli

- [x] Repo yapısını oluştur
- [x] Python environment seç
- [x] `README.md`, `.gitignore`, `.env.example` dosyalarını hazırla
- [x] Ortak kod standartlarını belirle
- [x] Loglama formatını belirle
- [x] Konfigürasyon yönetimi yaklaşımını belirle
- [x] Temel klasör yapısını oluştur

**Tamamlanma kriteri:** Proje yerel ortamda kurulabilir olmalı; konfigürasyon ve gizli bilgiler koddan ayrılmış olmalı.

## 2. Ortak Domain ve Veri Modeli

- [x] Exchange, symbol, price, spread ve opportunity için ortak veri modellerini tanımla
- [x] Zaman damgası standardını belirle
- [x] Symbol normalizasyon kuralını belirle
- [x] Veri validasyon kurallarını yaz
- [x] Hatalı veri formatları için hata tiplerini belirle
- [ ] Exchange event timestamp ile local receive timestamp ayrımını doğrula
- [ ] Negatif spread değerlerinin geçerli bir ekonomik sonuç olarak temsil edilebildiğini doğrula
- [ ] Veri modellerinin research ve simulation hedefleriyle uyumunu gözden geçir

**Tamamlanma kriteri:** Modeller geçerli ve geçersiz veriyi ayırmalı; negatif ekonomik sonuçları otomatik olarak bozuk veri kabul etmemeli.

## 3. Data Collector

- [x] Binance için REST veri çekme modülü yaz
- [x] Binance için WebSocket veri çekme modülü yaz
- [x] Bybit adapter'ını yaz
- [x] OKX adapter'ını yaz
- [x] Retry ve reconnect mekanizması ekle
- [x] Timeout yönetimi ekle
- [x] Duplicate veri kontrolü ekle
- [x] Collector loglarını standardize et
- [x] Collector için unit test yaz
- [x] BTC/USDT için kısa kontrollü veri toplama pilotunu yürüt
- [x] Exchange event timestamp ve local receive timestamp alanlarının anlamını doğrula
- [x] WebSocket veri kaybı, sequence gap ve reconnect davranışını gözlemle
- [x] Mesaj sıklığı, depolama büyümesi ve veri kalitesini ölç
- [x] Veri saklama ve retention politikası için geçici ölçüm temelli karar oluştur
- [x] Pilot sonuçlarını dokümante et

**Pilot planı:** Öncelikle BTC/USDT ile 3–7 günlük veri toplama denemesi yap. Sonuçlar yeterliyse ETH/USDT, XRP/USDT ve diğer borsalara yönelik kapsamı genişlet.

**Pilot notu:** Kısa kontrollü pilot ve ölçüm aracı `docs/btc_usdt_pilot_report.md` içinde kaydedildi. 3–7 günlük kesintisiz üretim koşusu, kesin diff-depth sequence doğrulaması ve CPU/bellek ölçümü açık takip işidir.

**Tamamlanma kriteri:** Collector yalnızca bağlantı kurmamalı; veri kalitesi, zaman damgaları, kopmalar ve depolama maliyeti açısından da değerlendirilmiş olmalı.

## 4. Data Standardization

- [x] Exchange bazlı cevapları ortak formata dönüştür
- [x] Bid, ask, last ve volume alanlarını normalize et
- [x] Timestamp dönüştürme katmanı ekle
- [x] Eksik alanlar için validasyon koy
- [x] Bozuk kayıtları reject et
- [x] Normalizasyon testlerini yaz
- [ ] Best bid/ask quantity alanlarını gerekli hesaplamalar için doğrula
- [ ] Order-book depth verisinin hangi borsalarda ve formatlarda kullanılabildiğini doğrula
- [ ] UTC zaman standardını tüm veri akışında kontrol et
- [ ] Stale, missing ve out-of-order verilerin nasıl ele alınacağını dokümante et
- [ ] Veri kaynağı ve validation status bilgisini gerektiğinde kayıtlara ekle

**Tamamlanma kriteri:** Farklı borsalardan gelen veriler aynı hesaplama katmanında tutarlı şekilde kullanılabilmeli. Eksik veriler uydurulmuş değerlerle doldurulmamalı.

## 5. Storage Katmanı

- [x] PostgreSQL şemasını tasarla
- [x] Redis kullanım alanlarını netleştir
- [x] InfluxDB kullanım alanlarını netleştir
- [x] Market data için storage adapter yaz
- [x] Opportunity/result kayıtları için PostgreSQL repository yaz
- [x] Cache okuma/yazma katmanını yaz
- [x] Storage entegrasyon testleri yaz
- [ ] Market-data timestamp ve veri kaynağı alanlarının kalıcı olarak saklandığını doğrula
- [ ] Backtest ve experiment configuration kayıtlarını tasarla
- [ ] Model version ve evaluation sonuçlarının izlenebilirliğini planla
- [ ] Retention ve eski veri temizleme politikasını belirle
- [ ] Ham veri ve işlenmiş veri saklama maliyetini değerlendir

**Tamamlanma kriteri:** Market verisi, fırsatlar, simülasyon sonuçları ve deney konfigürasyonları birbirleriyle ilişkilendirilebilir olmalı.

## 6. Arbitrage Engine

- [x] Cross-exchange fiyat karşılaştırma mantığını yaz
- [x] Spread hesaplama fonksiyonunu yaz
- [x] Fee hesaplama fonksiyonunu yaz
- [x] Slippage modelini yaz
- [x] Latency etkisini hesaba katan katmanı yaz
- [x] Net profit hesaplama fonksiyonunu yaz
- [x] Minimum kârlılık eşiği tanımla
- [x] Opportunity logging ekle
- [x] Arbitrage unit testleri yaz
- [ ] Negatif spread doğrulamasını gözden geçir ve gerekiyorsa düzelt
- [ ] Top-of-book spread ile order-book depth kullanılarak hesaplanan maliyetleri açıkça ayır
- [ ] Net profit hesaplamasında slippage'ın iki kere düşülmediğini doğrula
- [ ] Notional ve quantity hesaplarının anlamını netleştir
- [ ] Order-book derinliği yetersiz olduğunda doğru davranışı test et
- [ ] Fee rate ve diğer maliyet varsayımlarını konfigürasyondan yönet
- [ ] Candidate, gross-positive candidate ve net-profitable candidate ayrımını uygula veya doğrula
- [ ] Data staleness ve simulated latency değişkenlerini ayrı alanlar olarak ele al

### Kritik hesaplama kuralları

1. Negatif spread, tek başına invalid data değildir.
2. Pozitif gross spread, net kâr anlamına gelmez.
3. Order-book walking ile hesaplanan buy cost ve sell proceeds slippage etkisini zaten içerebilir. Bu durumda aynı slippage tekrar düşülmemeli.
4. Order book'ta yeterli miktar yoksa mevcut olmayan likidite varsayılmamalı.
5. `latency_bps` üzerinden hesaplanan maliyet, gerçek ağ gecikmesinin ölçümü değil, bir maliyet varsayımıdır.
6. Market-data staleness ve simüle edilen execution latency birbirinden ayrı tutulmalı.

**Tamamlanma kriteri:** Finansal hesaplamalar açık tanımlara dayanmalı ve bağımsız olarak hesaplanmış beklenen sonuçlarla test edilmeli.

## 7. Feature Engineering

- [x] Price difference feature'ını üret
- [x] Spread percentage feature'ını üret
- [x] Volume feature'larını üret
- [x] Volatility feature'ını üret
- [x] Fee/slippage/latency feature'larını üret
- [x] Exchange pair feature'ını üret
- [x] Feature pipeline testlerini yaz
- [ ] Market-data age feature'ının tanımını ve hesaplanmasını doğrula
- [ ] Order-book depth feature'larını veri bulunabilirliğine göre değerlendir
- [ ] Exchange timestamp farkının neyi temsil ettiğini dokümante et
- [ ] Her feature'ın karar anında gerçekten erişilebilir olduğunu doğrula
- [ ] Future data leakage kontrolleri ekle
- [ ] Feature set sürümleme yaklaşımını belirle

**Tamamlanma kriteri:** Feature'lar yalnızca karar anında bilinebilen bilgilerden oluşmalı. Gelecekte oluşan fiyat veya simülasyon sonucu model girdisi olarak kullanılmamalı.

## 8. ML Service

### 8.1 Dataset ve Target

- [ ] Dataset hazırlama işini yaz
- [ ] Her dataset satırının neyi temsil ettiğini tanımla
- [ ] Target label tanımını yap
- [ ] Label üretiminde kullanılan execution policy ve değerlendirme süresini dokümante et
- [ ] Kârlı ve kârsız adayları dataset'e dahil et
- [ ] Yalnızca fırsat görülen dönemlerden veri seçilmesinden kaynaklanan selection bias riskini kontrol et
- [ ] Dataset generation testlerini yaz
- [ ] Feature ve label arasında future data leakage olmadığını doğrula

**Başlangıç target tanımı:**

- `1`: Tanımlanmış simülasyon politikası ve maliyet varsayımları altında net simüle edilmiş kâr pozitif.
- `0`: Tanımlanmış simülasyon politikası ve maliyet varsayımları altında net simüle edilmiş kâr sıfır veya negatif.

Label, yalnızca ilk gözlenen gross spread'e göre oluşturulmamalı. Araştırma hedefi gecikme sonrasındaki maliyet sonrası kârlılıksa, label da bunu temsil etmeli.

### 8.2 Training Pipeline

- [ ] Train/validation/test split pipeline yaz
- [ ] Kronolojik veri bölme yaklaşımını uygula
- [ ] Eğitim ve değerlendirme dönemlerini dokümante et
- [ ] Model threshold seçimini validation verisiyle sınırla
- [ ] Final test verisinin model seçiminde kullanılmadığını doğrula
- [ ] Gerekirse walk-forward evaluation tasarla

**Kural:** Finansal zaman serileri için yalnızca rastgele train/test split kullanma. Gelecekteki gözlemlerin geçmiş eğitim verisine sızmasını önle.

### 8.3 Models

- [ ] Logistic Regression baseline eğitimi yaz
- [ ] Random Forest eğitimi yaz
- [ ] Gradient Boosting eğitimi yaz
- [ ] Model hyperparameter konfigürasyonlarını kaydet
- [ ] Model eğitim sonuçlarını kaydet
- [ ] Model versiyonlama yaklaşımını belirle
- [ ] Model yükleme ve inference davranışını test et

### 8.4 Evaluation

- [ ] Precision hesapla
- [ ] Recall hesapla
- [ ] F1-score hesapla
- [ ] Confusion matrix oluştur
- [ ] PR-AUC değerini değerlendir
- [ ] ROC-AUC değerini uygun olduğunda hesapla
- [ ] Accuracy değerini tek başarı ölçütü olarak kullanmadığını doğrula
- [ ] ML sonuçlarını rule-based baselines ile karşılaştır
- [ ] Sonuçları aynı simulation assumptions altında değerlendir

### 8.5 Prediction API

- [ ] Prediction API'yi yaz
- [ ] Request/response validation ekle
- [ ] Model version bilgisini response veya kayıtlarla ilişkilendir
- [ ] Model yüklenememesi ve inference hatalarını ele al
- [ ] ML servis testlerini yaz
- [ ] Model çıktısının gerçek trade emri oluşturmadığını doğrula

**Tamamlanma kriteri:** Dataset, target, training ve evaluation süreci tekrarlanabilir olmalı. ML'nin baseline'dan daha iyi olduğu önceden varsayılmamalı.

## 9. Simulation Engine

- [ ] Virtual wallet modelini yaz
- [ ] Virtual balance yönetimini yaz
- [ ] Simulated order mantığını yaz
- [ ] BUY/SELL simülasyonunu yaz
- [ ] Fee/slippage etkisini simülasyona ekle
- [ ] Market-data staleness kurallarını simülasyona ekle
- [ ] Simulated latency senaryolarını uygula
- [ ] P&L hesaplama modülünü yaz
- [ ] Trade history kaydı ekle
- [ ] Equity curve hesaplamasını ekle
- [ ] Drawdown ve performans metriklerini yaz
- [ ] Inventory varsayımlarını dokümante et
- [ ] Partial fill kapsamını belirle veya kapsam dışı olduğunu belirt
- [ ] Simulation testlerini yaz

### Simulation kuralları

- Gerçek emir gönderilmez.
- Gerçek para veya gerçek bakiye kullanılmaz.
- Simüle edilen işlem, kullanılan fiyat, miktar, ücret ve diğer maliyet varsayımlarıyla kaydedilir.
- Her iki borsada gerekli envanterin mevcut olduğu varsayılıyorsa bu açıkça belirtilir.
- Simülasyonun modellemediği gerçek dünya koşulları sonuç raporlarında açıklanır.

**Tamamlanma kriteri:** Virtual balance ve P&L hesapları test edilmiş olmalı; aynı veri ve konfigürasyonla sonuçlar tekrarlanabilir olmalı.

## 10. Backtesting

- [ ] Historical data loader yaz
- [ ] Historical replay mekanizması yaz
- [ ] Strategy execution akışını yaz
- [ ] Cost-aware backtest mantığını yaz
- [ ] Backtest konfigürasyonunu kaydet
- [ ] Backtest sonuçlarını kaydet
- [ ] Backtest metriklerini üret
- [ ] Kronolojik replay doğruluğunu test et
- [ ] Future data leakage olmadığını doğrula
- [ ] Backtest testlerini yaz

### Backtest karşılaştırmaları

- [ ] Gross-spread baseline
- [ ] Fee-aware baseline
- [ ] Cost-aware baseline
- [ ] ML-filtered baseline

Tüm yöntemler karşılaştırılabilir veri, fee ayarları ve execution assumptions kullanmalı.

**Tamamlanma kriteri:** Her backtest; veri dönemi, strateji, model sürümü, maliyetler ve deney ayarlarıyla yeniden üretilebilir olmalı.

## 11. Paper Trading

- [ ] Live public data akışını bağla
- [ ] Arbitrage engine ile bağla
- [ ] ML prediction ile bağla
- [ ] Simulation engine ile bağla
- [ ] Gerçek order göndermeyen bir pipeline oluştur
- [ ] Paper trading sonuçlarını kaydet
- [ ] Stale data durumunda davranışı doğrula
- [ ] Servis hatalarında simülasyonun nasıl duracağını veya devam edeceğini belirle
- [ ] Paper trading sonuçlarını backtest sonuçlarından ayrı raporla

**Tamamlanma kriteri:** Canlı public market data kullanılsa bile sistem yalnızca sanal karar ve sonuç üretmeli; borsaya gerçek emir gönderilmemeli.

## 12. FastAPI Katmanı

- [ ] App skeleton oluştur
- [ ] Health endpoint ekle
- [ ] Markets endpoint ekle
- [ ] Prices endpoint ekle
- [ ] Opportunities endpoint ekle
- [ ] Predictions endpoint ekle
- [ ] Trades endpoint ekle
- [ ] Portfolio endpoint ekle
- [ ] Performance endpoint ekle
- [ ] Backtest başlatma ve sonuç sorgulama endpoint'lerini değerlendir
- [ ] Request/response validation ekle
- [ ] Hata response standardını belirle
- [ ] API integration testleri yaz

**Tamamlanma kriteri:** Endpoint'ler dokümante edilmiş olmalı; hatalı istekler ve bağımlı servis hataları kontrollü biçimde ele alınmalı.

## 13. Logging ve Monitoring

- [ ] Structured logging formatını belirle
- [ ] Service bazlı log formatını uygula
- [ ] Request ID takibi ekle
- [ ] Error logging standardı ekle
- [ ] Metrics üretme katmanı oluştur
- [ ] Health check response'larını standardize et
- [ ] Uyarı/alert kriterlerini belirle
- [ ] Collector message count ve data gap metriklerini izle
- [ ] Reconnect ve service failure metriklerini izle
- [ ] Data staleness dağılımını takip et
- [ ] Backtest ve model evaluation sonuçlarını izle
- [ ] Loglarda secret sızmadığını test et

**Tamamlanma kriteri:** Sistem hatalarının veri toplama, hesaplama, storage, ML veya API kaynaklı olduğu ayırt edilebilmeli.

## 14. Testing Katmanı

- [ ] Unit test yapısını doğrula
- [ ] Integration test yapısını doğrula
- [ ] API testleri ekle
- [ ] Failure scenario testleri ekle
- [ ] Data validation testleri ekle
- [ ] Financial calculation testlerini tamamla
- [ ] Dataset ve target testlerini ekle
- [ ] Leakage kontrol testlerini ekle
- [ ] Simulation ve backtest testlerini ekle
- [ ] Performance test iskeleti oluştur
- [ ] Tekrarlanabilirlik testlerini ekle
- [ ] Docker Compose entegrasyon testlerini ekle

### Zorunlu finansal test senaryoları

- [ ] Negatif spread geçerli bir ekonomik sonuç olarak işleniyor
- [ ] Pozitif gross spread, maliyetlerden sonra negatif net kâr üretebiliyor
- [ ] Fee hesaplaması doğru
- [ ] Slippage iki kez düşülmüyor
- [ ] Yetersiz order-book depth durumunda uydurma likidite kullanılmıyor
- [ ] Invalid price ve quantity değerleri reddediliyor
- [ ] Stale data tanımlanmış kurala göre işleniyor
- [ ] Eksik exchange verisi uydurulmuyor
- [ ] Net profit bağımsız hesaplamayla doğrulanıyor
- [ ] Gelecek verisi feature olarak kullanılmıyor

### Önceki doğrulama kaydı

Daha önce bildirilen test sonucu:

`py -3.14 -m pytest -q tests/test_feature_engineering.py tests/test_data_collector.py tests/test_standardization.py tests/test_storage.py tests/test_arbitrage_engine.py`

Sonuç: `15 passed in 0.06s`

Bu sonuç yalnızca belirtilen testlerin o çalıştırmada başarılı olduğunu gösterir. Sonraki kod değişikliklerinden sonra testleri tekrar çalıştır ve sonucu yeni tarih/commit ile kaydet. Henüz çalıştırılmamış testleri başarılı olarak işaretleme.

## 15. Dockerization

- [ ] Her bağımsız servis için gerekli Dockerfile'ları yaz
- [ ] `.dockerignore` dosyalarını ekle
- [ ] Docker Compose dosyasını yaz
- [ ] Container health check ekle
- [ ] Restart policy belirle
- [ ] Non-root çalıştırma yaklaşımını uygula
- [ ] Image boyutunu küçültme adımlarını uygula
- [ ] Environment-based configuration kullanımını doğrula
- [ ] Persistent volume yapılandırmasını doğrula
- [ ] Container startup/shutdown davranışını test et
- [ ] Docker Compose ile tam açılışı doğrula

**Not:** Her modül için ayrı container oluşturmak zorunlu değildir. Container sınırları servis sorumluluklarına ve gerçek gereksinimlere göre belirlenmeli.

**Tamamlanma kriteri:** Gerekli servisler yerel ortamda belgelenmiş komutlarla başlatılabilmeli ve health check'leri doğrulanmalı.

## 16. Service Communication

- [ ] Servisler arası veri akışını netleştir
- [ ] API contract'larını tanımla
- [ ] DB ownership kurallarını belirle
- [ ] Redis kullanım sınırlarını belirle
- [ ] Servis bağımlılıklarını dokümante et
- [ ] Timeout ve retry davranışlarını tanımla
- [ ] Error handling kurallarını standardize et
- [ ] Duplicate event ve idempotency ihtiyacını değerlendir
- [ ] Servislerin sorumluluklarının gereksiz biçimde çakışmadığını kontrol et

**Tamamlanma kriteri:** Her servisin sorumluluğu ve kullandığı veri kaynakları açık olmalı. Servisler arası hatalar tüm sistemi kontrolsüz biçimde bozmamalı.

## 17. Security

- [ ] Secrets'i environment veya uygun secrets manager ile yönet
- [x] `.env` dosyasını Git dışında bırak
- [ ] API authentication ihtiyacını değerlendir ve gerekiyorsa uygula
- [ ] Input validation ekle
- [ ] Rate limiting ihtiyacını değerlendir
- [ ] DB erişimini private tut
- [ ] Container security kurallarını uygula
- [ ] Logging'de secret sızmasını engelle
- [ ] Least privilege yaklaşımını uygula
- [ ] Public market-data kullanımında gereksiz credential kullanma
- [ ] Gerçek trading ve withdrawal API izinlerini kullanma
- [ ] Dependency güvenliğini kontrol et

**Tamamlanma kriteri:** Kaynak kodda secret bulunmamalı; gereksiz yetki veya public erişim bırakılmamalı.

## 18. Fault Tolerance

- [x] Exchange failure retry mekanizması ekle
- [x] WebSocket reconnect ekle
- [ ] DB unavailable senaryolarını ele al
- [ ] Redis unavailable senaryolarını ele al
- [ ] Service crash recovery mekanizmasını doğrula
- [ ] Duplicate/missing data handling davranışını doğrula
- [ ] Timeout sonrası tekrar deneme sınırlarını belirle
- [ ] Tekrarlanan başarısızlıkların log ve metric üretmesini sağla
- [ ] Recovery sonrasında veri tutarlılığını test et

**Tamamlanma kriteri:** Geçici servis hataları kontrolsüz döngüye, sessiz veri kaybına veya uydurma fırsatlara neden olmamalı.

## 19. Cloud Hazırlığı

- [ ] Servisleri gerektiği ölçüde stateless hale getir
- [ ] Config'i environment-based yap
- [ ] Docker image'larını cloud uyumlu hale getir
- [ ] Managed service kararlarını gerçek ihtiyaçlara göre ver
- [ ] VPC ve security group tasarımını yap
- [ ] ECS mi EC2 mi kararını gerekçelendir
- [ ] RDS/ElastiCache gibi managed servisleri değerlendir
- [ ] Secrets management tasarla
- [ ] Cloud logging/monitoring planla
- [ ] Cost control planı yap
- [ ] Minimum gerekli kaynakları belirle
- [ ] Kullanılmayan kaynakların kapatılması ve silinmesi için prosedür hazırla
- [ ] AWS'ye geçmeden önce local Docker sistemini doğrula

**Tamamlanma kriteri:** AWS'ye geçiş teknik gereksinimlere, güvenliğe ve bütçeye dayalı bir kararla yapılmalı.

## 20. AWS Deployment

- [ ] Network altyapısını kur
- [ ] App runtime ortamını kur
- [ ] Load balancer gereksinimini değerlendir ve gerekiyorsa kur
- [ ] Managed database gereksinimini değerlendir
- [ ] Managed cache gereksinimini değerlendir
- [ ] Application secrets'i güvenli biçimde bağla
- [ ] Monitoring/logging'i bağla
- [ ] Deployment pipeline yaklaşımını belirle
- [ ] IAM least-privilege kurallarını uygula
- [ ] Private network ve security group ayarlarını doğrula
- [ ] Billing alert ve bütçe takibi kur
- [ ] Health check ve recovery davranışını doğrula
- [ ] Deployment ve cleanup dokümantasyonunu tamamla
- [ ] AWS kaynaklarının gereksiz ücret üretmediğini kontrol et

**Önemli:** AWS deployment zorunlu olarak hemen yapılmayacak. Önce yerel sistem ve araştırma pipeline'ı çalışır hale getirilecek. Kullanılacak AWS servisleri maliyet ve gereksinim değerlendirmesinden sonra seçilecek.

## 21. Research Experiments

- [ ] Gross-spread baseline sonuçlarını üret
- [ ] Fee-aware baseline sonuçlarını üret
- [ ] Cost-aware baseline sonuçlarını üret
- [ ] Market-data staleness deneylerini çalıştır
- [ ] Veri çözünürlüğü destekliyorsa latency senaryolarını çalıştır
- [ ] ML-filtered baseline sonuçlarını üret
- [ ] Bütün yöntemleri aynı veri ve execution assumptions altında karşılaştır
- [ ] Gerekirse feature ablation deneyi yap
- [ ] Chronological test period üzerinde değerlendirme yap
- [ ] Sonuç tabloları ve grafiklerini üret
- [ ] Deney konfigürasyonlarını ve model sürümlerini kaydet
- [ ] Sonuçların sınırlamalarını dokümante et
- [ ] Literatür taraması yapmadan novelty iddiasında bulunma

### Karşılaştırılacak temel sonuçlar

- Net simulated P&L.
- Seçilen aday ve simüle edilen işlem sayısı.
- Kârlı işlem oranı.
- Precision, recall ve F1.
- PR-AUC, uygun olduğunda.
- Toplam fee maliyeti.
- Tahmini slippage.
- Simülasyonda kullanılan latency maliyeti.
- Missed profitable candidates.
- Sonuçların farklı zaman aralıklarındaki tutarlılığı.

**Tamamlanma kriteri:** Sonuçlar araştırma sorusuna cevap vermeli. ML baseline'dan daha iyi değilse bu sonuç da açıkça raporlanmalı.

## 22. Son Stabilizasyon

- [ ] İlgili tüm unit testleri çalıştır
- [ ] Integration testleri çalıştır
- [ ] Failure testlerini çalıştır
- [ ] Metric takibini doğrula
- [ ] Docker Compose ile tam açılışı doğrula
- [ ] Health check sonuçlarını doğrula
- [ ] Backtest tekrar üretilebilirliğini doğrula
- [ ] Feature ve target leakage kontrollerini doğrula
- [ ] Güvenlik kontrol listesini gözden geçir
- [ ] AWS kullanılıyorsa health kontrolü yap
- [ ] AWS maliyetlerini ve açık kaynakları kontrol et
- [ ] Documentation eksiklerini tamamla
- [ ] README kurulum adımlarını temiz bir ortamda test et
- [ ] Sonuçları ve bilinen sınırlamaları raporla

**Tamamlanma kriteri:** Sistem belgelenmiş adımlarla yeniden kurulabilmeli; test durumu ve bilinen sınırlamalar açıkça belirtilmeli.

---

## AI ile Çalışma Kuralları

Bu kurallar tüm geliştirme aşamalarında geçerlidir.

- [ ] AI'ya görev vermeden önce ilgili dosyaları ve mevcut implementasyonu incele.
- [ ] Değişiklikten önce problemin ve beklenen davranışın tanımını yap.
- [ ] Büyük çaplı rewrite yerine küçük ve test edilebilir değişiklikleri tercih et.
- [ ] Var olan çalışan kodu gerekçesiz değiştirme.
- [ ] Dosya, fonksiyon veya dependency varmış gibi varsayım yapma; repository'yi kontrol et.
- [ ] Yeni kodla birlikte uygun testleri ekle veya güncelle.
- [ ] Testlerin gerçekten çalıştırıldığını doğrula.
- [ ] Çalıştırılmayan testleri başarılı olarak işaretleme.
- [ ] Diff'i inceleyerek ilgisiz değişiklikleri kontrol et.
- [ ] API, schema veya davranış değişikliklerinde dokümantasyonu güncelle.
- [ ] Secret veya credential değerlerini kod ya da loglara ekleme.
- [ ] Gerçek trading veya withdrawal özelliği ekleme.
- [ ] Negatif spread'i yalnızca negatif olduğu için invalid kabul etme.
- [ ] Pozitif gross spread'i net kârla eş tutma.
- [ ] Slippage maliyetini iki kez düşürme.
- [ ] Data staleness ile simulated latency kavramlarını birbirine karıştırma.
- [ ] Gelecek bilgilerini model feature'ı olarak kullanma.
- [ ] Araştırma sonuçlarını önceden varsayma veya olduğundan iyi gösterme.
- [ ] Proje planıyla çelişen değişikliklerde önce gerekçeyi ve etkiyi açıkla.
- [ ] Önemli teknik kararları, varsayımları ve sınırlamaları dokümante et.

## Güncel Durum Özeti

### Önceki kayıtla tamamlanmış olarak işaretlenen bölümler

- [x] 1. Proje Temeli
- [x] 2. Ortak Domain ve Veri Modeli — temel işler
- [x] 3. Data Collector — temel modüller
- [x] 4. Data Standardization — temel normalizasyon
- [x] 5. Storage Katmanı — temel katmanlar
- [x] 6. Arbitrage Engine — temel hesaplama fonksiyonları
- [x] 7. Feature Engineering — temel feature pipeline

Bu işaretler, önceki takip listesinde belirtilen durumu korur. Yeni eklenen doğrulama görevleri ayrıca tamamlanana kadar açık kalır.

### Sıradaki ana çalışma

1. Arbitrage Engine'deki negatif spread doğrulamasını ve finansal hesaplama testlerini gözden geçir.
2. Data Collector için kontrollü BTC/USDT pilotunu planla ve veri kalitesini ölç.
3. Dataset ve target label tanımını kesinleştir.
4. Kronolojik train/validation/test pipeline'ını oluştur.
5. Rule-based baselines ve simulation akışını kur.
6. ML modellerini eğitip aynı simülasyon varsayımları altında karşılaştır.

### Son bilinen test sonucu

Daha önce bildirilen komut:

`py -3.14 -m pytest -q tests/test_feature_engineering.py tests/test_data_collector.py tests/test_standardization.py tests/test_storage.py tests/test_arbitrage_engine.py`

Sonuç: `15 passed in 0.06s`

Bu kayıt geçmişteki test çalıştırmasını ifade eder. Yeni kod değişikliklerinden sonra ilgili testleri tekrar çalıştır ve yeni sonucu ayrıca kaydet.

---

## Proje Genel Tamamlanma Kriteri

Proje ancak aşağıdaki koşullar karşılandığında araştırma ve portföy açısından tamamlanmış sayılacaktır:

- [ ] Veri toplama ve standardizasyon güvenilir çalışıyor.
- [ ] Finansal hesaplamalar testlerle doğrulanmış.
- [ ] Dataset ve target label tanımı belgelenmiş.
- [ ] Gelecek veri sızıntısı kontrol edilmiş.
- [ ] Rule-based baselines çalışıyor.
- [ ] Simulation ve backtesting tekrarlanabilir.
- [ ] ML modelleri uygun metriklerle değerlendirilmiş.
- [ ] ML sonuçları rule-based baselines ile karşılaştırılmış.
- [ ] Araştırma deneyleri ve sınırlamalar belgelenmiş.
- [ ] API ve dashboard gerekli sonuçları gösteriyor.
- [ ] Docker ortamı belgelenmiş adımlarla çalışıyor.
- [ ] Güvenlik ve maliyet kontrolleri uygulanmış.
- [ ] Son test ve kurulum talimatları doğrulanmış.

**Temel ilke:** Öncelik, daha fazla teknoloji eklemek değil; doğru veri, doğru finansal hesaplama, güvenilir simülasyon ve tekrarlanabilir araştırma sonuçları üretmektir.
