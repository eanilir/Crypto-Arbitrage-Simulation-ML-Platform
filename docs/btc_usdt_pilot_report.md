# BTC/USDT Veri Toplama Pilot Raporu

## Kapsam

Bu rapor, Binance public `BTCUSDT@bookTicker` WebSocket akışı üzerinde 13 Ekim 2026 tarihinde yapılan kısa kontrollü pilotu kaydeder. Pilot aracı:

```powershell
python scripts/btc_usdt_pilot.py --duration 60 --output data/processed/btc_usdt_pilot.ndjson
```

Bu çalışma, 3-7 günlük üretim pilotunun yerine geçmez. Uzun dönem pilot için aynı komutun kesintisiz ve izlenen bir ortamda çalıştırılması gerekir.

## Ölçüm Sonuçları

| Ölçüm | Sonuç |
| --- | ---: |
| Süre | 17.035 s |
| Alınan mesaj | 749 |
| Mesaj sıklığı | 43.968 mesaj/s |
| Reconnect | 0 |
| Geçersiz kayıt | 0 |
| Out-of-order gözlemi | 0 |
| `event_timestamp` kapsaması | 0/749 |
| `received_timestamp` kapsaması | 749/749 |
| Ham payload boyutu | 80,923 byte |
| Ham payload günlük tahmini | yaklaşık 410 MB/gün |

İkinci kısa bağlantı kontrolünde 22.432 saniyede 1,463 mesaj ve 65.22 mesaj/s ölçüldü. Kısa örneklerde sıklık değiştiği için retention hesabında tek bir sabit oran kullanılmamalı; uzun dönem p95/p99 mesaj sıklığı ayrıca ölçülmelidir.

## Timestamp Yorumu

Binance `bookTicker` payload'ında bu pilotta `E`, `T` veya `ts` alanı bulunmadı. Bu nedenle mevcut akışta:

- `received_timestamp`: mesajın client tarafından alındığı UTC zamanı; ölçüldü ve her geçerli kayda yazıldı.
- `event_timestamp`: bu stream için mevcut değil; doldurulmadı.
- `received_timestamp - event_timestamp`: event zamanı olmadığı için ağ gecikmesi olarak hesaplanmadı.

Mevcut `MarketQuote.timestamp` alanı event timestamp mevcut olduğunda onu, yoksa receive zamanını kullanabildiğinden, uzun vadede event ve receive zamanlarının ayrı zorunlu alanlar olarak saklanması gerekir.

## Sequence, Kayıp ve Reconnect

Mesajlarda Binance `u` update ID alanı bulundu. Kısa koşuda ardışık olmayan ID sıçramaları gözlendi; pilot scripti bunları `sequence_gap_count` olarak raporladı. `bookTicker` akışı filtrelenmiş en iyi bid/ask güncellemelerini taşıdığı için ID farkı tek başına ağda veri kaybı kanıtı değildir. Kesin gap doğrulaması için Binance diff-depth stream (`U`, `u`, `pu`) ve snapshot senkronizasyonu kullanılmalıdır.

Kısa koşularda reconnect olmadı ve geçersiz JSON/mesaj görülmedi. Bu, reconnect davranışının sağlıklı olduğunu kanıtlamaz; kontrollü disconnect ve 3-7 günlük doğal bağlantı gözlemi ayrıca yapılmalıdır.

## Depolama ve Retention Kararı

İlk ölçüm, ham NDJSON için yaklaşık 0.4 GB/gün mertebesini gösterdi. Bu değer JSON alanları, metadata, indeksler, sıkıştırma ve çoklu exchange eklenmeden önceki yalnızca payload tahminidir.

Geçici politika:

- Ham WebSocket kayıtlarını 7 gün sakla.
- Normalize edilmiş, kalite alanları eklenmiş kayıtları 30 gün sakla.
- Günlük sıkıştırılmış arşivi daha uzun süre saklamadan önce gerçek depolama maliyetini ölç.
- Event timestamp bulunmayan kayıtları silme; `event_timestamp=null` ve `timestamp_quality=missing` olarak işaretle.
- 3-7 günlük ölçüm tamamlanınca mesaj sıklığının p95'i, gerçek sıkıştırma oranı ve disk büyümesiyle politikayı yeniden değerlendir.

## Sonuç ve Açık İşler

Kısa kontrollü pilot bağlantı, mesaj alımı, local receive zamanı, temel veri kalitesi ve yaklaşık depolama büyümesini doğruladı. Ancak aşağıdakiler uzun dönem pilot ile tamamlanmalıdır:

- 3-7 günlük kesintisiz BTC/USDT toplama.
- Kontrollü disconnect/reconnect senaryosu.
- Diff-depth ile kesin sequence gap doğrulaması.
- CPU, bellek ve gerçek disk kullanımının izlenmesi.
- Event timestamp sağlayan uygun Binance stream veya exchange alanının ayrıca doğrulanması.
