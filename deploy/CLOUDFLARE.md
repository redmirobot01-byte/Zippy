# VPS-siz öz VPN-iň: Cloudflare Workers (mugt, kredit kartsyz)

Bu iň amatly **uzak möhletli** wariant: ne VPS, ne pul, ne kredit karty gerek.
[Cloudflare Workers Free](https://developers.cloudflare.com/workers/platform/pricing/)
plany — günde 100 000 sorag, kredit kartsyz, hemişelik mugt. Serwer seniň
hasabyňda işleýär, ýagny traffigiňi näbelli adamlar görmeýär (diňe
Cloudflare-iň özi, edil islendik HTTPS saýtynda bolşy ýaly).

`deploy/cloudflare-worker.js` — **VLESS over WebSocket / TLS** inbound-y.
Protokol Xray/v2rayNG bilen utgaşykly; `cloudflare:sockets` arkaly daşarky
TCP birikmesini açýar. Node-da Cloudflare API-leriň mock'lary bilen
**uçdan-uça synagdan geçirildi** (`node tests/worker_test.mjs`, 5/5 OK).

---

## Ädimme-ädim (5 minut)

### 1. UUID döret we ýatda sakla
```bash
python3 -c "import uuid; print(uuid.uuid4())"
# mysal: 8b3c1d2e-....   ← bu SENIŇ gizlin açaryň, hiç ýerde neşir etme
```

### 2. Cloudflare hasaby
<https://dash.cloudflare.com/sign-up> → e-poçta bilen hasap aç (kart soramaýar) → e-poçtany tassykla.

### 3. Worker döret
`Workers & Pages` → **Create** → **Create Worker** → ady (meselem `zippy-blue42`) → **Deploy**.

### 4. Kody goý
**Edit code** → redaktordaky hemme zady poz →
[`deploy/cloudflare-worker.js`](cloudflare-worker.js) faýlynyň **hemmesini** göçürip goý →
**Save and deploy**.

> `wrangler` ýa-da `git` gerek däl — diňe brauzerdäki editor ýeterli.

### 5. `UUID` üýtgeýjisini goş
Worker → **Settings** → **Variables and Secrets** → **Add variable**:

| Ady | Bahasy |
| --- | --- |
| `UUID` | 1-nji ädimdäki UUID |
| `WS_PATH` *(islege görä)* | `/ws` (deslapky) |

Soňra **Save and deploy** bas (üýtgeýji üýtgese gaýtadan deploy gerek).

### 6. URL-ni al
Worker sahypasyndaky URL, meselem:
```
https://zippy-blue42.myname.workers.dev
```
Barla:
- `https://zippy-blue42.myname.workers.dev/` → `It works.` sahypasy görünmeli;
- `https://.../<UUID>` → base64 abuna teksti görünmeli.

`UUID` goýulmadyk bolsa 503 ýalňyşlygy çykar — bu howpsuzlyk üçin şeýle:
hemmeler üçin umumy açar ulanylmaýar.

### 7. Link + QR döret
```bash
python -m zippy worker-link \
  --host zippy-blue42.myname.workers.dev \
  --uuid 8b3c1d2e-....
```
Çykar:
```
configs/worker-link.txt          vless:// linki
configs/worker-qr.svg            telefona skanirlemek üçin QR
configs/worker-subscription.txt  base64 abuna
configs/worker-client.json       v2rayN / NekoRay / Xray üçin
```

### 8. Telefonda birik
**v2rayNG / Hiddify / NekoBox** → `+` → **QR skanirle** → `worker-qr.svg`-ny
skanirle → birik. Ýa-da abuna URL hökmünde şuny goş:
```
https://zippy-blue42.myname.workers.dev/<UUID>
```

El bilen girizseň, parametrler hökman şeýle bolmaly:
`security=tls`, `type=ws`, `path=/ws`, `sni=<host>`, `encryption=none`, **`ed` ýok**.

---

## Çäklendirmeler we duýduryşlar

| Zat | Düşündiriş |
| --- | --- |
| Diňe TCP | UDP / QUIC / Hysteria ýok (Workers `connect()` diňe TCP). DNS we köp saýt TCP bilen işleýär. |
| 100 s boş wagt | Free planda WebSocket 100 sekunt hereketsiz ýapylýar; klientde keepalive açyk bolsun. |
| 100 000 sorag/gün | WebSocket birikmesi 1 sorag hasaplanýar, habarlar hasaplanmaýar; şahsy ulanyşa ýeterlik. |
| Cloudflare IP-leri | Worker Cloudflare-iň öz IP-lerine birigip bilmeýär; olary klientde «gönümel / direct» goş. |
| `workers.dev` peteklenip bilner | Käbir sebitlerde domen ýapyk bolsa, öz domeniňi Cloudflare-e goşup şoňa bagla. |
| Gizlinlik | UUID — ýeke-täk açar. `/<UUID>` salgysyny bilen adam seniň Worker-iňi ulanyp biler. Ony paýlaşma. |
| Kanun | Ýerli kanunlary we Cloudflare-iň hyzmat şertlerini berjaý et. |

## Näsazlyklary çözmek

| Alamat | Sebäp / çözgüt |
| --- | --- |
| `503 UUID goýulmady` | 5-nji ädim gaýtalanmady ýa-da deploy edilmedi |
| Birikme derrew üzülýär | `security=tls` / `type=ws` / `path=/ws` parametrleri ýalňyş; `ed` parametri bar — aýyr |
| `404 Not Found` | `WS_PATH` we linkdäki `path` gabat gelmeýär |
| Brauzerde `It works.` ýok | Kod doly göçürilmedi ýa-da deploy bolmady |
| Haýal / kesilýär | Başga düwün gerek däl — Worker-iň özi; 100 s keepalive meselesine seret |

## Synag
```bash
node tests/worker_test.mjs          # Node 18+: mock Cloudflare API-leri bilen 5/5
python -m zippy verify --self-test  # barlaýjynyň özi
pytest -q                          # 12 test
```
