# INB-1A 拆柜入库工作台实施方案

日期：2026-09-10。当前完成 Step 1：架构审查与方案，不代表功能已实现。

## 1. 已保存的起点

- 基线提交：`67323db8924c0954e7e39a2f5822e247376ddb96`。
- 基线标签：`yuki-baseline-20260910`。
- 开发分支：`feature/inbound-1a-workbench`。
- 迁移代码最新版本：`20260909_0033`，静态检查只有一个 head。任务原文的 0026 已被恢复阶段验证的迁移链取代，新增迁移应接在 0033 后。
- 本次未连接或迁移业务数据库，实际数据库 revision 尚未核对。
- 保留已有 recovery 分支和 284 个未跟踪恢复文件；本步骤只新增本文档。不得批量暂存这些文件。

## 2. 业务范围

仓库文员按表格方式人工录入一柜货的拆柜数据，保存草稿，校验后批量确认入库。一次确认必须同时完成入库状态、库存、库存流水和审计，任何一行失败则整批回滚。

支持人工输入已有库位、批量粘贴、逐格编辑和 Hold。FastAPI 是唯一写入入口。仅在 DEV/TEST 验证；不包括扫码、PDA、AI、邮件、微信、财务或审批。保留既有 Ocean Inbound 和 Dispatch 行为。

## 3. 可复用架构及缺口

| 位置 | 已有能力 | 本阶段处理 |
| --- | --- | --- |
| `backend/app/models/inbound.py` | 柜号、FC、仓库、客户、库位、托盘、重量、来源、日期；状态数值 0–5 | 复用主体；独立保存工作台生命周期，不能改写旧状态枚举 |
| `backend/app/services/inbound.py` | 范围校验、编号、审计、更新锁、历史记录保护 | 增加草稿与工作台状态规则，阻止旧更新/删除入口绕过已收货保护 |
| `backend/app/models/inventory.py` | `source_inbound_id` 唯一约束、余额、库位分布、库存流水 | 保持一行入库对应一个库存批次；补齐入库来源快照 |
| `backend/app/services/inventory.py` | 收货生成库存、行锁、可选不提交 | 抽取事务内共用方法，保留旧接口的状态要求 |
| `backend/app/services/ocean_inbound.py` | 实收校验、版本、排序加锁、差异备注 | 当前确认收货只更新入库，不生成库存；不能直接视为新工作台的完整入账能力 |
| `backend/app/models/warehouse.py` | 仓库及库位主数据、库位所属仓库 | 人工输入时解析现有有效库位，拒绝跨仓和停用库位 |
| `backend/app/models/amazon_fc_address.py` | FC 唯一编码和启用标记 | 复用 FC 校验，不另建 FC 表 |
| `backend/app/models/container_tracking.py` | 柜号及不同运输周期 | 柜号不是唯一运输周期；不因录入草稿自动创建运输跟踪记录 |
| `backend/app/services/access_policy.py` | 客户/仓库范围及历史记录保护 | 所有列表、草稿、收货入口统一复用 |
| `frontend/src/pages/InboundPage.tsx` | 入库列表、抽屉录入、导入、库存/Ocean 跳转 | 增加独立工作台视图及入口，保留原列表 |

当前未发现独立 Batch/Master Batch 模块。本阶段保存批次标识，不扩展成新的批次管理系统。

### 必须随入库闭环修复的 Hold 问题

现有 Hold 主要转移托盘和箱数余额，重量/体积仍可能保留可用值。普通出库及 FBA 分配服务没有明确拒绝整批 HOLD 库存，因此存在仅按重量或体积分配的绕过路径。

新工作台的整行 Hold 必须在两类分配服务统一拦截所有数量维度，同时保留既有部分 Hold 行为。不得通过清零原始重量损失数据。测试必须覆盖托盘、箱数、重量、体积以及混合数量分配。

## 4. 字段与状态设计

复用入库记录的柜号、仓库、客户、FC、库位、托盘数、拆柜日期、备注、创建人和时间。计划新增工作台来源/状态、批次与主批次、原始重量与单位、整行 Hold、转仓/转 FC 和版本字段；正式字段名称在 Step 2 按现有模型惯例落实。

