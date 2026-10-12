# Storage Katmanı Tasarımı

## PostgreSQL

- `market_quotes` tablosu: canlı piyasa fiyatlarını saklar.
- `arbitrage_opportunities` tablosu: hesaplanan fırsatları saklar.
- `symbol` ve `quote_time` üzerinde indeks kullanılır.
- `metadata` alanı JSONB olarak ek meta verileri tutar.

## Redis

- Kısa süreli cache için kullanılır.
- En sık kullanılan işlevler: son fiyat cache, fiyat snapshot, hesaplanmış spread cache.
- TTL ile otomatik silme desteklenir.

## InfluxDB

- Zaman serisi verisi için kullanılır.
- Örnek kullanım: `market_quote` ölçümü, her tick için `symbol`, `exchange`, `bid`, `ask`, `last` ve `timestamp`.
- Analitik sorgular ve grafikler için uygundur.

## Uygulama Notları

- Market verisi yazım katmanı: `InMemoryMarketDataAdapter`
- Fırsat kaydı katmanı: `InMemoryOpportunityRepository`
- Cache katmanı: `InMemoryCacheStore`

Bu yapı, gerçek PostgreSQL/Redis/InfluxDB bağlantıları eklenmeden önce ortak arayüzü tanımlar.
