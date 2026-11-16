// End-to-end test of deploy/cloudflare-worker.js under Node with mocked
// Cloudflare APIs (WebSocketPair + cloudflare:sockets). Run: node tests/worker_test.mjs
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

class MockWS {
  constructor() {
    this.listeners = {};
    this.sent = [];
    this.closed = false;
    this.accepted = false;
  }
  accept() { this.accepted = true; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  async emit(data) {
    for (const fn of this.listeners.message || []) await fn({ data });
  }
  send(data) { this.sent.push(data); }
  close() {
    if (this.closed) return;
    this.closed = true;
    for (const fn of this.listeners.close || []) fn({});
  }
  bytes() {
    return Buffer.concat(this.sent.map((x) => Buffer.from(
      x instanceof ArrayBuffer ? new Uint8Array(x) : x)));
  }
}

let lastServer = null;
globalThis.WebSocketPair = class {
  constructor() {
    this[0] = new MockWS();
    this[1] = new MockWS();
    lastServer = this[1];
  }
};
// Node's Response rejects status 101; Cloudflare accepts it.
globalThis.Response = class {
  constructor(body, init = {}) {
    this.body = body;
    this.status = init.status;
    this.headers = init.headers || {};
    this.webSocket = init.webSocket;
  }
};

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "zippy-worker-"));
const src = fs.readFileSync(path.join(root, "deploy/cloudflare-worker.js"), "utf8");
assert.ok(src.includes('from "cloudflare:sockets"'), "worker import tapylmady");
fs.writeFileSync(path.join(tmp, "mock.mjs"),
  fs.readFileSync(path.join(root, "tests/mock-cloudflare-sockets.mjs")));
fs.writeFileSync(path.join(tmp, "worker.mjs"),
  src.replace('from "cloudflare:sockets"', 'from "./mock.mjs"'));

const UUID = "11111111-2222-3333-4444-555555555555";
const GOOD = Buffer.from(UUID.replace(/-/g, ""), "hex");
const BAD = Buffer.alloc(16, 0x42);

function vlessHeader(id, host, port, payload) {
  return Buffer.concat([
    Buffer.from([0]), id, Buffer.from([0, 1]),
    Buffer.from([(port >> 8) & 255, port & 255]),
    Buffer.from([1]), Buffer.from(host.split(".").map(Number)),
    payload,
  ]);
}

async function waitFor(predicate, ms = 3000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (predicate()) return;
    await new Promise((r) => setTimeout(r, 20));
  }
  throw new Error("wagt geçdi: jogap gelmedi");
}

const target = http.createServer((_req, res) => {
  res.writeHead(200, { "Content-Length": 11 });
  res.end("HELLO-ZIPPY");
});
await new Promise((r) => target.listen(0, "127.0.0.1", r));
const targetPort = target.address().port;

const { default: worker } = await import(pathToFileURL(path.join(tmp, "worker.mjs")).href);
const req = (url, upgrade) => ({
  url,
  headers: new Headers(upgrade ? { Upgrade: "websocket" } : {}),
});

// 1. Missing UUID must fail loudly, not silently use a shared secret.
const noUuid = await worker.fetch(req("https://zippy.test/ws", true), {});
assert.equal(noUuid.status, 503);
console.log("  [OK] UUID goýulmasa 503 (umumy açar ulanylmaýar)");

// 2. Ordinary HTTP request returns a decoy page.
const page = await worker.fetch(req("https://zippy.test/", false), { UUID });
assert.equal(page.status, 200);
assert.match(page.body, /It works/);
console.log("  [OK] adaty HTTP soragyna örtük sahypa");

// 3. Full VLESS-over-WS round trip with a real TCP target.
const wsResp = await worker.fetch(req("https://zippy.test/ws", true), { UUID });
assert.equal(wsResp.status, 101);
assert.ok(lastServer.accepted);
const ws = lastServer;
const request = Buffer.from(
  "GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
await ws.emit(vlessHeader(GOOD, "127.0.0.1", targetPort, request));
await waitFor(() => ws.bytes().includes("HELLO-ZIPPY"));
const response = ws.bytes();
assert.equal(response[0], 0, "VLESS jogap wersiýasy");
assert.equal(response[1], 0, "addons uzynlygy");
assert.match(response.toString("latin1"), /HTTP\/1\.1 200/);
assert.match(response.toString("latin1"), /HELLO-ZIPPY/);
console.log("  [OK] VLESS/WS uçdan-uça: kelle → TCP → HTTP jogaby");

// 4. Wrong UUID is rejected without leaking any data.
const badResp = await worker.fetch(req("https://zippy.test/ws", true), { UUID });
assert.equal(badResp.status, 101);
const badWs = lastServer;
await badWs.emit(vlessHeader(BAD, "127.0.0.1", targetPort, request));
assert.equal(badWs.closed, true, "nädogry UUID kabul edildi");
assert.equal(badWs.bytes().length, 0, "nädogry UUID-a jogap iberildi");
console.log("  [OK] nädogry UUID ret edildi");

// 5. Subscription endpoint returns a base64 vless:// link.
const sub = await worker.fetch(req(`https://zippy.test/${UUID}`, false), { UUID });
const decoded = Buffer.from(sub.body, "base64").toString();
assert.match(decoded, /^vless:\/\//);
assert.match(decoded, /security=tls/);
assert.match(decoded, /type=ws/);
console.log("  [OK] /UUID abuna URL-i");

target.close();
fs.rmSync(tmp, { recursive: true, force: true });
console.log("\n  5/5 Worker synagy geçdi ✅\n");
