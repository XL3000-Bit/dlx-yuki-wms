# PDA V1 验收报告（PHASE PDA-1A）

验收日期：2026-09-02
基线提交：`cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`
验收范围：只验证当前 PDA 首版实现，不新增功能、不执行真实数据库迁移、不写生产数据、不构建 APK。

## 1. 最终结论

```text
PDA_OPERATIONS_V1 = PARTIAL
SOURCE_IMPLEMENTATION = PASS
FRONTEND_TYPESCRIPT = PASS
FRONTEND_PRODUCTION_BUILD = PASS
FRONTEND_PDA_UNIT_TESTS = PASS_18_OF_18
BACKEND_REGRESSION = NOT_RUN_MISSING_TEST_DEPS
PDA_WRITE_E2E = BLOCKED_NO_SAFE_TEST_DB
REAL_DEVICE_SCANNER_HEAD = NOT_VERIFIED
REAL_DEVICE_CAMERA_SCAN = NOT_VERIFIED
PDA_CAMERA_HTTP = BLOCKED_INSECURE_CONTEXT
OFFLINE_QUEUE_RECOVERY = NOT_VERIFIED_REAL_DEVICE
WAREHOUSE_DATA_ISOLATION = FAIL_STATIC_USER_PARTITION_MISSING
BUSINESS_WRITE_IDEMPOTENCY = PARTIAL_CONFIRM_PICK_ONLY
INVENTORY_AUDIT_CONSISTENCY = NOT_VERIFIED_RUNTIME
APK = NOT_STARTED
DB_PHASE_12_1D_B = NOT_STARTED
```

不能将 PDA 首版标记为验收通过。前端 TypeScript、生产构建和 18 个 PDA 单元测试均通过，五类作业入口及对应 API 也已存在；但后端回归没有可用的项目 Python 测试环境，未提供可处置的 PostgreSQL/专用测试库，真机扫码、相机、断网恢复均未执行。静态审查还发现离线队列缺少用户/仓库归属，以及普通扫描离线重放没有端到端幂等保护。

## 2. 工作区与变更边界

验收开始时工作区已经包含大量未提交改动。本次只新增本报告，没有清理、覆盖、暂存或提交既有改动。

基线命令与结果：

```text
git rev-parse HEAD
cefe1a23b9779b71ce9c7097b0fdf020a14bca6d

git diff --cached --name-status
<empty>

git diff --check
PASS（仅出现既有文件 LF 将转 CRLF 的工作区警告）
```

验收开始时的已跟踪修改：

```text
M backend-java/.gitignore
M backend-java/README.md
M backend-java/pom.xml
M backend-java/src/main/java/com/dlxyuki/wms/WmsApplication.java
M backend-java/src/main/java/com/dlxyuki/wms/config/AppProperties.java
M backend-java/src/main/java/com/dlxyuki/wms/config/DatabaseConfig.java
M backend-java/src/main/java/com/dlxyuki/wms/config/SecurityConfig.java
M backend-java/src/main/java/com/dlxyuki/wms/fba/FbaController.java
M backend-java/src/main/java/com/dlxyuki/wms/fba/FbaRepository.java
M backend-java/src/main/java/com/dlxyuki/wms/fba/FbaService.java
M backend-java/src/main/resources/application.yml
M backend/app/api/v1/endpoints/company_profile.py
M backend/app/api/v1/router.py
M backend/app/models/__init__.py
M backend/app/models/company_profile.py
M docs/CURRENT_SYSTEM_SETTINGS_ASSESSMENT.md
M frontend/package-lock.json
M frontend/package.json
M frontend/src/App.tsx
M frontend/src/layouts/AppLayout.tsx
```

验收开始时还存在下列未跟踪范围：`backend-java/docs/`、`backend-java/src/main/java/com/yuki/`、`backend-java/src/main/resources/mapper/`、若干 Java 测试和工具、迁移 `0025/0026`、company profile/3PL 后端与测试、PDA 文档及前端、nginx、图片和文档生成工具。它们均视为验收前已有内容，没有被本次工作清理或改写。

与 PDA 验收直接相关的现有文件包括：

