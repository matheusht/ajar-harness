// obyte-ocore lab — in-process node harness (modeled on test/aa.test.js boot pattern)
// Usage: node lab.js <script>  — each script gets a fresh scratch data dir
"use strict";
const path = require("path");
const fs = require("fs");

const LAB_ROOT = __dirname;
const O_CORE = "/Users/matheusvsky/Documents/trab/obyte-ocore-2026-08-ocore";

// 1) fresh scratch data dir per run
const dst_dir = path.join(LAB_ROOT, ".labdata-" + (process.env.LAB_TAG || "default"));
fs.rmSync(dst_dir, { recursive: true, force: true });
fs.mkdirSync(dst_dir, { recursive: true });

// 2) boot ocore library in-process against the scratch dir
process.chdir(O_CORE);
require(O_CORE + "/enforce_singleton.js");
// patch desktop_app BEFORE constants.js (which calls getAppRootDir at load time)
const desktop_app = require(O_CORE + "/desktop_app.js");
desktop_app.getAppDataDir = function () { return dst_dir; };
desktop_app.getAppRootDir = function () { return O_CORE; };
const constants = require(O_CORE + "/constants.js");
// zero the upgrade MCIs so ALL rules apply from genesis in the lab
constants.aa2UpgradeMci = 0;
constants.aa3UpgradeMci = 0;
constants.v4UpgradeMci = 0;
constants.pemCurvesFixMci = 0;
constants.noPrivateAssetsWithConditionsUpgradeMci = 0;

const db = require(O_CORE + "/db.js");
const storage = require(O_CORE + "/storage.js");
const network = require(O_CORE + "/network.js");
const validation = require(O_CORE + "/validation.js");
const objectHash = require(O_CORE + "/object_hash.js");
const signature = require(O_CORE + "/signature.js");
const composer = require(O_CORE + "/composer.js");
const mutex = require(O_CORE + "/mutex.js");

const script = process.argv[2];
if (!script) { console.error("usage: node lab.js <script>"); process.exit(1); }
require(path.resolve(LAB_ROOT, script))(db, storage, network, validation, objectHash, signature, composer, mutex, constants)
  .then(() => { console.log("LAB-DONE"); process.exit(0); })
  .catch(e => { console.error("LAB-ERR", e); process.exit(1); });
