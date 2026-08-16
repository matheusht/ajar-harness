// kp-entry.mts
import { createI18nOptions } from "@angular/build/private";
import { join } from "node:path";
var evilKey = "a/../../../../../../../evil";
var meta = {
  i18n: {
    locales: {
      [evilKey]: { translation: "/tmp/i18n-kp/ws/messages.xlf" }
    }
  }
};
var i18n = createI18nOptions(meta, ["en"]);
var desc = i18n.locales[evilKey];
console.log("=== locale key accepted as subPath:", JSON.stringify(desc.subPath), "(ensureValidSubPath NOT applied to keys)");
console.log("=== explicit-subPath control:");
try {
  createI18nOptions({ i18n: { locales: { fr: { translation: "/tmp/i18n-kp/ws/messages.xlf", subPath: "../evil" } } } }, ["fr"]);
  console.log("CONTROL FAIL: explicit subPath ../evil accepted");
} catch (e) {
  console.log("CONTROL OK: explicit subPath throws:", e.message);
}
console.log("=== resolver join:", JSON.stringify(join("@angular/common/locales/global", evilKey)));
console.log("=== output-paths write target:", JSON.stringify(join("/tmp/i18n-kp/out", desc.subPath, "bundle.js")));