```text
frontend/src/App.tsx
frontend/src/layouts/AppLayout.tsx
frontend/src/pages/PdaPage.tsx
frontend/src/pages/PdaOperations.tsx
frontend/src/pages/pda.css
frontend/src/api/scanExecution.ts
frontend/src/components/pda/CameraScanner.tsx
frontend/src/components/pda/PdaOfflineQueue.tsx
frontend/src/components/pda/offlineQueueDb.ts
frontend/src/components/pda/offlineQueuePolicy.ts
frontend/src/components/pda/offlineQueuePolicy.test.mjs
frontend/src/components/pda/cameraScanPolicy.ts
frontend/src/components/pda/cameraScanPolicy.test.mjs
backend/app/api/v1/endpoints/scan_execution.py
backend/app/models/scan_execution.py
backend/app/schemas/scan_execution.py
backend/app/services/scan_execution.py
backend/tests/test_scan_execution.py
backend/alembic/versions/20260830_0022_scan_execution_foundation.py
backend/alembic/versions/20260830_0023_picking_scan_workflow.py
docs/PDA_BARCODE_STANDARD.md
docs/PDA_PROJECT_KICKOFF.md
```

`backend/alembic/versions/20260902_0025_merge_heads.py` 和 `20260902_0026_company_profile_singleton.py` 仅做存在性记录，未修改，也未执行 `alembic upgrade`、`downgrade` 或 `stamp`。

## 3. 已执行验证

| 项目 | 命令/证据 | 结果 |
|---|---|---|
| TypeScript | `frontend/node_modules/.bin/tsc.cmd -b` | PASS，退出码 0 |
| 生产构建 | `npm run build`（`tsc -b && vite build`） | PASS，Vite 7.3.6，5,045 modules，约 6.08 秒；仅有大 chunk 提示 |
| PDA 单元测试 | `node --test src/components/pda/*.test.mjs` | PASS，18/18 |
| diff 空白错误 | `git diff --check` | PASS；只有换行符警告 |
| Python 解释器发现 | `.venv`/`venv`、`py -0p`、依赖导入探测 | 找到系统 Python 3.13 和 Astral CPython 3.11.16，但项目无 `.venv`/`venv`，两者均缺少 `pytest` |
| 后端 pytest | 未执行 | `NOT_RUN_MISSING_TEST_DEPS`；按约束未安装 Python/依赖、未改 PATH |
| 写入 E2E | 未执行 | 没有已确认可处置的 PostgreSQL 或专用测试库；没有对真实业务库写入 |

`backend/tests/conftest.py` 本身使用 `sqlite://`、`StaticPool`，并覆盖 `get_db`，设计上可隔离运行现有 pytest；本机缺少项目依赖使其无法启动。该事实不能替代实际回归结果，也不能证明 PostgreSQL 行为。

## 4. 首版入口与五类作业闭环

`frontend/src/App.tsx:21` 懒加载 `PdaPage`，`frontend/src/App.tsx:34` 注册 `/pda` 路由。

| 作业 | 前端调用 | 服务端实现与事务边界 | 静态结论 |
|---|---|---|---|
| 入库 | 查询 `/inbound`，写入 `POST /inbound/{id}/receive-to-inventory` | `receive_inbound` 锁定入库单，检查状态及 `source_inbound_id` 重复，创建库存批次、库存流水和审计日志后一次提交 | 重复收货有状态/唯一关系防护；实现存在，运行回归未执行 |
| 出库 | 查询 `/outbounds`，写入 `POST /outbounds/{id}/dispatch` 或 `/complete` | `change` 先检查状态转换；dispatch 调用 readiness；complete 更新分配、库存、FBA 分配、流水及审计后一次提交 | 重复 dispatch/complete 会被状态机拒绝；前置条件存在，运行回归未执行 |
| 拣货 | `/scan-sessions/{id}/scan`、`/confirm-pick` | `confirm_pick` 锁定 session、picking item、allocation、lot；按 `(session_id, client_operation_id)` 查重；endpoint 统一提交/回滚 | 数量确认具备服务端幂等；普通 scan 不具备同等级幂等 |
| 移库 | 查询 `/inventory`，写入 `POST /inventory/{id}/move` | 锁库存批次，校验目标仓库，更新库位并写 MOVE 流水/审计后提交 | 事务闭环存在；无请求幂等键，未拒绝同库位移动，静态上可重复写流水 |
| 盘点 | 查询 `/inventory`，写入 `POST /inventory/{id}/adjust` | 锁库存批次，防止负库存，更新原始/可用数量并写 ADJUSTMENT 流水/审计后提交 | 当前是即时调整，不是服务端盘点任务；无请求幂等键，重复请求会重复调整 |

