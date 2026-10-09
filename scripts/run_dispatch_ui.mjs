// Keep npm's Windows command shell out of executable path parsing.
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('../', import.meta.url));
const python = fileURLToPath(new URL(
  process.platform === 'win32' ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python',
  import.meta.url,
));
const script = fileURLToPath(new URL('./verify_dispatch_ui.py', import.meta.url));
if (!existsSync(python)) {
  console.error('Dispatch acceptance requires the existing backend virtual environment.');
  process.exit(1);
}
const result = spawnSync(python, [script, ...process.argv.slice(2)], {
  cwd: root,
  stdio: 'inherit',
  windowsHide: true,
  shell: false,
});
if (result.error) console.error(`Dispatch acceptance could not start: ${result.error.code ?? 'UNKNOWN'}`);
process.exit(result.status ?? 1);
