# INSTRUCTIONS.md Değişiklik Günlüğü (Changelog)

Bu belge, `builder/INSTRUCTIONS.md` dosyasına yapılan her değişikliği, eklenme gerekçesini (hangi test vaka hatasından kaynaklandığını) ve tam metnini adım adım kaydeder. İleride kuralları temizlemek, sadeleştirmek veya brief'e aşırı özelleşmiş (overfitting) kuralları ayıklamak için referans olarak kullanılır.

---

## Adım 1: Temel Talimatlar (Starter Kit V3)
- **Tarih:** 2026-10-10
- **Amaç:** Codex CLI'nin Brief ve OpenAPI'den raw Freya workflow JSON üretmesini sağlamak.
- **Kapsam:** Deterministik state graph, OpenAPI sözleşme uyumu, code_exec sandbox kuralları, statik konumlandırmanın (layout) Python'a bırakılması.

---

## Adım 2: Brief A Sıkı Uygunluk Temizliği (Compliance Audit)
- **Tarih:** 2026-10-11 02:05 TRT
- **Gerekçe:** `COMPLIANCE_AUDIT.md` denetiminde önceki manuel yamalarda açılışta 2 yerine 4 tur sorma gibi brief dışı gevşetmeler tespit edildi.
- **Yapılan Değişiklik:** Brief A kural 3'e ("yes", "that's me", "speaking" veya ad) tam uyumlu, gereksiz genişletmelerden arındırılmış genel dil oluşturuldu.

---

## Adım 3: Brief A İlk 10 Vaka Testinden Çıkarılan Genel İyileştirmeler
- **Tarih:** 2026-10-11 02:54 TRT
- **Tetikleyen Test:** `build-20261010T231140Z-c232b6` (5/10 PASS)
- **Eklenen Kurallar ve Gerekçeleri:**

### 3.1. Tarih ve Sayı Formatı Esnekliği (PUB-04 Kök Nedeni)
- **Problem:** Extractor `2026-11-06` döndürdü; kod yalnız `iso:2026-11-06` beklediği için tarihi okuyamadı ve 75 kez aynı soruyu sordu.
- **Eklenen Kural:**
  > *"When parsing extracted dates or amounts, accept both plain ISO strings (YYYY-MM-DD) and normalized prefixed formats (iso:YYYY-MM-DD, days:N, this:weekday, next:weekday); do not fail or enter a retry loop merely because an artificial prefix is absent."*
- **A+B Adayındaki Doğrulama:** Bu mantığı kullanan A+B adayında PUB-04 ilk denemede **PASS** aldı.

### 3.2. Sınırlı Tekrar Sayacı ve Çıkış Garantisi (PUB-04, PUB-07 Kök Nedeni)
- **Problem:** Tarih veya teyit anlaşılmadığında agent'ın sonsuz döngüye girmesi.
- **Eklenen Kural:**
  > *"Every clarification, re-ask, or retry branch (such as asking for an unclear date or confirmation again) MUST track an attempt counter with a strict low limit (e.g. 1 or 2 asks) and provide a deterministic fallback/exit (e.g. propose the deadline or close per policy), NEVER looping indefinitely."*

### 3.3. Bekleyen Teklife / Soruya Öncelik (PUB-05 Kök Nedeni)
- **Problem:** Hardship sonrası transfer teklifine müşteri "No, I don't want transfer. Any discount?" dediğinde `question` etiketi teklif reddini ezdi; sempati ve transfer 7 kez tekrarlandı.
- **Eklenen Kural:**
  > *"When the agent poses an offer or binary question (e.g., offering support transfer for hardship, or an amount/date proposal), if the customer declines or says no (even alongside a question or complaint), resolve the pending offer immediately. Strictly adhere to brief limits on repeated offers and sympathy (e.g., offer support only once, one sympathy sentence); never repeat sympathy or support transfer offers in loops."*

### 3.4. Asgari Tutar (Floor) vs Restructuring Önceliği (PUB-06 Kök Nedeni)
- **Problem:** "The full amount is too much" cümlesi yanlışlıkla `restructure` sayılıp doğrudan transfer edildi; asgari ödeme (floor) teklif etme kuralı işletilmedi.
- **Eklenen Kural:**
  > *"Saying the full amount is too much or cannot be paid must be handled under the amounts/floor policy, NOT superseded by or classified as a restructuring/payment plan request unless the caller explicitly requests a payment plan or lower instalments."*

