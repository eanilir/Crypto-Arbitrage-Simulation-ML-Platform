# AI Workflow Takip Listesi

Not: Bu liste mevcut proje durumuna göre işaretlenmiştir.

## 1. Proje Temeli
- [x] Repo yapısını oluştur
- [x] Python environment seç
- [x] README.md, .gitignore, .env.example dosyalarını hazırla
- [x] Ortak kod standartlarını belirle
- [x] Loglama formatını belirle
- [x] Konfigürasyon yönetimi yaklaşımını belirle
- [x] Temel klasör yapısını oluştur

## 2. Ortak Domain ve Veri Modeli
- [x] Exchange, symbol, price, spread, opportunity için ortak veri modellerini tanımla
- [x] Zaman damgası standardını belirle
- [x] Symbol normalizasyon kuralını belirle
- [x] Veri validasyon kurallarını yaz
- [x] Hatalı veri formatları için hata tiplerini belirle

## 3. Data Collector
- [x] Binance için REST veri çekme modülü yaz
- [x] Binance için WebSocket veri çekme modülü yaz
- [x] Bybit adapter’ını yaz
- [x] OKX adapter’ını yaz
- [x] Retry ve reconnect mekanizması ekle
- [x] Timeout yönetimi ekle
- [x] Duplicate veri kontrolü ekle
- [x] Collector loglarını standardize et
- [x] Collector için unit test yaz

## 4. Data Standardization
- [x] Exchange bazlı cevapları ortak formata dönüştür
- [x] Bid, ask, last, volume alanlarını normalize et
- [x] Timestamp dönüştürme katmanı ekle
- [x] Eksik alanlar için validasyon koy
- [x] Bozuk kayıtları reject et
- [x] Normalizasyon testlerini yaz

## 5. Storage Katmanı
- [x] PostgreSQL şemasını tasarla
- [x] Redis kullanım alanlarını netleştir
- [x] InfluxDB kullanım alanlarını netleştir
- [x] Market data için storage adapter yaz
- [x] Opportunity/result kayıtları için PostgreSQL repository yaz
- [x] Cache okuma/yazma katmanını yaz
- [x] Storage entegrasyon testleri yaz

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

## 7. Feature Engineering
- [x] Price difference feature’ını üret
- [x] Spread percentage feature’ını üret
- [x] Volume feature’larını üret
- [x] Volatility feature’ını üret
- [x] Fee/slippage/latency feature’larını üret
- [x] Exchange pair feature’ını üret
- [x] Feature pipeline testlerini yaz

## 8. ML Service
- [ ] Dataset hazırlama işini yaz
- [ ] Target label tanımını yap
- [ ] Train/test split pipeline yaz
- [ ] Logistic Regression baseline eğitimi yaz
- [ ] Random Forest eğitimi yaz
- [ ] Gradient Boosting eğitimi yaz
- [ ] Model evaluation metriklerini yaz
- [ ] Model versioning yaklaşımı belirle
- [ ] Prediction API’yi yaz
- [ ] ML servis testlerini yaz

## 9. Simulation Engine
- [ ] Virtual wallet modelini yaz
- [ ] Virtual balance yönetimini yaz
- [ ] Simulated order mantığını yaz
- [ ] BUY/SELL simülasyonunu yaz
- [ ] Fee/slippage/latency etkisini simülasyona ekle
- [ ] P&L hesaplama modülünü yaz
- [ ] Trade history kaydı ekle
- [ ] Drawdown ve performans metriklerini yaz
- [ ] Simulation testlerini yaz

## 10. Backtesting
- [ ] Historical data loader yaz
- [ ] Historical replay mekanizması yaz
- [ ] Strategy execution akışını yaz
- [ ] Cost-aware backtest mantığını yaz
- [ ] Backtest sonuçlarını kaydet
- [ ] Backtest metriklerini üret
- [ ] Backtest testlerini yaz

