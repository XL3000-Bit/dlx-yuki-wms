# Yuki Task Queue

## TASK OUTBOUND_SLICE_1

STATUS: READY
LEVEL: L2
BRANCH: feature/outbound-ef-parity-slice-1
PROMPT: docs/codex-outbound-playbook/prompts/SLICE_1.md
BASE_BRANCH: feature/outbound-ef-parity
BLOCKED_BY: NONE

## TASK OUTBOUND_SLICE_2

STATUS: BLOCKED
LEVEL: L2
BRANCH: feature/outbound-ef-parity-slice-2
PROMPT: docs/codex-outbound-playbook/prompts/SLICE_2.md
BASE_BRANCH: feature/outbound-ef-parity
BLOCKED_BY: OUTBOUND_SLICE_1

## TASK OUTBOUND_SLICE_3

STATUS: BLOCKED
LEVEL: L2
BRANCH: feature/outbound-ef-parity-slice-3
PROMPT: docs/codex-outbound-playbook/prompts/SLICE_3.md
BASE_BRANCH: feature/outbound-ef-parity
BLOCKED_BY: OUTBOUND_SLICE_2

## TASK OUTBOUND_SLICE_4

STATUS: BLOCKED
LEVEL: L2
BRANCH: feature/outbound-ef-parity-slice-4
PROMPT: docs/codex-outbound-playbook/prompts/SLICE_4.md
BASE_BRANCH: feature/outbound-ef-parity
BLOCKED_BY: OUTBOUND_SLICE_3

## TASK OUTBOUND_SLICE_5

STATUS: BLOCKED
LEVEL: L1
BRANCH: feature/outbound-ef-parity-slice-5
PROMPT: docs/codex-outbound-playbook/prompts/SLICE_5.md
BASE_BRANCH: feature/outbound-ef-parity
BLOCKED_BY: OUTBOUND_SLICE_4

Only one task may have `STATUS: READY` at a time unless a future user explicitly authorizes parallel tasks.
