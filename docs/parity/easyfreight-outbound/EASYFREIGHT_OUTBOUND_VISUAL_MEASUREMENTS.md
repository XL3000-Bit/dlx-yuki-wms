# EasyFreight Outbound Visual Measurements

## Method and boundary

The authenticated page was measured with temporary browser viewport overrides at
the three requested CSS viewport sizes. Browser zoom was not changed. Only
geometry, overflow, labels, control counts, and visibility were recorded; row
content was not retained. The viewport override was reset after capture.

## Three-zone layout

| Viewport | Primary / right divider X | Right content X | Primary scroll viewport | Right scroll viewport | Primary table width | OB BOL table width |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1920 × 1080 | 800 | 817 | 760 × 1014 | 1093 × 1013 | 1859 | 2558 |
| 1600 × 900 | 668 | 686 | 629 × 834 | 904 × 833 | 1859 | 2558 |
| 1440 × 900 | 603 | 620 | 563 × 834 | 810 × 833 | 1859 | 2558 |

All dimensions are CSS pixels rounded to integers. At each viewport the divider
was a visible one-pixel element with an east-west resize cursor. The split stayed
near 42 percent primary / 58 percent right content as the viewport narrowed.

## Overflow and stacking

| Viewport | Primary horizontal overflow | Right horizontal overflow | Remaining title Y | Evidence state |
| --- | ---: | ---: | ---: | --- |
| 1920 × 1080 | 1099 | 1481 | 1076 | PARTIAL |
| 1600 × 900 | 1230 | 1670 | 1076 | PARTIAL |
| 1440 × 900 | 1296 | 1764 | 1076 | PARTIAL |

The primary table and right-side tables require horizontal scrolling at all three
sizes. OB BOL List and Remaining BOL List are vertically stacked inside the
right-side scroll region. At 1600 × 900 and 1440 × 900 the lower title begins
below the viewport, so users must scroll the right pane to reach it. This is a
captured reference behavior, not automatically a DLX requirement.

## Table measurements

| Table | Header height | Typical first-row height | Content width | Parity state |
| --- | ---: | ---: | ---: | --- |
| Primary Outbound | about 59 | about 59 | 1714 to 1859 depending on loaded layout state | PARTIAL |
| OB BOL List | about 73 | about 49 | 2558 | PARTIAL |
| Remaining BOL List | about 73 | about 59 | 967 to 1061 depending on loaded layout state | PARTIAL |

## Responsive behavior

| Behavior | Evidence | Parity state |
| --- | --- | --- |
| Splitter | A full-height east-west resize handle was visible at all tested sizes. | MATCHED |
| Hide right pane | Hide OB BOL List removed the right-side lists; Show OB BOL List restored them. | MATCHED |
| Narrow desktop | Columns do not collapse into cards; both sides preserve dense grids and horizontal scroll. | PARTIAL |
| Right lower list | It remains below the upper list rather than becoming a separate tab. | PARTIAL |
| Reset Window | Did not visibly change the tested right-pane scroll position. | UNKNOWN |
| Split persistence | Reload/session persistence was not changed or tested. | BLOCKED |

## Column and view controls

| Control | Read-only evidence | Parity state |
| --- | --- | --- |
| Mange Properties | Opening increased visible property/column checkboxes by 29; closing restored the baseline count. | PARTIAL |
| Views | Added an input/control surface, but no view was created, selected, or saved. | UNKNOWN |
| Top filters | Opened independently and added six selects plus fourteen inputs relative to the closed baseline. | MATCHED |
| Bottom filters | Opened independently and added five selects plus eleven inputs relative to the closed baseline. | MATCHED |

Shared-view mutation, ownership, defaults, per-user persistence, and permission
behavior remain BLOCKED. No column or view preference was saved.

**Recommendation:** NOT READY FOR PARITY IMPLEMENTATION
