# Mevcut adayın public ölçümü (ayrı çalışma ortamı)

Bu paket yalnızca resmî kit runner'ını, istemciyi ve public vaka verisini taşır.
Workflow üretmez veya değiştirmez. Python 3.10+ ve `freya-bank-mock.freyavoice.workers.dev`
adresine doğrulanmış HTTPS erişimi olan bir makinede çalıştır.

Gerekli ortam değişkenlerini o makinede güvenli olarak ayarla:
`FREYA_API_KEY` (workspace anahtarı) ve `FREYA_BANK_TEAM_KEY` (aynı takım anahtarı).
Anahtarları pakete, çıktıya veya git'e koyma; TLS doğrulamasını kapatma.

```bash
tar -xzf freya-public-runner.tar.gz
cd freya-public-runner
python3 tools/run_cases.py 815d58a1-f50a-4793-8499-92c866640e61 \
  --only PUB-01 --out results/pub01.json
```

`results/pub01.json` içinde `passed: 1`, `total: 1` ve ilgili satırda
`pass: true` görülürse aynı adayın Brief A kapsamını ölç:

```bash
python3 tools/run_cases.py 815d58a1-f50a-4793-8499-92c866640e61 \
  --brief A --out results/brief-a.json
```

Test sonuç dosyaları customer_id içerir; yerel ve özel tutulmalı. Hata analizi
için her satırdaki `failed`, `tools`, `call_id` ve `slowest_turn_s` alanlarını
incele. `freya.get_call(call_id)` gerçek konuşma/tool olaylarını verir.
PUB-01 geçmezse 10 vakayı bu sıranın koşulu gereği başlatma; önce hatayı ayır.
Bu makinede testleri koşturmak için Codex veya builder model erişimi gerekmez.