### 3.5. "Full Amount" İfadesi Eşlemesi (PUB-10 Kök Nedeni)
- **Problem:** Müşteri "I will pay the full amount" dediğinde tutar past-due olarak güncellenmedi.
- **Eklenen Kural:**
  > *"Recognize expressions like 'full amount', 'the full amount', 'all of it' as the full past-due balance."*

### 3.6. Konuşma Modelinin Kendi Başına Soru Uydurmasını Engelleme (PUB-07 Kök Nedeni)
- **Problem:** Model kural dışı olarak "how much can you pay?" diye sordu (Kural 24 ihlali).
- **Eklenen Kural:**
  > *"The dialogue model must strictly speak from the deterministic state; never permit the speech model to invent unprompted questions (e.g. asking how much the caller can pay when forbidden by policy)."*

---

## Adım 4: A+B Testinden Çıkarılan İyileştirmeler (Hazırlık)
- **Tarih:** 2026-10-11 03:40 TRT
- **Tetikleyen Testler:** `PUB-06` (Amount note eksikliği), `PUB-07` (Tatil günü kuralı), `PUB-12` (Erken bantta 1 deneme kuralı).
- **Eklenecek Genel Kurallar:**

1. **Floor teklifinde yasal/zorunlu uyarı:**
   - Asgari ödeme önerildiğinde, brief gereği kalan tutarın gecikmede kalacağı ("the rest stays overdue") açıkça belirtilmelidir.
2. **Tatil günü sonraki iş gününe taşıma (Holiday Rollover):**
   - Müşteri banka tatiline denk gelen bir gün önerirse, o tarih son teslim tarihini (deadline) aşmıyorsa, doğrudan sonraki ilk iş günü teklif edilmelidir.
3. **Erken bant (1-7 gün) ikna sınırı:**
   - 1-7 gün gecikmeli ürünlerde ikna hakkı kesinlikle 1'dir; müşteri reddettiğinde 2. kez teklif yapılmamalıdır.

---

## Adım 5: Brief'e özel kuralları koşullu hale getirme
- **Tarih:** 2026-10-11
- **Gerekçe:** Önceki eklemeler floor uyarısını, erken bant sınırını ve tatil kaydırmayı tüm brief'lerin genel kuralı gibi sunuyordu. Bunlar yalnız A/B kaynaklarında varsa uygulanır.
- **Değişiklik:** Normal üretim talimatı, miktar/tarih/deneme/uyarı kurallarını verilen brief'ten türetmeyi ve soru yanıtı önceliğini ilgili brief'in sırasına göre kurmayı söyler. Genel kalan ilkeler format uyumu, sınırlı tekrar, tool iç sonucunu kontrol ve konuşma/state tutarlılığıdır. Eski adaya bağlı `repair_*.py` modülleri normal builder yolunda kullanılmaz.

---

## Adım 6: Tek string JSON çıkarımı ve konuşma/state sapması

- **Tarih:** 2026-10-11
- **Kanıt:** `build-20261011T091307Z-6d115e` adayının PUB-04 çağrısı `06366aae-a0ed-4cdf-b8f3-45193fd0f870`. İlk açık isim teyidi `intent: identity_yes, binary: yes` olarak çıkarıldı; kod tek string içinde JSON nesnesi beklediği için okuyamadı. Sonraki çıkarım hata verdi. Agent, state hâlâ `greeting` iken brief dışı evcil hayvan sorusu sordu; ardından `not_reached/unclear` ile kapattı.
- **Genel düzeltme:** Ayrı, tipli extractor alanları kullan; JSON nesnesini string alanın içine gömme. Çıkarım hatası veya kesik söz, ret/yanlış cevap değildir ve iş kuralı sayacını tüketmez. Bekleyen soru ile konuşulan soru aynı kalmalıdır; uygun sabit metin mekanizması varsa deterministik state metnini kullan. Statik validatör açık “string içinde JSON nesnesi” tarifini reddeder.

---

## Adım 7: Aşamaya Göre Daraltılmış Çıkarım (Stage-Scoped Extraction) ve Gecikme Sınırı

