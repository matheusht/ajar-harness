var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// packages/angular/build/src/utils/load-translations.ts
var import_node_crypto = require("node:crypto");
var fs = __toESM(require("node:fs"));
async function createTranslationLoader() {
  const { parsers, diagnostics } = await importParsers();
  return (path2) => {
    const content = fs.readFileSync(path2, "utf8");
    const unusedParsers = /* @__PURE__ */ new Map();
    for (const [format, parser] of Object.entries(parsers)) {
      const analysis = parser.analyze(path2, content);
      if (analysis.canParse) {
        const { locale, translations } = parser.parse(path2, content, analysis.hint);
        const integrity = "sha256-" + (0, import_node_crypto.createHash)("sha256").update(content).digest("base64");
        return { format, locale, translations, diagnostics, integrity };
      } else {
        unusedParsers.set(parser, analysis);
      }
    }
    const messages = [];
    for (const [parser, analysis] of unusedParsers.entries()) {
      messages.push(analysis.diagnostics.formatDiagnostics(`*** ${parser.constructor.name} ***`));
    }
    throw new Error(
      `Unsupported translation file format in ${path2}. The following parsers were tried:
` + messages.join("\n")
    );
  };
}
async function importParsers() {
  try {
    const {
      Diagnostics,
      ArbTranslationParser,
      SimpleJsonTranslationParser,
      Xliff1TranslationParser,
      Xliff2TranslationParser,
      XtbTranslationParser
    } = await import("@angular/localize/tools");
    const diagnostics = new Diagnostics();
    const parsers = {
      arb: new ArbTranslationParser(),
      json: new SimpleJsonTranslationParser(),
      xlf: new Xliff1TranslationParser(),
      xlf2: new Xliff2TranslationParser(),
      // The name ('xmb') needs to match the AOT compiler option
      xmb: new XtbTranslationParser()
    };
    return { parsers, diagnostics };
  } catch {
    throw new Error(
      `Unable to load translation file parsers. Please ensure '@angular/localize' is installed.`
    );
  }
}

// packages/angular/build/src/utils/i18n-options.ts
var import_node_path = __toESM(require("node:path"));
function loadTranslations(locale, desc, workspaceRoot, loader, logger, usedFormats, duplicateTranslation) {
  let translations = void 0;
  for (const file of desc.files) {
    const loadResult = loader(import_node_path.default.join(workspaceRoot, file.path));
    for (const diagnostics of loadResult.diagnostics.messages) {
      if (diagnostics.type === "error") {
        logger.error(`Error parsing translation file '${file.path}': ${diagnostics.message}`);
      } else {
        logger.warn(`WARNING [${file.path}]: ${diagnostics.message}`);
      }
    }
    if (loadResult.locale !== void 0 && loadResult.locale !== locale) {
      logger.warn(
        `WARNING [${file.path}]: File target locale ('${loadResult.locale}') does not match configured locale ('${locale}')`
      );
    }
    usedFormats?.add(loadResult.format);
    file.format = loadResult.format;
    file.integrity = loadResult.integrity;
    if (translations) {
      for (const [id, message] of Object.entries(loadResult.translations)) {
        if (translations[id] !== void 0) {
          const duplicateTranslationMessage = `[${file.path}]: Duplicate translations for message '${id}' when merging.`;
          switch (duplicateTranslation) {
            case "ignore":
              break;
            case "error":
              logger.error(`ERROR ${duplicateTranslationMessage}`);
              break;
            case "warning":
            default:
              logger.warn(`WARNING ${duplicateTranslationMessage}`);
              break;
          }
        }
        translations[id] = message;
      }
    } else {
      translations = loadResult.translations;
    }
  }
  desc.translation = translations;
}

// ../../../../../../../private/tmp/n1f/entry.ts
async function main() {
  const loader = await createTranslationLoader();
  const workspaceRoot = "/tmp/n1f/ws";
  const logger = { warn: (m) => console.log("[WARN]", m), error: (m) => console.log("[ERR]", m) };
  const attackDesc = { files: [{ path: "../evil/outside.xlf" }] };
  try {
    const out = {};
    await loadTranslations("fr", attackDesc, workspaceRoot, loader, logger, /* @__PURE__ */ new Set(), "warning");
    const t = attackDesc.translation;
    console.log(
      "[HOP1] loaded translations from OUT-OF-WORKSPACE path:",
      JSON.stringify(Object.keys(t ?? {}))
    );
    console.log("[HOP1] marker content present:", JSON.stringify(t?.["marker-message-id"] ?? null));
    console.log("[HOP1] READ-OUTSIDE-WORKSPACE =", t?.["marker-message-id"] ? "true" : "false");
  } catch (e) {
    console.log("[HOP1] FAILED:", (e?.message ?? String(e)).slice(0, 200));
  }
  const benignDesc = { files: [{ path: "benign.xlf" }] };
  try {
    await loadTranslations("fr", benignDesc, workspaceRoot, loader, logger, /* @__PURE__ */ new Set(), "warning");
    const t = benignDesc.translation;
    console.log(
      "[HOP2] in-workspace translations loaded:",
      JSON.stringify(Object.keys(t ?? {}))
    );
    console.log("[HOP2] benign marker present:", t?.["benign-message-id"] ? "true" : "false");
  } catch (e) {
    console.log("[HOP2] FAILED:", (e?.message ?? String(e)).slice(0, 200));
  }
}
main();
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
