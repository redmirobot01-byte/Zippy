# Mugt köpçülikleýin konfigurasiýalar (GitHub)

Bu papka **hakyky, şu wagt GitHub-da neşir edilýän** VLESS / VMess / Shadowsocks / Trojan
konfigurasiýalaryny almak üçin gurallary we bir nusga sanawy saklaýar.

## ⚠️ Ilki bilen okaň

Bu düwünler **näbelli adamlar** tarapyndan dolandyrylýar. Şonuň üçin:

- parollar, bank, 2FA kodlary, şahsy hatlar üçin **ulanmaň**;
- olar siziň IP-iňizi, görýän wagtyňyzy we domenleriňizi loglap biler;
- şifrlenmedik HTTP traffigini üýtgedip biler;
- düwünler birnäçe sagatda ýapylyp bilýär — şonuň üçin hemişe täzesini alyň;
- howpsuzlyk gerek bolsa **öz serveriňizi** gurup ulanyň: `sudo bash deploy/install.sh`.

## ⚡ Iň çalt ýol: QR-ny skanirle (telefon)

`configs/qr-verified-subscription.svg` faýlyny kompýuteriň ekranynda aç (ýa-da
aşakdaky görnüşde görkez) → **v2rayNG / Hiddify**-da «+» → **QR skanirle** →
abuna awtomatiki goşular → «Täzele» → bir düwün saýlap birik.

| QR faýly | Näme berýär |
| --- | --- |
| `qr-verified-subscription.svg` | **hemmesi, barlanan** (maslahat) |
| `qr-vless-subscription.svg` | diňe VLESS / Reality |
| `qr-vmess-subscription.svg` | diňe VMess |
| `qr-shadowsocks-subscription.svg` | diňe Shadowsocks |

QR-laryň içinde diňe ýokardaky abuna URL-leri bar — her gezek skanirläniňde
GitHub-dan **iň täze** sanaw alynýar (konfiglar könelemeýär).

Şeýle hem `configs/subscription-fresh.txt` — 30 sany täze konfig base64 abuna
görnüşinde (2026-11-16). Mazmunyny göçürip, klientiň «clipboard-dan import» bölümine goý.

Öz QR-yňy döretmek üçin:

```bash
python -m zippy qr --url "https://raw.githubusercontent.com/.../configs_base64.txt" --out qr.svg
```

## Täze konfiglary almak

```bash
python -m zippy subs --proto vless,vmess,ss --limit 30
python -m zippy subs --proto vless --check --limit 20          # diňe porty açyk bolanlar
python -m zippy subs --proto ss,vless --check --out subscription.txt
python -m zippy sources                                       # çeşmeleriň sanawy
```

`--check` her düwüne TCP birikme synagyny geçirýär (diňe porty açyk bolanlary görkezýär).
`--out subscription.txt` netijäni **base64 abuna** görnüşinde ýazýar — ony v2rayNG /
Hiddify / NekoBox-a «abuna URL» hökmünde goşup bilersiňiz.

2026-11-16 barlagynda 8 çeşmeden **24 045** sany üýtgeşik konfig alyndy
(14 261 VLESS, 6 120 VMess, 2 755 Shadowsocks, 848 Trojan, …).

## Göni abuna (subscription) URL-leri

Klientiňize göçürip goýuň (her gezek täze sanawy özi alar):

| Protokol | URL |
| --- | --- |
| Hemmesi (barlanan) | `https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/verified/configs_base64.txt` |
| VLESS | `https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/protocols/vless.txt` |
| VMess | `https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/protocols/vmess.txt` |
| Shadowsocks | `https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/protocols/shadowsocks.txt` |
| VLESS Reality (täze) | `https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt` |
| Garyşyk (PSG) | `https://raw.githubusercontent.com/itsyebekhe/PSG/main/config.txt` |
| Garyşyk (Aggregator) | `https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt` |
| VLESS (.proxy) | `https://raw.githubusercontent.com/mheidari98/.proxy/main/vless` |

Repolar: [0xRadikal/Free-v2ray-Configs](https://github.com/0xRadikal/Free-v2ray-Configs),
[igareck/vpn-configs-for-russia](https://github.com/igareck/vpn-configs-for-russia),
[itsyebekhe/PSG](https://github.com/itsyebekhe/PSG),
[mahdibland/V2RayAggregator](https://github.com/mahdibland/V2RayAggregator),
[mheidari98/.proxy](https://github.com/mheidari98/.proxy).

## `free-configs-sample.txt`

Şu papkadaky nusga sanaw — 2026-11-16 UTC-da alnan 16 sany konfig. Ol **barlanmady**
(sandbox-dan daşarky porta çykyş ýok). Göçürip ulanmazdan öň:

```bash
python -m zippy subs --proto vless,vmess,ss --check --limit 20
```

bilen täzelerini we işleýänlerini alyň.

## Klientler

- Android: **v2rayNG**, **Hiddify**, **NekoBox**
- iOS: **Shadowrocket**, **Hiddify**, **Streisand**
- Windows / macOS / Linux: **v2rayN**, **NekoRay**, **Hiddify**, `python -m zippy local` (SOCKS5)
