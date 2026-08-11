// KP-F3-kill — decisive experiment: does the sender's bearer re-spend (F3 "invisible fork")
// actually move the private output, or is it an inert ghost?
//
// REAL code driven (pinned ocore a7eb776), real entry points:
//   - validation.validate  (real unit-level validation — the F3 "standard check")
//   - private_payment.validateAndSavePrivatePaymentChain -> divisible_asset.validateDivisiblePrivatePayment
//     (real recipient-side payload validation — the security boundary for private payments)
//
// Ledger rows seeded directly (p2-lab convention, schema-exact, correct unit hashes + kvstore
// joints); the lab cannot stand up a full real network (no MC advancement), so units are seeded
// as if received; the code under test is 100% real pinned code.
//
// Scenario: sender S sends private output X to recipient R (merchant). R spends X (U1) — the
// accepted payment. S (who retains the blinding — bearer design) publishes a unit A_own carrying
// the SAME spend proof P under S's own address, then delivers a private payload claiming to spend
// X. F3 claims this is an "invisible fork" that defrauds R. This experiment tests whether A_own
// can actually spend X in the ledger.
"use strict";
const path = require("path");
const fs = require("fs");
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
const OUT = path.join(__dirname);
const DATA = path.join(OUT, ".kp-f3-data");
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
const keys = { sender: makeKey(), recipient: makeKey(), witness: makeKey() };
const defOf = (k) => ["sig", { pubkey: k.pub }];
const addrOf = (k) => objectHash0.getChash160(defOf(k));
const sender_addr = addrOf(keys.sender);
const recipient_addr = addrOf(keys.recipient);
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
			{ address: recipient_addr, amount: 0 },
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

