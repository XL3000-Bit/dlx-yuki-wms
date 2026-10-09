# PHASE 12.1D-B 真实数据库受控升级报告

## 最终结论

**PASS**

在已确认的维护窗口内，真实 PostgreSQL 数据库 `dlx_yuki_wms` 已使用唯一获准的 Alembic 命令升级到唯一 head `20260902_0026`。最终备份可列举且校验通过；业务表行数、公司资料原字段内容和审计记录均未发生非预期变化；单例约束已生效；进程内只读冒烟测试通过。未执行测试套件、stamp、downgrade、数据修复、恢复、提交、推送或代码修改。

本报告的数据库结论与后续 PDA 验收相互独立。数据库阶段结束时的分离状态为：

```text
DATABASE_SCHEMA_STATUS      = DEPLOYED_AND_CURRENT
APPLICATION_SERVICE_STATUS  = STOPPED
OPERATIONAL_AVAILABILITY    = NOT_RESTORED
PDA_OPERATIONS_V1           = PARTIAL
```

## 授权与范围

- 授权标记：`START_PHASE_12_1D_B = YES`
- 执行日期：2026-09-02（America/Los_Angeles）
- 检查开始：2026-09-02 11:58:03 -07:00
- 最终验收完成：2026-09-02 12:03:00 -07:00
- 仓库：`C:\Users\XL\dlx-yuki-wms`
- Git 分支：`feature/java-api-parity`
- 基线提交：`cefe1a23b9779b71ce9c7097b0fdf020a14bca6d`
- 本阶段唯一数据库变更：`alembic upgrade 20260902_0026`

仓库开始时已有大量未提交及未跟踪文件。本阶段未修改这些既有文件，未暂存或提交任何文件；唯一新增仓库文件是本报告。

## 维护窗口与写入冻结

- 升级前没有匹配本仓库的 `uvicorn`、`app.main`、`npm` 或 `vite` 进程。
- 端口 8000 和 5173 均无监听。
- 未发现相关 Windows 服务。
- 因服务原始状态就是停止，未结束任何进程，也没有可记录的 PID。
- 升级和只读冒烟结束后再次检查：相关进程数 0，相关监听数 0。
- 为保持原始运行状态，本阶段没有在结束时启动后端或前端。

## 升级前安全门

### 数据库身份

| 项目 | 结果 |
| --- | --- |
| 数据库 | `dlx_yuki_wms` |
| 用户 | `dlx_user` |
| 地址/端口 | `::1/128:5432` |
| PostgreSQL | 17.11（Windows） |
| 恢复节点 | 否，`pg_is_in_recovery() = false` |
| 只读模式 | 否 |
| schema | `public` |
| 升级前数据库大小 | 127,858,355 bytes |

### 迁移状态与静止性

- 升级前 `alembic_version` 精确为两个版本：`20260830_0023`、`20260901_0021`。
- Alembic 唯一 head：`20260902_0026`。
- 合并路径已核对：`20260830_0023 -> 20260831_0024`，随后 `20260831_0024 + 20260901_0021 -> 20260902_0025 -> 20260902_0026`。
- 无其他数据库会话、无未授予锁、无其他活跃事务。
- 公司资料精确一行，ID 为 1；升级前不存在 `singleton_key`。
- 公司资料原字段规范化 SHA-256：`3b819cb2fb4fdac89ba47d4ecb6d2235fe5e8498c5adfd0fb5aa83a08b1adc73`。
- `COMPANY_PROFILE` 审计记录数：0。

### 迁移文件冻结哈希

| 文件 | SHA-256 |
| --- | --- |
| `20260902_0025_merge_heads.py` | `738255CF6804D40C0C946FA942565F6DD49C4711F4BBF886071D2FA068D64525` |
| `20260902_0026_company_profile_singleton.py` | `1B9D1C20187F12C958B665A40741074C270E7A8984158F3D856D61306311CE9B` |

创建备份后、执行迁移前再次核对上述数据库身份、版本、会话/锁、公司资料和文件哈希，结果未变。

## 最终升级前备份

- 备份目录：`C:\Users\XL\dlx-yuki-wms-private-backups\phase_12_1d_b\20260902_120105`
- custom-format dump：`C:\Users\XL\dlx-yuki-wms-private-backups\phase_12_1d_b\20260902_120105\dlx_yuki_wms_preupgrade.dump`
- 文件大小：7,928,090 bytes
- SHA-256：`9E5381292D22373E0FA1E497077E676F88616396053C21B97F26B63AF81B0F0F`
- `pg_restore --list`：成功，清单 2,399 行
- 清单文件：`C:\Users\XL\dlx-yuki-wms-private-backups\phase_12_1d_b\20260902_120105\pg_restore_list.txt`
- 备份目录位于仓库外部。

第一次备份调用在连接数据库或运行 `pg_dump` 之前，因为从错误的 Python 工作目录加载应用配置失败而中止。该尝试没有产生数据库变更，留下空目录 `C:\Users\XL\dlx-yuki-wms-private-backups\phase_12_1d_b\20260902_120032`（0 个文件）。随后从正确的后端目录重新执行并完成上述有效备份。既有 12.1D-A 备份未被覆盖或删除。

## 实际迁移

在 `backend` 目录执行：

```text
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade 20260902_0026
```

结果：退出码 0。Alembic 日志确认按以下顺序执行：

