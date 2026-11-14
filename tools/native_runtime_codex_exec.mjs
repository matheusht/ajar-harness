/** Host-private WebSocket framing for an owned native Codex exec-server stdio pipe. */
import { createInterface } from 'node:readline';
import { timingSafeEqual } from 'node:crypto';
const limit = 1048576;
let server, socket, token;
const emit = value => {
  const line = JSON.stringify(value) + '\n';
  if (Buffer.byteLength(line) > 2 * limit || process.stdout.writableLength > 4 * limit) process.exit(2);
  process.stdout.write(line);
};
const equal = value => typeof value === 'string' && value.length === token.length &&
  timingSafeEqual(Buffer.from(value), Buffer.from(token));
for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  if (Buffer.byteLength(line) > 2 * limit) break;
  try {
    const data = JSON.parse(line);
    if (!server) {
      if (typeof data.token !== 'string' || data.token.length < 32) break;
      token = 'Bearer ' + data.token;
      server = Bun.serve({ hostname: '127.0.0.1', port: 0,
        fetch(request, server) {
          if (socket || new URL(request.url).pathname !== '/' || !equal(request.headers.get('authorization'))) {
            return new Response('', { status: 403 });
          }
          if (!server.upgrade(request)) return new Response('', { status: 400 });
        },
        websocket: { maxPayloadLength: limit, backpressureLimit: 4 * limit, closeOnBackpressureLimit: true,
          open(ws) { socket = ws; },
          message(ws, message) {
            if (typeof message !== 'string' || Buffer.byteLength(message) > limit) return ws.close(1009);
            try { JSON.parse(message); emit({ frame: message }); } catch { ws.close(1003); }
          },
          close() { process.exit(0); },
        },
      });
      emit({ ready: `ws://127.0.0.1:${server.port}/` });
    } else {
      if (!socket || typeof data.frame !== 'string' || Buffer.byteLength(data.frame) > limit) break;
      JSON.parse(data.frame);
      if (socket.send(data.frame) === 0) break;
    }
  } catch { break; }
}
socket?.close();
server?.stop(true);