// build a correctly-hashed serial unit: inline base payment (+ optional payload_location:"none"
// message with spend proofs). Signing mirrors composer.js (placeholder sig length = 88 chars).
function buildUnit(objectHash, objectLength, authorKey, authorAddress, ts, parentUnits, lastBall, lastBallUnit, baseInput, baseInputAmount, tpsFee, spendProofs, privatePayloadHash) {
	const messages = [
		{ app: "payment", payload_location: "inline", payload: { inputs: [baseInput], outputs: [{ address: authorAddress, amount: 0 }] } },
	];
	if (privatePayloadHash) {
		const msg = { app: "payment", payload_location: "none", payload_hash: privatePayloadHash };
		if (spendProofs) msg.spend_proofs = spendProofs;
		messages.push(msg);
	}
	const objUnit = {
		version: "4.0", alt: "1",
		authors: [{ address: authorAddress, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
		parent_units: parentUnits, last_ball: lastBall, last_ball_unit: lastBallUnit,
		timestamp: ts, messages, headers_commission: 0, payload_commission: 0, tps_fee: tpsFee || 0,
	};
	for (let i = 0; i < 4; i++) {
		objUnit.headers_commission = objectLength.getHeadersSize(objUnit);
		objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
		const fees = objUnit.headers_commission + objUnit.payload_commission + (objUnit.tps_fee || 0);
		messages[0].payload.outputs[0].amount = Math.max(0, baseInputAmount - fees);
		messages[0].payload_hash = objectHash.getBase64Hash(messages[0].payload, true);
		objUnit.payload_commission = objectLength.getTotalPayloadSize(objUnit);
	}
	const hashToSign = objectHash.getUnitHashToSign(objUnit);
	objUnit.authors[0].authentifiers.r = Buffer.from(ecdsa.ecdsaSign(hashToSign, Buffer.from(authorKey.priv, "hex")).signature).toString("base64");
	objUnit.unit = objectHash.getUnitHash(objUnit);
	return objUnit;
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
	console.log("GENESIS unit:", genesis.unit, "ball:", genesisBall);

	const db = require(O_CORE + "/db.js");
	conf.bLight = false;

	await new Promise((resolve) => {
		db.takeConnectionFromPool((conn) => {
			conn.query("SELECT 1", () => { conn.release(); resolve(); });
		});
	});
	for (const [subject, value, mci] of [
		["op_list", JSON.stringify([witness_addr]), -1],
		["threshold_size", "10000", -1],
		["base_tps_fee", "10", -1],
		["tps_interval", "60", -1],
		["tps_fee_multiplier", "10", -1],
	]) {
		await new Promise((resolve) => {
			db.takeConnectionFromPool((conn) => {
				conn.query("INSERT OR IGNORE INTO system_vars (subject, value, vote_count_mci) VALUES (?,?,?)", [subject, value, mci], () => { conn.release(); resolve(); });
			});
		});
	}
	console.log("PRE-PROVISIONED op_list:", JSON.stringify([witness_addr]));

	const storage = require(O_CORE + "/storage.js");
	const validation = require(O_CORE + "/validation.js");
	const objectHash = require(O_CORE + "/object_hash.js");
	const privatePayment = require(O_CORE + "/private_payment.js");
	const kvstore = require(O_CORE + "/kvstore.js");

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

	await storage.initCaches();
	for (let i = 0; i < 200 && typeof storage.getMinRetrievableMci() !== "number"; i++) await sleep(100);
	console.log("DB-READY min_retrievable_mci=", storage.getMinRetrievableMci());

	function validateAndSave(joint, label) {
		return new Promise((resolve, reject) => {
			validation.validate(joint, {
				ifOk: (objValidationState, unlock) => {
					console.log(label, "VALIDATION OK sequence=" + objValidationState.sequence);
					objValidationState.count_primary_aa_triggers = objValidationState.count_primary_aa_triggers || 0;
					require(O_CORE + "/writer.js").saveJoint(joint, objValidationState, null, () => {
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

	// ---- A) genesis through the REAL validation + save path ----
	await validateAndSave({ unit: genesis, ball: genesisBall }, "GENESIS");
	const gOuts = await query("SELECT output_index, address, amount FROM outputs WHERE unit=? ORDER BY output_index", [genesis.unit]);
	console.log("GENESIS outputs:", JSON.stringify(gOuts));
	const idxOf = (addr) => gOuts.find(o => o.address === addr).output_index;

	// ---- B) seed private asset definition + output X (schema-exact mirror of writer+chain output) ----
	const assetDef = {
		is_private: true, is_transferrable: false, auto_destroy: true, fixed_denominations: false,
		issued_by_definer_only: true, cosigned_by_definer: false, spender_attested: false,
	};
	// asset-definition unit (author = sender/definer), correctly hashed, seeded at mci 0 (= settled)
	const assetUnit = buildUnit(objectHash, objectLength, keys.sender, sender_addr, 1700000000, [genesis.unit], genesisBall, genesis.unit,
		{ type: "issue" }, 0, 0, null, null);
	// asset message replaces the base payment: rebuild messages for an asset-definition unit
	const assetUnitReal = {
		version: "4.0", alt: "1",
		authors: [{ address: sender_addr, authentifiers: { r: "----------------------------------------------------------------------------------------" } }],
		parent_units: [genesis.unit], last_ball: genesisBall, last_ball_unit: genesis.unit,
		timestamp: 1700000000,
		messages: [{ app: "asset", payload_location: "inline", payload: assetDef, payload_hash: objectHash.getBase64Hash(assetDef, true) }],
		headers_commission: 0, payload_commission: 0, tps_fee: 0,
	};
	assetUnitReal.headers_commission = objectLength.getHeadersSize(assetUnitReal);
	assetUnitReal.payload_commission = objectLength.getTotalPayloadSize(assetUnitReal);
	const assetHash = objectHash.getUnitHash(assetUnitReal);
	assetUnitReal.unit = assetHash;
	await new Promise((res, rej) => kvstore.put("j\n" + assetHash, JSON.stringify({ unit: assetUnitReal }), (e) => (e ? rej(e) : res())));

	const X = { amount: 500, address: recipient_addr, blinding: crypto.randomBytes(12).toString("base64"), asset: assetHash };
	const xUnit = buildUnit(objectHash, objectLength, keys.recipient, recipient_addr, 1700000000, [genesis.unit], genesisBall, genesis.unit,
		{ unit: genesis.unit, message_index: 0, output_index: idxOf(recipient_addr) }, 1e13, 0, null, null);
	X.unit = xUnit.unit;
	await new Promise((res, rej) => kvstore.put("j\n" + X.unit, JSON.stringify({ unit: xUnit }), (e) => (e ? rej(e) : res())));

	for (const addr of [sender_addr, recipient_addr, witness_addr]) {
		await query("INSERT OR IGNORE INTO addresses (address) VALUES (?)", [addr]);
		await query("INSERT OR IGNORE INTO definitions (definition_chash, definition, has_references) VALUES (?,?,?)",
			[addr, JSON.stringify(defOf(addr === sender_addr ? keys.sender : addr === recipient_addr ? keys.recipient : keys.witness)), 0]);
	}
	const seedUnit = async (u, author, mci, isStable) => {
		await query("INSERT OR IGNORE INTO units (unit, version, alt, timestamp, headers_commission, payload_commission, is_free, is_on_main_chain, main_chain_index, latest_included_mc_index, level, witnessed_level, is_stable, sequence, best_parent_unit, last_ball_unit, tps_fee) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
			[u.unit, "4.0", "1", u.timestamp || 1700000000, u.headers_commission || 0, u.payload_commission || 0, 1, 1, mci, 0, 1, 0, isStable, "good", u.parent_units[0], u.last_ball_unit, u.tps_fee || 0]);
		await query("INSERT OR IGNORE INTO parenthoods (child_unit, parent_unit) VALUES (?,?)", [u.unit, u.parent_units[0]]);
		await query("INSERT OR IGNORE INTO unit_authors (unit, address, definition_chash) VALUES (?,?,?)", [u.unit, author, author]);
		await query("INSERT OR IGNORE INTO balls (ball, unit) VALUES (?,?)", [objectHash.getBallHash(u.unit), u.unit]);
		for (let i = 0; i < u.messages.length; i++) {
			const m = u.messages[i];
			await query("INSERT OR IGNORE INTO messages (unit, message_index, app, payload_hash, payload_location) VALUES (?,?,?,?,?)",
				[u.unit, i, m.app, m.payload_hash, m.payload_location]);
		}
	};
	await seedUnit(assetUnitReal, sender_addr, 0, 1);
	await query("INSERT OR IGNORE INTO assets (unit, message_index, cap, is_private, is_transferrable, auto_destroy, fixed_denominations, issued_by_definer_only, cosigned_by_definer, spender_attested) VALUES (?,?,?,?,?,?,?,?,?,?)",
		[assetHash, 0, null, 1, 0, 1, 0, 1, 0, 0]);
	await seedUnit(xUnit, recipient_addr, 0, 1);
	await query("INSERT OR IGNORE INTO outputs (unit, message_index, output_index, address, amount, blinding, asset) VALUES (?,?,?,?,?,?,?)",
		[X.unit, 0, 0, X.address, X.amount, X.blinding, X.asset]);
	console.log("SEEDED asset", assetHash, "+ X", X.unit, "(addr", X.address + ", blinding", X.blinding + ")");

	// ---- C) U1: recipient spends X (real recipient-side chain validation) ----
	const P = objectHash.getBase64Hash({
		asset: X.asset, unit: X.unit, message_index: 0, output_index: 0,
		address: X.address, amount: X.amount, blinding: X.blinding,
	});
	console.log("P (spend proof of X, binds owner address):", P);
	const u1Payload = {
		asset: X.asset,
		inputs: [{ unit: X.unit, message_index: 0, output_index: 0 }],
		outputs: [{ address: sender_addr, amount: 500, blinding: crypto.randomBytes(12).toString("base64") }],
	};
	const u1Hash = objectHash.getBase64Hash(u1Payload, true);
	const U1 = buildUnit(objectHash, objectLength, keys.recipient, recipient_addr, Math.round(Date.now() / 1000), [genesis.unit], genesisBall, genesis.unit,
		{ unit: genesis.unit, message_index: 0, output_index: idxOf(recipient_addr) }, gOuts.find(o => o.output_index === idxOf(recipient_addr)).amount, 100000, [{ spend_proof: P }], u1Hash);
	console.log("U1 (recipient's real spend of X):", U1.unit);
	await seedUnit(U1, recipient_addr, null, 0);
	await query("INSERT OR IGNORE INTO spend_proofs (unit, message_index, spend_proof_index, spend_proof, address) VALUES (?,?,?,?,?)",
		[U1.unit, 1, 0, P, recipient_addr]);
	const d1 = await new Promise((resolve) => {
		privatePayment.validateAndSavePrivatePaymentChain([{ unit: U1.unit, message_index: 1, payload: u1Payload, output: u1Payload.outputs[0], output_index: 0 }], {
			ifError: (err) => { console.log("U1-CHAIN ifError:", err); resolve({ ok: false, err }); },
			ifOk: () => { console.log("U1-CHAIN OK"); resolve({ ok: true }); },
		});
	});
	if (!d1.ok) throw new Error("U1 chain failed: " + d1.err);
	const spAfterU1 = await query("SELECT unit, address, spend_proof FROM spend_proofs ORDER BY unit");
	console.log("SPEND-PROOFS-ROWS after U1:", JSON.stringify(spAfterU1));
	const xInputsU1 = await query("SELECT unit, type, src_unit, src_message_index, src_output_index, address, asset FROM inputs WHERE src_unit=? AND src_message_index=0 AND src_output_index=0", [X.unit]);
	console.log("X INPUTS rows after U1:", JSON.stringify(xInputsU1));

	// ---- D) A_own: sender publishes the same P under their own address — REAL unit-level validation ----
	const aPayload = {
		asset: X.asset,
		inputs: [{ unit: X.unit, message_index: 0, output_index: 0 }],
		outputs: [{ address: sender_addr, amount: 500, blinding: crypto.randomBytes(12).toString("base64") }],
	};
	const aHash = objectHash.getBase64Hash(aPayload, true);
	const aParents = [assetHash, genesis.unit].sort(); // sorted; includes the sender's asset-def so the author has no parallel conflicting units
	const A_own = buildUnit(objectHash, objectLength, keys.sender, sender_addr, Math.round(Date.now() / 1000), aParents, genesisBall, genesis.unit,
		{ unit: genesis.unit, message_index: 0, output_index: idxOf(sender_addr) }, gOuts.find(o => o.output_index === idxOf(sender_addr)).amount, 100000, [{ spend_proof: P }], aHash);
	console.log("A_own (attacker unit, same P, implied attacker address):", A_own.unit);
	// REAL unit-level validation (the F3 "standard check") — no save yet
	let sA = null;
	try {
		sA = await new Promise((resolve, reject) => {
			validation.validate({ unit: A_own }, {
				ifOk: (objValidationState, unlock) => {
					console.log("A_own VALIDATION OK sequence=" + objValidationState.sequence);
					unlock();
					resolve(objValidationState);
				},
				ifUnitError: (e) => { console.log("A_own UNIT-ERROR", e); reject(new Error("A_own unit error: " + e)); },
				ifJointError: (e) => { console.log("A_own JOINT-ERROR", e); reject(new Error("A_own joint error: " + e)); },
				ifTransientError: (e) => { console.log("A_own TRANSIENT", e); reject(new Error("A_own transient: " + e)); },
				ifNeedParentUnits: (arr) => { console.log("A_own NEED-PARENTS", arr); reject(new Error("A_own need parents")); },
				ifNeedHashTree: () => { console.log("A_own NEED-HASH-TREE"); reject(new Error("A_own need hash tree")); },
			});
		});
		console.log("A_own UNIT-LEVEL RESULT: ACCEPTED (no (P, attacker) row — the F3 unit-level gap, real path)");
	} catch (e) {
		console.log("A_own UNIT-LEVEL RESULT: REJECTED:", e.message);
	}
	// mirror writer.saveJoint: A_own's rows (as if the unit had been saved after validation)
	await seedUnit(A_own, sender_addr, null, 0);
	await query("INSERT OR IGNORE INTO spend_proofs (unit, message_index, spend_proof_index, spend_proof, address) VALUES (?,?,?,?,?)",
		[A_own.unit, 1, 0, P, sender_addr]);
	const spAfterA = await query("SELECT unit, address, spend_proof FROM spend_proofs ORDER BY unit");
	console.log("SPEND-PROOFS-ROWS after A_own:", JSON.stringify(spAfterA));

	// ---- E) deliver A_own's payload (claims to spend X) through the REAL recipient-side path ----
	const dA = await new Promise((resolve) => {
		privatePayment.validateAndSavePrivatePaymentChain([{ unit: A_own.unit, message_index: 1, payload: aPayload, output: aPayload.outputs[0], output_index: 0 }], {
			ifError: (err) => { console.log("A_own-CHAIN ifError:", err); resolve({ ok: false, err }); },
			ifOk: () => { console.log("A_own-CHAIN OK (UNEXPECTED)"); resolve({ ok: true }); },
		});
	});
	console.log("A_own PAYLOAD RESULT:", dA.ok ? "ACCEPTED (fork created)" : "REJECTED: " + dA.err);

	// ---- F) final ledger state ----
	const xOut = await query("SELECT unit, message_index, output_index, address, amount, asset, is_spent FROM outputs WHERE unit=? AND message_index=0 AND output_index=0", [X.unit]);
	console.log("X OUTPUT row after all:", JSON.stringify(xOut));
	const xInputs = await query("SELECT unit, type, src_unit, src_message_index, src_output_index, address, asset FROM inputs WHERE src_unit=? AND src_message_index=0 AND src_output_index=0", [X.unit]);
	console.log("X INPUTS rows after all (who spent X in the DAG):", JSON.stringify(xInputs));
	const u1Inputs = await query("SELECT unit, type, src_unit, src_message_index, src_output_index, address, asset FROM inputs WHERE unit=?", [U1.unit]);
	console.log("U1 INPUTS rows:", JSON.stringify(u1Inputs));
	const aInputs = await query("SELECT unit, type, src_unit, src_message_index, src_output_index, address, asset FROM inputs WHERE unit=?", [A_own.unit]);
	console.log("A_own INPUTS rows (does the ghost spend anything in the DAG?):", JSON.stringify(aInputs));

	console.log("\n=== KP-F3 RESULTS ===");
	console.log("unit-level ghost acceptance:", sA ? "TRUE (F3 unit-level gap is real)" : "FALSE");
	console.log("payload-level ghost spend accepted:", dA.ok ? "TRUE (fork!)" : "FALSE (rejected: " + dA.err + ")");
	console.log("competing inputs row for X:", xInputs.length > 1 ? "TRUE" : "FALSE (only U1 spent X in the DAG)");
	console.log("X is_spent:", JSON.stringify(xOut));
	process.exit(0);
}
main().then(() => {
	process.exit(0);
}).catch(e => {
	console.log("RESULT-ERROR:", e.message);
	process.exit(2);
});
