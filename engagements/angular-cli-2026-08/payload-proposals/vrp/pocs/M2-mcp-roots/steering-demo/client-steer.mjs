// C3B steering demo client — tool call 1: get_best_practices returns the
// instruction-shaped attacker guide (repo-derived content -> assistant instructions).
// Roots answered with pathToFileURL(path.join(import.meta.dirname, 'workspace')).href (the declared MCP root).
import { spawn }
import path from 'node:path';
import { pathToFileURL } from 'node:url'; from 'node:child_process';
const srv = path.join(import.meta.dirname, 'mcp-server.cjs');
const child = spawn(process.execPath, [srv], { stdio: ['pipe','pipe','pipe'] });
let buf = '';
const pending = new Map();
child.stderr.on('data', d => process.stderr.write('[SRV] ' + d.toString().slice(0, 300)));
child.stdout.on('data', (d) => {
  buf += d.toString();
  let idx;
  while ((idx = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, idx).trim(); buf = buf.slice(idx+1);
    if (!line) continue;
    let msg; try { msg = JSON.parse(line); } catch { continue; }
    if (msg.method && msg.id !== undefined) {
      if (msg.method === 'roots/list') {
        child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: { roots: [{ uri: pathToFileURL(path.join(import.meta.dirname, 'workspace')).href }] } }) + '\n');
      } else {
        child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: {} }) + '\n');
      }
      continue;
    }
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  }
});
const call = (id, method, params) => new Promise((res) => { pending.set(id, res); child.stdin.write(JSON.stringify({jsonrpc:'2.0', id, method, params}) + '\n'); setTimeout(()=>res({timeout:true}), 30000); });
async function main() {
  const init = await call(1, 'initialize', { protocolVersion: '2025-06-18', capabilities: { roots: { listChanged: true } }, clientInfo: { name: 'c3b-steer', version: '1' } });
  child.stdin.write(JSON.stringify({jsonrpc:'2.0', method:'notifications/initialized'}) + '\n');
  await new Promise(r=>setTimeout(r, 1800));
  const r = await call(3, 'tools/call', { name: 'get_best_practices', arguments: { workspacePath: path.join(import.meta.dirname, 'workspace') } });
  console.log('TOOL-1-RESP:', JSON.stringify(r).slice(0, 1600));
  child.kill(); process.exit(0);
}
main();
