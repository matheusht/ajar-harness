// packages/angular/build/src/utils/server-rendering/manifest.ts
import { Buffer } from "node:buffer";
import { extname } from "node:path";

// packages/angular/build/src/utils/hash.ts
import assert from "node:assert";
var xxhashInstance;
function getXxhash() {
  assert(
    xxhashInstance,
    "Hash utility must be initialized by awaiting `initializeHash()` before use."
  );
  return xxhashInstance;
}
function calculateHash(data) {
  const instance = getXxhash();
  if (typeof data === "string") {
    return instance.h64ToString(data);
  }
  return instance.h64Raw(data).toString(16).padStart(16, "0");
}

// packages/angular/build/src/tools/esbuild/bundler-files.ts
function createOutputFile(path, data, type) {
  if (typeof data === "string") {
    let cachedContents = null;
    let cachedText = data;
    let cachedHash = null;
    return {
      path,
      type,
      get contents() {
        cachedContents ??= new TextEncoder().encode(data);
        return cachedContents;
      },
      set contents(value) {
        cachedContents = value;
        cachedText = null;
      },
      get text() {
        cachedText ??= new TextDecoder("utf-8").decode(this.contents);
        return cachedText;
      },
      get size() {
        return this.contents.byteLength;
      },
      get hash() {
        cachedHash ??= calculateHash(cachedText ?? this.contents);
        return cachedHash;
      },
      clone() {
        return createOutputFile(this.path, cachedText ?? this.contents, this.type);
      }
    };
  } else {
    let cachedContents = data;
    let cachedText = null;
    let cachedHash = null;
    return {
      get contents() {
        return cachedContents;
      },
      set contents(value) {
        cachedContents = value;
        cachedText = null;
      },
      path,
      type,
      get size() {
        return this.contents.byteLength;
      },
      get text() {
        cachedText ??= new TextDecoder("utf-8").decode(this.contents);
        return cachedText;
      },
      get hash() {
        cachedHash ??= calculateHash(this.contents);
        return cachedHash;
      },
      clone() {
        return createOutputFile(this.path, this.contents, this.type);
      }
    };
  }
}

// packages/angular/build/src/utils/server-rendering/manifest.ts
var SERVER_APP_MANIFEST_FILENAME = "angular-app-manifest.mjs";
var SERVER_APP_ENGINE_MANIFEST_FILENAME = "angular-app-engine-manifest.mjs";
var SERVER_GENERATED_EXTERNALS = /* @__PURE__ */ new Set([
  "./polyfills.server.mjs",
  "./" + SERVER_APP_MANIFEST_FILENAME,
  "./" + SERVER_APP_ENGINE_MANIFEST_FILENAME
]);
var MAIN_SERVER_OUTPUT_FILENAME = "main.server.mjs";
var UNSAFE_CHAR_MAP = {
  "`": "\\`",
  "$": "\\$",
  "\\": "\\\\"
};
function escapeUnsafeChars(str) {
  return str.replace(/[$`\\]/g, (c) => UNSAFE_CHAR_MAP[c]);
}
function generateAngularServerAppEngineManifest(i18nOptions, allowedHosts, baseHref) {
  const entryPoints = {};
  const supportedLocales = {};
  if (i18nOptions.shouldInline && !i18nOptions.flatOutput) {
    for (const locale of i18nOptions.inlineLocales) {
      const { subPath } = i18nOptions.locales[locale];
      const importPath = `${subPath ? `${subPath}/` : ""}${MAIN_SERVER_OUTPUT_FILENAME}`;
      entryPoints[subPath] = `() => import('./${importPath}')`;
      supportedLocales[locale] = subPath;
    }
  } else {
    entryPoints[""] = `() => import('./${MAIN_SERVER_OUTPUT_FILENAME}')`;
    supportedLocales[i18nOptions.sourceLocale] = "";
  }
  let basePath = baseHref || "/";
  if (basePath.length > 1 && basePath.at(-1) === "/") {
    basePath = basePath.slice(0, -1);
  }
  const manifestContent = `
export default {
  basePath: '${basePath}',
  allowedHosts: ${JSON.stringify(allowedHosts, void 0, 2)},
  supportedLocales: ${JSON.stringify(supportedLocales, void 0, 2)},
  entryPoints: {
    ${Object.entries(entryPoints).map(([key, value]) => `'${key}': ${value}`).join(",\n    ")}
  },
};
`;
  return manifestContent;
}
function generateAngularServerAppManifest(additionalHtmlOutputFiles, outputFiles, inlineCriticalCss, routes, locale, baseHref, initialFiles, metafile, publicPath) {
  const serverAssetsChunks = [];
  const serverAssets = {};
  for (const file of [...additionalHtmlOutputFiles.values(), ...outputFiles]) {
    const extension = extname(file.path);
    if (extension === ".html" || inlineCriticalCss && extension === ".css") {
      const jsChunkFilePath = `assets-chunks/${file.path.replace(/[./]/g, "_")}.mjs`;
      const escapedContent = escapeUnsafeChars(file.text);
      serverAssetsChunks.push(
        createOutputFile(
          jsChunkFilePath,
          `export default \`${escapedContent}\`;`,
          2 /* ServerApplication */
        )
      );
      let size = Buffer.byteLength(file.text);
      let pos = file.text.indexOf("\r\n");
      while (pos !== -1) {
        size--;
        pos = file.text.indexOf("\r\n", pos + 2);
      }
      serverAssets[file.path] = `{size: ${size}, hash: '${file.hash}', text: () => import('./${jsChunkFilePath}').then(m => m.default)}`;
    }
  }
  const entryPointToBrowserMapping = routes?.length ? void 0 : generateLazyLoadedFilesMappings(metafile, initialFiles, publicPath);
  const manifestContent = `
export default {
  bootstrap: () => import('./main.server.mjs').then(m => m.default),
  inlineCriticalCss: ${inlineCriticalCss},
  baseHref: '${baseHref}',
  locale: ${JSON.stringify(locale)},
  routes: ${JSON.stringify(routes, void 0, 2)},
  entryPointToBrowserMapping: ${JSON.stringify(entryPointToBrowserMapping, void 0, 2)},
  assets: {
    ${Object.entries(serverAssets).map(([key, value]) => `'${key}': ${value}`).join(",\n    ")}
  },
};
`;
  return { manifestContent, serverAssetsChunks };
}
function generateLazyLoadedFilesMappings(metafile, initialFiles, publicPath = "") {
  const entryPointToBundles = {};
  for (const [fileName, { entryPoint, exports, imports }] of Object.entries(metafile.outputs)) {
    if (!entryPoint || exports?.length < 1 || !fileName.endsWith(".js")) {
      continue;
    }
    const importedPaths = [`${publicPath}${fileName}`];
    for (const { kind, external, path } of imports) {
      if (external || initialFiles.has(path) || kind !== "import-statement") {
        continue;
      }
      importedPaths.push(`${publicPath}${path}`);
    }
    entryPointToBundles[entryPoint] = importedPaths;
  }
  return entryPointToBundles;
}
export {
  SERVER_APP_ENGINE_MANIFEST_FILENAME,
  SERVER_APP_MANIFEST_FILENAME,
  SERVER_GENERATED_EXTERNALS,
  generateAngularServerAppEngineManifest,
  generateAngularServerAppManifest
};
/**
 * @license
 * Copyright Google LLC All Rights Reserved.
 *
 * Use of this source code is governed by an MIT-style license that can be
 * found in the LICENSE file at https://angular.dev/license
 */
