// E4-8 — AA→AA response chains on the two-node network (retry of E3-8)
// Base: e31-aa-demo.js (confirmed AA path) + e26-aa-trigger.js (unconditional forwarder form).
// CHAIN = 12 forwarder AAs: trigger pays AA1; AA1 forwards 1000 to AA2; AA2 -> AA3; ...
// The composer's shared response budget (aa_composer.js:1834-1836
// `arrResponses.length >= MAX_RESPONSES_PER_PRIMARY_TRIGGER(10)` — "over all branches stemming
// from the primary trigger") should cap the chain at 10 responses regardless of AA count.
// ROLE=hub  PORT=6611 : posts the 12 definitions + waypoint + trigger + waypoints, relays over ws.
// ROLE=node PORT=6612 : receives, validates, saves, stabilizes; the chain fires at stabilization.
// Measures: response count (budget cutoff), response-hash determinism across nodes, work.
"use strict";
const path = require("path");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const WebSocket = require(O_CORE + "/node_modules/ws");
const { boot, keys, defOf, signHash, sleep, TOTAL } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e48-" + ROLE);
const CHAIN_N = parseInt(process.env.CHAIN_N || 12, 10);
const TRIGGER_AMOUNT = 100000;
const HOP_STEP = 2000; // per-hop decrease; each forwarder outputs less than it receives by >= the commission margin

function forwarderDef(nextAddress, hopAmount) {
	return ["autonomous agent", {
		bounce_fees: { base: 10000 },
		messages: [
			{
				app: "payment",
				payload: {
					asset: "base",
					outputs: [{ address: nextAddress, amount: hopAmount }]
				}
			}
		]
	}];
}

function makeSigner(key) {
	const constants = require(O_CORE + "/constants.js");
	return {
		readDefinition: (conn, address, cb) => cb(null, defOf(key)),
		readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }),
		readPrivateKey: (address, p, cb) => cb(null, Buffer.from(key.priv, "hex")),
	};
}

function dump(ctx, tag) {
	return Promise.all([
		ctx.query("SELECT address FROM aa_addresses ORDER BY address"),
		ctx.query("SELECT mci, unit, address FROM aa_triggers ORDER BY mci"),
		ctx.query("SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain, is_aa_response FROM units ORDER BY main_chain_index"),
		ctx.query("SELECT unit, output_index, address, amount FROM outputs WHERE is_spent=0 ORDER BY unit, output_index"),
		ctx.query("SELECT unit, address FROM aa_response_hashes ORDER BY unit"),
	]).then(([aa, trig, units, outs, respHashes]) => {
		console.log("[" + tag + "] AA_ADDRESSES:", aa.length);
		console.log("[" + tag + "] UNITS:", JSON.stringify(units.map(r => ({ mci: r.main_chain_index, seq: r.sequence, st: r.is_stable, aa: r.is_aa_response }))));
		console.log("[" + tag + "] UNS PENT-OUTPUTS:", JSON.stringify(outs.slice(0, 20)));
		console.log("[" + tag + "] AA_RESPONSE_HASHES:", JSON.stringify(respHashes.map(r => r.unit)));
		return { aa, trig, units, outs, respHashes };
	});
}

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout")), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: { protocol_version: "4.0", alt: "1", library: "ocore", library_version: "0.4.6", program: "e48-lab", program_version: "0.0.1" } }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e48", command: "subscribe", params: { subscription_id: "e48-sub", last_mci: 0, library_version: "0.4.6" } }]));
			setTimeout(() => resolve(ws), 800);
		});
	});
}
function sendJoint(ws, joint) {
	if (ws.readyState === 1) { ws.send(JSON.stringify(["justsaying", { subject: "joint", body: joint }])); return true; }
	return false;
}

function composeGeneric(ctx, key, address, opts) {
	return new Promise((resolve, reject) => {
		ctx.composer.composeJoint({
			paying_addresses: [address],
			signing_addresses: [address],
			outputs: opts.outputs || [{ address, amount: 0 }],
			messages: opts.messages || [],
			signer: makeSigner(key),
			callbacks: {
				ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
				ifError: (e) => reject(new Error(opts.label + " compose error: " + JSON.stringify(e).slice(0, 250))),
				ifNotEnoughFunds: (e) => reject(new Error(opts.label + " not enough funds: " + e)),
			},
		});
	});
}

