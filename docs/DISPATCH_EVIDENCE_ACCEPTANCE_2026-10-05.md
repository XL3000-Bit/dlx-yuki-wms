# 派发真实证据机制与浏览器验收 — 2026-10-05

> 当前进度见 [2026-10-07 技术收尾与隔离上线演练](DISPATCH_RELEASE_ACCEPTANCE_2026-10-07.md)：真实 PostgreSQL 部分出库并发已补验，规则发布工具已补真实账号认证，浏览器服务端响应、过期与刷新历史补验通过；原生文件选择及完整当前业务页面流程仍待验证。下文是历史记录，不计为本次通过。生产规则仍未确认、未启用。

本记录接续 [派发闭环验收](DISPATCH_CLOSURE_ACCEPTANCE_2026-10-05.md)，以当前未提交代码及实际执行结果为准。保留原有成果；未部署、推送、修改生产数据、迁移旧业务记录、修改项目凭据或重启现有服务。

**结论：三项持久化证据已接入只读预检和原有事务内派发阻断。FBA、私仓在独占隔离环境中完成浏览器成功流程；成功使用明确标记的测试专用策略，只证明机制，不代表生产规则获准。没有确认、启用策略的真实派发继续阻断。**

## 规则依据与边界

| 来源 | 可确认的内容 | 不能据此确认的内容 |
| --- | --- | --- |
| 当前用户要求 | FBA/私仓独立；禁止混装；仓库/客户/归属/数量约束；活动异常及过期证据阻断；计划变化使旧审批失效；管理员不绕过业务条件 | 每个业务必需的具体单据、审批/复核岗位、有效期及取消异常是否合格 |
| `FBA_WORKBENCH_YUKI.md`，现有单据/BOL/异常/权限代码 | 已有 Picking、BOL 查看/下载、生成和上传归档、异常状态与审计、角色和仓库/客户范围，可以复用 | 单据存在或能下载不等于获准用于派发；FINAL 不等于批准 |
| `uni-fba-parity/UNI-YUKI-PARITY-CONTRACT.md` 的 P_UNKNOWN、P_WRITE、P_LOAD/P_DOC，W05 复用和业务域约束 | 不将未知事项写成已确认规则；复用已有能力；读取 BOL 不应生成新单据；保持独立域 | D22 费用审批不构成派发审批规则 |
| `uni-fba-parity/UNI-FBA-DETAIL.md`、`UNI-FBA-DOCUMENTS.md`、`UNI-FBA-VS-YUKI-GAP.md` | 费用审批、单据生成/版本/取消行为和管理粒度仍有未观察/未知项 | 无可靠的生产派发证据契约；不能从外部页面或测试替身补出规则 |

测试策略及 fixture 属于机制验收数据，不能作为生产规则来源。以下三个决策仍未获得确认。

## 已实现

- 0039 迁移复用 operational documents，增加可空业务类型（旧单据不猜测回填），新增按仓库、业务类型和版本管理的不可变策略及追加式证据审查记录。无生产策略 seed，无普通页面/API 策略启用入口。
- 策略显式配置单据类型、ORDER/LOAD 粒度、生成 BOL 是否可接受及 BOL 状态、各审查角色和有效期、独立审批及取消异常处理。缺失、禁用、无出处或非法策略均不能授权。策略更新通过新版本撤销旧版本授权。
- 单据验证业务类型、仓库、客户、订单/派车归属、版本、AVAILABLE 状态、创建人及事件。生成 BOL 核对来源和明细；上传文件核对实际可读取内容、大小与摘要。归档、内容/归属改变、来源变化会使原审查失效。
- 单据确认、异常复核和计划审批保存审查人、角色/范围、计划修订、策略版本、内容快照/摘要、结果、说明、操作 ID、时间及到期时间。审批依赖当前有效的单据和异常审查；旧计划、旧策略、权限撤销、过期、内容变化继续阻断。
- 异常关联派车单、订单及相关业务来源；活动异常直接阻断。已解决异常要求真实处理人、处理结果、时间及审计，取消异常仅在明确策略允许且证据完整时合格；历史缺身份记录不会自动修复。
- 证据写入和派发沿用事务保护；PostgreSQL 对证据来源写入增加事务锁和不可变记录保护，避免检查与写入间竞态。精确重放不增加审查/执行/审计；不同内容复用操作 ID 冲突；失败整体回滚。
- FBA/私仓独立证据工作台：显示规则来源、处理角色、缺失/过期原因和历史，可生成 BOL、上传现有单据、记录异常解决及提交审查。规则未配置时管理者也不能确认；派发后停止编辑。普通页面不能把未配置规则变成授权。
- 前端按有效证据到期时间刷新，刷新预检/失败派发同步刷新证据，防止过期后仍显示旧 PASS。FBA 下游详情保持 FBA 入口和 Dispatched 阶段；私仓详情保持独立入口。
- 修复 BOL 在关闭 autoflush 的事务中重复注册的问题；保留此前已存在的重复记录，没有自动清洗业务数据。