PDA 通用四类作业在离线或权限不足时被禁用，只有拣货扫描页实现本地离线队列。因此不能把拣货页已有的离线行为推定为所有五类作业都支持离线。

## 5. 高风险链检查

### 5.1 入库重复生成库存

- `backend/app/services/inventory.py:48-54` 对入库单加锁并检查既有 `source_inbound_id`，同一事务创建批次、INBOUND 流水和审计。
- `backend/tests/test_inventory.py:11` 有防重复用例，但本次未能执行。
- 结论：`PASS_STATIC / NOT_VERIFIED_RUNTIME`。

### 5.2 重复 dispatch / complete 与前置条件

- `backend/app/services/outbound.py:90-107` 先做 readiness 和状态转换检查，再更新状态；重复调用不在允许转换集合中。
- `backend/app/services/dispatch_readiness.py:106-109` 在非 READY 时返回 409。
- readiness 静态覆盖 allocation、picking、BOL、carrier 和未关闭异常等条件；complete 仅从允许状态进入并在一个提交内处理库存与流水。
- 现有测试覆盖正常 dispatch/complete 生命周期，但没有明确的“重复 dispatch”和“重复 complete”断言。
- 结论：`PASS_STATIC / TEST_GAP / NOT_VERIFIED_RUNTIME`。

### 5.3 拣货离线重放与幂等

- `confirm-pick` 使用 `client_operation_id`，`backend/app/services/scan_execution.py:974-981` 在写入前返回既有事件；迁移 `0023` 还提供非空值的部分唯一索引。
- `backend/tests/test_scan_execution.py:577-617` 有原子性与幂等用例，但本次未执行。
- 普通 `SCAN_VALUE` 虽然在客户端生成 `client_operation_id`，`frontend/src/pages/PdaPage.tsx:72-81` 重放时只发送扫描值；`backend/app/api/v1/endpoints/scan_execution.py:94-103` 的请求也只接受 `value`。网络响应丢失后重试可能再次追加扫描事件或重复推动步骤。
- 结论：`BUSINESS_WRITE_IDEMPOTENCY = PARTIAL_CONFIRM_PICK_ONLY`。

### 5.4 移库源/目标与流水

- 服务端使用锁并校验目标库位属于同一仓库，写入 MOVE 流水与审计。
- 没有拒绝 `to_location_id == current location_id`；静态上同库位操作仍可生成“移动”流水。
- 目标库位的 active 状态没有在该服务方法中显式校验。
- 没有客户端操作号或其他请求级去重，重复提交会产生重复流水。
- 结论：`PARTIAL_STATIC / NOT_VERIFIED_RUNTIME`。

### 5.5 盘点调整

- 服务端锁定批次并防止可用/原始库存变负，库存变更、流水及审计处于同一提交边界。
- PDA 端 `makeCountNo` 只生成写入 remark 的客户端编号，服务端没有把它作为幂等键，也没有服务端盘点任务生命周期。
- 重复提交同一调整会再次改变库存；零变化是否应允许也没有专门验收用例。
- 结论：`PARTIAL_STATIC / IDEMPOTENCY_GAP / NOT_VERIFIED_RUNTIME`。

### 5.6 仓库与用户隔离

