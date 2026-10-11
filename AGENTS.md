# Çalışma kuralları

- Kullanıcıyla Türkçe konuş. Bağlam için FREYA_HANDOFF.md, güncel durum için STATUS.md oku.
- Canlı test yapılmış veya sorun çözülmüş sayılması için gerçek çağrı ve sonuç kanıtı gerekir. Offline kontrol, ledger ve konuşma hakemi sonuçlarını ayrı belirt.
- Her deney için yeni, benzersiz adlı workflow oluştur; candidate → workflow_id → agent_id → test sonucunu kaydet. Eski workflow'ları izinsiz silme.
- Anahtarları çıktıya, workflow'a veya git'e yazma. env.sh dosyasını koru; trace içindeki auth başlıklarını ve oturum sırrı olan customer_id değerlerini maskele.
- PUB testlerini resmi tools/run_cases.py ile yeni banka oturumunda çalıştır. Aynı workspace'te tek simülasyon çalıştır; devam eden testi bitmeden terk etme.
- Sabit telefon modeli AGENT_LLM değişmez. Agent yalnızca verilen banka API'sini kullanır. Sentetik vaka cevaplarını builder kurallarına gömme.
- Brief ve OpenAPI çalışma zamanı girdileridir. Üretilmiş agentı platformda elle düzeltme; değişiklikleri yeniden üretilebilir kodda yap.
- Kalıcı kurallar burada, ilerleme/komutlar/kanıtlar ve sonraki adım STATUS.md içinde tutulur. Mevcut içerikleri koru.
- Builder giriş noktası `python3 -m builder.run`; brief dosyaları, --openapi, --model ve --reasoning-effort açık girdilerdir. Mevcut Codex girişi kullanılır, global ayarlar değiştirilmez, model hatasında sessiz fallback yapılmaz.
- Demo/PUB başarısı builder geliştirmeye önkoşul değildir. Gizli brief'lerde practice vaka/cevap anahtarı varsayma; public runner zorunlu üretim aşaması değildir. Üretim bütçesi export dahil en fazla 30 dakikadır.
