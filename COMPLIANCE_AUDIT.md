# Brief A uygunluk denetimi — 2026-10-11

Kapsam: `briefs/brief-a.md`, `tools/openapi.json`, önceki UI adayı `c4c86803-d9fb-4764-89d7-2588deeb59f9` için yerel kaynak `runs/session-product-repair-20261010T225720Z/workflow.json` ve aynı mantığın kaynak onarım modülleri. Bu denetim eski çağrıların gözlemi ile yerel karar kodunu ayırır; yeşil birim testleri resmî PUB skoru değildir.

| Davranış/değişiklik | Dayanak | Denetim sonucu |
|---|---|---|
| Açılışta ilk cümle ve adla kişiyi sorma | Brief A 1–2 | Kaydedilmiş çağrılarda var. |
| Açılışta iki kez sorma; ikinci yanıttan sonra hâlâ belirsizse `not_reached/unclear` | Brief A 3 | **İki→dört değişikliği aykırı.** `builder/repair_opening_and_security.py` ve yeni builder talimatından kaldırıldı. Eski yayınlanmış adaylar tarihsel olarak dört tur içerebilir; temiz aday ayrıca denetlenecek. |
| “yeah”, “it's me”, “talking to him” gibi ifadeleri otomatik kimlik teyidi sayma | Brief A 3 yalnız “yes”, “that's me”, “speaking” veya müşterinin kendi adını sayar | **Dayanaksız genişletme.** Önceki UI çağrılarında işe yaradığı görülmesi brief izni değildir. Yeni talimat yalnız listelenen biçimleri kabul eder; bu yorum organizatörce genişletilmedikçe farklı sözler ikinci soruyu gerektirir. |
| Geçerli DOB `input_answer` değeri varken `input_event` sınıflandırması bozulsa da `verify_identity`ye gönderme | Brief A 11; OpenAPI `/verify_identity` body `answer`, `field` | Uygun teknik onarım: tarih YYYY-MM-DD'ye çevrilir; yanlış cevap ancak bankanın `verified=false` sonucu ile sayılır. |
| `status=success` yerine iç `data.ok`/`verified` sonucunu değerlendirme | OpenAPI `/verify_identity` 200: `ok=false` işlem yapılmadı; 500: servis hatası | Gerekli. 885c... çağrısında HTTP/dış success ama iç `ok=false` vardı. |
| `the call is already closed` sonucunda tarihi yeniden istememe | OpenAPI `ok=false,error` imkânı; 885c... canlı banka yanıtı | Hata terminal görünüyor; aynı çağrıda tekrar deneme anlamlı değil. **Tam hata metni OpenAPI'de belgelenmemiş**, canlı mock davranışına dayanıyor. |
| Doğrulama tamamlanmadan `no_promise/service_error` kapatma | Brief A 46 tablosunda `service_error`, promise kayıt hatası için kural 37'ye bağlı; `not_verified` için yalnız `failed/declined` var | **Uygunluk boşluğu.** Önceki `repair_closed_session.py` bu eşleşmeyi kullandı; brief teknik kimlik/kapalı oturum sonucuna uygun outcome/reason tanımlamıyor. Doğru kod netleşmeden bu eşleşme brief uyumlu ilan edilemez. |
| Tam doğrulamadan sonra bankadan dönen ürün, gecikmiş tutar ve günü söyleme | Brief A 16–17; OpenAPI `/get_account` ürün alanları | Uygun; `78ea...` çağrısında `get_account ok=true` sonrası yapıldı. Banka ürünün geçmişini açıklamıyor; böyle bir geçmiş uydurulmamalı (kural 44). |
| Açık “borç benim değil / bu ürünü hiç kullanmadım / kapatılmıştı” itirazında `no_promise/dispute` | Brief A 40, 46 | Gerekli. Cümlede soru işareti olması açık ret beyanını geçersiz kılmaz. |
| Ürün hakkında belirsiz soru ve bilgi isteğinde bankadan bilinenlerle cevap verme | Brief A 17 ve 44; kesin itiraz yoksa 40 tetiklenmez | Gerekli yorum. Bir açıklama/netleştirme turu **brief'te zorunlu sayı olarak yazmıyor**; UX tercihi olarak ayrılmalı. |
| `input_event=dispute` ama `input_raw` eksikse otomatik kesin itiraz saymama | Brief A 40 için açık beyan kanıtı gerekir; 78ea... extractor olayı | Savunulabilir güvenlik fallback'i, fakat brief tam olarak bu extractor arızasını tarif etmez. Kesin itiraz kanıtı yoksa açıklama/ayrıştırma gerekir. |