## 11. Paper Trading
- [ ] Live public data akışını bağla
- [ ] Arbitrage engine ile bağla
- [ ] ML prediction ile bağla
- [ ] Simulation engine ile bağla
- [ ] Gerçek order göndermeyen bir pipeline oluştur
- [ ] Paper trading sonuçlarını kaydet

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
- [ ] Request/response validation ekle
- [ ] API integration testleri yaz

## 13. Logging ve Monitoring
- [ ] Structured logging formatı belirle
- [ ] Service bazlı log formatı uygula
- [ ] Request ID takibi ekle
- [ ] Error logging standardı ekle
- [ ] Metrics üretme katmanı oluştur
- [ ] Health check response’larını standardize et
- [ ] Uyarı/alert kriterlerini belirle

## 14. Testing Katmanı
- [ ] Unit test yapısı kur
- [ ] Integration test yapısı kur
- [ ] API testleri ekle
- [ ] Failure scenario testleri ekle
- [ ] Data validation testleri ekle
- [ ] Performance test iskeleti oluştur

## 15. Dockerization
- [ ] Her servis için Dockerfile yaz
- [ ] .dockerignore dosyalarını ekle
- [ ] Docker Compose dosyasını yaz
- [ ] Container health check ekle
- [ ] Restart policy belirle
- [ ] Non-root çalıştırma yaklaşımını uygula
- [ ] Image boyutunu küçültme adımlarını uygula

## 16. Service Communication
- [ ] Servisler arası veri akışını netleştir
- [ ] API contract’ları tanımla
- [ ] DB ownership kurallarını belirle
- [ ] Redis kullanım sınırlarını belirle
- [ ] Servis bağımlılıklarını dokümante et

## 17. Security
- [ ] Secrets’i env ile yönet
- [ ] .env’yi Git dışı bırak
- [ ] API authentication ekle
- [ ] Input validation ekle
- [ ] Rate limiting ihtiyacını değerlendir
- [ ] DB erişimini private tut
- [ ] Container security kurallarını uygula
- [ ] Logging’de secret sızmasını engelle

## 18. Fault Tolerance
- [ ] Exchange failure retry mekanizması ekle
- [ ] WebSocket reconnect ekle
- [ ] DB unavailable senaryolarını ele al
- [ ] Redis unavailable senaryolarını ele al
- [ ] Service crash recovery mekanizması planla
- [ ] Duplicate/missing data handling ekle

## 19. Cloud Hazırlığı
- [ ] Servisleri stateless hale getir
- [ ] Config’i environment-based yap
- [ ] Docker image’ları cloud uyumlu hale getir
- [ ] Managed service kararlarını ver
- [ ] VPC ve security group tasarımını yap
- [ ] ECS mi EC2 mi kararını ver
- [ ] RDS/ElastiCache gibi managed servisleri planla
- [ ] Secrets management tasarla
- [ ] Cloud logging/monitoring planla
- [ ] Cost control planı yap

## 20. AWS Deployment
- [ ] Network altyapısını kur
- [ ] App runtime ortamını kur
- [ ] Load balancer kur
- [ ] Managed database kur
- [ ] Managed cache kur
- [ ] Application secrets’i bağla
- [ ] Monitoring/logging’i bağla
- [ ] Deployment pipeline yaklaşımını belirle

## 21. Son Stabilizasyon
- [ ] Load test yap
- [ ] Failure test yap
- [ ] Metric takibini doğrula
- [ ] Docker Compose ile tam açılışı doğrula
- [ ] AWS ortamında health kontrolü yap
- [ ] Documentation eksiklerini tamamla

## Mevcut durum özeti
- Hazır: 1, 2, 3, 4, 5, 6, 7
- Sıra bekleyen: 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21
- Son doğrulama: `py -3.14 -m pytest -q tests/test_feature_engineering.py tests/test_data_collector.py tests/test_standardization.py tests/test_storage.py tests/test_arbitrage_engine.py` -> 15 passed in 0.06s