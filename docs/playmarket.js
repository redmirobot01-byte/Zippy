/* Zippy VPN — Play Market link ýasaýjy (Google Play sowda linkleri) */
(function () {
  "use strict";

  const PLAY_STORE_BASE = "https://play.google.com/store/apps/details";

  const AI_SYSTEM_PROMPT =
    "Sen Android programmalarynyň Google Play Market-däki paket adyny tapýan kömekçisің. " +
    "Adaty nädogry sözler, baglanyşyklar ýa-da şerhler ýazma. Jogabyň diňe paýlaşyk görünüşi " +
    "bolmaly, mysal üçin com.example.app. Nädogry bolsa, jogap bermekden ýeňrel.";

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
    { name: "1.1.1.1 (Cloudflare)", package: "com.cloudflare.1111", note: "Cloudflare-iň çalt DNS we VPN ulanylyşy" },
    // --- AI programmalary ---
    { name: "ChatGPT", package: "com.openai.chatgpt", note: "OpenAI-yň söhbetdeşlik AI programmasy" },
    { name: "Gemini", package: "com.google.ai.gemini", note: "Google-yň ýokary AI söhbetdeşligi" },
    { name: "Microsoft Copilot", package: "com.microsoft.copilot", note: "Microsoft-yň AI kömekçisi" },
    { name: "Perplexity", package: "com.perplexity.ai", note: "Sorag-jogap AI we gözleg" },
    { name: "Claude", package: "com.anthropic.claude", note: "Anthropic-iň Claude AI söhbetdeşligi" }
  ];

  const STATE = { current: null, aiOn: false };

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
    aiToggle: $("pmAiToggle"),
    aiSettings: $("pmAiSettings"),
    aiKey: $("pmAiKey"),
    aiBase: $("pmAiBase"),
    aiModel: $("pmAiModel"),
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

  /* AI akylly gözleg: programma adyny AI-a berip paket adyny tapýar.
     API açary ýeke-ýeke brauzerde galýar, servera iberilýär (local sazlama). */
  async function aiLookup(name, apiKey, baseUrl, model) {
    const response = await fetch(baseUrl.replace(/\/$/, "") + "/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + apiKey
      },
      body: JSON.stringify({
        model: model || "gpt-4o-mini",
        temperature: 0,
        max_tokens: 20,
        messages: [
          { role: "system", content: AI_SYSTEM_PROMPT },
          { role: "user", content: "Google Play Market programmasynyň ady: " + name }
        ]
      })
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error("API " + response.status + " hatasy" + (detail ? ": " + detail.slice(0, 160) : ""));
    }
    const data = await response.json();
    const text = (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || "";
    const match = text.match(/[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+/);
    return match ? match[0] : null;
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

  function renderResult(app, link, packageName, displayName) {
    STATE.current = link;
    els.result.hidden = false;
    els.appName.textContent = displayName || (app ? app.name : "Play Market programmasy");
    els.packageText.textContent = "id=" + packageName;
    els.link.textContent = link;
    els.open.href = link;
    hideError();
  }

  async function resolveSearch(query) {
    const text = (query || "").trim();
    if (!text) {
      hideError();
      return;
    }
    if (isPackageId(text)) {
      renderResult(null, buildLink(text), text);
      return;
    }
    if (STATE.aiOn) {
      const apiKey = els.aiKey.value.trim();
      if (!apiKey) {
        els.result.hidden = true;
        showError("AI akylly gözleg üçin açary giriziň (saýlaw sahypasyndaky «🤖 AI» düwmesinden soň görünýän meýdança).");
        return;
      }
      try {
        const packageName = await aiLookup(text, apiKey, els.aiBase.value.trim() || "https://api.openai.com/v1", els.aiModel.value.trim());
        if (packageName) {
          renderResult(null, buildLink(packageName), packageName, text);
          return;
        }
        showToast("AI paketi tapmady — ýerli registre geçýär");
      } catch (err) {
        showToast("AI hata: " + err.message + " — ýerli registre geçýär");
      }
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
    APPS.forEach((app) => {
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

  els.aiToggle.addEventListener("click", () => {
    STATE.aiOn = !STATE.aiOn;
    els.aiToggle.classList.toggle("active", STATE.aiOn);
    els.aiSettings.hidden = !STATE.aiOn;
    if (STATE.aiOn) els.aiKey.focus();
    hideError();
  });
  els.aiKey.addEventListener("input", () => {
    if (els.aiKey.value.trim()) sessionStorage.setItem("zippy_ai_key", els.aiKey.value.trim());
    else sessionStorage.removeItem("zippy_ai_key");
  });

  renderChips();
  renderAppList();

  // Üýtgeşmeleri gaýtadan açanyňda açary ýatda sakla
  els.aiKey.value = sessionStorage.getItem("zippy_ai_key") || "";
})();