核心实现：`backend/app/services/dispatch_evidence.py`、证据模型/Schema、0039 迁移、`loads.py` API、`LoadDispatchEvidence.tsx` 及现有预检/事务派发服务。测试专用策略只在测试模块/临时验收 seed 中创建，生产应用不导入测试模块。

## 实际运行验证

| 验证 | 结果 | 实际边界 |
| --- | --- | --- |
| SQLite 证据及派发生命周期测试 | 37 通过（15 + 22） | 归属、规则禁用、权限撤销、版本/有效期、异常归因、重放、回滚等 |
| FBA 工作台后端测试 | 6 通过 | 下游入口/阶段修复后运行 |
| 前端派发/预检 Node 测试 | 16 通过 | 含证据到期刷新调度回归 |
| 前端 TypeScript/Vite 构建 | 通过 | 仍有 bundle 大小提示，不能替代业务验收 |
| 独占 PostgreSQL 17 全新迁移 | 0001 → `20261005_0039` 通过 | 验证 data_directory/测试角色；不使用项目数据库地址 |
| 隔离 PostgreSQL 场景 | 41 通过（原 27 + 真实证据 14） | FBA/私仓、精确重放、并发、数据库追加式保护、失效/权限/规则撤销、缺 FINAL、跨仓异常脱敏、同事务 BOL 注册、真实审查过期、异常处理归因和失败回滚 |

上阶段 387 通过/1 跳过、只读 21 通过是历史结果，本阶段没有为凑验收重新运行。新增变化的验证如上。

## 浏览器实际验收

使用真实 in-app 浏览器与独占 PostgreSQL、后端和 Vite 服务，随机 loopback 端口。测试角色/订单/库存/异常均为 synthetic；没有浏览器访问生产业务。截图位于 `docs/evidence/dispatch-2026-10-05/`。

| 场景 | 实际操作与结果 | 截图 |
| --- | --- | --- |
| 私仓成功与前置阻断 | 登录 → 库存分配 → FINAL 计划 → 暂存 → START/SCAN/COMPLETE 装车核验 → READY。先提交，被缺单据/审查及活动异常阻断。生成 BOL、记录异常解决结果、单据确认/异常复核/计划审批后提交，进入 DISPATCHED。随后私仓订单详情显示 Dispatched、STANDARD、仓库/客户和 BOL。派发后按钮禁用 | `private-blocked.jpg`、`private-dispatched.jpg`、`private-downstream.jpg` |
| FBA 成功与前置阻断 | 同样从分配、FINAL、暂存及装车核验开始，先实际提交并阻断，再完成 BOL、异常处理和三个审查，派发成功。进入 FBA Dispatched 列表及独立订单详情，显示 FBA、Dispatched、4 PLT、0 CTN；已派发分配/排期不再可编辑 | `fba-blocked.jpg`、`fba-dispatched.jpg`、`fba-downstream.jpg` |
| 未配置策略 | 从分配、FINAL、暂存和核验完成到 READY，管理者实际提交被 `DOCUMENT_RULES_NOT_CONFIGURED`、`DISPATCH_APPROVAL_MISSING`、`EXCEPTION_REVIEW_RULES_MISSING` 阻断；规则显示尚未确认，审查按钮禁用，状态仍 READY | `unconfigured-blocked.jpg` |
| 到期证据 | 使用明确 TEST ONLY、5 秒有效期策略，生成单据并完成三个审查；到期后实际提交失败，DOC/EX 为 `EVIDENCE_EXPIRED`，审批依赖失效。证据界面及预检同步显示阻断，状态仍 READY | `expired-blocked.jpg` |
| 越权 | 切换 viewer 登录，完整加载后的证据页显示要求 ADMIN、当前角色无权处理，各写按钮禁用。接口 403 另由后端/PG 验证，不声称浏览器发送了被禁用的写请求 | `viewer-denied.jpg` |
| 重复及失败反馈 | 浏览器确认提交中/已派发后的按钮保护及实际失败原因。操作 ID 重放、不同内容复用、并发和事务回滚由 PG 场景实测；未声称浏览器强制双 POST 或浏览器注入失败 | 上述已派发/阻断截图及 PG 场景 |