- 原始重量使用精确十进制，单位限定 LB/KG；保留输入值与单位。服务端统一换算为现有 `weight_lbs`，明确精度和舍入；前端不能成为库存计算的唯一依据。
- 库存保留入库来源、仓库/库位、FC、批次、柜号、原始重量/单位、Hold 和收货时间快照。转仓信息仅作标记，不自动执行跨仓库存移动。
- 不复制创建人等可信上下文，操作者与时间由服务端产生。
- 草稿允许未填完；标记 READY 和确认收货时要求托盘数大于零、有效 FC/库位、所属仓库一致、完整柜号/批次，以及合法重量和单位。
- 工作台状态为 DRAFT → READY → RECEIVED；未收货记录可取消为 CANCELLED。允许 READY 返回 DRAFT 编辑；RECEIVED 和 CANCELLED 不可通过普通草稿接口修改。
- 新状态与旧数值状态分开保存。旧接口、旧记录、历史归档继续遵循原语义；工作台收货后的旧状态映射必须由服务端单点处理并加兼容测试。
- 删除未收货草稿采用审计可追溯的取消；已收货拒绝删除。编辑使用版本校验，避免两位文员互相覆盖。

## 5. API、权限与错误

沿用现有 `/inbound` 路由约定，增加草稿创建、更新、删除及批量 receive；保留列表查询。静态 `/drafts`、`/receive` 路由应注册在 `/{record_id}` 前，避免路径被当作整数 ID。

请求只接受业务字段及预期版本。返回逐行 ID、状态、版本、库存关联和可读校验错误；批量收货接受不重复的入库 ID 与预期版本。

- 读操作沿用登录用户及数据范围；写操作复用 ADMIN、MANAGER、INBOUND、WAREHOUSE 对应权限。
- 删除权限保持现有管理员边界，除非后续明确调整角色政策。
- 每一行都校验仓库/客户范围及 live-record 限制，不能只校验批量请求第一行。
- 非法字段返回 422；状态、版本、重复入库冲突返回 409。重复已收货明确返回 `ALREADY_RECEIVED`，不再生成库存。
- 不硬编码账号，不增加权限豁免。

## 6. 原子收货与防重复

1. 检查请求格式、空列表、重复 ID；按固定 ID 顺序锁定入库记录，并刷新数据库状态。
2. 验证全部记录存在、权限、来源、版本、READY 状态、主数据与正托盘数量；有任一错误则终止整批。
3. 检查库存关联；已收货或已存在库存时返回冲突。不得用前端按钮禁用代替服务端保证。
4. 在同一事务内逐行生成库存批次、库位分布和 INBOUND 流水，保留 `source_inbound_id` 数据库唯一约束。
5. 设置整行 Hold 和正确余额/状态；无需调用会自行提交的 Hold 方法。共用服务只能 flush，不能提前 commit。
6. 更新收货状态、时间和版本，写审计，最后统一提交。唯一约束冲突需完整回滚并转换成稳定业务错误。

并发保护由行锁和唯一约束共同提供。SQLite 单元测试不能证明 PostgreSQL 行锁有效，需另做隔离 PostgreSQL 双请求验证。重复请求采用冲突语义；混合已收货与未收货请求整批拒绝，不进行部分成功。

审计事件：`INBOUND_DRAFT_CREATED`、`INBOUND_DRAFT_UPDATED`、`INBOUND_DRAFT_DELETED`、`INBOUND_RECEIVED`、`INVENTORY_CREATED_FROM_INBOUND`。记录操作者、时间、实体、前后值与工作台来源；审计失败也必须回滚库存。

## 7. 表格工作台

列按要求提供：Location、Pallet、FC、Batch、Container、Date、Weight、Unit、Hold、Transfer Warehouse、Note。主批次、仓库/客户等公共上下文在适当位置统一设置，避免每行重复输入。

提供新增多行、删除未确认行、TSV 粘贴、逐格编辑、固定表头、FC/库位/Hold/状态筛选，以及行数/托盘/重量汇总。混合单位汇总需分别显示原始单位或清楚标明换算后的统一单位，不能直接相加。逐格错误可定位；保存后刷新恢复草稿，收货后显示库存关联。提交期间阻止重复点击，但仍依赖后端防重复。

## 8. 分步实施与验收