async function main() {
	const ctx = await boot(DATA, PORT, { bServeAsHub: ROLE === "hub" });
	console.log("[" + ROLE + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	if (ROLE === "node") {
		console.log("[node] waiting for the hub's chain + AA triggers...");
		let aaFired = false;
		for (let i = 0; i < 240; i++) {
			await sleep(1000);
			const trig = await ctx.query("SELECT COUNT(*) AS c FROM aa_triggers");
			const resp = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_aa_response=1");
			if (trig[0].c > 0 || resp[0].c > 0) {
				aaFired = true;
				console.log("[node] AA machinery engaged (aa_triggers=" + trig[0].c + " responses=" + resp[0].c + ")");
			}
			const stable = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (aaFired && stable[0].c >= 8) break;
		}
		await sleep(8000);
		const state = await dump(ctx, "node-final");
		const responses = state.units.filter(r => r.is_aa_response === 1);
		console.log("[node] RESPONSE-COUNT:", responses.length, "(expected ~10 — the shared budget cap)");
		const stable = state.units.filter(r => r.is_stable === 1).length;
		console.log("NODE-DONE stable=" + stable + " aa_addresses=" + state.aa.length + " responses=" + responses.length);
		process.exit(responses.length >= 1 ? 0 : 3);
	}

	// ---- hub ----
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);
	const objectHash = ctx.objectHash;

	// compose the chain in REVERSE: the last AA pays the user; each earlier AA pays the next
	const defs = {};
	let nextAddress = ctx.user_addr;
	const addrByIndex = {};
	const amountByIndex = {};
	// each hop outputs AMOUNT[i] and receives AMOUNT[i-1]; AMOUNT[i] = AMOUNT[i-1] - HOP_STEP
	// leaves >= HOP_STEP (2000) for the response unit's commission (~1546) and margin.
	for (let i = CHAIN_N; i >= 1; i--) {
		const hopAmount = TRIGGER_AMOUNT - (i - 1) * HOP_STEP;
		const def = forwarderDef(nextAddress, hopAmount);
		const addr = objectHash.getChash160(def);
		defs[addr] = def;
		addrByIndex[i] = addr;
		amountByIndex[i] = hopAmount;
		nextAddress = addr;
	}
	console.log("[hub] chain of " + CHAIN_N + " forwarders; entry AA1 =", addrByIndex[1].slice(0, 16) + "...");

	const seq = [];
	// post all definitions
	for (let i = 1; i <= CHAIN_N; i++) {
		seq.push({ label: "DEF-" + i, key: keys.user, addr: ctx.user_addr, opts: { messages: [{ app: "definition", payload: { address: addrByIndex[i], definition: defs[addrByIndex[i]] } }] } });
	}
	seq.push({ label: "WAYPOINT-1", key: keys.witness, addr: ctx.witness_addr, opts: {} });
	seq.push({ label: "TRIGGER", key: keys.user, addr: ctx.user_addr, opts: {
		outputs: [{ address: addrByIndex[1], amount: TRIGGER_AMOUNT }, { address: ctx.user_addr, amount: 0 }],
	} });
	seq.push({ label: "WAYPOINT-2", key: keys.witness, addr: ctx.witness_addr, opts: {} });
	seq.push({ label: "WAYPOINT-3", key: keys.witness, addr: ctx.witness_addr, opts: {} });
	seq.push({ label: "WAYPOINT-4", key: keys.witness, addr: ctx.witness_addr, opts: {} });

	const t0 = Date.now();
	for (const step of seq) {
		const joint = await composeGeneric(ctx, step.key, step.addr, Object.assign({ label: step.label }, step.opts));
		await ctx.validateAndSave(joint, step.label);
		if (sendJoint(ws, joint)) console.log("[hub] relayed " + step.label);
		await sleep(700);
	}
	await sleep(15000);
	const state = await dump(ctx, "hub-final");
	const responses = state.units.filter(r => r.is_aa_response === 1);
	const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
	console.log("[hub] RESPONSE-COUNT:", responses.length, "elapsed=" + elapsed + "s");
	console.log("HUB-DONE responses=" + responses.length + " elapsed=" + elapsed + "s");
	process.exit(state.aa.length >= CHAIN_N ? 0 : 4);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