- **Tarih:** 2026-10-11 13:50 TRT
- **Kanıt:** `build-20261011T092921Z-d3b1ba` adayının PUB-04 çağrısı `3118f4d5-ce74-483a-bb6a-c54ebce856fb`. Tüm iş mantığı ve tarih anlaşması doğru geçti ancak tek bir `listen` node'unda tanımlı 19 extractor alanı yüzünden çıkarım turu 60 saniyeden uzun sürdü; platform çağrıyı sessizlik zaman aşımından (`customer-ended-call`) kapattı.
- **Genel kural (Brief-Agnostic):** Verilen brief hangi aşamaları (kimlik kontrolü, hesap doğrulama, teklif müzakeresi, teyit okuması vb.) tanımlıyorsa, extraction şemaları yalnız o aktif aşamanın karar vereceği alanlarla sınırlı tutulmalıdır (node başına 2 ila 5 alan). Tek bir node'a tüm akışın onlarca değişkeni yığılmamalıdır.
- **Statik Koruma:** `builder/validate.py` içine conversation node başına en fazla 8 extraction alanı sınırı eklendi (>8 alan doğrudan yerel validasyonda reddedilir).

---

## Adım 8: Göreceli Tarih Çözümü, Belirsiz Dönem Önceliği ve Bounded API Retry

- **Tarih:** 2026-10-11 16:20 TRT
- **Kanıtlar:** `build-20261011T105306Z-47f058` adayının 7/10 benchmark analizindeki 3 başarısız vaka:
  - `PUB-02`: LLM tarih çıkarıcısının "tomorrow" ifadesini sunucunun gerçek saatine (11 Ekim -> 12 Ekim) bağlayarak simülasyonun `now` saatinden (14 Ekim -> 15 Ekim) sapması.
  - `PUB-07`: "the week after next" ifadesinde çıkarıcının hem `vague` hem de tahmini `2026-10-25` üretmesi; kodun `has_date` kontrolünü `vague` öncesinde yapması sebebiyle Rule 21 ("ask once for the exact day") kuralının atlanması.
  - `PUB-05`: `verify_identity` API çağrısının mock banka sunucusundaki anlık HTML/ağ dalgalanmasında tek hata ile oturumu sonlandırması.
- **Genel kurallar (Brief-Agnostic):**
  1. **Göreceli Tarihlerin Deterministik Çözümü:** "today", "tomorrow", "this/next <weekday>" ifadeleri LLM'in genel date parser'ına bırakılmamalı; `date_kind` gibi ayrık/kategorik alanlarla çıkarılmalı ve Python'da oturumun `now` değişkeni çapa alınarak deterministik hesaplanmalıdır.
  2. **Belirsiz Dönem Önceliği:** Çıkarıcı `vague` tespiti yapmışsa, ürettiği tahmini/uydurma kesin tarih değeri tarafından ezilmemelidir (`has_date = ... and not vague`). Deterministik kod, brief'in belirsiz dönem politikasını (kesin günü sorma, ardından son teslim tarihini önerme) işletmelidir.
  3. **Callback ve Ödeme Yollarında Tutarlılık:** Açık tarih, göreceli tarih ve belirsiz dönem ayrımı yalnızca ödeme teklifinde değil, geri arama (callback) aşamasında da işletilmelidir.
  4. **Geçici Taşıma/Gateway Hatalarında Bounded Retry:** API isteklerinde iş kuralı hatası ile geçici ağ/5xx/HTML hataları ayrılmalı; brief'in izin verdiği sınırlar dahilinde (ör. 2 deneme) tekrar deneme yapılmalıdır.

---

## Adım 9: Sözlü teklifin ürün kapsamlı takibi (Brief B PUB-12)

- İlk yerel karşı örnek, belirsiz cevap dalında sayacın doğru kalmasına rağmen `state_instruction` tarafından aynı teklifin tekrarlanabildiğini gösterdi. Sonradan Freya API'sinden PUB-12 tam çağrı izi kurtarıldı: car loan teklifine açık `refuse` çıkarıldı; kod state'i doğru biçimde toplu `confirm` aşamasına aldı. Buna rağmen konuşma modeli `confirm` talimatı yerine car loan için yeni bir tutar/tarih önerdi. Bu gerçek çağrının kök nedeni **konuşma/state sapmasıdır**; belirsiz cevap yolu ayrı bir potansiyel hatadır.
- Genel builder talimatı, brief'in belirttiği kapsamda hem deneme sayısını hem teklifin gerçekten söylenmesini izlemeyi, belirsiz çıkarımı/gerçek bilgi sorusunu ret veya yeni teklif saymadan yalnız bekleyen cevabı netleştirmeyi ve aşama geçişinde önceki teklifin LLM tarafından yeniden üretilmesini engellemeyi gerektiriyor. Kesin teklif ve toplu read-back metni mümkünse state'ten oluşturulup sabit TTS ile söylenmeli. Ürün, vaka, müşteri cümlesi veya sabit deneme sayısı eklenmedi.

