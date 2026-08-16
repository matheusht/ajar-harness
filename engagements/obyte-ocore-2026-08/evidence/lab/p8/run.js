// P8 — S1 in formula eval: is_valid_signed_package budget gates are bare-mci (no disjunct)
// Claim: formula/evaluation.js:1652 (3-package cap) and :1693 (max_complexity = mci>=fix ? 10 : 0)
// are gated on the bare unit position. An AA attached below pemCurvesFixMci evaluates with
// max_complexity=0 (falsy -> custom budget SKIPPED, definition.js:110/632) and NO 3-call cap.
// Real-path evaluation via formula/index.js (the same path AA triggers use); packages delivered
// via trigger.data (the real delivery pattern), so dotted authentifier paths survive.
module.exports = async function (db, storage, network, validation, objectHash, signature, composer, mutex, constants) {
  const util = require("util");
  const ecdsa = require("/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore/node_modules/secp256k1");
  const crypto = require("crypto");
  const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";
  const formulaParser = require(O_CORE + "/formula/index.js");
  const signed_message = require(O_CORE + "/signed_message.js");

  // ---- 1. fix MCI nonzero (lab zeroes all upgrade MCIs) ----
  const FIX = 1000000;
  constants.pemCurvesFixMci = FIX;
  console.log("[P8] constants.pemCurvesFixMci =", constants.pemCurvesFixMci, " MAX_SIGNED_PACKAGES_PER_AA_EVAL =", constants.MAX_SIGNED_PACKAGES_PER_AA_EVAL);

  // ---- 2. keypair + definition + address (real secp256k1) ----
  const priv = crypto.randomBytes(32);
  const pub = Buffer.from(ecdsa.publicKeyCreate(priv));
  const pubkey_b64 = pub.toString("base64");
  const definition = ["sig", { pubkey: pubkey_b64 }];
  const address = objectHash.getChash160(definition);
  console.log("[P8] address", address, "pubkey", pubkey_b64);

  // ---- 3. signed-package builders (real signatures) ----
  function makePkg(innerMessage, def, addr, authKey) {
    const pkg = { signed_message: innerMessage, authors: [{ address: addr, definition: def, authentifiers: {} }] };
    pkg.authors[0].authentifiers[authKey] = "";
    const h = objectHash.getSignedPackageHashToSign(pkg);
    pkg.authors[0].authentifiers[authKey] = signature.sign(h, priv);
    return pkg;
  }

  // simple sig definition package (auth key "r")
  const simplePkg = makePkg("p8-simple", definition, address, "r");
  console.log("[P8] simple package sig verify:", signature.verify(objectHash.getSignedPackageHashToSign(simplePkg), simplePkg.authors[0].authentifiers.r, pubkey_b64));

  // complex 'r of set' definition (20 sig members, mine last -> walk complexity ~21; auth key "r.19")
  const branches = [];
  for (let i = 0; i < 19; i++) {
    const otherPub = Buffer.from(ecdsa.publicKeyCreate(crypto.randomBytes(32)));
    branches.push(["sig", { pubkey: otherPub.toString("base64") }]);
  }
  branches.push(["sig", { pubkey: pubkey_b64 }]);
  const rsetDef = ["r of set", { required: 1, set: branches }];
  const rsetAddr = objectHash.getChash160(rsetDef);
  const rsetPkg = makePkg("p8-rset", rsetDef, rsetAddr, "r.19");

  // ---- 4. instrument validateSignedMessage (thin observer: records the max_complexity arg; passes through) ----
  const origValidate = signed_message.validateSignedMessage;
  const observed = { maxComplexity: [], calls: 0, results: [] };
  signed_message.validateSignedMessage = function (conn, pkgArg, addrArg, mcArg, cbArg) {
    if (typeof mcArg === "function") { cbArg = mcArg; mcArg = undefined; }
    observed.calls++;
    observed.maxComplexity.push(mcArg);
    const cb = (err, lbm) => { observed.results.push({ err, last_ball_mci: lbm }); return cbArg(err, lbm); };
    return origValidate.call(this, conn, pkgArg, addrArg, mcArg, cb);
  };

  // ---- 5. evaluate helpers (packages via trigger.data — the real AA trigger delivery pattern) ----
  const readGetterProps = function (aa_address, func_name, cb) {
    storage.readAAGetterProps(db, aa_address, func_name, null, cb);
  };
  function evalFormula(formula, mci, trigger, label) {
    const opts = {
      conn: db,
      formula,
      trigger,
      messages: [], // bAA context
      objValidationState: { last_ball_mci: mci, last_ball_timestamp: 1.5e9 },
      address: address
    };
    return new Promise((resolve) => {
      const t0 = Date.now();
      formulaParser.evaluate(opts, [], "", (err, res) => {
        const elapsed = Date.now() - t0;
        resolve({ label, mci, err, res, elapsed, calls: observed.calls, maxComplexity: observed.maxComplexity.slice(), results: observed.results.slice() });
        observed.calls = 0; observed.maxComplexity = []; observed.results = [];
      });
    });
  }
  const TRIG_SIMPLE = { data: { pkg: simplePkg, addr: address } };
  const TRIG_RSET = { data: { pkg: rsetPkg, addr: rsetAddr } };

  // ---- 7a. THE DIVERGENCE: single call, below vs above the gate ----
  console.log("\n[P8-7a] single is_valid_signed_package call: max_complexity divergence");
  const below1 = await evalFormula("$result = is_valid_signed_package(trigger.data.pkg, trigger.data.addr); $result", FIX - 500000, TRIG_SIMPLE, "below-fix");
  const above1 = await evalFormula("$result = is_valid_signed_package(trigger.data.pkg, trigger.data.addr); $result", FIX + 500000, TRIG_SIMPLE, "above-fix");
  console.log("[P8-7a] below-fix:", JSON.stringify({ res: below1.res, err: below1.err, elapsed: below1.elapsed, maxComplexity: below1.maxComplexity }));
  console.log("[P8-7a] above-fix:", JSON.stringify({ res: above1.res, err: above1.err, elapsed: above1.elapsed, maxComplexity: above1.maxComplexity }));

  // ---- 7b. BEHAVIORAL divergence: complex definition (walk complexity ~21 > 10, < 100) ----
  console.log("\n[P8-7b] behavioral divergence: 'r of set' (required=1, 20 sig members) signed-message definition");
  const belowC = await evalFormula("$result = is_valid_signed_package(trigger.data.pkg, trigger.data.addr); $result", FIX - 500000, TRIG_RSET, "below-fix-rset");
  const aboveC = await evalFormula("$result = is_valid_signed_package(trigger.data.pkg, trigger.data.addr); $result", FIX + 500000, TRIG_RSET, "above-fix-rset");
  console.log("[P8-7b] below-fix (max_complexity=0, budget SKIPPED):", JSON.stringify({ res: belowC.res, err: belowC.err, elapsed: belowC.elapsed, maxComplexity: belowC.maxComplexity, results: belowC.results }));
  console.log("[P8-7b] above-fix (max_complexity=10, budget ENFORCED):", JSON.stringify({ res: aboveC.res, err: aboveC.err, elapsed: aboveC.elapsed, maxComplexity: aboveC.maxComplexity, results: aboveC.results }));

  // ---- 7c. AMPLIFICATION: N independent calls in one AA formula ----
  console.log("\n[P8-7c] amplification: N is_valid_signed_package calls in one AA formula");
  function nPkgs(n) {
    const pkgs = [];
    for (let i = 0; i < n; i++) pkgs.push(makePkg("p8-n-" + i, definition, address, "r"));
    return pkgs;
  }
  for (const n of [1, 3, 10, 30, 60]) {
    const pkgs = nPkgs(n);
    let stmts = "";
    for (let i = 0; i < n; i++) stmts += "  $r" + i + " = is_valid_signed_package(trigger.data.pkgs[" + i + "], trigger.data.addr);\n";
    stmts += "  true\n";
    const f = stmts;
    // validation side (formula/validation.js — the migration asymmetry check)
    const valBelow = await new Promise((resolve) => formulaParser.validate({ formula: f, complexity: 1, count_ops: 0, bAA: true, mci: FIX - 500000, locals: {}, readGetterProps }, (vr) => resolve(vr)));
    const valAbove = await new Promise((resolve) => formulaParser.validate({ formula: f, complexity: 1, count_ops: 0, bAA: true, mci: FIX + 500000, locals: {}, readGetterProps }, (vr) => resolve(vr)));
    const belowN = await evalFormula(f, FIX - 500000, { data: { pkgs, addr: address } }, "below-fix");
    const aboveN = await evalFormula(f, FIX + 500000, { data: { pkgs, addr: address } }, "above-fix");
    console.log("[P8-7c] n=" + n,
      "| validation below-fix:", valBelow.error ? "ERR:" + JSON.stringify(valBelow.error) : "ok(complexity=" + valBelow.complexity + ")",
      "| validation above-fix:", valAbove.error ? "ERR:" + JSON.stringify(valAbove.error) : "ok(complexity=" + valAbove.complexity + ")",
      "| below: res=" + belowN.res, "err=" + JSON.stringify(belowN.err), "calls=" + belowN.calls, "elapsed=" + belowN.elapsed + "ms",
      "| above: res=" + aboveN.res, "err=" + JSON.stringify(aboveN.err), "calls=" + aboveN.calls, "elapsed=" + aboveN.elapsed + "ms");
  }

  // restore
  signed_message.validateSignedMessage = origValidate;
  console.log("\n[P8] DONE");
};
