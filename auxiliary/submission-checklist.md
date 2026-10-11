# Freya Bank Kredi Kartı Ekstre Borcu — Teslim Kontrol Listesi

Bu denetim raporu, `final/BRIEF.md` teslimat şartnamesi ve mevcut çalışma kopyası durumu karşılaştırılarak hazırlanmıştır. Ana Codex agent'ının teslim öncesi tamamlaması gereken somut eksikler ve riskler aşağıda listelenmiştir.

---

## 1. Teslim Alanları ve Mevcut Durum Denetimi (`submission.json`)

`final/BRIEF.md` şablonuna göre `submission.json` alanlarının salt okunur denetim sonuçları:

| Alan | Beklenen İçerik | Mevcut Durum / Tespit | Durum |
|---|---|---|---|
| `team` | Takım adı | Tanımlanmamış; henüz belirlenmedi. | **Eksik** |
| `members` | Üye listesi (`[{"name": "...", "email": "..."}]`) | Yalnızca ana kullanıcının e-postası biliniyor; resmi üye listesi ve tam isimler eksik. | **Eksik** |
| `repo` | GitHub repository URL'si | Kullanıcı hesabı biliniyor ancak remote repo henüz oluşturulmadı. | **Eksik** |
| `commit` | Çalıştırılan koda ait commit SHA | **Kritik:** Çalışma alanında `.git` metadata'sı yok (`git status` -> `fatal: not a git repository`). Commit bilgisi şu an doğrulanamaz. | **Kritik Eksik** |
| `run_command` | Builder çalıştırma komutu | Gerçek komutla birebir uyumlu olmalıdır:<br>`python3 -m builder.run --case-folder final --openapi submission/contract.openapi.json --mock-base-url https://freya-bank-mock-final-20261011-9a3f21.freya-bank-mock-25.workers.dev --model gpt-6.1-sol --reasoning-effort medium` | **Hazır (Komut belirlendi)** |
| `workflow` | Repo köküne göre bağıl workflow export yolu | `submission/final.workflow.json` (veya `runs/.../workflow.export.json`). Ana agent'ın üretimi sürüyor; henüz kopyalanmadı/export edilmedi. | **Üretim Sürüyor** |
| `trace` | Repo köküne göre bağıl builder oturum logu | Gerçek Codex session trace yolu (örn. `runs/build-20261011T174559Z-a12f7a/codex-0.events.jsonl` veya `trace.jsonl`). | **Üretim Sürüyor** |
| `mock_url` | Canlı Cloudflare Worker adresi | `https://freya-bank-mock-final-20261011-9a3f21.freya-bank-mock-25.workers.dev` (Canlı `/health` 200, 617 fixture doğrulanmış). | **Doğrulandı & Hazır** |

---

## 2. Kritik Riskler ve Doğrulama Adımları

### Risk 1: Git Metadata Eksikliği ve Commit Uydurma Riski
- **Bulgu:** Çalışma kopyasında `.git` dizini bulunmamaktadır.
- **Kural:** Geçmişte çalıştırılmış kodun hangi commit'e karşılık geldiği tahmini olarak uydurulamaz.
- **Gereken İşlem:**
  1. Ana agent `git init` yapmalı, remote repo adresini eklemelidir.
  2. `pre-run-manifest.json` içindeki dosyaların hash eşitliği kontrol edildikten sonra temiz bir commit oluşturulmalıdır.
  3. Oluşan gerçek commit SHA'sı `submission.json` içerisine yazılmalıdır.

### Risk 2: Trace Dosyası Seçimi (Özet/Test Logu vs. Gerçek Builder Oturumu)
- **Bulgu:** `final/BRIEF.md` madde 40 ve 44 gereği hakemler, workflow'un builder tarafından el ile düzenleme yapılmadan üretildiğini doğrulamak için trace dosyasını inceler.
- **Risk:** Gerçek builder oturum logu (`codex-0.events.jsonl` / `trace.jsonl`) yerine sonradan oluşturulan `summary.json`, test koşu logları veya sadeleştirilmiş özetlerin verilmesi teslimatın geçersiz sayılmasına yol açabilir.
- **Gereken İşlem:** `submission.json` içindeki `"trace"` alanı, çalıştırılan `python3 -m builder.run` oturumuna ait ham olay logunu (`codex-0.events.jsonl` veya eşdeğer builder trace) işaret etmeli ve repo köküne göre bağıl olmalıdır.

### Risk 3: Dosya Yollarının Bağıl Olması (Relative Paths)
- **Bulgu:** `submission.json` içinde mutlak yollar (`/home/furkan/...`) kullanılmamalıdır.
- **Gereken İşlem:** Hem `"workflow"` hem de `"trace"` alanları doğrudan repo kök dizinine göre bağıl yol olarak verilmelidir (örn. `submission/final.workflow.json` ve `runs/build-.../codex-0.events.jsonl`).

### Risk 4: Pre-Run Manifest ile Kaynak Dosyaların Karşılaştırılması
- **Bulgu:** Builder çalıştırılmadan önce `submission/pre-run-manifest.json` oluşturulmuş ve 59 dosyanın sha256 hash değeri mühürlenmiştir.
- **Gereken İşlem:** Commit atılmadan ve teslim edilmeden önce tüm 59 dosya hash kontrolünden geçirilmeli (`sha256sum -c`), kodda builder çalışması esnasında izinsiz değişiklik yapılmadığı teyit edilmelidir.

### Risk 5: Secret ve Gizli Veri İhlali Denetimi
- **Bulgu:** BRIEF ve platform kuralları gereği API anahtarları, Cloudflare yetki belirteçleri ve oturum sırları asla commit edilmemeli veya teslim dosyalarına karışmamalıdır.
- **Gereken İşlem:**
  - `env.sh` dosyası `.gitignore` kapsamında kalmalı, git staging'e alınmamalıdır.
  - Trace dosyaları veya workflow export'u içindeki `Authorization: Bearer ...` başlıkları kontrol edilmeli, gerçek anahtarların dışarı sızmadığı teyit edilmelidir.
  - Test müşteri verilerine ait müşteri numaraları veya hassas değişkenler raporda veya commit mesajlarında açıkça ifşa edilmemelidir.

---

## 3. Teslimat Öncesi Son Kontrol Listesi (Checklist)

- [ ] Builder üretimi tamamlandı ve yerel doğrulamadan (`builder/validate.py`) 0 hata ile geçti.
- [ ] Export edilen workflow `submission/final.workflow.json` yoluna kopyalandı.
- [ ] `submission/pre-run-manifest.json` içindeki 59 dosyanın hash'leri doğrulandı.
- [ ] Git deposu ilklendirildi (`git init`), uzaktan repo eklendi (`git remote add origin ...`).
- [ ] Gizli anahtarlar (`env.sh` vb.) gitignore edildiği kontrol edildi.
- [ ] Kod commit edildi ve gerçek commit hash'i alındı.
- [ ] `submission.json` eksiksiz oluşturuldu (`team`, `members`, `repo`, `commit`, `run_command`, `workflow`, `trace`, `mock_url`).
- [ ] `workflow` ve `trace` yollarının repo köküne göre bağıl olduğu teyit edildi.
- [ ] Cloudflare Worker mock'unun (`https://freya-bank-mock-final-20261011-9a3f21.freya-bank-mock-25.workers.dev`) erişilebilir ve canlı olduğu son kez doğrulandı.
- [ ] E-posta teslimatı için `submission.json`, export edilen workflow ve trace dosyası hazırlandı (`yavuz@freyavoice.ai` adresine 23:00 Istanbul / 20:00 UTC öncesi).