Önceki birleşik adayın yerel karar kodunda ek cümle denemeleri:

| Girdi (event) | Brief'e göre beklenen | Eski adayın sonucu |
|---|---|---|
| “This debt is not mine. Why is it here?” (`dispute`) | Açık itiraz → kapat | `dispute` ile kapat, uygun. |
| “I never had this card. What is it?” (`dispute`) | Açık itiraz → kapat | `dispute` ile kapat, uygun. |
| “I don't have this credit card. Why is it on my account?” (`dispute`) | Açık sahiplik reddi → kapat | Belirsizlik açıklamasına geçiyor, **uygunsuz**. |
| “Could you tell me which product is overdue?” (`other`) | `get_account` ürün bilgisiyle yanıtla | “Bu bilgim yok” ve ödeme teklifi, **uygunsuz**. |
| “Which account are you talking about?” (`other`) | Bilinen ürün bilgisini açıkla | “Bu bilgim yok” ve ödeme teklifi, **uygunsuz**. |
| “I'm not sure I recognize this account. Can you tell me more?” (`other`) | Bilinenleri söyle, uydurma; gerekirse netleştir | Açıklama turu, makul. |
| “How did I get this card?” (`other`) | Geçmiş bilinmiyor de; bilinen kart bilgisini ayır | Genel “Bu bilgim yok” ve ödeme teklifi, eksik. |

Bu matris yerel `evaluate` kodunu örnek değişkenlerle çalıştırır; konuşma modelinin gerçek üslubunu veya Freya çağrı skorunu kanıtlamaz. Yeni temiz builder adayı, kendi ürettiği node yapısına göre ayrıca incelenecek. Mevcut adaylara özgü onarım modülleri `builder.run` tarafından çağrılmaz.

## A+B kapsam ve öncelik ölçütleri

Brief B, A'yı tümüyle kaldırmaz; yalnız belirttiği kuralları değiştirir. Temiz A+B adayında şu durumlar ayrı aranacak:

| Gerekli davranış | Kaynak |
|---|---|
| `get_account` sırasındaki 1–3 ürünü ayrı durumla izleme; her ürünün `days_late` bandı, deadline, floor ve persuasion sayacı farklı olabilir | B 1, 3, 5; A 18, 25, 30 |
| Başta tüm gecikmiş ürünleri söyleme ve yalnız bir kez “hepsini bugün” sorma; olumsuz yanıtta ürün sırasıyla ilerleme | B 2, 4; A 17, 28'in B tarafından genişletilmesi |
| Ortak önerilen tarih bir ürünün deadline'ını aşıyorsa yalnız o ürünün tarihini kendi deadline'ına çekme ve bunu okumada söyleme | B 6; A 19, 23 |
| Tüm sözleri toplu okumak ve tek onay almak, sonra ürün başına `create_promise` | B 7; A 34–37'nin kapsam değişimi |
| İtiraz veya “already paid” tek ürünün akışını bitirir, `add_note` yazar ve diğer ürüne devam eder; önceki A çağrı kapanışına üstün gelir | B 8–9; A 39–40'ın B tarafından değiştirilmesi |
| Transfer çağrı düzeyinde önceliklidir; önceden kaydedilmiş sözler kalır, onaylı ama kaydedilmemişler yazılmaz, hiç not eklenmez | B 10; A 41–42, 46 |
| Bir ürünün `create_promise` işlemi iki kez başarısızsa yalnız ona `service_error` notu, diğer kaydedilen sözler kalır | B 11; A 37 |
| Kapanışta transfer üstün; aksi durumda herhangi kayıtlı söz varsa `promise`; hiç yoksa tüm notlar paid ise `paid`, değilse API sırasındaki ilk paid olmayan notun reason'ı | B Closing; A 46 |

`builder/run.py` normal yolda yalnız `layout` ve `validate` kullanır. `repair_identity_gate.py`, `repair_dispute_clarification.py`, `repair_opening_and_security.py`, `repair_closed_session.py`, `repair_product_uncertainty.py` ise belirli eski adayın node adlarına, code-string parçalarına ve Brief A'nın tek ürün akışına bağlıdır. Özellikle `repair_dispute_clarification.py`nin tüm çağrıyı `dispute` ile bitirmesi B 9'a aykırıdır; bunlar A+B üretimine taşınmaz. Genel yararlı ilkeler `builder/INSTRUCTIONS.md`ye girdi bağımlı olarak yazıldı, eski yamalar otomatik uygulanmıyor.
