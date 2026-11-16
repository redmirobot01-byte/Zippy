// Node test mock for `cloudflare:sockets` — real TCP to a local target.
import net from "node:net";
import { Duplex } from "node:stream";

export function connect({ hostname, port }) {
  const socket = net.connect({ host: hostname, port });
  socket.on("error", () => {});
  const { readable, writable } = Duplex.toWeb(socket);
  return { readable, writable };
}
