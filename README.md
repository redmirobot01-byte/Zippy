# Zippy VPN

**GitHub-dan gurlan, işleýän VLESS / VMess / Shadowsocks serveri.**

Bu repo boşdy; indi içinde iki zadyň ikisi hem bar:

1. **Özüňiň dolandyrýan serweriň** — arassa Python-da ýazylan, hakyky şifrlemeli
   **Shadowsocks AEAD** + **VLESS** (Xray bilen utgaşykly, TLS goldaýar) inbound-lary,
   taýýar `vless://` / `ss://` linkleri, SOCKS5 klienti we VPS gurnaýjy skriptleri.
2. **Hakyky Xray-core gurnaýjysy** — `VLESS + REALITY`, `VMess + WebSocket` we
   `Shadowsocks` (DPI/petekleme garşy iň çydamly wariant).
3. **GitHub-daky mugt konfigurasiýalar** — 8 sany işjeň repodan 24 000+ täze
   VLESS/VMess/SS/Trojan linkini alyp, işleýänlerini saýlaýan gural.

> Tehniki taýdan bu proksi (TCP tunnel) — Android/iOS-daky v2rayNG / Hiddify /
> Shadowrocket ony enjamyň **VPN režimine** öwürýär. Kompýuterde `zippy local`
> SOCKS5 proxy berýär. Kernel TUN / WireGuard gerek bolsa, aşakdaky «Çäklendirmeler»
> bölümine serediň.

---

## 0. «Indi näme etmeli?» — 3 ýol, birini saýla

| Maksadyň | Näme etmeli | Wagty |
| --- | --- | --- |
| **Şu wagt telefonda internete girmek** | v2rayNG / Hiddify gur → [`configs/qr-verified-subscription.svg`](configs/qr-verified-subscription.svg) QR-ny skanirle → «Täzele» → düwün saýla → birik. Işlemese başga düwün saýla. | ~2 min |
| **Öz howpsuz, hemişelik VPN-iň** | VPS (Ubuntu, köpçülikleýin IP) al → aşakdaky bir buýrugy işlet → `/etc/zippy/links.txt`-däki linki telefona göçür. | ~10 min |
| **Kodyň işleýänini barlamak** | `pip install -r requirements.txt && python -m zippy selftest` (9/9 OK) | ~1 min |

> VPS-iň ýok bolsa, ikinji ýol üçin maňa «VPS ýok» diý — Hetzner/Oracle ýaly
> arzan ýa-da mugt wariantlary we ädimleri bilelikde saýlarys. VPS-iň IP-si bar bolsa,
> şony bersegi gurnama buýrugyny taýýar görnüşde ýazyp bererin.
>
> ⚠️ Birinji ýoldaky düwünler näbelli adamlaryňky — parol/bank/2FA üçin ulanmaň.

---

## 1. Çalt başlamak (öz kompýuteriňde, 1 minut)

```bash
git clone https://github.com/redmirobot01-byte/Zippy.git
cd Zippy
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python -m zippy selftest       # ← hakyky şifrleme bilen 9/9 uçdan-uça synag
```

Synag netijesi (hemmesi loopback-de, hakyky TCP + AES-GCM/ChaCha20 bilen):

```
[OK] shadowsocks aes-256-gcm (1 KB)
[OK] shadowsocks aes-128-gcm (64 KB, multi-chunk)
[OK] shadowsocks chacha20-poly1305 (200 KB)
[OK] vless tcp (2 KB)
[OK] wrong UUID rejected
[OK] tampered AEAD tag rejected
[OK] local SOCKS5 via VLESS
[OK] local SOCKS5 via Shadowsocks
[OK] vless over TLS (8 KB)
```

Soňra öz serweriňi işe giriz:

```bash
python -m zippy init --host 127.0.0.1 --tls       # zippy.json + sertifikat + açarlar
python -m zippy serve                              # 8388 (SS) we 8443 (VLESS+TLS)
python -m zippy links --write                      # links.txt, subscription.txt
python -m zippy qr --proto vless                   # telefona skanirlemek üçin QR SVG
python -m zippy local --port 10808                 # kompýuter üçin SOCKS5
curl --socks5-hostname 127.0.0.1:10808 https://example.com
```

`zippy.json` **hiç haçan Git-e goşulmaň** (`.gitignore` içinde, 0600 rugsat bilen ýazylýar) —
parol we UUID şol ýerde.

---

## 2. Hakyky VPN: VPS-e gurnamak

