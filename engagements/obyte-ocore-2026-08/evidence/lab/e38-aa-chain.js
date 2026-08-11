// E3-8 — AA to AA response chains on the two-node network (secondary triggers).
// Chain: TRIGGER pays AA-A; A's response pays AA-B; B's response pays AA-C; C's response pays the
// trigger author. Measures: (1) the chain executes end-to-end through handleSecondaryTriggers;
// (2) response ordering/hash determinism across both nodes; (3) the shared 10-response cap
// (MAX_RESPONSES_PER_PRIMARY_TRIGGER) with an 11-AA chain -> revert -> bounce-refund.
// ROLE=hub PORT=6611 / ROLE=node PORT=6612. Real composer/validation/writer/stabilization/AA path.
"use strict";
const path = require("path");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const WebSocket = require(O_CORE + "/node_modules/ws");
const { boot, keys, defOf, signHash, sleep } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e38-" + ROLE);
const TRIGGER_AMOUNT = 100000;
const CHAIN_LEN = parseInt(process.env.CHAIN_LEN || "3", 10); // 3 = happy path; 11 = cap test
// per-hop paid amount (decreasing to leave fee headroom)
const HOP = 2000; // per-hop paid amount (fee headroom: response costs ~550)

function makeSigner(key) {
	const constants = require(O_CORE + "/constants.js");
	return {
		readDefinition: (conn, address, cb) => cb(null, defOf(key)),
		readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }),
		readPrivateKey: (address, p, cb) => cb(null, Buffer.from(key.priv, "hex")),
	};
}

// chain AA i (0-indexed) pays AA i+1; the last AA pays the trigger author.
function chainAADefinition(nextAddress, isLast) {
	return ["autonomous agent", {
		bounce_fees: { base: 10000 },
		messages: [{
			app: "payment",
			payload: {
				asset: "base",
				outputs: [{ address: isLast ? "{trigger.address}" : nextAddress, amount: isLast ? 400 : HOP }]
			}
		}]
	}];
}

function dump(ctx, tag) {
	return Promise.all([
		ctx.query("SELECT address, unit, mci FROM aa_addresses ORDER BY address"),
		ctx.query("SELECT mci, unit, address FROM aa_triggers ORDER BY mci"),
		ctx.query("SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain, is_aa_response FROM units ORDER BY main_chain_index, unit"),
		ctx.query("SELECT unit, app, payload FROM messages WHERE app='payment' ORDER BY unit"),
		ctx.query("SELECT o.unit, o.output_index, o.address, o.amount FROM outputs o ORDER BY o.unit, o.output_index"),
	]).then(([aa, trig, units, msgs, outs]) => {
		console.log("[" + tag + "] AA_ADDRESSES:", JSON.stringify(aa.map(r => r.address.slice(0, 10))));
		console.log("[" + tag + "] AA_TRIGGERS_LEFT:", JSON.stringify(trig));
		console.log("[" + tag + "] UNITS:", JSON.stringify(units.map(r => ({ mci: r.main_chain_index, st: r.is_stable, seq: r.sequence, aa: r.is_aa_response, u: r.unit.slice(0, 10) }))));
		const payments = msgs.map(m => ({ u: m.unit.slice(0, 10), out: JSON.stringify((m.payload || {}).outputs || []) }));
		console.log("[" + tag + "] PAYMENT-MESSAGES:", JSON.stringify(payments));
		const chainResponses = units.filter(r => r.is_aa_response === 1).map(r => r.unit);
		console.log("[" + tag + "] AA_RESPONSE_HASHES:", JSON.stringify(chainResponses));
		return { aa, trig, units, msgs, outs, chainResponses };
	});
}

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout")), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: { protocol_version: "4.0", alt: "1", library: "ocore", library_version: "0.4.6", program: "e38-lab", program_version: "0.0.1" } }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e38", command: "subscribe", params: { subscription_id: "e38-sub", last_mci: 0, library_version: "0.4.6" } }]));
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
	const constants = require(O_CORE + "/constants.js");
	console.log("[" + ROLE + "] booted port", PORT, "chain_len=" + CHAIN_LEN, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	if (ROLE === "node") {
		console.log("[node] listening on", PORT, "- waiting for the AA chain...");
		let aaFired = false;
		let prevCount = -1;
		for (let i = 0; i < 240; i++) {
			await sleep(1000);
			const resp = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_aa_response=1");
			const trig = await ctx.query("SELECT COUNT(*) AS c FROM aa_triggers");
			if (resp[0].c > 0 || trig[0].c > 0) aaFired = true;
			const stable = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (aaFired && stable[0].c >= 4 + CHAIN_LEN + 2) break;
			if (resp[0].c !== prevCount) { prevCount = resp[0].c; console.log("[node] responses so far:", resp[0].c, "triggers_left:", trig[0].c); }
		}
		await sleep(5000);
		const state = await dump(ctx, "node-final");
		const chainLen = state.chainResponses.length;
		console.log("NODE-DONE responses=" + chainLen + " (expected " + (CHAIN_LEN <= 10 ? CHAIN_LEN : "revert") + ")");
		process.exit(0);
	}

	// ---- hub ----
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);
	const objectHash = ctx.objectHash;

	// build the chain AA definitions
	const aaDefs = [];
	const aaAddrs = [];
	for (let i = 0; i < CHAIN_LEN; i++) {
		// next address is aaAddrs[i+1] if not last; the address must be computable BEFORE the def
		const def = i === CHAIN_LEN - 1 ? chainAADefinition(null, true) : chainAADefinition("PENDING", false);
		// recompute with the real next address once known: two-pass
		aaDefs.push(null);
		aaAddrs.push(null);
	}
	// two-pass: the last AA has no next; build from the end
	for (let i = CHAIN_LEN - 1; i >= 0; i--) {
		const next = i === CHAIN_LEN - 1 ? null : aaAddrs[i + 1];
		aaDefs[i] = chainAADefinition(next, i === CHAIN_LEN - 1);
		aaAddrs[i] = objectHash.getChash160(aaDefs[i]);
	}
	console.log("[hub] AA chain addresses:", aaAddrs.map(a => a.slice(0, 10)).join(" -> "));

	const seq = [];
	for (let i = 0; i < CHAIN_LEN; i++) {
		seq.push({ label: "DEF-" + i, key: keys.user, addr: ctx.user_addr, opts: { messages: [{ app: "definition", payload: { address: aaAddrs[i], definition: aaDefs[i] } }] } });
	}
	seq.push({ label: "WAYPOINT-1", key: keys.witness, addr: ctx.witness_addr, opts: {} });
	seq.push({ label: "TRIGGER", key: keys.user, addr: ctx.user_addr, opts: { outputs: [{ address: aaAddrs[0], amount: TRIGGER_AMOUNT }, { address: ctx.user_addr, amount: 0 }] } });
	for (let i = 0; i < 5; i++) seq.push({ label: "WAYPOINT-" + (i + 2), key: keys.witness, addr: ctx.witness_addr, opts: {} });

	for (const step of seq) {
		const joint = await composeGeneric(ctx, step.key, step.addr, Object.assign({ label: step.label }, step.opts));
		await ctx.validateAndSave(joint, step.label);
		if (sendJoint(ws, joint)) console.log("[hub] relayed " + step.label);
		await sleep(900);
	}
	await sleep(15000);
	const state = await dump(ctx, "hub-final");
	console.log("HUB-DONE aa_addresses=" + state.aa.length + " responses=" + state.chainResponses.length);
	process.exit(state.aa.length >= CHAIN_LEN ? 0 : 4);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
