# ⚡ Zippy VPN — GitHub arkaly işleýän Happ VPN (Android · VPS-siz)

**Zippy VPN** — hiç hili VPS serwer satyn almazdan, göni **GitHub Actions** we **GitHub Pages** arkaly işleýän awtomatiki VPN abuna (podpiska) ulgamydyr. **Android**-da **Happ VPN** programmasy üçin ýörite sazlandy.

- **VPS gerek däl:** Serwerleri GitHub Actions her **3 sagatdan** awtomatiki ýygnaýar, **Xray-core** bilen hakyky birikmäni (`204`) we tizligi (`ms`) barlaýar hem-de täzeleýär.
- **Happ üçin taýýar:** `#profile-title`, `#profile-update-interval`, `#subscription-userinfo` we `happ://add/...` göni açylýan linkler bilen doly işleýär.
- **Güýçli protokollary goldaýar:** `VLESS Reality (Vision / XHTTP)`, `VLESS TLS (WS / gRPC)`, `Hysteria2 (QUIC)`, `Trojan`, `Shadowsocks AEAD / 2022`, `VMess TLS` we **Anti-DPI TLS Fragment** (`happ-fragment.json`).
- **Howpsuzlyk süzgüji:** Şifrlenmedik (`security=none`), sertifikaty nädogry (`allowInsecure=1`), ýalan reklama we içki/nädogry IP salgylary awtomatiki aýrylýar.
- **Android Web Panel:** 1 basymda Happ-a goşmak, linki nusgalamak, oflaýn QR kod we serwerleri ýurt/protokol boýunça süzmek (`docs/`).

---

## 📱 Happ VPN üçin taýýar abuna linkleri

Android telefonyňyzda aşakdaky linkleriň birini nusgalap, **Happ VPN** → **`+`** → **Buferden goş (Import from clipboard)** basyň:

### ⭐ 1. Esasy Happ Abuna (Maslahat berilýär — 100 serwer)
```text
https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/happ.txt
```

### 🚀 2. Çalt TOP-30 (Çalt ping üçin)
```text
https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/happ-fast.txt
```

### 🛡️ 3. Diňe VLESS Reality (Güýçli bloklama garşy)
```text
https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/reality.txt
```

### 🧩 4. Happ Fragment — Anti-DPI (Xray JSON)
```text
https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/happ-fragment.json
```

### 🔐 5. Happ Base64 (Adaty link ýüklenmese)
```text
https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/happ-base64.txt
```

### 📂 Protokol boýunça aýratyn linkler

| Görnüş | Abuna linki (Happ / Hiddify / v2rayNG) |
| :--- | :--- |
| **VLESS** | `https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/vless.txt` |
| **Hysteria2** | `https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/hy2.txt` |
| **Trojan** | `https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/trojan.txt` |
| **Shadowsocks** | `https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/ss.txt` |
| **VMess TLS** | `https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/vmess.txt` |
| **Ählisi (Base64)** | `https://raw.githubusercontent.com/redmirobot01-byte/Zippy/main/sub/base64.txt` |

### 🌐 Ätiýaçlyk aýna (Mirror) linkler
Eger internet prowaýderiňizde `raw.githubusercontent.com` haýal açylsa, şol bir abunany şu aýnalardan ulanyň:

- **jsDelivr CDN:**
  ```text
  https://cdn.jsdelivr.net/gh/redmirobot01-byte/Zippy@main/sub/happ.txt
  ```
- **GitHub Pages (Web Panel açylandan soň):**
  ```text
  https://redmirobot01-byte.github.io/Zippy/sub/happ.txt
  ```

---

## 🌐 Android Web Paneli işjeňleşdirmek (1 gezeklik — telefondan)

Web Paneli (`https://redmirobot01-byte.github.io/Zippy/`) açmak üçin:

1. Şu repozitoriýada **Settings** → **Pages** bölümine giriň.
2. **Build and deployment → Source** ýerinde **GitHub Actions** (ýa-da **Deploy from a branch** → `main` → `/docs`) saýlap **Save** basyň.
3. 1 minutdan soň **`https://redmirobot01-byte.github.io/Zippy/`** salgysynda **«Happ VPN-de Aç»** düwmeli we QR kodly paneliňiz işläp başlar.

## 🔄 Serwerleri telefondan islendik wagt täzelemek

Serwerler her **3 sagatdan** awtomatiki täzelenýär. El bilen derrew täzelemek üçin:

1. Repozitoriýada **Actions** bölümine giriň.
2. **«Zippy VPN — Serwerleri Täzele»** saýlaň.
3. **Run workflow** → **Run workflow** düwmesine basyň (1–2 minutda täze Xray barlagyndan geçen serwerler ýazylýar).

## ➕ Öz şahsy açaryňyzy goşmak

Öz tapan `vless://`, `trojan://`, `vmess://`, `ss://` ýa-da `hysteria2://` açarlaryňyzy [`config/custom_nodes.txt`](config/custom_nodes.txt) faýlyna her setire birini ýazyp ýatda saklaň — olar abunanyň iň ýokarsyna goşulýar. Çeşmeleri bolsa [`config/sources.json`](config/sources.json) faýlyndan sazlap bilersiňiz.

---

## 🛠️ Gurluşy

```text
Zippy/
├── .github/workflows/
│   ├── update-vpn.yml      # Her 3 sagat Xray-core bilen serwerleri barlap täzeleýär
│   └── pages.yml           # Android Web Paneli GitHub Pages-a çykarýar
├── config/
│   ├── sources.json        # Çeşmeler, çäkler we Happ profil sazlamalary
│   └── custom_nodes.txt    # Öz goşýan şahsy serwer açarlaryňyz
├── zippy/                  # Parser, howpsuzlyk süzgüji, Xray barlagçy we eksporter
├── scripts/
│   ├── update_subs.py      # Abunalary täzeleýän esasy skript
│   └── serve_panel.py      # Web Paneli lokal/göni görmek üçin HTTP serwer
├── sub/                    # Happ üçin taýýar abuna faýllary
├── docs/                   # Android üçin türkmen dilindäki Web Panel + QR generator
└── tests/                  # Awtomatiki testler
```
