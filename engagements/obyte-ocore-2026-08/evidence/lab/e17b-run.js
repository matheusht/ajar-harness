// E1-7 Phase B — two-node network entry (v2: hub relays via a plain ws client into the node's
// REAL inbound network path; the node listens on its own port and processes the units through
// handleJustsaying 'joint' -> validation -> writer.saveJoint -> advanceMcStability).
// ROLE=hub PORT=6611 NODE_PORT=6612 : full node (posts units) + ws client into the node.
// ROLE=node PORT=6612              : full node listening; receives + stabilizes the unit stream.
"use strict";
const path = require("path");
const WebSocket = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/ws");
const { boot, keys, sleep } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e17b-" + ROLE);

function dumpState(ctx, tag) {
	return ctx.query("SELECT unit, level, main_chain_index, is_stable, sequence, is_on_main_chain, witnessed_level FROM units ORDER BY main_chain_index").then(rows => {
		console.log("[" + tag + "] UNITS:", JSON.stringify(rows.map(r => ({ mci: r.main_chain_index, lvl: r.level, st: r.is_stable, seq: r.sequence, wl: r.witnessed_level }))));
		return ctx.query("SELECT COUNT(*) AS c FROM balls").then(balls => {
			console.log("[" + tag + "] BALLS:", balls[0].c);
			return rows;
		});
	});
}

// plain ws client speaking the Obyte relay handshake (version -> subscribe), then sending joints
function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout to " + url)), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: {
				protocol_version: "4.0", alt: "1", library: "ocore",
				library_version: "0.4.6", program: "e17b-lab", program_version: "0.0.1",
			} }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e17b", command: "subscribe", params: {
				subscription_id: "e17b-sub", last_mci: 0, library_version: "0.4.6",
			} }]));
			console.log("[hub-ws] handshake sent to", url);
			setTimeout(() => resolve(ws), 800); // give the node a beat to set bSubscribed
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
		await dumpState(ctx, "node-after-genesis");
		console.log("[node] listening on", PORT, "- waiting for the hub's unit stream...");
		// watch for stabilization; also react if the process dies on an uncaught throw
		for (let i = 0; i < 90; i++) {
			await sleep(1000);
			const rows = await ctx.query("SELECT COUNT(*) AS c FROM units WHERE is_stable=1");
			if (rows[0].c >= 4) {
				console.log("[node] observed >=4 stable units");
				break;
			}
		}
		await sleep(3000);
		const final = await dumpState(ctx, "node-final");
		const stable = final.filter(r => r.is_stable === 1).length;
		const balls = await ctx.query("SELECT COUNT(*) AS c FROM balls");
		console.log("NODE-DONE stable=" + stable + " balls=" + balls[0].c);
		process.exit(stable >= 4 && balls[0].c >= 4 ? 0 : 3);
	}

	// hub: wait for the node to be up, then open the relay client into it
	await sleep(3000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);

	const N_UNITS = 8; // 4 user + 4 witness waypoints
	for (let i = 1; i <= N_UNITS; i++) {
		const isWitness = (i % 2 === 0);
		const key = isWitness ? keys.witness : keys.user;
		const addr = isWitness ? ctx.witness_addr : ctx.user_addr;
		const label = (isWitness ? "WAYPOINT" : "USER") + "-" + i;
		const joint = await ctx.composeUnit(key, addr, label);
		await ctx.validateAndSave(joint, label);
		if (sendJoint(ws, joint))
			console.log("[hub] relayed " + label + " to node");
		await sleep(700);
	}
	await sleep(4000);
	await dumpState(ctx, "hub-final");
	console.log("HUB-DONE");
	process.exit(0);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
