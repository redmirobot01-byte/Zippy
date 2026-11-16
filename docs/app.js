/* Zippy VPN — Android-first Web Panel for Happ VPN */
(function () {
  "use strict";

  const DEFAULT_REPO = "redmirobot01-byte/Zippy";
  const DEFAULT_BRANCH = "main";

  const state = {
    repo: DEFAULT_REPO,
    branch: DEFAULT_BRANCH,
    mirrorId: "raw",
    protoFilter: "all",
    countryFilter: "all",
    stats: null,
    qrValue: "",
  };

  const MAIN_SUBS = [
    {
      id: "happ",
      file: "happ.txt",
      title: "Esasy Happ Abuna",
      tag: "Maslahat berilýär",
      tagClass: "tag-green",
      recommended: true,
      countKey: "happ_main",
      desc: "Reality, VLESS, Hysteria2, Trojan we SS — deňagramly iň gowy serwerler. Happ-da awto-täzelenýär.",
    },
    {
      id: "fast",
      file: "happ-fast.txt",
      title: "Çalt TOP-30",
      tag: "Ýokary tizlik",
      tagClass: "tag-cyan",
      recommended: false,
      countKey: "happ_fast",
      desc: "Iň ýokary baha alan 30 serwer — Happ-da ping barlagy 2 sekuntda tamamlanýar.",
    },
    {
      id: "reality",
      file: "reality.txt",
      title: "VLESS Reality",
      tag: "Anti-Blok",
      tagClass: "tag-amber",
      recommended: false,
      countKey: "reality",
      desc: "Diňe XTLS-Reality serwerleri — çäklendirilen mobil we Wi-Fi torlar üçin iň güýçli gorag.",
    },
    {
      id: "fragment",
      file: "happ-fragment.json",
      title: "Happ Fragment (Xray JSON)",
      tag: "Anti-DPI",
      tagClass: "tag-violet",
      recommended: false,
      countKey: "fragment",
      desc: "TLS ClientHello paketini bölekläp geçirýär — SNI bloklanýan torlarda ýörite görnüş.",
    },
    {
      id: "happ_b64",
      file: "happ-base64.txt",
      title: "Happ Base64",
      tag: "Base64",
      tagClass: "tag-cyan",
      recommended: false,
      countKey: "happ_main",
      desc: "Base64 görnüşde kodlanan esasy abuna (Happ, Hiddify we v2rayNG bilen hem işleýär).",
    },
  ];

  const PROTO_SUBS = [
    { file: "vless.txt", title: "VLESS", countKey: "vless" },
    { file: "hy2.txt", title: "Hysteria2 (QUIC)", countKey: "hy2" },
    { file: "trojan.txt", title: "Trojan TLS", countKey: "trojan" },
    { file: "ss.txt", title: "Shadowsocks AEAD", countKey: "ss" },
    { file: "vmess.txt", title: "VMess TLS", countKey: "vmess" },
    { file: "base64.txt", title: "Ählisi (Base64)", countKey: "total" },
  ];

  const PROTO_FILTERS = [
    { id: "all", label: "Ählisi" },
    { id: "reality", label: "REALITY" },
    { id: "vless", label: "VLESS" },
    { id: "hy2", label: "Hysteria2" },
    { id: "trojan", label: "Trojan" },
    { id: "ss", label: "Shadowsocks" },
    { id: "vmess", label: "VMess" },
  ];

  function isGithubPagesHost() {
    return location.hostname.endsWith(".github.io");
  }

  function isHttpLiveHost() {
    return location.protocol === "https:" || location.protocol === "http:";
  }

  function getMirrors() {
    const [owner, repoName] = state.repo.split("/");
    const branch = state.branch || "main";
    const list = [
      {
        id: "raw",
        label: "GitHub Raw",
        build: (file) => `https://raw.githubusercontent.com/${owner}/${repoName}/${branch}/sub/${file}`,
      },
      {
        id: "pages",
        label: "GitHub Pages",
        build: (file) => `https://${owner}.github.io/${repoName}/sub/${file}`,
      },
      {
        id: "jsdelivr",
        label: "jsDelivr CDN",
        build: (file) => `https://cdn.jsdelivr.net/gh/${owner}/${repoName}@${branch}/sub/${file}`,
      },
    ];
    if (isHttpLiveHost() && !isGithubPagesHost()) {
      list.push({
        id: "current",
        label: "Göni (şu sahypa)",
        build: (file) => new URL(`./sub/${file}`, location.href).href,
      });
    }
    return list;
  }

  function buildSubUrl(file) {
    const mirrors = getMirrors();
    const chosen = mirrors.find((m) => m.id === state.mirrorId) || mirrors[0];
    return chosen.build(file);
  }

  function buildHappDeepLink(target) {
    return `happ://add/${target}`;
  }

  let toastTimer = null;
  function showToast(msg) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2300);
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
      ta.focus();
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

  function openQrModal(title, value) {
    const backdrop = document.getElementById("qrBackdrop");
    const titleEl = document.getElementById("qrTitle");
    const frame = document.getElementById("qrFrame");
    if (!backdrop || !titleEl || !frame) return;

    state.qrValue = value;
    titleEl.textContent = title;
    const svg = window.ZippyQR ? window.ZippyQR.renderSvg(value, 3) : null;
    if (svg) {
      frame.innerHTML = svg;
    } else {
      frame.textContent = "Açar gaty uzyn — «Nusgala» düwmesini ulanyň.";
      frame.style.color = "#0f172a";
      frame.style.fontSize = "0.82rem";
      frame.style.padding = "18px";
    }
    backdrop.hidden = false;
  }

  function closeQrModal() {
    const backdrop = document.getElementById("qrBackdrop");
    if (backdrop) backdrop.hidden = true;
  }

  function formatRelativeTime(isoStr, fallback) {
    if (!isoStr) return fallback || "—";
    const ts = Date.parse(isoStr);
    if (Number.isNaN(ts)) return fallback || isoStr;
    const diffMin = Math.max(0, Math.round((Date.now() - ts) / 60000));
    if (diffMin < 2) return "Ýaňyja";
    if (diffMin < 60) return `${diffMin} min öň`;
    const hrs = Math.floor(diffMin / 60);
    if (hrs < 24) return `${hrs} sagat öň`;
    const days = Math.floor(hrs / 24);
    return `${days} gün öň`;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderMirrors() {
    const wrap = document.getElementById("mirrorPills");
    if (!wrap) return;
    wrap.textContent = "";
    const mirrors = getMirrors();
    for (const m of mirrors) {
      const btn = el("button", "pill" + (m.id === state.mirrorId ? " active" : ""), m.label);
      btn.type = "button";
      btn.setAttribute("role", "radio");
      btn.setAttribute("aria-checked", m.id === state.mirrorId ? "true" : "false");
      btn.addEventListener("click", () => {
        state.mirrorId = m.id;
        renderMirrors();
        updatePrimaryHero();
        renderSubscriptions();
      });
      wrap.appendChild(btn);
    }
  }

  function updatePrimaryHero() {
    const url = buildSubUrl("happ.txt");
    const urlEl = document.getElementById("primaryUrl");
    const openEl = document.getElementById("openHappPrimary");
    if (urlEl) urlEl.textContent = url;
    if (openEl) openEl.href = buildHappDeepLink(url);
  }

  function renderHeaderStats() {
    const s = state.stats;
    const statusText = document.getElementById("statusText");
    const updatedAt = document.getElementById("updatedAt");
    const mainCount = document.getElementById("mainCount");
    const countryCount = document.getElementById("countryCount");

    if (!s) {
      if (statusText) statusText.textContent = "Taýýar";
      return;
    }

    const counts = s.counts || {};
    const total = counts.total || 0;
    const main = counts.happ_main || 0;
    const cLen = (s.countries || []).length;

    if (statusText) statusText.textContent = `İşjeň · ${total} serwer`;
    if (updatedAt) {
      updatedAt.textContent = formatRelativeTime(s.updated_at, s.updated_human);
      updatedAt.title = s.updated_human || s.updated_at || "";
    }
    if (mainCount) mainCount.textContent = `${main} serwer`;
    if (countryCount) countryCount.textContent = `${cLen}+ ýurt`;

    const repoUrl = `https://github.com/${state.repo}`;
    for (const id of ["repoLink", "footerRepoLink"]) {
      const a = document.getElementById(id);
      if (a) a.href = repoUrl;
    }
    const actionsA = document.getElementById("actionsRunLink");
    if (actionsA) actionsA.href = `${repoUrl}/actions/workflows/update-vpn.yml`;
    const customA = document.getElementById("customNodesLink");
    if (customA) customA.href = `${repoUrl}/edit/${state.branch}/config/custom_nodes.txt`;
  }

  function renderSubscriptions() {
    const mainWrap = document.getElementById("mainSubsList");
    const protoWrap = document.getElementById("protoGrid");
    const counts = (state.stats && state.stats.counts) || {};

    if (mainWrap) {
      mainWrap.textContent = "";
      for (const item of MAIN_SUBS) {
        const url = buildSubUrl(item.file);
        const card = el("article", "sub-card" + (item.recommended ? " recommended" : ""));

        const top = el("div", "sub-top");
        const left = el("div");
        const titleRow = el("div", "sub-title-row");
        titleRow.appendChild(el("span", "sub-title", item.title));
        titleRow.appendChild(el("span", `tag ${item.tagClass}`, item.tag));
        left.appendChild(titleRow);
        left.appendChild(el("p", "sub-desc", item.desc));
        top.appendChild(left);

        const cnt = counts[item.countKey];
        if (typeof cnt === "number") {
          top.appendChild(el("span", "count-chip", `${cnt} sany`));
        }
        card.appendChild(top);

        const actions = el("div", "sub-actions");
        const openBtn = el("a", "btn btn-accent-outline btn-sm", "Happ-da aç");
        openBtn.href = buildHappDeepLink(url);

        const copyBtn = el("button", "btn btn-secondary btn-sm", "Linki nusgala");
        copyBtn.type = "button";
        copyBtn.addEventListener("click", () => {
          copyText(url, `✓ «${item.title}» linki nusgalandy!`);
        });

        const qrBtn = el("button", "btn btn-secondary btn-sm", "QR");
        qrBtn.type = "button";
        qrBtn.addEventListener("click", () => openQrModal(item.title, url));

        actions.append(openBtn, copyBtn, qrBtn);
        card.appendChild(actions);
        mainWrap.appendChild(card);
      }
    }

    if (protoWrap) {
      protoWrap.textContent = "";
      for (const item of PROTO_SUBS) {
        const url = buildSubUrl(item.file);
        const row = el("div", "proto-item");
        const info = el("div");
        info.appendChild(el("div", "proto-name", item.title));
        const cnt = counts[item.countKey];
        info.appendChild(
          el("div", "proto-meta", typeof cnt === "number" ? `${cnt} serwer` : item.file)
        );

        const btns = el("div", "proto-btns");
        const openA = el("a", "btn btn-accent-outline btn-sm", "Happ");
        openA.href = buildHappDeepLink(url);
        const copyB = el("button", "btn btn-secondary btn-sm", "Nusgala");
        copyB.type = "button";
        copyB.addEventListener("click", () => {
          copyText(url, `✓ ${item.title} linki nusgalandy!`);
        });
        btns.append(openA, copyB);

        row.append(info, btns);
        protoWrap.appendChild(row);
      }
    }
  }

  function getFilteredNodes() {
    const all = (state.stats && state.stats.featured_nodes) || [];
    return all.filter((n) => {
      if (state.protoFilter !== "all" && n.protocol !== state.protoFilter) return false;
      if (state.countryFilter !== "all" && n.country !== state.countryFilter) return false;
      return true;
    });
  }

  function renderServerFilters() {
    const pWrap = document.getElementById("protoFilterPills");
    const cWrap = document.getElementById("countryFilterPills");
    const all = (state.stats && state.stats.featured_nodes) || [];

    if (pWrap) {
      pWrap.textContent = "";
      for (const pf of PROTO_FILTERS) {
        const btn = el(
          "button",
          "pill" + (state.protoFilter === pf.id ? " active" : ""),
          pf.label
        );
        btn.type = "button";
        btn.addEventListener("click", () => {
          state.protoFilter = pf.id;
          renderServerFilters();
          renderServerList();
        });
        pWrap.appendChild(btn);
      }
    }

    if (cWrap) {
      cWrap.textContent = "";
      const seen = new Map();
      for (const n of all) {
        if (n.country && n.country !== "UN") {
          seen.set(n.country, {
            code: n.country,
            flag: n.flag || "🌐",
            count: (seen.get(n.country)?.count || 0) + 1,
          });
        }
      }
      const countries = [{ code: "all", label: "Ähli ýurtlar" }].concat(
        Array.from(seen.values())
          .sort((a, b) => b.count - a.count)
          .slice(0, 12)
          .map((c) => ({ code: c.code, label: `${c.flag} ${c.code} (${c.count})` }))
      );

      for (const c of countries) {
        const btn = el(
          "button",
          "pill" + (state.countryFilter === c.code ? " active" : ""),
          c.label
        );
        btn.type = "button";
        btn.addEventListener("click", () => {
          state.countryFilter = c.code;
          renderServerFilters();
          renderServerList();
        });
        cWrap.appendChild(btn);
      }
    }
  }

  function badgeTagClass(protocol) {
    if (protocol === "reality") return "tag-amber";
    if (protocol === "hy2") return "tag-violet";
    if (protocol === "vless") return "tag-green";
    return "tag-cyan";
  }

  function renderServerList() {
    const listWrap = document.getElementById("nodeList");
    const countEl = document.getElementById("filteredCount");
    if (!listWrap) return;

    const nodes = getFilteredNodes();
    if (countEl) countEl.textContent = `${nodes.length} serwer görkezilýär`;
    listWrap.textContent = "";

    if (!nodes.length) {
      listWrap.appendChild(
        el("div", "empty-state", "Bu süzgüç boýunça serwer tapylmady. Başga protokoly ýa-da ýurdy saýlaň.")
      );
      return;
    }

    for (const n of nodes) {
      const row = el("div", "node-row");
      const main = el("div", "node-main");
      const title = el("div", "node-title");

      title.appendChild(el("span", "", `${n.flag || "🌐"} ${n.country_tk || n.country}`));
      title.appendChild(el("span", `tag ${badgeTagClass(n.protocol)}`, n.badge));
      if (typeof n.latency_ms === "number" && n.latency_ms > 0) {
        title.appendChild(el("span", "latency-badge", `${n.latency_ms} ms`));
      }

      const sniPart = n.sni && n.sni !== "—" ? ` · SNI: ${n.sni}` : "";
      const sub = el(
        "div",
        "node-sub",
        `${n.host_masked}:${n.port} · ${n.transport}${sniPart}`
      );
      main.append(title, sub);

      const actions = el("div", "node-actions");
      const happBtn = el("a", "btn btn-accent-outline btn-sm", "Happ");
      happBtn.href = buildHappDeepLink(n.uri);
      happBtn.title = "Happ VPN-ä goş";

      const copyBtn = el("button", "btn btn-secondary btn-sm", "Nusgala");
      copyBtn.type = "button";
      copyBtn.addEventListener("click", () => {
        copyText(n.uri, `✓ ${n.flag} ${n.badge} açary nusgalandy! Happ-da «+» basyp goşuň.`);
      });

      const qrBtn = el("button", "btn btn-secondary btn-sm", "QR");
      qrBtn.type = "button";
      qrBtn.addEventListener("click", () => {
        openQrModal(`${n.flag} ${n.country_tk} · ${n.badge}`, n.uri);
      });

      actions.append(happBtn, copyBtn, qrBtn);
      row.append(main, actions);
      listWrap.appendChild(row);
    }
  }

  function initTabs() {
    const buttons = document.querySelectorAll(".tab-btn");
    const panels = document.querySelectorAll(".tab-panel");
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.getAttribute("data-tab");
        buttons.forEach((b) => {
          const active = b === btn;
          b.classList.toggle("active", active);
          b.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach((p) => {
          p.classList.toggle("active", p.id === `panel-${target}`);
        });
      });
    });
  }

  function initGlobalActions() {
    document.getElementById("copyPrimaryBtn")?.addEventListener("click", () => {
      const url = buildSubUrl("happ.txt");
      copyText(url, "✓ Happ abuna linki nusgalandy!");
    });

    document.getElementById("qrPrimaryBtn")?.addEventListener("click", () => {
      const url = buildSubUrl("happ.txt");
      openQrModal("Zippy VPN — Happ Abuna", url);
    });

    document.getElementById("copyKeysBtn")?.addEventListener("click", () => {
      const nodes = (state.stats && state.stats.featured_nodes) || [];
      if (!nodes.length) {
        showToast("Serwer sanawy entek ýüklenmedi");
        return;
      }
      const batch = nodes.slice(0, 25).map((n) => n.uri).join("\n");
      copyText(batch, `✓ ${Math.min(25, nodes.length)} sany açar nusgalandy! Happ-da «+» → Buferden goş basyň.`);
    });

    document.getElementById("copyFilteredBtn")?.addEventListener("click", () => {
      const nodes = getFilteredNodes();
      if (!nodes.length) {
        showToast("Nusgalamak üçin serwer ýok");
        return;
      }
      const text = nodes.map((n) => n.uri).join("\n");
      copyText(text, `✓ ${nodes.length} serwer nusgalandy! Happ-da buferden goşuň.`);
    });

    document.getElementById("qrCloseBtn")?.addEventListener("click", closeQrModal);
    document.getElementById("qrCopyBtn")?.addEventListener("click", () => {
      if (state.qrValue) copyText(state.qrValue, "✓ Nusgalandy!");
    });
    document.getElementById("qrBackdrop")?.addEventListener("click", (e) => {
      if (e.target.id === "qrBackdrop") closeQrModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeQrModal();
    });
  }

  async function loadStats() {
    // Prefer live current-host URL when previewed outside github.io so links work immediately
    if (isHttpLiveHost() && !isGithubPagesHost()) {
      state.mirrorId = "current";
    }
    renderMirrors();
    updatePrimaryHero();
    renderSubscriptions();

    try {
      const resp = await fetch(`./sub/stats.json?t=${Date.now()}`, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.stats = data;
      if (data.repo && data.repo.includes("/")) state.repo = data.repo;
      if (data.branch) state.branch = data.branch;
    } catch (_) {
      const statusText = document.getElementById("statusText");
      if (statusText) statusText.textContent = "Oflaýn tertip";
    }

    renderMirrors();
    updatePrimaryHero();
    renderHeaderStats();
    renderSubscriptions();
    renderServerFilters();
    renderServerList();
  }

  initTabs();
  initGlobalActions();
  loadStats();
})();
