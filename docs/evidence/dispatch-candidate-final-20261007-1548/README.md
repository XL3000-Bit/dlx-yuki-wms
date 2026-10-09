# 派发候选版本最终回归：2026-10-07

本轮候选源码冻结于 2026-10-07 15:49:43 PDT，全部最终结果对应同一源码状态。HEAD 为 `413b6dfd3f08089fe8dd87d2beb1cc232ea40fb9`，470 个源码文件的集合摘要为 `f026e632f0b36dbf8b13994678b171e97385222a6cc1c26582309f2f85262513`。[candidate.json](candidate.json) 保存逐文件摘要及全部未提交修改摘要；最终文档补充不改变候选源码。全部原有成果保留，没有提交、推送、部署或生产操作。

## 本轮修复

- 修复全项目前端严格检查的调用、表格列、接口、选择状态和离线队列数据契约；移除既有 noCheck 和 ts-nocheck，严格检查涵盖 src、E2E 及根目录 TypeScript。没有用 any、忽略错误、空实现或排除目录消除错误。
- 修复 FBA 分配页面把预留记录 ID 当作库存批次 ID 的错误，保留库存批次与预留归属，新增两项转换回归。
- 复用计划写入接口，补齐草稿数量编辑、保存、版本/修订显示和下一版草稿入口。FINAL 内容不可直接修改；新版本仍受数量、归属和派发证据约束。
- 修复 Windows 下 npm E2E 相对可执行路径无法运行的问题，改用跨平台 Node 启动入口，转发参数和退出码，继续复用独占资源管理脚本。
- 正式页面 E2E 增加 FBA、私仓计划内容变化、数量阻断、旧审批失效、刷新重登及恢复派发场景。没有增加测试业务页面、绕过入口、生产策略或迁移。

## 本轮实际最终结果

| 项目 | 通过 | 失败 | 跳过 / 未验证 | 原始证据 |
| --- | --- | --- | --- | --- |
| 完整后端 | 421 | 0 | 1：SQLite 无真实 PostgreSQL 行锁；对应竞争另经 PostgreSQL 验证 | final-backend.log、final-backend-junit.xml |
| 独立只读预检 | 21 | 0 | 0 | final-readonly.log |
| 完整前端测试 | 55 | 0 | 0 | final-frontend-test.log |
| 全项目前端严格类型检查 | 通过，剩余错误 0 | 0 | 0 | final-frontend-typecheck.log |
| E2E 独立类型检查 / 前端构建 | 均通过 | 0 | 0 | final-frontend-typecheck-e2e-dispatch.log、final-frontend-build.log |
| 独占 PostgreSQL | 47 场景及新建/代表性升级验证通过 | 0 | 0 | final-postgres.log |
| npm run test:e2e:dispatch | 3 个测试、16 项页面场景 | 0 | 0 | browser-run.log、browser/results.json、browser/playwright-results.json |
| 操作系统原生文件选择 | — | — | 未验证 | 不将自动化 setInputFiles 冒充原生选择 |
| 既有 Chrome L 工具上传 | — | — | 历史阻塞未重试，原因未知 | 没有新证据，未重新诊断或修改权限 |

后端保留 11 条配置弃用警告，构建保留包体大小警告；均非失败。历史发布/文件恢复演练未因本轮无相关变更重跑，不计入本轮通过。[verification.json](verification.json) 为机器可读测试结果，[results.json](results.json) 汇总状态和边界。

执行入口：后端虚拟环境运行完整 pytest 并指定本次独占 basetemp；独立只读预检运行后端只读预检测试模块；前端运行 npm test、npm run typecheck、npm run typecheck:e2e:dispatch、npm run build；仓库根目录运行后端 Python 的 scripts/verify_dispatch_isolated.py。正式页面入口为 frontend 下 `npm run test:e2e:dispatch -- --output <新证据目录>`，默认自动管理独占 PostgreSQL、API、Web、文件库和 Chromium，成功或失败均停止本次资源。

## 计划内容变化的实际页面证据

两类业务均通过正式页面完成：库存分配 → FINAL v1 → 暂存/装车 → 上传/审查/审批；确认 FINAL 数量输入禁用后创建合法 v2 草稿。将 4 托改为 3 托保存，锁定返回 409 `PARTIAL_OR_UNATTRIBUTED_PLAN_UNSUPPORTED`，页面显示原因；恢复 4 托后锁定成功，显示 FINAL v2、修订 5。

此时实际派发返回 409：单据/审批/异常复核 `EVIDENCE_STALE`，装车核验 `LOADING_VERIFICATION_STALE_OR_UNATTRIBUTED`。刷新及退出重新登录后仍显示版本与阻断。通过现有页面重新装车核验、单据审查、异常复核和计划审批后派发成功并打开下游详情。仅重新审批不够，所有已失效的证据都须重新取得。

逐项页面观察与实际响应分别保存在 [browser/results.json](browser/results.json) 和 [browser/page-results.json](browser/page-results.json)，必要截图保存在 browser 的附件目录；本次目录未保存 HAR 或 trace，不能将其列为已有证据。拒绝记录、旧审批及 v2 新审批仍在页面历史中；没有删除或替换历史。

交付核对见 [离线审计](../dispatch-delivery-audit-20261007/README.md)；唯一上线门禁及业务规则填写表见 [交付门禁](../../DISPATCH_DELIVERY_GATE_2026-10-07.md)。原回归结果保持历史执行时间，不计作交付审计新跑的测试。

关键截图：[FBA v2 重登后](browser/FBA-plan-v2-stale-relogin.png)、[私仓 v2 重登后](browser/PRIVATE-plan-v2-stale-relogin.png)。browser 目录保存 29 张 PNG，包含内容变化阻断、恢复派发和下游详情。正式浏览器使用 Chromium 153.0.8010.12，3 个测试无重试、无跳过、无 flaky。

上传成功、取消自动化输入、空文件 422、TEST_ONLY 大小超限 413、独占存储故障 500、归属冲突 409、权限撤销后 403、重复暂存/提交、未配置规则和证据过期阻断均由页面及响应共同验证。没有新增未经确认的文件格式规则。

## 失败修复与清理

初次后端运行遇到共享 pytest 临时目录 WinError 5，保留 backend.log；改用独占临时目录后全套通过。初次 npm 入口报相对路径无法识别，保留 npm-entry-failure-browser-run.log；修复启动入口后实际 npm 全套通过。一次日志重定向的验证命令拼接错误保存在 verification-command-failure.log，纠正命令后所有最终前端检查通过。初次失败均没有从证据中删除，也没有计入最终通过。

[browser/run.json](browser/run.json) 保存 22:49:44–22:51:17 UTC 的执行时间、策略标识、工作区摘要及 cleanup=PASS，残留监听为空。独占 PG/API/Web 端口分别为 50655/50656/50657，浏览器工作目录为 `C:\Users\XL\AppData\Local\Temp\yuki-dispatch-browser-06rarr_v`；独占 PostgreSQL 场景目录为 `C:\Users\XL\AppData\Local\Temp\yuki-dispatch-pg-8kf4pnbd`，均已停止且保留日志。[final-audit.json](final-audit.json) 记录最后的源码一致性与端口检查。

所有成功仅证明隔离 TEST_ONLY 机制。`mechanism_acceptance_complete=false`、`production_ready=false`。原生文件选择仍未验证，生产业务规则仍未确认/启用。[上线操作与最小业务填写表](../../DISPATCH_RELEASE_PREPARATION_2026-10-05.md) 保留两类业务独立的必需单据、岗位/有效期、独立审批、异常接受条件及真实批准出处；建议不能作生产授权。
