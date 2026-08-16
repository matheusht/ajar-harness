// E2-16 victim — the victim IS their own hub (bServeAsHub + device identity), listening on 6611.
// The attacker (e2-16-attacker.js) delivers a hub/deliver device message encrypted to an UNKNOWN
// key; the bToMe path skips the recipient-key check; device.js handleJustsaying('hub/message')
// calls decryptPackage -> else branch -> scheduled setTimeout throw -> uncaught -> process crash.
"use strict";
const path = require("path");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";

process.on("uncaughtException", (err) => {
	console.log("[victim] UNCAUGHT-EXCEPTION:", String(err).slice(0, 300));
	console.log("[victim] PROCESS WILL CRASH (uncaughtException handler re-throws)");
	setTimeout(() => { process.exit(101); }, 50); // emulate the re-throw crash with a marker exit
});

const { boot, keys } = require("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab/e17b-boot.js");
const DATA = path.join("/Users/matheusvsky/Documents/trab/llm-redteam-harness/engagements/obyte-ocore-2026-08/evidence/lab", ".e2-16-victim-data");
const PORT = parseInt(process.env.PORT || "6611", 10);

async function main() {
	const ctx = await boot(DATA, PORT, { bServeAsHub: true });
	console.log("[victim] booted as hub on port", PORT, "genesis", ctx.genesis.unit.slice(0, 12) + "...");

	// --- device identity (lab keys, never real) ---
	const ecdsa = require(O_CORE + "/node_modules/secp256k1");
	const crypto = require("crypto");
	const device = require(O_CORE + "/device.js");
	const objectHash = require(O_CORE + "/object_hash.js");

	const perm_priv = crypto.randomBytes(32);
	const perm_pub = Buffer.from(ecdsa.publicKeyCreate(perm_priv, true)).toString("base64");
	const temp_priv = crypto.randomBytes(32);
	const temp_pub = Buffer.from(ecdsa.publicKeyCreate(temp_priv, true)).toString("base64");

	device.setDevicePrivateKey(perm_priv);
	device.setTempKeys(temp_priv, null, () => {});
	const my_addr = device.getMyDeviceAddress();
	console.log("[victim] device address:", my_addr);
	console.log("[victim] permanent pub:", perm_pub);
	console.log("[victim] temp pub:", temp_pub);
	console.log("[victim] READY — waiting for attacker hub/deliver (device identity + bToMe path active)");

	// keep the process alive; the network listener + eventBus handle the attacker
	setInterval(() => {}, 1000);
}

main().catch((e) => { console.error("[victim] BOOT-ERR", e); process.exit(2); });