Serweriň (meselem Hetzner / Oracle / DigitalOcean, Ubuntu 22.04+) köpçülikleýin IP-si
bolmaly. Portlary bulut firewall-ynda hem açyň.

### a) Ýeňil wariant — şu repo (Python, hiç hili Docker gerek däl)

```bash
# GitHub-dan göni (bir buýruk):
curl -fsSL https://raw.githubusercontent.com/redmirobot01-byte/Zippy/arena/2a68f12a-zippy/deploy/install.sh | sudo -E bash

# ýa-da repony klonlap:
sudo -E bash deploy/install.sh
```

Skript: Python + `cryptography` gurnaýar → täze parol/UUID we TLS sertifikaty döredýär →
`systemd` hyzmatyny (`zippy.service`) işe girizýär → `ufw` portlaryny açýar →
`/etc/zippy/links.txt` içinde taýýar linkleri çykarýar.

Üýtgedip bolýar: `ZIPPY_HOST`, `SS_PORT`, `VLESS_PORT`, `ZIPPY_BRANCH`.

```
sudo systemctl status zippy --no-pager
sudo journalctl -u zippy -f
cat /etc/zippy/links.txt
```

### b) DPI / petekleme garşy — hakyky Xray-core + REALITY (maslahat)

```bash
curl -fsSL https://raw.githubusercontent.com/redmirobot01-byte/Zippy/arena/2a68f12a-zippy/deploy/install-xray.sh | sudo -E bash
```