- 通用作业查询均携带 `warehouse_id`，切换仓库时四个 panel 以 warehouse id 重新挂载，可清空对应组件的瞬时结果。
- 选择值保存为全局 `localStorage['pda-warehouse-id']`，没有用户维度。
- 离线队列 `PdaQueuePayload` 只有 `session_id/value/quantity/step/source`，没有 `user_id` 或 `warehouse_id`；IndexedDB 也是同源全局库。退出并换账号后，旧账号的待同步记录仍可能由新会话尝试发送。
- 服务端仍会做当前用户权限/作用域校验，因此越权写入不应被客户端状态直接绕过；但这不能替代客户端队列所有权隔离，也可能造成错误重放、阻塞或信息残留。
- 结论：`WAREHOUSE_DATA_ISOLATION = FAIL_STATIC_USER_PARTITION_MISSING`。

## 6. 前端交互、离线与相机

### 已有保护

- 拣货扫描使用同步 `scanInFlightRef`，可阻止同一 React render 周期内 Enter、按钮或相机回调重复入队。
- IndexedDB 队列有唯一客户端操作号、FIFO、发送租约、最多 3 次自动重试、指数退避、认证阻塞和永久失败状态。
- 18 个 Node 单元测试覆盖持久化、FIFO、并发同步、重试、认证错误、租约恢复和相机去重策略。
- 相机组件在停止、卸载和启动竞态时调用 `MediaStreamTrack.stop()`；权限拒绝及不支持场景有降级提示。

### 未关闭风险

- 通用 `ScanField` 同时绑定 `onPressEnter` 和按钮 click，只依赖异步 `busy` state，没有同步 in-flight ref；极快的双触发仍可能发出两个查询/操作链。
- 离线单元测试不能替代浏览器刷新、真实网络切换、登录态切换、IndexedDB 升级和真机恢复测试。
- 相机要求 secure context 且依赖 `getUserMedia`/`BarcodeDetector`。浏览器通过普通局域网 HTTP 地址访问时不满足 secure context，不能验收相机扫描。参考：[MDN getUserMedia 安全上下文要求](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。

因此：

```text
PDA_CAMERA_HTTP = BLOCKED_INSECURE_CONTEXT
REAL_DEVICE_CAMERA_SCAN = NOT_VERIFIED
REAL_DEVICE_SCANNER_HEAD = NOT_VERIFIED
OFFLINE_QUEUE_RECOVERY = NOT_VERIFIED_REAL_DEVICE
```

USB/蓝牙扫码枪作为键盘输入理论上不受页面 HTTP 相机限制，但尚未用真实设备验证扫码后 Enter、焦点保持、大小写、连续扫码和双触发。

## 7. 必须补做的验收矩阵

只有完成以下项目，才可重新评估 `PDA_OPERATIONS_V1 = PASS`：

1. 在项目自有、可复现且不需临时安装依赖的 Python 环境中运行完整后端 pytest，并保存失败日志与测试数量。
2. 对专用、可销毁的 PostgreSQL 测试库运行五类写入链；核对业务表、库存流水、审计日志和失败回滚。不得指向生产/真实业务库。
3. 增加并执行重复 dispatch、重复 complete、重复 move、重复 adjust、同库位 move、非活动目标库位的明确回归用例。
4. 修复离线队列的用户/仓库分区与登录切换清理/接管规则，并让 `SCAN_VALUE` 的客户端操作号进入服务端请求和唯一约束。
5. 在真实 PDA/手机和扫码枪上验证：连续扫码、Enter/按钮竞态、弱网、断网入队、刷新、进程被杀、恢复同步、401/403、永久失败和手工重试。
6. 通过 HTTPS（或浏览器明确认可的安全本地主机上下文）验证相机权限、后摄像头优先、识别去重、停止轨道和拒绝权限后的恢复。
7. 用两个账号、两个仓库验证切换后页面缓存、IndexedDB 队列、查询结果及服务端权限均不串仓、不串用户。

## 8. 本阶段未执行事项

- 未安装 Python、未升级依赖、未修改 PATH。
- 未运行任何 Alembic upgrade/downgrade/stamp；未修改迁移 `0025/0026`。
- 未对真实/生产数据库执行写入。
- 未修改 Java、Settings、Nginx 或其他无关代码。
- 未构建 APK。
- 未执行 `git add`、commit 或 push。

最终记账保持：`PDA_OPERATIONS_V1 = PARTIAL`。数据库 Phase 12.1D-B 与 APK 均保持 `NOT_STARTED`。