成功路径使用 TEST ONLY 持久化策略及真实实现，不使用固定 PASS 消除 UNKNOWN。截图是界面证据；事务/并发结论来自数据库测试。

浏览器路径未单独验收上传文件、拒绝后重新审查及生产策略配置发布流程。上传真实性/归档失效有代码和测试覆盖，但不将其称作浏览器通过。POD/真实承运商执行及上线迁移均不在本次通过范围。

## 临时资源与可复现入口

- PG 场景目录：`C:\Users\XL\AppData\Local\Temp\yuki-dispatch-pg-j_x9dxya`，41 场景后已停止，保留日志及数据。
- 浏览器目录：`C:\Users\XL\AppData\Local\Temp\yuki-dispatch-browser-g55ghuyo`，保留 cluster/backend/frontend/seed 日志和 synthetic 数据。验收结束只停止本次拥有的服务及集群，不删除目录。
- PG：`backend/.venv/Scripts/python.exe scripts/verify_dispatch_isolated.py`。
- 浏览器：`backend/.venv/Scripts/python.exe scripts/start_dispatch_browser_isolated.py`；输出新的独占资源目录与随机地址。向输出目录中的 `stop` 文件写入内容结束；runner 的 finally 停止其创建的子进程和集群。无需项目 `.env`，不得替换为现有数据库地址。
- 截图清单及 SHA256 见同目录 `manifest.json`。凭据不放入本记录或截图清单。

## 一次性业务决策表

请分别给 FBA、私仓确认以下三组规则；确认前继续禁用，不能派发生产业务。

| 待确认规则 | 已有依据 | 建议选项及影响 |
| --- | --- | --- |
| 必需单据、归属粒度、可接受来源/状态、单据确认角色及有效期 | 有 BOL/Picking/上传与归档能力；未有获准的必需清单或版本有效性契约 | 逐业务列清单及 ORDER/LOAD 粒度，明确是否接受系统 BOL、状态和岗位/有效期。建议接受前要求 AVAILABLE 且当前来源一致；额外必需单据会增加缺件阻断。具体清单/有效期不代定 |
| 计划审批角色、是否独立于创建/锁定人、有效期 | FINAL 仅锁定；费用审批不是派发审批 | 建议独立审批，以减少自审；如果业务确实允许同人需明确批准。岗位/有效期由业务确定；计划/证据变化一律使审批失效 |
| 异常复核角色、有效期、CANCELED 是否合格 | 有 OPEN/INVESTIGATING/RESOLVED/CANCELED 及处理审计；活动异常明确阻断 | 建议 RESOLVED 且处理证据完整后才能复核；CANCELED 默认保持未授权，若接受须明确。复核岗位/有效期确认后才能启用 |

技术上的模型、持久化、权限、版本、过期、并发及操作流程已实现；上述业务决定、部署环境受控迁移和生产验收仍待完成。不得将测试策略下成功称为生产可用。

## 本次验收收尾（2026-10-05，最终回归）

