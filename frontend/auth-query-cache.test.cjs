const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const { QueryClient } = require('@tanstack/react-query')
const output = ts.transpileModule(fs.readFileSync(path.join(__dirname, 'src/stores/authQueryCache.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const mod = { exports: {} }
new Function('module', 'exports', output)(mod, mod.exports)

test('logout and login discard permissions, scoped records and old mutations; refresh preserves the session', () => {
  let listener
  const cache = new QueryClient()
  const unsubscribe = mod.exports.bindAuthQueryCache({ subscribe: fn => { listener = fn; return () => { listener = undefined } } }, cache)
  const populate = () => {
    cache.setQueryData(['current-user'], { role: 'ADMIN', permissions: ['manage_outbound'] })
    cache.setQueryData(['loads', 'PRIVATE'], [{ id: 1 }])
    cache.getMutationCache().build(cache, { mutationKey: ['old-session'] })
  }
  populate()
  listener({ accessToken: 'refreshed-admin' }, { accessToken: 'admin' })
  assert.equal(cache.getQueryData(['current-user']).role, 'ADMIN')
  listener({ accessToken: null }, { accessToken: 'refreshed-admin' })
  assert.equal(cache.getQueryCache().getAll().length, 0)
  assert.equal(cache.getMutationCache().getAll().length, 0)
  populate() // A late old-session result must not survive the next login.
  listener({ accessToken: 'viewer' }, { accessToken: null })
  assert.equal(cache.getQueryData(['current-user']), undefined)
  assert.equal(cache.getQueryData(['loads', 'PRIVATE']), undefined)
  unsubscribe()
  assert.equal(listener, undefined)
})