[XTLS/Xray-install](https://github.com/XTLS/Xray-install) arkaly
[Xray-core](https://github.com/XTLS/Xray-core) `v26.11.9` gurnalýar we üç inbound açylýar:

| Port | Protokol | Link |
| --- | --- | --- |
| 443 | VLESS + XTLS-RPRX-Vision + REALITY | `vless://…?security=reality&pbk=…&sid=…` |
| 8080 | VMess + WebSocket | `vmess://…` |
| 8388 | Shadowsocks `aes-256-gcm` (TCP+UDP) | `ss://…` |

Açarlar `/etc/zippy-xray/credentials.json`, abuna `/etc/zippy-xray/subscription.txt`.
`REALITY_DEST` we `REALITY_SNI` üýtgedip, VPS-iňizden elýeterli bolan HTTPS saýtyny saýlaň
(ýerine ýetirilmezden öň `xray run -test -config …` bilen barlanýar).

Panel gerek bolsa (web UI, köp ulanyjy, statistikalar):
[3x-ui](https://github.com/MHSanaei/3x-ui) — `bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh)`.

---

## 3. Kliente birikdirmek

| Enjam | Programma | Näme girizmeli |
| --- | --- | --- |
| Android | v2rayNG / Hiddify / NekoBox | `vless://…` ýa-da `vmess://…` linki (ýa-da QR) |
| iPhone | Shadowrocket / Hiddify / Streisand | `ss://…` ýa-da `vless://…` |
| Windows | v2rayN / NekoRay / Hiddify | `links.txt`, `client.json` |
| Linux/macOS | `python -m zippy local` → SOCKS5 | `curl --socks5-hostname 127.0.0.1:10808 …` |
| Ählisi | abuna (subscription) | `subscription.txt` / `configs/README.md` URL-leri |

`--tls` bilen gurlan VLESS öz-gol çekilen sertifikat ulanýar, şonuň üçin linkde
`allowInsecure=1` bar. Hakyky domen + Let's Encrypt (ýa-da REALITY) ulanmak has gowy.

---

## 4. GitHub-daky mugt taýýar konfigurasiýalar

```bash
python -m zippy subs --proto vless,vmess,ss --limit 30
python -m zippy subs --proto vless --check --limit 20 --out subscription.txt
python -m zippy sources
```

8 sany işjeň GitHub reposyndan (barlanan: 2026-11-16) **24 045** üýtgeşik konfig alynýar.
`--check` diňe TCP porty açyk bolanlary görkezýär. Nusga sanaw: `configs/free-configs-sample.txt`.
Jikme-jiklikler we **howpsuzlyk duýduryşlary**: [`configs/README.md`](configs/README.md).

> ⚠️ Köpçülikleýin proksiler näbelli adamlar tarapyndan dolandyrylýar — parol/bank/2FA
> üçin ulanmaň. Öz serveriňiz elmydama howpsuz.

---

## 5. Buýruklaryň sanawy

| Buýruk | Wezipesi |
| --- | --- |
| `python -m zippy init --host IP --tls` | konfig + UUID + parol + TLS sertifikaty |
| `python -m zippy serve` | serweri işe giriz |
| `python -m zippy links --write` | `links.txt`, `subscription.txt` |
| `python -m zippy qr --proto vless` | QR kody (SVG) |
| `python -m zippy client-config` | Xray/v2rayN üçin `client.json` |
| `python -m zippy local --proto vless` | lokal SOCKS5 (10808) |
| `python -m zippy subs --check` | GitHub-dan işleýän mugt konfiglar |
| `python -m zippy cert` | TLS sertifikatyny täzele |
| `python -m zippy selftest` | 9 sany uçdan-uça synag |
| `pytest -q` | 9 sany birlik + integrasiýa testi |

---

## 6. Protokollar we olaryň çeşmeleri

Öz kody GitHub-daky resmi implementasiýalaryň **hakyky çeşme kody** bilen deňeşdirilip ýazyldy
(çaklama däl):

| Zat | Çeşme |
| --- | --- |
| VLESS kelleleri, buýruklar, salgy tipleri | [XTLS/Xray-core](https://github.com/XTLS/Xray-core) `proxy/vless/encoding/{encoding,addons}.go`, `common/protocol/{headers,address,payload}.go` |
| Shadowsocks AEAD: `EVP_BytesToKey`, `HKDF-SHA1("ss-subkey")`, 0x3FFF çank, LE nonce | [shadowsocks/shadowsocks-crypto](https://github.com/shadowsocks/shadowsocks-crypto), [shadowsocks-rust](https://github.com/shadowsocks/shadowsocks-rust) |
| SIP002 `ss://` linki | Shadowsocks SIP002 spesifikasiýasy |
| Xray gurnama we REALITY | [XTLS/Xray-install](https://github.com/XTLS/Xray-install), [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui) |

Goldanýan şifrler: `aes-256-gcm` (deslapky), `aes-128-gcm`, `chacha20-ietf-poly1305`.
Her ugurda aýratyn 32/16 baýt duz (salt) we 0-dan başlaýan 12 baýtlyk nonce hasaplaýjy;
her çank iki AEAD operasiýasy (uzynlyk + maglumat) bilen goralýar.

---

## 7. Howpsuzlyk we çäklendirmeler

**Howpsuzlyk**

- Parol/UUID `zippy.json`-da, 0600; loglarda ýazylmaýar.
- Nädogry UUID we bozulan AEAD tegi derrew ret edilýär (synaglarda barlandy).
- Deslapky `allow_private=false`: klient serweriň öz LAN/127.0.0.1 adreslerine çykyp bilmeýär (SSRF goragy).
- VLESS `security=none` **şifrlenen däl**, diňe UUID bilen tassyklanýar → hökman `--tls` ýa-da REALITY ulanyň.
  Shadowsocks hemişe şifrlenen.
- Hiç hili traffik ýazgysy (log) saklanmaýar; diňe `host:port` INFO derejesinde çykyş edilýär.

**Çäklendirmeler**

- Python serweri **diňe TCP** goldaýar (UDP/QUIC ýok). UDP gerek bolsa `install-xray.sh` (SS TCP+UDP) ulanyň.
- Ýadro TUN enjamy ýok → bu proksi. Telefonda VPN režimini v2rayNG/Hiddify üpjün edýär;
  kompýuterde ähli traffigi TUN-a geçirmek üçin `tun2socks` / [boringtun](https://github.com/cloudflare/boringtun)
  (WireGuard) ýaly goşmaça gural gerek.
- Öz-gol çekilen TLS sertifikat → klientde `allowInsecure=1` (linkde bar). MITM howpy sebäpli
  diňe synag üçin; önümçilikde hakyky domen + sertifikat ýa-da REALITY.
- Bir UUID / bir parol (ýönekeýlik üçin). Köp ulanyjy gerek bolsa 3x-ui paneli.
- Ýerli kanunlary we hyzmat şertlerini berjaý edip ulanyň.

---

## Faýl agajy

```
zippy/            server + protokollar (crypto, stream, shadowsocks, vless, socks, subs, cli)
deploy/install.sh         Python serwerini VPS-e gurnaýjy (systemd)
deploy/install-xray.sh    Xray-core + REALITY + VMess + SS gurnaýjy
configs/                  mugt GitHub konfig çeşmeleri + nusga sanaw
tests/                    pytest (9 test) + selftest moduly
```

Kody erkin ulanyp, üýtgedip bilersiňiz (açyk çeşme). Mesele / goşant üçin GitHub Issues açyň.