**本阶段机制验收收尾完成；生产上线仍待规则批准及受控执行。** 本节替代上文“浏览器未单独验收上传、拒绝补正及配置发布”的缺口说明；上文数字是历史结果，不计入本次通过。没有扩展 POD/承运商集成，没有部署、推送、操作生产库、修改项目凭据或重启现有服务。原有未提交成果保留。

### 本次修复及补齐

- 增加受控策略 CLI、FBA/PRIVATE 独立待填模板、严格字段/出处校验、无写入 dry-run、六组规则及版本差异预览、比较版本发布/撤销和追加审计。缺项不补默认值；没有新增普通页面发布入口。批准材料真实性仍需受控操作者核对，CLI 的 actor-id 是审计身份输入，不代替操作者认证。
- TEST_ONLY 授权增加环境、数据库角色、独占临时集群目录和所有权标记的联合检查；生产环境即使使用该测试库也拒绝测试策略。SQLite 测试必须显式标记拥有的测试连接。启动入口不导入测试 seed，UNKNOWN 不转成固定 PASS。
- 上传空文件明确返回 422 并清理失败资源；上传单据按已有最高版本递增，保留历史重复记录。上传弹窗持续显示真实接口错误，待提交期间防重，重开重置文件状态。
- 修复派发后证据页刷新错误：关闭业务的证据允许只读查询与历史展示，写入仍被拒绝。刷新预检/失败派发同步刷新证据，旧审批失效及时显示。
- 补充代表性旧库升级、备份恢复、迁移故障回滚/重试验证工具及上线说明；不需要在 0039 之后新增迁移，不回填未知业务/身份/审批，不清理旧单据。

### 本次实际运行结果

证据目录：`docs/evidence/dispatch-final-20261005/`，日志/截图/DOM 快照摘要见 `manifest.json`，结构化结果见 `results.json`。日志中的此前失败尝试保留用于追溯，仅 `backend-final.log` 是最终后端通过结果。

| 本次执行 | 实际结果 | 证据及边界 |
| --- | --- | --- |
| 完整后端测试 | **415 通过，1 跳过，退出 0** | `backend-final.log`；跳过 `test_migration_safety.py::test_concurrent_partial_cannot_overdraw`，原因是该 SQLite 用例需要真实 PG 行锁；它是历史部分出货场景，未声称本次 PG 场景替代了此用例 |
| 独立只读预检 | **21 通过** | `readonly.log` |
| 前端全部测试 | **51 通过，0 跳过** | `frontend-tests.log` |
| TypeScript / Vite 构建 | **通过** | `frontend-build.log`；bundle 大小提示仍存在，构建不替代业务验收 |
| 独占 PostgreSQL 全新迁移及相关场景 | **0001 → 0039 成功，44 场景通过** | `postgres-final.log`；包含权限、版本/到期、重放、并发、回滚、配置预览/发布/撤销及生产环境拒绝 TEST_ONLY |
| 旧库升级及恢复 | **通过** | 同 PG 日志：0036 代表性身份/UNKNOWN/同版本重复单据，pg_dump / 独立恢复，0037/0038，再注入 0039 DDL 失败；确认回滚到 0038、旧数据保留后正常重试至 0039，检查约束、viewer 拒绝和 UNKNOWN 派发阻断 |
| 文件库备份恢复 | **7 个实际上传文件，恢复后摘要全部一致** | `filestore-restore.json`；此隔离文件库演练与旧库备份演练分别验证恢复机制，不声称是生产一致性备份 |
| FBA / 私仓待填模板 | **都按预期拒绝，退出 2** | `template-FBA-validation.log`、`template-PRIVATE-validation.log`；不需要数据库即可校验，无默认规则发布 |

最初完整后端运行受临时目录权限影响失败；改用本次独占临时目录后完整重跑通过。pytest 缓存权限及 Alembic 配置弃用提示不影响退出结果。未验证项目：生产备份/升级/切换、生产策略批准/发布、生产业务验收；未执行历史部分出货 PG 行锁用例；POD/承运商不在本阶段范围。

