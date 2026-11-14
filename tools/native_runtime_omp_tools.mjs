/** Native OMP tools in an uncredentialed owner. OS isolation belongs to the launcher. */
import { readFile, realpath } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const [sdkArg, workspaceArg] = process.argv.slice(2);
const sdk = await realpath(sdkArg);
const workspace = await realpath(workspaceArg);
const manifest = JSON.parse(await readFile(path.join(sdk, 'package.json'), 'utf8'));
if (manifest.name !== '@oh-my-pi/pi-coding-agent' || manifest.version !== '18.20.0') {
  throw new Error('native_sdk_version_unsupported');
}
const { createTools, Settings } = await import(pathToFileURL(path.join(sdk, 'src/sdk.ts')).href);
const { toolWireSchema } = await import(pathToFileURL(path.join(sdk, '../pi-ai/src/utils/schema/wire.ts')).href);
const { validateToolArguments } = await import(pathToFileURL(path.join(sdk, '../pi-ai/src/utils/validation.ts')).href);
const settings = Settings.isolated({ 'tools.xdev': false, 'bash.direnv': 'off', 'async.enabled': false });
const tools = await createTools({ cwd: workspace, hasUI: false, settings,
  getSessionFile: () => null, getSessionSpawns: () => null, restrictToolNames: true,
  skipPythonPreflight: true, enableLsp: false, noContextFiles: true,
}, ['read', 'write', 'edit', 'grep', 'glob', 'bash']);
const catalog = tools.map(t => ({ name: t.name, description: t.description, inputSchema: toolWireSchema(t) }));
const pending = new Map();
const completed = new Set();
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
const reply = (request, data = {}) => emit({ type: 'response', id: request.id,
  command: request.type, success: true, data });
const fail = request => emit({ type: 'response', id: request?.id,
  command: request?.type, success: false, error: 'native_tool_request_refused' });
emit({ type: 'ready', sdkVersion: manifest.version, bunVersion: Bun.version,
  platform: process.platform, arch: process.arch });
const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  if (Buffer.byteLength(line) > 1048576) break;
  let request;
  try {
    request = JSON.parse(line);
    if (request.type === 'catalog') { reply(request, { tools: catalog }); continue; }
    if (request.type === 'cancel') {
      const active = pending.get(request.call_id);
      active?.abort();
      reply(request, { requested: !!active });
      continue;
    }
    const tool = tools.find(t => t.name === request.tool);
    if (request.type !== 'call' || !tool || !/^[A-Za-z0-9_.:-]{1,160}$/.test(request.call_id) ||
        pending.has(request.call_id) || completed.has(request.call_id) || pending.size >= 8 || completed.size >= 4096) {
      fail(request); continue;
    }
    const abort = new AbortController();
    pending.set(request.call_id, abort);
    reply(request, { accepted: true });
    Promise.resolve().then(() => tool.execute(request.call_id, validateToolArguments(tool,
      { id: request.call_id, type: 'toolCall', name: tool.name, arguments: request.arguments },
      { keepUnknownRootKeys: tool.lenientArgValidation === true }), abort.signal)).then(
      result => emit({ type: 'tool_result', call_id: request.call_id,
        result, status: 'returned' }),
      () => emit({ type: 'tool_result', call_id: request.call_id,
        result: { content: [{ type: 'text', text: 'Native tool outcome unavailable; reconcile effects.' }] },
        status: 'unknown' }),
    ).finally(() => { pending.delete(request.call_id); completed.add(request.call_id); });
  } catch { fail(request); }
}
for (const abort of pending.values()) abort.abort();
