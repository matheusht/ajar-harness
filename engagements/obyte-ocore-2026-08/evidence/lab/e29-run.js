// E2-9 — NATURAL-BURST F4: 20 units in one second (mass-claim pattern), no attacker.
// Measures: per-unit declared tps_fee (composer estimate) vs settlement (getFinalTpsFee),
// the resulting tps_fees_balance, and whether ANY unit's author is frozen (negative balance).
// Two-node lab (e17b pattern): hub composes + relays over the real relay protocol; node
// validates + stabilizes; settlement (updateTpsFees) runs at stabilization.
// ROLE=hub PORT=6611 NODE_PORT=6612   /   ROLE=node PORT=6612
"use strict";
const path = require("path");
const WebSocket = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/ws");
const { boot, keys, sleep } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e29-" + ROLE);

async function setTpsInterval(ctx, interval) {
	// mainnet default is tps_interval=1; the lab boot sets 60. Set it to 1 (mainnet-equivalent).
	await ctx.query("UPDATE system_vars SET value=? WHERE subject='tps_interval'", [String(interval)]);
	const rows = await ctx.query("SELECT subject, value FROM system_vars WHERE subject IN ('base_tps_fee','tps_interval','tps_fee_multiplier')");
	console.log("[" + ROLE + "] SYSVARS: " + JSON.stringify(rows));
}

function dumpFees(ctx, tag) {
	return ctx.query("SELECT address, mci, tps_fees_balance FROM tps_fees_balances ORDER BY mci").then(rows => {
		console.log("[" + tag + "] TPS_FEES_BALANCES: " + JSON.stringify(rows));
		return rows;
	});
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

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout to " + url)), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: {
				protocol_version: "4.0", alt: "1", library: "ocore",
				library_version: "0.4.6", program: "e29-lab", program_version: "0.0.1",
			} }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e29", command: "subscribe", params: {
				subscription_id: "e29-sub", last_mci: 0, library_version: "0.4.6",
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
	await setTpsInterval(ctx, 1);
	console.log("[" + ROLE + "] booted port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	if (ROLE === "node") {
		// wait for the burst stream to stabilize
		for (let i = 0; i < 240; i++) {
			await sleep(1000);
			const rows = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (rows[0].c >= 23) { console.log("[node] observed >=23 stable units"); break; }
		}
		await sleep(4000);
		await dumpUnits(ctx, "node-final");
		await dumpFees(ctx, "node-final");
		// FREEZE TEST: try to author a fresh unit with the composer's normal (calm) estimate
		// after the burst settled — if the author's balance is negative, the min-fee gate
		// must reject it (the author is frozen).
		try {
			const fresh = await ctx.composeUnit(ctx.keys.user, ctx.user_addr, "FREEZE-TEST");
			const declared = fresh.unit.tps_fee;
			console.log("[node] FREEZE-TEST composed declared tps_fee=" + declared);
			await ctx.validateAndSave(fresh, "FREEZE-TEST");
			console.log("[node] FREEZE-TEST ACCEPTED (author NOT frozen)");
		} catch (e) {
			console.log("[node] FREEZE-TEST REJECTED: " + String(e).slice(0, 200) + " (author frozen)");
		}
		process.exit(0);
	}

	// hub: wait for the node, then post: waypoint -> 20-burst -> waypoint -> settle tail
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);

	const T0 = Math.round(Date.now() / 1000);
	console.log("[hub] T0=" + T0 + " posting waypoint-1");

	// waypoint 1
	let joint = await ctx.composeUnit(keys.witness, ctx.witness_addr, "WP-1");
	await ctx.validateAndSave(joint, "WP-1");
	sendJoint(ws, joint);
	await sleep(300);

	// the burst: 20 user units back-to-back (all within the same second)
	const BURST = 20;
	for (let i = 1; i <= BURST; i++) {
		joint = await ctx.composeUnit(keys.user, ctx.user_addr, "BURST-" + i);
		await ctx.validateAndSave(joint, "BURST-" + i);
		sendJoint(ws, joint);
	}
	const TB = Math.round(Date.now() / 1000);
	console.log("[hub] burst of " + BURST + " posted, end second=" + TB + " (window " + (TB - T0) + "s)");

	// waypoint 2 (closes the burst window; same second or next — either way elapsed=1 via ||1)
	joint = await ctx.composeUnit(keys.witness, ctx.witness_addr, "WP-2");
	await ctx.validateAndSave(joint, "WP-2");
	sendJoint(ws, joint);

	// settle tail: a few more waypoints to force stabilization past the burst window
	for (let i = 0; i < 3; i++) {
		await sleep(1000);
		joint = await ctx.composeUnit(keys.witness, ctx.witness_addr, "WP-TAIL-" + i);
		await ctx.validateAndSave(joint, "WP-TAIL-" + i);
		sendJoint(ws, joint);
	}
	console.log("[hub] done posting; waiting for the node to stabilize + settle");
	await sleep(8000);
	await dumpUnits(ctx, "hub-final");
	await dumpFees(ctx, "hub-final");
	console.log("HUB-DONE");
	process.exit(0);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