### 本次真实浏览器操作与结果

真实 in-app 浏览器使用本次独占 PostgreSQL/API/Vite，随机 loopback 端口 60463/60464/60465；synthetic 登录、库存、订单与明确 TEST_ONLY 策略。以下均是实际页面操作，不以 API 测试代替浏览器成功路径。两个业务分别从分配、FINAL 锁定、暂存及装车核验进入 READY，再执行证据流程和派发。

| 流程 | 实际结果 | 关键证据（均在本次目录） |
| --- | --- | --- |
| 私仓文件上传与归属 | 空文件被 422 拒绝；超过验收限制的文件上传失败并显示原因；订单归属不匹配被拒绝；有效文件成功注册 | `browser-invalid.*`、`browser-upload-failure.*`、`browser-ownership.*`、`browser-private-correction.txt` |
| 私仓拒绝补正与重新批准 | 单据拒绝记录保留，补正文件和重新单据/异常审查后审批；审批拒绝后重新审批；再次上传新版本使旧审批失效，重新审查/审批后派发成功 | `browser-stale-approval.*`、`browser-private-dispatched.*` |
| FBA 上传及拒绝补正 | 错误订单归属被拒绝；有效 LOAD 文件上传，单据拒绝与审批拒绝分别留历史；重新审查和批准；新文件版本使旧批准失效，实际提交派发收到阻断，重新审查/审批后进入 DISPATCHED | `browser-fba-ownership.*`、`browser-fba-rejected.txt`、`browser-fba-stale-approval.*`、`browser-fba-blocked.*`、`browser-fba-dispatched.*` |
| 刷新一致性及历史 | 两业务派发后实际页面刷新，仍为 DISPATCHED；证据只读、旧文件 SUPERSEDED、旧拒绝记录仍可翻页查看，修复前刷新报错已消除 | `browser-fba-refresh-history.*`、`browser-private-refresh-history.*`、`browser-private-actual-reload.*` |
| 独立下游详情 | 私仓详情显示 STANDARD / Dispatched，FBA 详情显示 FBA / Dispatched，两业务均显示实际 4 PLT，保持独立入口 | `browser-private-downstream.*`、`browser-fba-downstream.*` |
| 未配置规则及权限不足 | 未配置规则显示 UNKNOWN 和缺失原因，ADMIN 审查按钮仍禁用；viewer 明确显示角色要求、写按钮禁用 | `browser-unconfigured.*`、`browser-permission-planned.*` |
| 到期及重复操作反馈 | 5 秒 TEST_ONLY 证据到期后实际派发返回阻断，仍 READY；页面显示过期及审批依赖失效。提交中及关闭后按钮防重 | `browser-expiring-approved.txt`、`browser-expired.*` 及两业务派发截图 |

权限不足/重复操作在浏览器证明按钮与提示行为，没有强制发送已禁用的写请求或双 POST；接口 403、精确重放/冲突、并发和事务回滚由本次后端及 PG 实测。空文件与超限文件证明已实现的无效上传校验，不声称存在未定义的文件内容格式规则。TEST_ONLY 成功只证明实现机制，不能称为生产可用。

### 停止临时资源及上线交接

本次 PG 场景资源目录 `C:\Users\XL\AppData\Local\Temp\yuki-dispatch-pg-q32jzxhg`、浏览器资源目录 `C:\Users\XL\AppData\Local\Temp\yuki-dispatch-browser-t9bsh1w4` 均已停止，原始日志/数据保留。资源所有权由 runner 核对；仅停止本次创建进程，最终监听检查见 `cleanup.json`。

上线配置、备份、迁移、验证、版本发布/撤销、审计及故障恢复步骤见 [上线准备操作说明](DISPATCH_RELEASE_PREPARATION_2026-10-05.md)。其中最终填写表只要求两业务各自确认必需单据与粒度/来源/状态、三类审查岗位与有效期、独立审批、取消异常是否接受，以及真实批准记录和六组出处。模板保持待填且禁用；生产执行仍需明确授权，本次没有自动启用生产策略。