```text
20260830_0023 -> 20260831_0024  staging load verification
20260831_0024 + 20260901_0021 -> 20260902_0025  merge heads
20260902_0025 -> 20260902_0026  company profile singleton
```

## 升级后验收

### 版本与结构

- `alembic current`：`20260902_0026 (head)`。
- `alembic heads`：唯一 `20260902_0026 (head)`。
- `alembic_version` 从两行收敛为预期的一行。
- public 表数从 39 增至 41，仅新增预期表：
  - `load_verification_transactions`：0 行
  - `stage_transactions`：0 行
- 升级后数据库大小：128,038,579 bytes。

### 行数完整性

除 Alembic 自身版本表的预期 `2 -> 1` 以及两个新表外，全部既有业务表行数保持不变：

| 表 | 升级前 | 升级后 |
| --- | ---: | ---: |
| `amazon_fc_addresses` | 0 | 0 |
| `audit_logs` | 1,921 | 1,921 |
| `bol_items` | 9 | 9 |
| `bols` | 5 | 5 |
| `carriers` | 0 | 0 |
| `company_profiles` | 1 | 1 |
| `container_trackings` | 1 | 1 |
| `customers` | 0 | 0 |
| `document_events` | 8 | 8 |
| `fba_inventory_allocations` | 93 | 93 |
| `fba_shipments` | 93 | 93 |
| `import_errors` | 99,324 | 99,324 |
| `import_jobs` | 11 | 11 |
| `import_rows` | 37,331 | 37,331 |
| `inbound_records` | 633 | 633 |
| `inventory_lot_locations` | 521 | 521 |
| `inventory_lots` | 626 | 626 |
| `inventory_priority_rules` | 4 | 4 |
| `inventory_transactions` | 738 | 738 |
| `loads` | 1 | 1 |
| `operational_documents` | 4 | 4 |
| `operational_exception_events` | 7 | 7 |
| `operational_exceptions` | 2 | 2 |
| `operational_notifications` | 1 | 1 |
| `outbound_inventory_allocations` | 12 | 12 |
| `outbound_orders` | 24 | 24 |
| `picking_list_items` | 4 | 4 |
| `picking_lists` | 15 | 15 |
| `scan_events` | 0 | 0 |
| `scan_sessions` | 0 | 0 |
| `user_customer_scopes` | 0 | 0 |
| `user_warehouse_scopes` | 0 | 0 |
| `users` | 1 | 1 |
| `warehouse_areas` | 1 | 1 |
| `warehouse_locations` | 282 | 282 |
| `warehouses` | 1 | 1 |
| `work_order_events` | 4 | 4 |
| `work_orders` | 1 | 1 |

### 公司资料单例与审计

- 公司资料仍精确一行，ID 仍为 1。
- 新字段 `singleton_key = 1`。
- 字段类型：`integer`；`NOT NULL`：是；默认值：`1`。
- `ck_company_profiles_singleton_key_is_one` CHECK 约束存在并要求值为 1。
- `uq_company_profiles_singleton_key` UNIQUE 约束及对应唯一索引存在。
- 排除新字段后，公司资料原字段规范化 SHA-256 仍为 `3b819cb2fb4fdac89ba47d4ecb6d2235fe5e8498c5adfd0fb5aa83a08b1adc73`，与升级前完全一致。
- `COMPANY_PROFILE` 审计记录数仍为 0，迁移没有制造业务审计事件。
- 升级后无其他数据库会话、无未授予锁。

## 只读冒烟测试

- 使用 FastAPI `TestClient` 在一次性 Python 验证进程内直接调用 ASGI 应用。它没有绑定网络端口、没有启动 Uvicorn，也不存在响应请求的外部服务进程。
- `GET /health`：HTTP 200，响应包含 `status: ok`、`service: DLX Yuki WMS V3`。
- 使用现有 ORM 服务在事务回滚/关闭保护下读取公司资料：成功，`id=1`、`singleton_key=1`。
- 认证 Company Profile GET：`SKIPPED_NO_SAFE_CREDENTIALS`。没有创建用户、令牌或密码，也没有把该安全跳过判为失败。
- `TestClient` 上下文关闭后，一次性 Python 进程正常退出；冒烟结束后的进程检查为相关进程 0，端口 8000/5173 监听数 0。因此该 HTTP 200 只证明应用对象可在进程内响应，不是服务已恢复上线的证据。

## 变更边界与禁止项确认

- 未编辑应用代码或 Alembic 迁移文件；升级前后迁移哈希一致。
- 未运行 `pytest` 或任何会写入真实数据库的测试。
- 未运行 `alembic stamp`、`alembic downgrade` 或手工 DDL/DML。
- 未修改、修复、清理或删除业务数据。
- 未执行数据库恢复；备份只用于验证可恢复性基础条件。
- 未 stage、commit 或 push。
- 未使用宽泛 `taskkill`；没有需要结束的进程。
- `git diff --check` 无空白错误，仅报告既有文件的 LF/CRLF 提示。

## 结论

PHASE 12.1D-B 的授权目标已完成。真实数据库当前精确位于 `20260902_0026` 唯一 head，数据与公司资料完整性检查通过，备份有效且位于仓库外部。数据库阶段结束时应用服务仍保持升级前的停止状态，运营可用性未恢复；这不影响数据库升级最终状态：**PASS**。
