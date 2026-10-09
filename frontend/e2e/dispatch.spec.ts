import { test, expect, type Page, type Locator } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const workspace = process.env.YUKI_UI_WORKSPACE!
const destination = process.env.YUKI_UI_EVIDENCE!
const fixtures = JSON.parse(fs.readFileSync(path.join(workspace, 'fixtures.json'), 'utf8'))
const resultsPath = path.join(destination, 'page-results.json')
// A failed test restarts the worker. Preserve earlier test evidence across workers.
const steps: any[] = fs.existsSync(resultsPath) ? JSON.parse(fs.readFileSync(resultsPath, 'utf8')).steps : []
function fault(action: string) {
  execFileSync(process.env.YUKI_UI_PYTHON!, [process.env.YUKI_UI_RUNNER!, '--fault', action, '--workspace', workspace], { stdio: 'pipe' })
}
async function step(page: Page, name: string, perform: () => Promise<void>) {
  const entry = { name, started_at: new Date().toISOString(), status: 'RUNNING' } as any
  steps.push(entry)
  try { await test.step(name, perform); entry.status = 'PASS' }
  catch (e) { entry.status = 'FAIL'; entry.error = String(e); throw e }
  finally {
    entry.finished_at = new Date().toISOString()
    const filename = `${steps.length.toString().padStart(3, '0')}-${name.replace(/[^a-zA-Z0-9_-]/g, '_')}.png`
    await page.screenshot({ path: path.join(destination, filename), fullPage: true }).catch(() => {})
    entry.screenshot = filename
    fs.writeFileSync(resultsPath, JSON.stringify({ policy: 'TEST ONLY', browser_version: page.context().browser()?.version(), native_file_picker: 'NOT_VERIFIED', steps }, null, 2))
  }
}
async function login(page: Page, user = 'admin') {
  await page.goto('/login')
  await page.getByLabel('Username', { exact: true }).fill(user)
  await page.getByLabel('Password', { exact: true }).fill('WarehousePassword!')
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await expect(page.locator('.signout-btn')).toBeVisible()
}
async function open(page: Page, domain: string) {
  await page.goto(`/loads/${domain === 'FBA' ? 'fba' : 'private'}?selected=${fixtures[domain].load_id}`)
  await expect(page.getByRole('button', { name: '提交实际派发（事务内重验）', exact: true })).toBeVisible()
  return page.locator('.ant-drawer-body').last()
}
async function select(page: Page, scope: Locator, label: string, option?: string) {
  const item = scope.locator('.ant-form-item').filter({ has: scope.page().getByText(label, { exact: true }) })
  await item.locator('.ant-select-selector').click()
  const options = page.locator('.ant-select-dropdown:visible .ant-select-item-option')
  await (option ? options.filter({ hasText: option }).first() : options.first()).click()
}
async function namedSelect(page: Page, scope: Locator, label: string) {
  await scope.getByRole('combobox', { name: label, exact: true }).click()
  await page.locator('.ant-select-dropdown:visible .ant-select-item-option').first().click()
}
async function action(page: Page, scope: Locator, button: string, endpoint: string, status = 200) {
  const waiting = page.waitForResponse(r => r.request().method() !== 'GET' && new URL(r.url()).pathname.endsWith(endpoint))
  await scope.getByRole('button', { name: button, exact: true }).click()
  const response = await waiting
  const body = await response.text()
  // Business responses only; never capture login headers, tokens or credentials.
  steps.at(-1)?.responses?.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status(), body })
  if (steps.at(-1) && !steps.at(-1).responses) steps.at(-1).responses = [{ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status(), body }]
  expect(response.status(), body).toBe(status)
  try { return JSON.parse(body || '{}') } catch { return { text: body } }
}
async function prepare(page: Page, domain: string) {
  const f = fixtures[domain], scope = await open(page, domain), base = `/loads/${f.load_id}`
  await select(page, scope, '已有库存预留')
  await scope.getByLabel('托盘数量', { exact: true }).fill('4')
  await action(page, scope, '保存派车分配', `${base}/allocations`, 201)
  await action(page, scope, '创建草稿计划', `${base}/plans`, 201)
  await expect(scope.getByRole('button', { name: '将全部分配写入计划', exact: true })).toBeEnabled()
  const plan = await action(page, scope, '将全部分配写入计划', `/lines`)
  await action(page, scope, '校验并锁定计划', `/finalize`)
  await action(page, scope, '转为待派发', `${base}/status`)
  for (const [label, value] of Object.entries({ '订单 ID': f.order_id, '拣货明细 ID': f.picking_item_id, '暂存位置 ID': f.staging_location_id, '实测数量': 4 })) {
    await scope.getByLabel(label, { exact: true }).fill(String(value))
  }
  await action(page, scope, '记录暂存', `${base}/stage`, 200)
  await action(page, scope, '记录暂存', `${base}/stage`, 409)
  await expect(scope.getByText('操作阻断', { exact: true })).toBeVisible()
  await action(page, scope, '开始核验', `${base}/verify/start`)
  await action(page, scope, '记录装车扫描', `${base}/verify/scan`, 200)
  await action(page, scope, '核对数量并完成核验', `${base}/verify/complete`)
  await expect(scope.getByText(/装车核验：已完成/)).toBeVisible()
  return { scope, base, plan }
}
async function upload(page: Page, scope: Locator, filename: string, status = 201) {
  await scope.getByRole('button', { name: /Upload$/ }).click()
  const modal = page.getByRole('dialog', { name: 'Upload document', exact: true })
  await select(page, modal, 'Document type', 'WAREHOUSE')
  await modal.locator('input[type=file]').setInputFiles(path.join(workspace, 'upload-fixtures', filename))
  const result = await action(page, modal, 'OK', '/documents', status)
  if (status !== 201) {
    await expect(modal.locator('.ant-alert')).toBeVisible()
    steps.at(-1).feedback ??= []
    const screenshot = `${steps.length}-${filename}-${status}-feedback.png`
    await page.screenshot({ path: path.join(destination, screenshot), fullPage: true })
    steps.at(-1).feedback.push({ filename, status, text: await modal.locator('.ant-alert').innerText(), screenshot })
    await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
  } else await expect(modal).not.toBeVisible()
  return result
}
async function review(page: Page, scope: Locator, base: string, kind: string, note: string, reject = false) {
  await scope.getByLabel('复核或异常处理说明').fill(note)
  await expect(scope.getByRole('button', { name: `${reject ? '拒绝' : '确认'} ${kind}`, exact: true })).toBeEnabled()
  return action(page, scope, `${reject ? '拒绝' : '确认'} ${kind}`, `${base}/evidence/reviews`, 200)
}

