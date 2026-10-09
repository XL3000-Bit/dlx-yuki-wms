const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

// Compile only the actual units under test in memory; no app bootstrap or server.
function unit(file, imports = {}) {
  const source = fs.readFileSync(path.join(__dirname, file), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(name => {
    if (!(name in imports)) throw new Error(`Unexpected runtime import: ${name}`)
    return imports[name]
  }, module, module.exports)
  return module.exports
}
const { createReadinessReader, readinessPresentation, planValue } = unit('src/components/loadReadinessState.ts')
const result = id => ({ load_id: id, ready: false, plan_id: null, plan_version: null, content_revision: null, checks: [] })
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }

test('four distinct statuses and missing plan values', () => {
  assert.deepEqual(Object.keys(readinessPresentation), ['PASS', 'BLOCKED', 'UNKNOWN', 'NOT_APPLICABLE'])
  assert.equal(new Set(Object.values(readinessPresentation).map(x => x.color)).size, 4)
  assert.notEqual(readinessPresentation.UNKNOWN.color, 'success')
  assert.equal(planValue(null), '缺失')
  assert.equal(planValue(3), '3')
})
test('successful business gaps preserve the backend conclusion and evidence', async () => {
  const states = [], data = { ...result(1), checks: [{ status: 'UNKNOWN', reason: 'missing evidence' }] }
  await createReadinessReader(async () => data, state => states.push(state)).refresh(1)
  assert.equal(states[0].kind, 'loading')
  assert.deepEqual(states[1], { kind: 'success', data })
  assert.equal(states[1].data.ready, false)
})
for (const status of [401, 403, 404, 503]) test(`HTTP ${status} is an access or technical error, never business UNKNOWN`, async () => {
  let state
  await createReadinessReader(async () => { throw { response: { status } } }, value => { state = value }).refresh(1)
  assert.deepEqual(state, { kind: status === 503 ? 'unavailable' : 'denied' })
})
test('refresh clears old data before a network failure', async () => {
  let state, calls = 0
  const next = deferred()
  const reader = createReadinessReader(() => ++calls === 1 ? Promise.resolve(result(1)) : next.promise, value => { state = value })
  await reader.refresh(1)
  const pending = reader.refresh(1)
  assert.deepEqual(state, { kind: 'loading' })
  next.reject(new Error('private error details'))
  await pending
  assert.deepEqual(state, { kind: 'unavailable' })
})
test('older object responses cannot replace the new result', async () => {
  const first = deferred(), second = deferred(), signals = []
  let state
  const reader = createReadinessReader((id, signal) => { signals.push(signal); return id === 1 ? first.promise : second.promise }, value => { state = value })
  const a = reader.refresh(1), b = reader.refresh(2)
  assert.equal(signals[0].aborted, true)
  second.resolve(result(2)); await b
  first.resolve(result(1)); await a
  assert.equal(state.data.load_id, 2)
})
test('stale failure and unmounted responses do not publish', async () => {
  const first = deferred(), second = deferred(), states = []
  const reader = createReadinessReader(id => id === 1 ? first.promise : second.promise, state => states.push(state))
  const a = reader.refresh(1), b = reader.refresh(2)
  first.reject(new Error('old')); await a
  reader.dispose()
  second.resolve(result(2)); await b
  assert.deepEqual(states, [{ kind: 'loading' }, { kind: 'loading' }])
})
test('a response for a different load is unavailable', async () => {
  let state
  await createReadinessReader(async () => result(2), value => { state = value }).refresh(1)
  assert.deepEqual(state, { kind: 'unavailable' })
})
test('API uses the existing client and only GET with cancellation', async () => {
  const calls = [], data = result(7), signal = new AbortController().signal
  const api = { get: async (...args) => { calls.push(args); return { data } } }
  const { getLoadDispatchReadiness } = unit('src/api/loads.ts', { './client': { api } })
  assert.equal(await getLoadDispatchReadiness(7, signal), data)
  assert.deepEqual(calls, [['/loads/7/dispatch-readiness', { signal }]])
})