| 步骤 | 产出 | 重点验证 |
| --- | --- | --- |
| Step 1（当前） | 本方案、基线标签、功能分支 | 已审查架构；无业务代码变更 |
| Step 2 | 模型、schema、迁移、草稿服务/API | 草稿 CRUD、范围权限、版本冲突、旧 API 兼容 |
| Step 3 | 原子 receive、库存/流水/审计、Hold 分配保护 | 单行/多行、回滚、重复和并发、全部数量维度 Hold |
| Step 4 | 后端测试及迁移验证 | SQLite 行为测试 + 隔离 PostgreSQL 约束与锁测试 |
| Step 5 | 表格工作台及组件测试 | 粘贴、编辑、单位、筛选、汇总、刷新和重复提交 |
| Step 6 | 回归及浏览器验收 | 后端、前端 build、lint/typecheck、Alembic、既有 Ocean/Dispatch/FBA |

后端主要修改范围：inbound/inventory 模型和 schema、对应 service/API、必要的 outbound/fba Hold 校验、迁移及相关测试。前端主要范围：入库工作台组件、API/types、入口及测试。每步检查完整 diff 和 diff stat，不混入无关恢复文件。

新增迁移接续 0033；先在隔离 DEV/TEST 数据库从旧版本升级，检查旧行默认值与唯一约束，再验证 downgrade/upgrade。不得重写已经存在的迁移，不接触生产或 `127.0.0.1:55432/yuki_chino_local`。

### 必测场景

- 草稿新增/修改/取消；无权限、跨仓/跨客户、停用/错误库位、错误 FC、空批次/柜号、零负托盘、错误重量单位。
- 单行和多行入库生成准确库存、库位分布、流水和五类审计；接收后不能通过旧更新或删除入口绕过锁定。
- 第二行校验失败、库存生成失败、审计失败均验证整批没有残留库存或状态变化。
- 重复收货、重复请求内 ID、并发同一行：库存仅一份。
- Hold 无法普通出库或 FBA 分配；非 Hold 及既有部分 Hold 行为回归。
- LB/KG 保存原值、换算与精度；页面混合单位汇总正确。
- 测试柜 `TEST-INB-001`、批次 `TEST-INB-BATCH-001`、FC `LAX9`：A01 为 5 托，A02 为 3 托，收货后共 8 托，再次收货仍为 8 托。仅在隔离测试数据中创建所需主数据。
- 浏览器验收覆盖粘贴、修改 FC/单位/Hold、确认、库存查看、刷新、重复确认。

## 9. 本步验证及当前状态

本次隔离后端预检成功退出，使用临时文档目录和 SQLite 测试夹具；排除了需要实际数据库的 `test_migration_backfills_existing_cargo_without_changing_stock`。Alembic 静态 heads 为唯一 `20260909_0033`。这些结果只证明开发起点，不证明新功能完成。

前一恢复阶段记录的前端 34 项、WPS 15 项和构建通过，本步未重新执行。已知 28 项原有严格 TypeScript 错误不在本阶段顺手修复；最终回归必须区分旧问题和新引入问题。

| 验收项 | 当前结果 |
| --- | --- |
| INBOUND_1A_BACKEND | NOT_STARTED |
| INBOUND_1A_FRONTEND | NOT_STARTED |
| INBOUND_1A_INVENTORY_LINK | NOT_STARTED |
| INBOUND_1A_IDEMPOTENCY | NOT_STARTED |
| INBOUND_1A_AUDIT | NOT_STARTED |
| INBOUND_1A_PERMISSIONS | NOT_STARTED |
| INBOUND_1A_TESTS | NOT_STARTED（仅基线后端预检通过） |
| INBOUND_1A_MIGRATION | NOT_STARTED（仅静态 head 核对） |
| REGRESSION | PARTIAL（完整功能回归待实现后执行） |
| WORKTREE | 新增方案文档；原有 recovery 未跟踪文件保留 |
| INBOUND_1A | PARTIAL |

剩余工作：Step 2–6 尚未实施，实际 DEV/TEST 数据库迁移与并发行为尚未验证。下一步从模型/schema 和草稿 API 开始。仅在全部关键验收通过后，逐文件暂存相关改动并使用任务指定的 feature 提交信息；不 merge、不 push、不删除 recovery 分支。