for (const domain of ['PRIVATE', 'FBA']) {
  test(`${domain} formal page lifecycle and upload errors`, async ({ page }) => {
    let scope: Locator, base: string, document: any
    await step(page, `${domain}-login-allocation-plan-stage-loading`, async () => {
      await login(page); ({ scope, base } = await prepare(page, domain))
    })
    await step(page, `${domain}-file-input-cancel-empty-oversize-outage-upload`, async () => {
      await scope.getByRole('button', { name: /Upload$/ }).click()
      let modal = page.getByRole('dialog', { name: 'Upload document', exact: true })
      await modal.locator('input[type=file]').setInputFiles([])
      await expect(modal.getByRole('button', { name: 'OK', exact: true })).toBeDisabled()
      await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
      await upload(page, scope, 'empty.csv', 422)
      await upload(page, scope, 'oversized.csv', 413)
      fault('storage-block')
      try { await upload(page, scope, 'valid.csv', 500) } finally { fault('storage-restore') }
      document = await upload(page, scope, 'valid.csv')
      await expect(scope.getByText('valid.csv', { exact: true })).toBeVisible()
    })
    await step(page, `${domain}-reject-correct-rereview-reapprove`, async () => {
      await namedSelect(page, scope, '单据订单')
      await action(page, scope, '生成并登记 BOL', `${base}/evidence/documents/bol`, 200)
      await review(page, scope, base, 'DOCUMENTS', `${domain} reject retained`, true)
      await action(page, scope, '提交实际派发（事务内重验）', `${base}/status`, 409)
      await expect(scope.getByRole('cell', { name: `${domain} reject retained`, exact: true })).toBeVisible()
      document = await upload(page, scope, 'corrected.csv')
      await namedSelect(page, scope, '关联异常')
      await scope.getByLabel('复核或异常处理说明').fill(`${domain} exception resolved`)
      await action(page, scope, '记录异常处理结果', '/resolve') // resolved endpoint handled below
      await review(page, scope, base, 'DOCUMENTS', `${domain} corrected reviewed`)
      await review(page, scope, base, 'EXCEPTIONS', `${domain} exception reviewed`)
      await review(page, scope, base, 'APPROVAL', `${domain} plan approved`)
    })
    await step(page, `${domain}-document-change-old-approval-invalid-block-refresh-renew`, async () => {
      document = await upload(page, scope, 'valid.csv')
      await action(page, scope, '提交实际派发（事务内重验）', `${base}/status`, 409)
      await expect(scope.getByText(/EVIDENCE_STALE/).first()).toBeVisible()
      await page.reload(); scope = page.locator('.ant-drawer-body').last()
      await expect(scope.getByText(/EVIDENCE_STALE/).first()).toBeVisible()
      await review(page, scope, base, 'DOCUMENTS', `${domain} renewed document`)
      await review(page, scope, base, 'EXCEPTIONS', `${domain} renewed exception`)
      await review(page, scope, base, 'APPROVAL', `${domain} renewed approval`)
    })
    await step(page, `${domain}-plan-content-version-invalidates-approval`, async () => {
      await expect(scope.getByText(/当前计划：v1 · FINAL/)).toBeVisible()
      await expect(scope.getByRole('button', { name: '保存计划内容', exact: true })).toBeDisabled()
      await expect(scope.getByLabel(/计划分配 #\d+ 托盘数量/)).toBeDisabled()
      const draft = await action(page, scope, '创建下一版草稿计划', `${base}/plans`, 201)
      expect(draft.version).toBe(2)
      const populated = await action(page, scope, '将全部分配写入计划', '/lines')
      await scope.getByLabel(/计划分配 #\d+ 托盘数量/).fill('3')
      const changed = await action(page, scope, '保存计划内容', '/lines')
      expect(changed.content_revision).toBeGreaterThan(populated.content_revision)
      expect(Number(changed.lines[0].pallet_qty)).toBe(3)
      const rejected = await action(page, scope, '校验并锁定计划', '/finalize', 409)
      expect(JSON.stringify(rejected)).toContain('PARTIAL_OR_UNATTRIBUTED_PLAN_UNSUPPORTED')
      await expect(scope.getByText(/PARTIAL_OR_UNATTRIBUTED_PLAN_UNSUPPORTED/).first()).toBeVisible()
      await scope.getByLabel(/计划分配 #\d+ 托盘数量/).fill('4')
      const restored = await action(page, scope, '保存计划内容', '/lines')
      expect(restored.content_revision).toBeGreaterThan(changed.content_revision)
      const finalized = await action(page, scope, '校验并锁定计划', '/finalize')
      expect(finalized.id).toBe(draft.id)
      expect(finalized.version).toBe(2)
      const blocked = await action(page, scope, '提交实际派发（事务内重验）', `${base}/status`, 409)
      expect(JSON.stringify(blocked)).toContain('EVIDENCE_STALE')
      await expect(scope.getByText(/当前计划：v2 · FINAL/)).toBeVisible()
      await expect(scope.getByText(/EVIDENCE_STALE/).first()).toBeVisible()
      await page.reload(); scope = page.locator('.ant-drawer-body').last()
      await expect(scope.getByText(/当前计划：v2 · FINAL/)).toBeVisible()
      await expect(scope.getByText(/EVIDENCE_STALE/).first()).toBeVisible()
      await page.locator('.ant-drawer-close').click()
      await page.locator('.signout-btn').click(); await login(page)
      scope = await open(page, domain)
      await expect(scope.getByText(/当前计划：v2 · FINAL/)).toBeVisible()
      await expect(scope.getByText(/EVIDENCE_STALE/).first()).toBeVisible()
      await page.screenshot({ path: path.join(destination, `${domain}-plan-v2-stale-relogin.png`), fullPage: true })
      for (const [label, value] of Object.entries({ '订单 ID': fixtures[domain].order_id, '拣货明细 ID': fixtures[domain].picking_item_id, '暂存位置 ID': fixtures[domain].staging_location_id, '实测数量': 4 })) {
        await scope.getByLabel(label, { exact: true }).fill(String(value))
      }
      await action(page, scope, '开始核验', `${base}/verify/start`)
      await action(page, scope, '记录装车扫描', `${base}/verify/scan`)
      await action(page, scope, '核对数量并完成核验', `${base}/verify/complete`)
      await review(page, scope, base, 'DOCUMENTS', `${domain} v2 documents reviewed`)
      await review(page, scope, base, 'EXCEPTIONS', `${domain} v2 exceptions reviewed`)
      const approval = await review(page, scope, base, 'APPROVAL', `${domain} v2 approved`)
      expect(JSON.stringify(approval)).toContain('APPROVAL')
    })
    await step(page, `${domain}-renewed-plan-dispatch-history-downstream`, async () => {
      await action(page, scope, '提交实际派发（事务内重验）', `${base}/status`)
      await expect(scope.getByRole('button', { name: '提交实际派发（事务内重验）', exact: true })).toBeDisabled()
      await page.reload()
      await expect(page.locator('.ant-drawer-body').last().getByText('DISPATCHED', { exact: true }).first()).toBeVisible()
      await page.locator('.ant-drawer-close').click()
      await page.locator('.signout-btn').click(); await login(page)
      scope = await open(page, domain)
      await expect(scope.getByRole('button', { name: '提交实际派发（事务内重验）', exact: true })).toBeDisabled()
      const history = scope.locator('.ant-table-wrapper').filter({ has: page.getByRole('columnheader', { name: '说明', exact: true }) })
      for (const note of [`${domain} v2 approved`, `${domain} plan approved`, `${domain} reject retained`]) {
        const firstPage = history.locator('.ant-pagination-item-1')
        if (await firstPage.count()) await firstPage.click()
        while (!(await history.getByRole('cell', { name: note, exact: true }).isVisible())) {
          const next = history.locator('.ant-pagination-next')
          await expect(next).not.toHaveClass(/ant-pagination-disabled/)
          await next.click()
        }
        await expect(history.getByRole('cell', { name: note, exact: true })).toBeVisible()
      }
      await page.goto(`/documents?selected=${document.id}`)
      await expect(page.getByText('Event history', { exact: true })).toBeVisible()
      await expect(page.getByText('UPLOADED', { exact: true })).toBeVisible()
      await page.screenshot({ path: path.join(destination, `${domain}-document-history.png`), fullPage: true })
      if (domain === 'FBA') {
        await page.goto(`/fba?selected=${fixtures[domain].fba_id}&stage=all`)
        await page.getByRole('button', { name: 'View Outbound', exact: true }).click()
        await expect(page.getByText('FBA outbound detail', { exact: true })).toBeVisible()
        const detail = page.locator('.fba-detail .ant-descriptions')
        await expect(detail.getByText(fixtures[domain].ob_no, { exact: true })).toBeVisible()
        await expect(detail.getByText('FBA', { exact: true })).toBeVisible()
        await expect(detail.getByText('Dispatched', { exact: true })).toBeVisible()
      } else {
        await page.goto(`/outbound/dispatch?selected_ob=${fixtures[domain].order_id}`)
        await page.getByRole('cell', { name: fixtures[domain].ob_no, exact: true }).locator('a').click()
        await expect(page.getByText(`${fixtures[domain].ob_no} — OB Details`, { exact: true })).toBeVisible()
        const detail = page.getByRole('region', { name: 'General Information', exact: true })
        await expect(detail.getByText(fixtures[domain].ob_no, { exact: true })).toBeVisible()
        await expect(detail.getByText('STANDARD', { exact: true })).toBeVisible()
        await expect(detail.getByText('Dispatched', { exact: true })).toBeVisible()
      }
      await page.screenshot({ path: path.join(destination, `${domain}-downstream.png`), fullPage: true })
    })
  })
}

test('formal page ownership permission expiry and unconfigured policy', async ({ page }) => {
  await step(page, 'ownership-upload-server-rejection', async () => {
    await login(page); await page.goto('/documents')
    await page.getByRole('button', { name: /Upload$/ }).click()
    const modal = page.getByRole('dialog', { name: 'Upload operational document', exact: true })
    await select(page, modal, 'Document type', 'WAREHOUSE')
    await modal.getByLabel('Load ID', { exact: true }).fill(String(fixtures.FBA.load_id))
    await modal.getByLabel('Outbound ID', { exact: true }).fill(String(fixtures.PRIVATE.order_id))
    await modal.locator('input[type=file]').setInputFiles(path.join(workspace, 'upload-fixtures/valid.csv'))
    await action(page, modal, 'OK', '/documents', 409)
    await expect(modal.getByText(/DOCUMENT_LOAD_MEMBERSHIP_MISMATCH/)).toBeVisible()
    await page.screenshot({ path: path.join(destination, 'ownership-feedback.png'), fullPage: true })
    await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.getByRole('button', { name: /Upload$/ }).click()
    await expect(modal.locator('.ant-alert')).toHaveCount(0)
    await expect(modal.getByRole('button', { name: 'OK', exact: true })).toBeDisabled()
    await expect(modal.getByLabel('Load ID', { exact: true })).toHaveValue('')
    await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
  })
  await step(page, 'real-permission-revocation-server-403-and-account-switch', async () => {
    await page.getByRole('button', { name: /Upload$/ }).click()
    const modal = page.getByRole('dialog', { name: 'Upload operational document', exact: true })
    await select(page, modal, 'Document type', 'WAREHOUSE')
    await modal.getByLabel('Load ID', { exact: true }).fill(String(fixtures.PRIVATE.load_id))
    await modal.getByLabel('Outbound ID', { exact: true }).clear()
    await modal.locator('input[type=file]').setInputFiles(path.join(workspace, 'upload-fixtures/valid.csv'))
    fault('role-revoke')
    try { await action(page, modal, 'OK', '/documents', 403); await expect(modal.locator('.ant-alert')).toBeVisible() }
    finally { fault('role-restore') }
    await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.locator('.signout-btn').click(); await login(page, 'viewer')
    const scope = await open(page, 'PRIVATE')
    await expect(scope.getByRole('button', { name: /Upload$/ })).toHaveCount(0)
    await expect(scope.getByRole('button', { name: '确认 APPROVAL', exact: true })).toBeDisabled()
    await page.reload()
    await expect(page.getByRole('button', { name: '确认 APPROVAL', exact: true })).toBeDisabled()
    await page.locator('.ant-drawer-close').click(); await page.locator('.signout-btn').click(); await login(page)
  })
  await step(page, 'unconfigured-policy-page-and-dispatch-block', async () => {
    const { scope, base } = await prepare(page, 'UNCONFIGURED')
    await expect(scope.getByText('业务规则未配置或未启用，真实派发继续阻断')).toBeVisible()
    await scope.getByLabel('复核或异常处理说明').fill('TEST ONLY unavailable authority')
    await expect(scope.getByRole('button', { name: '确认 APPROVAL', exact: true })).toBeDisabled()
    await action(page, scope, '提交实际派发（事务内重验）', `${base}/status`, 409)
  })
  await step(page, 'expired-evidence-server-and-page-block', async () => {
    const { scope, base } = await prepare(page, 'EXPIRING')
    await upload(page, scope, 'valid.csv')
    await namedSelect(page, scope, '单据订单')
    await action(page, scope, '生成并登记 BOL', `${base}/evidence/documents/bol`, 200)
    await review(page, scope, base, 'DOCUMENTS', 'expiring documents')
    await review(page, scope, base, 'EXCEPTIONS', 'expiring exceptions')
    await review(page, scope, base, 'APPROVAL', 'expiring approval')
    await page.waitForTimeout(17000)
    await page.reload()
    await expect(page.getByText(/EVIDENCE_EXPIRED/).first()).toBeVisible()
    await action(page, scope, '提交实际派发（事务内重验）', `${base}/status`, 409)
    await page.reload()
    await expect(page.getByText(/EVIDENCE_EXPIRED/).first()).toBeVisible()
  })
})
