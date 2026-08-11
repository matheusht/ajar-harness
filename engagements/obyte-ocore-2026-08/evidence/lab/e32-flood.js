// E3-2 — ATTACKER F4 flood end-to-end: can the attacker reach count>=30 with elapsed=1
// (all flood units stamped the same second), and what does the settlement charge?
// Structure follows E2-9's proven two-node pattern (waypoint -> burst -> waypoint -> settle tail),
// with one difference: the burst units are STAMPED to a fixed second (T0+1) so the settlement
// elapsed = 1 (mainnet-style). tps_interval=1 (mainnet).
// ROLE=node PORT=6612 / ROLE=hub PORT=6611 NODE_PORT=6612 N_FLOOD=30
"use strict";
const path = require("path");
const WebSocket = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/ws");
const { boot, keys, signHash, sleep, O_CORE } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e32-" + ROLE);
const N_FLOOD = parseInt(process.env.N_FLOOD || "30", 10);

async function setTpsInterval(ctx, interval) {
	await ctx.query("UPDATE system_vars SET value=? WHERE subject='tps_interval'", [String(interval)]);
	const rows = await ctx.query("SELECT subject, value FROM system_vars WHERE subject IN ('base_tps_fee','tps_interval','tps_fee_multiplier')");
	console.log("[" + ROLE + "] SYSVARS: " + JSON.stringify(rows));
}

function dumpUnits(ctx, tag) {
	return ctx.query("SELECT unit, main_chain_index, timestamp, tps_fee, actual_tps_fee, is_stable, sequence, witnessed_level FROM units ORDER BY main_chain_index").then(rows => {
		console.log("[" + tag + "] UNITS(" + rows.length + "): " + JSON.stringify(rows.map(r => ({
			mci: r.main_chain_index, ts: r.timestamp, declared: r.tps_fee, actual: r.actual_tps_fee,
			st: r.is_stable, seq: r.sequence, wl: r.witnessed_level,
		}))));
		return rows;
	});
}

function dumpFees(ctx, tag) {
	return ctx.query("SELECT address, mci, tps_fees_balance FROM tps_fees_balances ORDER BY mci").then(rows => {
		console.log("[" + tag + "] TPS_FEES_BALANCES: " + JSON.stringify(rows.map(r => ({ addr: r.address.slice(0, 8), mci: r.mci, bal: r.tps_fees_balance }))));
		return rows;
	});
}

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout")), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: { protocol_version: "4.0", alt: "1", library: "ocore", library_version: "0.4.6", program: "e32-lab", program_version: "0.0.1" } }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e32", command: "subscribe", params: { subscription_id: "e32-sub", last_mci: 0, library_version: "0.4.6" } }]));
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
	await setTpsInterval(ctx, 1);
	console.log("[" + ROLE + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12), "N_FLOOD=" + N_FLOOD);

	// stamp a composed unit to a fixed timestamp: sign FIRST (unit hash includes authentifiers), then hash
	const stamp = (joint, ts, key) => {
		joint.unit.timestamp = ts;
		for (const p in joint.unit.authors[0].authentifiers)
			joint.unit.authors[0].authentifiers[p] = signHash(ctx.objectHash.getUnitHashToSign(joint.unit), key.priv);
		joint.unit.unit = ctx.objectHash.getUnitHash(joint.unit);
		return joint;
	};

	if (ROLE === "node") {
		for (let i = 0; i < 240; i++) {
			await sleep(1000);
			const rows = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (rows[0].c >= N_FLOOD + 2) { console.log("[node] observed >= " + (N_FLOOD + 2) + " stable units"); break; }
		}
		await sleep(6000);
		await dumpUnits(ctx, "node-final");
		await dumpFees(ctx, "node-final");
		// FREEZE TEST: the user (attacker) authors a fresh unit with the calm estimate
		try {
			const fresh = await ctx.composeUnit(keys.user, ctx.user_addr, "FREEZE-TEST");
			await ctx.validateAndSave(fresh, "FREEZE-TEST");
			console.log("[node] FREEZE-TEST ACCEPTED (author NOT frozen)");
		} catch (e) {
			console.log("[node] FREEZE-TEST REJECTED: " + String(e).slice(0, 200) + " (author frozen)");
		}
		process.exit(0);
	}

	// hub
	let ws = null;
	for (let attempt = 0; attempt < 12 && !ws; attempt++) {
		await sleep(5000);
		try { ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT); }
		catch (e) { console.log("[hub] connect attempt " + (attempt + 1) + " failed"); }
	}
	if (!ws) throw Error("could not connect to the node");

	const T0 = Math.round(Date.now() / 1000); // WP-1 = T0-1, flood = T0 (elapsed=1), WP-2 = T0+1
	console.log("[hub] T0=" + T0 + " posting waypoint-1 (ts=" + T0 + ")");

	// waypoint 1 (witness), stamped T0
	let joint = await ctx.composeUnit(keys.witness, ctx.witness_addr, "WP-1");
	stamp(joint, T0 - 1, keys.witness);
	await ctx.validateAndSave(joint, "WP-1");
	sendJoint(ws, joint);
	await sleep(300);

	// the ATTACKER FLOOD: N_FLOOD user units, ALL stamped T0+1 (elapsed = 1 vs WP-1)
	const FLOOD_TS = T0;
	const start = Date.now();
	for (let i = 1; i <= N_FLOOD; i++) {
		joint = await ctx.composeUnit(keys.user, ctx.user_addr, "F" + i);
		stamp(joint, FLOOD_TS, keys.user);
		await ctx.validateAndSave(joint, "F" + i);
		sendJoint(ws, joint);
	}
	const wall = (Date.now() - start) / 1000;
	console.log("[hub] flood of " + N_FLOOD + " posted in " + wall.toFixed(1) + "s wall-clock (" + (N_FLOOD / wall).toFixed(1) + "/s), all stamped ts=" + FLOOD_TS);

	// waypoint 2 (witness), stamped T0+2 — closes the window
	joint = await ctx.composeUnit(keys.witness, ctx.witness_addr, "WP-2");
	stamp(joint, T0 + 2, keys.witness);
	await ctx.validateAndSave(joint, "WP-2");
	sendJoint(ws, joint);

	// settle tail
	for (let i = 0; i < 3; i++) {
		await sleep(1000);
		joint = await ctx.composeUnit(keys.witness, ctx.witness_addr, "WP-TAIL-" + i);
		await ctx.validateAndSave(joint, "WP-TAIL-" + i);
		sendJoint(ws, joint);
	}
	console.log("[hub] done posting; waiting for stabilization + settlement");
	await sleep(10000);
	await dumpUnits(ctx, "hub-final");
	await dumpFees(ctx, "hub-final");
	console.log("HUB-DONE");
	process.exit(0);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
