/* Zippy VPN — Play Market link ýasaýjy (Google Play sowda linkleri) */
(function () {
  "use strict";

  const PLAY_STORE_BASE = "https://play.google.com/store/apps/details";

  /* Python moduly zippy/playmarket.py-daky registr bilen deňleşýär. */
  const APPS = [
    { name: "Happ VPN", package: "com.happproxy", note: "Zippy VPN abunalary bilen işleýän Happ VPN klienti" },
    { name: "v2rayNG", package: "com.v2ray.ng", note: "VLESS / VMess / Trojan goldaýan meşhur Android klient" },
    { name: "Hiddify Next", package: "com.hiddify.next", note: "VLESS, Hysteria2, Trojan we Shadowsocks goldaýan klient" },
    { name: "NekoBox", package: "io.nekobox", note: "sing-box we Xray ýadroly köp protokol klienti" },
    { name: "Clash for Android", package: "com.github.kr328.clash", note: "Clash-yň ilkinji resmi Android görnüşi" },
    { name: "ClashMetaForAndroid", package: "com.meta.clash", note: "Müşderi meseleleri üçin Clash Meta görnüşi" },
    { name: "Shadowsocks", package: "com.shadowsocks", note: "Shadowsocks-yň resmi Android klienti" },
    { name: "WireGuard", package: "com.wireguard.android", note: "WireGuard VPN-iň resmi Android klienti" },
    { name: "1.1.1.1 (Cloudflare)", package: "com.cloudflare.1111", note: "Cloudflare-iň çalt DNS we VPN ulanylyşy" }
  ];

  const STATE = { current: null };

  const $ = (id) => document.getElementById(id);
  const els = {
    search: $("pmSearch"),
    packageInput: $("pmPackage"),
    packageBtn: $("pmPackageBtn"),
    chips: $("pmChips"),
    result: $("pmResult"),
    error: $("pmError"),
    appName: $("pmAppName"),
    packageText: $("pmPackageText"),
    link: $("pmLink"),
    open: $("pmOpen"),
    copy: $("pmCopy"),
    list: $("pmAppList"),
    toast: $("toast")
  };

  let toastTimer = null;
  function showToast(msg) {
    if (!els.toast) return;
    els.toast.textContent = msg;
    els.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2300);
  }

  async function copyText(text, okMsg) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        showToast(okMsg || "✓ Nusgalandy!");
        return true;
      }
    } catch (_) {
      // Fallback below for Android WebViews
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      showToast(ok ? (okMsg || "✓ Nusgalandy!") : "Nusgalap bolmady");
      return ok;
    } catch (_) {
      showToast("Nusgalap bolmady");
      return false;
    }
  }

  function buildLink(packageName) {
    return PLAY_STORE_BASE + "?id=" + encodeURIComponent(packageName);
  }

  const PACKAGE_RE = /^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$/;

  function isPackageId(text) {
    return PACKAGE_RE.test((text || "").trim());
  }

  function findApps(query) {
    const q = (query || "").trim().toLowerCase();
    if (!q) return [];
    const hits = [];
    for (const app of APPS) {
      const haystack = (app.name + " " + app.package + " " + app.name.toLowerCase()).toLowerCase();
      if (haystack.includes(q)) {
        hits.push(Object.assign({}, app, { score: 0 }));
      }
    }
    return hits;
  }

  function hideError() {
    els.error.hidden = true;
    els.error.textContent = "";
  }

  function showError(msg) {
    els.error.textContent = msg;
    els.error.hidden = false;
  }

  function renderResult(app, link, packageName) {
    STATE.current = link;
    els.result.hidden = false;
    els.appName.textContent = app ? app.name : "Play Market programmasy";
    els.packageText.textContent = "id=" + packageName;
    els.link.textContent = link;
    els.open.href = link;
    hideError();
  }

  function resolveSearch(query) {
    const text = (query || "").trim();
    if (!text) {
      hideError();
      return;
    }
    if (isPackageId(text)) {
      renderResult(null, buildLink(text), text);
      return;
    }
    const apps = findApps(text);
    if (!apps.length) {
      els.result.hidden = true;
      showError(
        "Tapylmady: «" + text + "». Gözleg sahypasynda sanawy aşağıdan görkeziň, ýa-da paket adyny «Ýa-da paket ady» sahypasyndaky ýere ýyzyň."
      );
      return;
    }
    renderResult(apps[0], buildLink(apps[0].package), apps[0].package);
  }

  function renderChips() {
    APPS.slice(0, 6).forEach((app) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pill";
      btn.textContent = app.name;
      btn.addEventListener("click", () => {
        els.search.value = app.name;
        resolveSearch(app.name);
      });
      els.chips.appendChild(btn);
    });
  }

  function renderAppList() {
    APPS.forEach((app) => {
      const row = document.createElement("div");
      row.className = "app-row";

      const main = document.createElement("div");
      main.className = "app-row-main";

      const name = document.createElement("div");
      name.className = "app-row-name";
      name.textContent = app.name;

      const note = document.createElement("div");
      note.className = "app-row-note";
      note.textContent = app.note + " · " + app.package;

      main.appendChild(name);
      main.appendChild(note);

      const open = document.createElement("a");
      open.className = "btn btn-secondary btn-sm";
      open.href = buildLink(app.package);
      open.target = "_blank";
      open.rel = "noopener noreferrer";
      open.textContent = "Play-da aç";

      row.appendChild(main);
      row.appendChild(open);
      els.list.appendChild(row);
    });
  }

  els.search.addEventListener("input", (event) => resolveSearch(event.target.value));
  els.packageBtn.addEventListener("click", () => resolveSearch(els.packageInput.value));
  els.packageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") resolveSearch(els.packageInput.value);
  });
  els.packageInput.addEventListener("input", () => {
    if (!els.packageInput.value.trim()) hideError();
  });
  els.copy.addEventListener("click", () => {
    if (STATE.current) copyText(STATE.current, "✓ Play Market linki nusgalandy!");
  });

  renderChips();
  renderAppList();
})();
