const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const moduleUnderTest = { exports: {} }
const output = ts.transpileModule(fs.readFileSync(path.join(__dirname, 'src/components/loadDispatchState.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
new Function('module', 'exports', output)(moduleUnderTest, moduleUnderTest.exports)
const { sameDispatchDomain, dispatchRequest, dispatchFailure, evidenceRefreshDelay, openVerificationRun } = moduleUnderTest.exports

test('accepted evidence refreshes at expiry and revocation; expired response stops polling', () => {
  const now = Date.parse('2026-10-05T22:00:00Z')
  const data = seconds => ({checks:[{status:'PASS',review:{expires_at:new Date(now+seconds*1000).toISOString()}}]})
  assert.equal(evidenceRefreshDelay(data(5),now),5100)
  assert.equal(evidenceRefreshDelay(data(3600),now),30000)
  assert.equal(evidenceRefreshDelay(data(-1),now),250)
  assert.equal(evidenceRefreshDelay({checks:[{status:'BLOCKED',reason:'EVIDENCE_EXPIRED'}]},now),false)
  assert.equal(evidenceRefreshDelay(undefined,now),false)
})

test('domain checks reject mixed business, cross warehouse and missing customer', () => {
  const load = { warehouse_id: 1, dispatch_business_type: 'PRIVATE', outbounds: [{ warehouse_id: 1, customer_id: 2, dispatch_business_type: 'PRIVATE' }] }
  assert.equal(sameDispatchDomain(load, 'PRIVATE'), true)
  assert.equal(sameDispatchDomain(load, 'FBA'), false)
  for (const change of [{ warehouse_id: 3 }, { customer_id: null }, { dispatch_business_type: 'FBA' }]) {
    assert.equal(sameDispatchDomain({ ...load, outbounds: [{ ...load.outbounds[0], ...change }] }, 'PRIVATE'), false)
  }
})
test('dispatch always submits an explicit final plan revision and operation ID', () => {
  const plan = { id: 8, status: 'FINAL', content_revision: 0 }
  assert.deepEqual(dispatchRequest(plan, 'request-1'), { status: 'DISPATCHED', plan_id: 8, expected_revision: 0, operation_id: 'request-1' })
  assert.throws(() => dispatchRequest({ ...plan, status: 'DRAFT' }, 'request-1'))
  for (const change of [{ id: null }, { content_revision: null }, { content_revision: -1 }, { content_revision: 1.5 }]) {
    assert.throws(() => dispatchRequest({ ...plan, ...change }, 'request-1'))
  }
  assert.throws(() => dispatchRequest(plan, ' '))
})
test('server blockers retain UNKNOWN and missing evidence; PASS does not authorize dispatch', () => {
  const checks = [
    { key: 'approval', status: 'UNKNOWN', reason: '无审批', reason_code: 'APPROVAL_MISSING', missing_information: ['审批人', '计划版本'] },
    { key: 'inventory', status: 'BLOCKED', reason: '不足', reason_code: 'SHORTAGE', missing_information: [] },
    { key: 'execution', status: 'PASS' }, { key: 'optional', status: 'NOT_APPLICABLE' },
  ]
  assert.deepEqual(dispatchFailure({ response: { data: { detail: { checks } } } }), ['approval: 无审批 (APPROVAL_MISSING)；缺少：审批人、计划版本', 'inventory: 不足 (SHORTAGE)'])
})
test('validation, conflict and network failures remain visible', () => {
  assert.deepEqual(dispatchFailure({ response: { data: { detail: [{ loc: ['body', 'plan_id'], msg: 'required' }] } } }), ['body.plan_id: required'])
  assert.deepEqual(dispatchFailure({ response: { data: { detail: 'PLAN_REVISION_CONFLICT' } } }), ['PLAN_REVISION_CONFLICT'])
  assert.deepEqual(dispatchFailure(new Error('offline')), ['offline'])
})

test('refresh resumes the persisted open batch and never reopens completed batches', () => {
  assert.equal(openVerificationRun(undefined),null)
  assert.equal(openVerificationRun({current_verification_run:null}),null)
  assert.equal(openVerificationRun({current_verification_run:{id:'persisted-uuid',status:'STARTED'}}),'persisted-uuid')
  assert.equal(openVerificationRun({current_verification_run:{id:'persisted-uuid',status:'COMPLETE'}}),null)
})
