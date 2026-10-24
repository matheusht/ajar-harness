import { appendFileSync } from 'node:fs'

let sequence = 0
const kinds = new Set(['primary', 'title', 'compaction', 'generate'])

function record(event, phase, fields = {}) {
  const output = process.env.T02_OBSERVER_PATH
  if (!output || !kinds.has(event.kind) || !/^ses_[A-Za-z0-9]+$/.test(event.sessionID)) {
    throw new Error('request-name observer failed')
  }
  appendFileSync(output, JSON.stringify({
    sequence: ++sequence, phase, sessionID: event.sessionID, kind: event.kind,
    modelID: String(event.model?.id ?? '').slice(0, 128), ...fields,
  }) + '\n')
}

export default {
  id: 't02.request-names',
  async setup(ctx) {
    await ctx.session.hook('model.request', (event) => record(event, 'prepared'))
    await ctx.session.hook('http.request', async (event) => {
      let body
      try {
        body = await event.request.clone().json()
      } catch {
        record(event, 'dispatch', { parseStatus: 'invalid_json' })
        throw new Error('request-name observer failed')
      }
      const tools = body?.tools ?? []
      if (!Array.isArray(tools) || tools.length > 64) {
        record(event, 'dispatch', { parseStatus: 'invalid_tools' })
        throw new Error('request-name observer failed')
      }
      const names = tools.map((tool) => tool?.function?.name ?? tool?.name)
      if (names.some((name) => typeof name !== 'string' || !/^[A-Za-z0-9_.:-]{1,128}$/.test(name))) {
        record(event, 'dispatch', { parseStatus: 'invalid_tools' })
        throw new Error('request-name observer failed')
      }
      record(event, 'dispatch', { parseStatus: 'parsed', toolNames: names })
    })
  },
}
