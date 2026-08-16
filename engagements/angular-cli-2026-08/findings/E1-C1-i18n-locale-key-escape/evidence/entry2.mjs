// packages/angular/build/src/utils/i18n-options.ts
function normalizeTranslationFileOption(option, locale, expectObjectInError) {
  if (typeof option === "string") {
    return [option];
  }
  if (Array.isArray(option) && option.every((element) => typeof element === "string")) {
    return option;
  }
  let errorMessage = `Project i18n locales translation field value for '${locale}' is malformed. `;
  if (expectObjectInError) {
    errorMessage += "Expected a string, array of strings, or object.";
  } else {
    errorMessage += "Expected a string or array of strings.";
  }
  throw new Error(errorMessage);
}
function ensureObject(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Project field '${name}' is malformed. Expected an object.`);
  }
}
function ensureString(value, name) {
  if (typeof value !== "string") {
    throw new Error(`Project field '${name}' is malformed. Expected a string.`);
  }
}
function ensureValidSubPath(value, name) {
  ensureString(value, name);
  if (!/^[\w-]*$/.test(value)) {
    throw new Error(
      `Project field '${name}' is invalid. It can only contain letters, numbers, hyphens, and underscores.`
    );
  }
}
function createI18nOptions(projectMetadata, inline, logger, ssrEnabled) {
  const { i18n: metadata = {} } = projectMetadata;
  ensureObject(metadata, "i18n");
  const i18n2 = {
    inlineLocales: /* @__PURE__ */ new Set(),
    // en-US is the default locale added to Angular applications (https://angular.dev/guide/i18n/format-data-locale)
    sourceLocale: "en-US",
    locales: {},
    get shouldInline() {
      return this.inlineLocales.size > 0;
    }
  };
  let rawSourceLocale;
  let rawSourceLocaleBaseHref;
  let rawsubPath;
  if (typeof metadata.sourceLocale === "string") {
    rawSourceLocale = metadata.sourceLocale;
  } else if (metadata.sourceLocale !== void 0) {
    ensureObject(metadata.sourceLocale, "i18n.sourceLocale");
    if (metadata.sourceLocale.code !== void 0) {
      ensureString(metadata.sourceLocale.code, "i18n.sourceLocale.code");
      rawSourceLocale = metadata.sourceLocale.code;
    }
    if (metadata.sourceLocale.baseHref !== void 0) {
      ensureString(metadata.sourceLocale.baseHref, "i18n.sourceLocale.baseHref");
      if (ssrEnabled) {
        logger?.warn(
          `'baseHref' in 'i18n.sourceLocale' may lead to undefined behavior when used with SSR. Consider using 'subPath' instead.

Note: 'subPath' specifies the URL segment for the locale, serving as both the HTML base HREF and the output directory name.
By default, if not explicitly set, 'subPath' defaults to the locale code.`
        );
      }
      rawSourceLocaleBaseHref = metadata.sourceLocale.baseHref;
    }
    if (metadata.sourceLocale.subPath !== void 0) {
      ensureValidSubPath(metadata.sourceLocale.subPath, "i18n.sourceLocale.subPath");
      rawsubPath = metadata.sourceLocale.subPath;
    }
    if (rawsubPath !== void 0 && rawSourceLocaleBaseHref !== void 0) {
      throw new Error(
        `'i18n.sourceLocale.subPath' and 'i18n.sourceLocale.baseHref' cannot be used together.`
      );
    }
  }
  if (rawSourceLocale !== void 0) {
    i18n2.sourceLocale = rawSourceLocale;
    i18n2.hasDefinedSourceLocale = true;
  }
  i18n2.locales[i18n2.sourceLocale] = {
    files: [],
    baseHref: rawSourceLocaleBaseHref,
    subPath: rawsubPath ?? i18n2.sourceLocale
  };
  if (metadata.locales !== void 0) {
    ensureObject(metadata.locales, "i18n locales");
    for (const [locale, options] of Object.entries(metadata.locales)) {
      let translationFiles;
      let baseHref;
      let subPath;
      if (options && typeof options === "object" && "translation" in options) {
        translationFiles = normalizeTranslationFileOption(options.translation, locale, false);
        if ("baseHref" in options) {
          ensureString(options.baseHref, `i18n.locales.${locale}.baseHref`);
          if (ssrEnabled) {
            logger?.warn(
              `'baseHref' in 'i18n.locales.${locale}' may lead to undefined behavior when used with SSR. Consider using 'subPath' instead.

Note: 'subPath' specifies the URL segment for the locale, serving as both the HTML base HREF and the output directory name.
By default, if not explicitly set, 'subPath' defaults to the locale code.`
            );
          }
          baseHref = options.baseHref;
        }
        if ("subPath" in options) {
          ensureValidSubPath(options.subPath, `i18n.locales.${locale}.subPath`);
          subPath = options.subPath;
        }
        if (subPath !== void 0 && baseHref !== void 0) {
          throw new Error(
            `'i18n.locales.${locale}.subPath' and 'i18n.locales.${locale}.baseHref' cannot be used together.`
          );
        }
      } else {
        translationFiles = normalizeTranslationFileOption(options, locale, true);
      }
      if (locale === i18n2.sourceLocale) {
        throw new Error(
          `An i18n locale ('${locale}') cannot both be a source locale and provide a translation.`
        );
      }
      i18n2.locales[locale] = {
        files: translationFiles.map((file) => ({ path: file })),
        baseHref,
        subPath: subPath ?? locale
      };
    }
  }
  if (inline === true) {
    i18n2.inlineLocales.add(i18n2.sourceLocale);
    Object.keys(i18n2.locales).forEach((locale) => i18n2.inlineLocales.add(locale));
  } else if (inline) {
    for (const locale of inline) {
      if (!i18n2.locales[locale] && i18n2.sourceLocale !== locale) {
        throw new Error(`Requested locale '${locale}' is not defined for the project.`);
      }
      i18n2.inlineLocales.add(locale);
    }
  }
  const localesData = Object.entries(i18n2.locales).filter(
    ([locale]) => i18n2.inlineLocales.has(locale)
  );
  for (let i = 0; i < localesData.length; i++) {
    const [localeA, { subPath: subPathA }] = localesData[i];
    for (let j = i + 1; j < localesData.length; j++) {
      const [localeB, { subPath: subPathB }] = localesData[j];
      if (subPathA === subPathB) {
        throw new Error(
          `Invalid i18n configuration: Locales '${localeA}' and '${localeB}' cannot have the same subPath: '${subPathB}'.`
        );
      }
    }
  }
  return i18n2;
}

// packages/angular_devkit/build_angular/src/utils/output-paths.ts
import { existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
function ensureOutputPaths(baseOutputPath, i18n2) {
  const outputPaths = i18n2.shouldInline ? [...i18n2.inlineLocales].map((l) => [
    l,
    i18n2.flatOutput ? baseOutputPath : join(baseOutputPath, i18n2.locales[l].subPath)
  ]) : [["", baseOutputPath]];
  for (const [, outputPath] of outputPaths) {
    if (!existsSync(outputPath)) {
      mkdirSync(outputPath, { recursive: true });
    }
  }
  return new Map(outputPaths);
}

// kp-entry2.mts
var evilKey = "a/../../../../../../../evil";
var meta = {
  i18n: {
    locales: {
      [evilKey]: { translation: "/tmp/i18n-kp/ws/messages.xlf" }
    }
  }
};
var i18n = createI18nOptions(meta, [evilKey]);
var desc = i18n.locales[evilKey];
console.log("=== locale key accepted, default subPath = the key:", JSON.stringify(desc.subPath));
console.log("=== ensureValidSubPath control (explicit subPath ../evil):");
try {
  createI18nOptions({ i18n: { locales: { fr: { translation: "/tmp/i18n-kp/ws/messages.xlf", subPath: "../evil" } } } }, ["fr"]);
  console.log("CONTROL FAIL");
} catch (e) {
  console.log("CONTROL OK throws:", e.message);
}
console.log("=== write-side: ensureOutputPaths with the malicious key ===");
var paths = ensureOutputPaths("/tmp/i18n-kp/out", i18n);
console.log("output paths map:", [...paths.entries()].map(([l, p]) => `${l} -> ${p}`).join("\n  "));
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
