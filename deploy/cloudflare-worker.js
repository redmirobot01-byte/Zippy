// Zippy — VLESS-over-WebSocket on Cloudflare Workers.
// VPS gerek däl: Workers Free plan (100 000 sorag/gün, kredit karty gerek däl).
//
// Gurnamak: deploy/CLOUDFLARE.md
//   Settings → Variables → UUID = <python -c "import uuid;print(uuid.uuid4())">
//   (islege görä WS_PATH = /ws)
// Soňra:  python -m zippy worker-link --host <name>.<sub>.workers.dev --uuid <UUID>
//
// Protokol: VLESS kellesi (XTLS/Xray-core bilen utgaşykly) WebSocket binar
// habarynyň içinde; daşarky TCP birikme `cloudflare:sockets` connect() bilen.
// Diňe TCP (UDP/QUIC ýok). TLS-i Cloudflare özi üpjün edýär (https://…workers.dev).
//
// BELLIK: Workers gelen WebSocket habarlaryny bir akym hökmünde görýär, şonuň
// üçin jogap kellesini (0x00 0x00) aýratyn habar bilen ibermek bolýar.

import { connect } from "cloudflare:sockets";

const DEFAULT_PATH = "/ws";

function uuidToBytes(uuid) {
  const hex = String(uuid).replace(/-/g, "").toLowerCase();
  if (!/^[0-9a-f]{32}$/.test(hex)) throw new Error("UUID nädogry");
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function sameId(a, b) {
  let diff = 0;
  for (let i = 0; i < 16; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

/** VLESS haýyş kellesini oka: ver|uuid|addonsLen|addons|cmd|port|atyp|addr|payload */
function parseVless(bytes) {
  let p = 0;
  if (bytes[p++] !== 0) throw new Error("VLESS wersiýasy");
  const id = bytes.slice(p, p + 16);
  p += 16;
  const addonsLen = bytes[p++];
  if (addonsLen) p += addonsLen;
  const cmd = bytes[p++];
  if (cmd !== 1) throw new Error("diňe TCP goldanylýar");
  const port = (bytes[p] << 8) | bytes[p + 1];
  p += 2;
  const atyp = bytes[p++];
  let hostname = "";
  if (atyp === 1) {
    hostname = [...bytes.slice(p, p + 4)].join(".");
    p += 4;
  } else if (atyp === 2) {
    const n = bytes[p++];
    hostname = new TextDecoder().decode(bytes.slice(p, p + n));
    p += n;
  } else if (atyp === 3) {
    const parts = [];
    for (let i = 0; i < 8; i++) {
      parts.push(((bytes[p] << 8) | bytes[p + 1]).toString(16));
      p += 2;
    }
    hostname = parts.join(":");
  } else {
    throw new Error("näbelli salgy tipi");
  }
  if (!hostname || !port) throw new Error("nyşana ýok");
  return { id, hostname, port, payload: bytes.slice(p) };
}

function toBytes(data) {
  if (typeof data === "string") return new TextEncoder().encode(data);
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  return new Uint8Array(0);
}

function handleWebSocket(ws, expectedId) {
  let writer = null;
  let started = false;
  let closed = false;

  const shutdown = () => {
    if (closed) return;
    closed = true;
    if (writer) {
      try {
        const p = writer.close();
        if (p && typeof p.catch === "function") p.catch(() => {});
      } catch (_) { /* eýýäm ýapyk */ }
    }
    try { ws.close(); } catch (_) { /* ignore */ }
  };

  ws.addEventListener("message", async (event) => {
    const bytes = toBytes(event.data);
    if (!bytes.length || closed) return;

    if (!started) {
      let head;
      try {
        head = parseVless(bytes);
      } catch (_) {
        shutdown();
        return;
      }
      if (!sameId(head.id, expectedId)) { shutdown(); return; }

      let socket;
      try {
        socket = connect({ hostname: head.hostname, port: head.port });
        writer = socket.writable.getWriter();
        started = true;
        ws.send(new Uint8Array([0, 0]));   // VLESS jogap kellesi: ver + addonsLen=0
        if (head.payload.length) await writer.write(head.payload);
      } catch (_) {
        shutdown();
        return;
      }

      // daşarky akym → WebSocket
      const reader = socket.readable.getReader();
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done || closed) break;
          ws.send(value);
        }
      } catch (_) { /* target ýapdy */ }
      shutdown();
      return;
    }

    // indiki habarlar — arassa ýük
    try { await writer.write(bytes); } catch (_) { shutdown(); }
  });

  ws.addEventListener("close", shutdown);
  ws.addEventListener("error", shutdown);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const uuid = env.UUID;
    if (!uuid) {
      return new Response("UUID goýulmady: Worker → Settings → Variables → UUID goşuň.",
        { status: 503, headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    const path = env.WS_PATH || DEFAULT_PATH;

    // Amatly abuna URL-i: https://<worker>/<UUID>
    if (url.pathname === "/" + uuid) {
      const q = new URLSearchParams({
        encryption: "none", security: "tls", type: "ws",
        host: url.hostname, path, sni: url.hostname, fp: "chrome",
      });
      const link = `vless://${uuid}@${url.hostname}:443?${q}#Zippy-Worker`;
      const b64 = btoa(link + "\n");
      return new Response(b64, { headers: { "content-type": "text/plain; charset=utf-8" } });
    }

    const upgrade = (request.headers.get("Upgrade") || "").toLowerCase();
    if (upgrade !== "websocket") {
      return new Response("<!doctype html><title>Zippy</title><h1>It works.</h1>",
        { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
    }
    if (url.pathname !== path) {
      return new Response("Not Found", { status: 404 });
    }

    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];
    server.accept();
    let expected;
    try { expected = uuidToBytes(uuid); } catch (_) {
      return new Response("UUID nädogry", { status: 500 });
    }
    handleWebSocket(server, expected);
    return new Response(null, { status: 101, webSocket: client });
  },
};
