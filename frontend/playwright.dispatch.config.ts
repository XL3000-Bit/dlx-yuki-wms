import { defineConfig } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import os from 'node:os'

// No default target: this suite may only run against a launcher-owned environment.
const workspace = process.env.YUKI_UI_WORKSPACE
const evidence = process.env.YUKI_UI_EVIDENCE
if (!workspace || !evidence || !process.env.YUKI_UI_BASE ||
    !fs.existsSync(path.join(workspace, 'owned-by-dispatch-verification'))) {
  throw new Error('Run scripts/verify_dispatch_ui.py; an exclusive isolated environment is required')
}
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const resources = JSON.parse(fs.readFileSync(path.join(workspace, 'resources.json'), 'utf8'))
if (path.dirname(path.resolve(workspace)) !== path.resolve(os.tmpdir()) ||
    !path.basename(workspace).startsWith('yuki-dispatch-browser-') ||
    fs.readFileSync(path.join(workspace, 'owned-by-dispatch-verification'), 'utf8') !== root ||
    resources.workspace !== workspace || resources.frontend !== process.env.YUKI_UI_BASE ||
    new URL(resources.frontend).hostname !== '127.0.0.1') throw new Error('Isolation ownership mismatch')
export default defineConfig({
  testDir: './e2e', testMatch: 'dispatch.spec.ts', workers: 1, retries: 0,
  timeout: 300_000, expect: { timeout: 15_000 },
  outputDir: path.join(evidence, 'browser-artifacts'),
  reporter: [['list'], ['json', { outputFile: path.join(evidence, 'playwright-results.json') }]],
  use: { baseURL: process.env.YUKI_UI_BASE, browserName: 'chromium',
    actionTimeout: 15_000, navigationTimeout: 30_000,
    viewport: { width: 1500, height: 1100 }, screenshot: 'only-on-failure',
    trace: 'off', video: 'off' }, // Authentication must not leak through traces/HAR/storageState.
})
