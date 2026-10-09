# 派发证据机制上线准备与受控操作说明

唯一上线门禁和集中业务规则填写表：[交付门禁](DISPATCH_DELIVERY_GATE_2026-10-07.md)。交付一致性核对：[离线审计](evidence/dispatch-delivery-audit-20261007/README.md)。下述回归统计属于冻结候选的既有实际执行，本次交付审计不重复计为新跑通过。

最新实际记录：[候选版本完整回归](evidence/dispatch-candidate-final-20261007-1548/README.md)。冻结候选回归的完整后端 421 通过 / 1 个 SQLite 行锁用例跳过（对应独占 PostgreSQL 另验）、只读预检 21、前端 55、PostgreSQL 47 场景、正式页面 E2E 3 测试 / 16 场景通过；全项目前端严格类型检查剩余 0 错误，构建通过。FBA、私仓均验证合法计划新版本使旧审批失效、刷新重登保持阻断、重取全部证据后派发。自动化文件输入不等于原生选择；原生选择未验证，既有 Chrome 工具未重试，原因未知。机制验收未结束，下列业务填写表保持待确认、未启用。

更新日期：2026-10-07。当前工作树包含此前运行代码修复及本次交付文档整理；尚未部署、推送或操作生产数据库。历史验收结果见 [证据验收记录](DISPATCH_EVIDENCE_ACCEPTANCE_2026-10-05.md) 中“本次验收收尾”。

**冻结候选源码的完整回归及严格类型检查通过；原生文件选择仍有缺口，生产可用性未获批准。** 冻结实际结果见 [候选回归记录](evidence/dispatch-candidate-final-20261007-1548/README.md)，本次交付离线审计不重跑、不计作新回归通过。FBA、私仓均须有各自获准的规则。模板中的 null 是待确认字段，不能作为可发布策略。普通业务页面没有规则发布入口，ADMIN 也不能绕过业务条件。工具校验结构、出处完整性、权限和版本，无法证明填写的批准文号真实；发布操作者必须核对真实批准材料，不能把建议或测试记录填作生产批准。

## 交付配置与秘密注入

交付清单隔离 backend/alembic.ini 与 backend/.env.example 的原始连接凭据，映射至 [脱敏配置目录](evidence/dispatch-delivery-audit-20261007/sanitized-config)。副本不生效，原件与 HEAD 一致并保持原状；凭据有效性未知。不要直接打包整个仓库或将 source_files 当交付清单，按 delivery_files 和 delivery_replacements 装配。由环境负责人经批准的安全通道注入 DATABASE_URL、JWT_SECRET_KEY，核对环境读取和目标身份；不将真实值写入发布包、命令参数或日志，不附带本地 .env。本次没有执行秘密注入、轮换或认证配置修改。

## 配置草稿与规则出处

入口：`scripts/dispatch_policy.py`；模板：[FBA.template.json](dispatch-policy/FBA.template.json)、[PRIVATE.template.json](dispatch-policy/PRIVATE.template.json)。每个仓库、业务类型独立版本，禁止共用一张混合业务派车单。

在仓库根目录运行下列离线命令；不需要数据库地址，也不会读取/写入策略：

```powershell
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py template --business FBA
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py template --business PRIVATE
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py validate --file docs/dispatch-policy/FBA.template.json
```

原始模板校验应退出 2 并列出待填字段；这是阻断成功，不是上线故障。复制模板为受控草稿，保留审批材料并填写所有字段：

- `warehouse_id` 使用核实过的真实仓库，`business_type` 只能 FBA / PRIVATE；`expected_version` 为该仓库该业务当前最新版本，无策略时为 0。它们由操作者核实，不需业务额外决定。
- `provenance.purpose` 生产必须为 PRODUCTION；`confirmation_reference` 是真实批准记录；`rule_sources` 必须分别提供 documents、document_review、approval、exception_review、independent_approver、allow_canceled_exceptions 六组出处。不得填 TEST ONLY / TEST_ONLY 引用。
- `documents` 明确类型、ORDER / LOAD 粒度、是否接受生成单据及 BOL 状态。生成证据仅支持 ORDER BOL；接受时必须列状态，禁止生成时 `bol_statuses` 必须显式为空。现有状态码：0 DRAFT、1 GENERATED、2 PRINTED、3 COMPLETED、4 CANCELED。这是代码枚举，并非允许生产接受这些状态。
- 三类审查分别填写非空、唯一、有效的角色列表和有效秒数。技术边界为 1–31536000 秒，不构成业务推荐值。单据类型与粒度不可重复，未知字段、未知角色/状态、缺失项均不能发布。
- `independent_approver` 与 `allow_canceled_exceptions` 必须明确决定，不补默认值。

字段与技术验证依据：`backend/app/schemas/dispatch_evidence.py`、`backend/app/services/dispatch_policy_config.py`。业务文档与现有 BOL/上传功能只证明有这些能力，未证明必需单据清单或有效期获准；FINAL 是计划锁定，费用审批不是派发审批。测试 fixture 只证明机制，不作为生产规则出处。

## 上线前备份、迁移与验证

以下为待执行的生产操作说明。已有演练只在独占隔离资源执行；本次交付审计没有创建服务或数据库，不能自动执行生产操作。

1. 选定经过评审的代码版本，记录工作树/构建产物摘要、当前 Alembic revision、表计数、仓库/客户权限及 UNKNOWN/重复单据基线。安排受控维护窗口，停止新增业务写入；由环境负责人执行，禁止本工具自行重启现有服务。
2. 从批准的运行环境读取数据库连接和认证配置，仅置于操作者进程环境；不修改项目凭据文件，不把连接串放命令行、文档或日志。核对目标实例/数据库身份，确认备份范围。
3. 使用 `pg_dump` custom format 备份数据库，同时备份 `DOCUMENT_STORAGE_ROOT` 文件库，保存 SHA256 清单、时间和对应 revision。备份保存在受控位置。在独立恢复库执行 `pg_restore`，核对表计数、revision、文档记录与文件摘要后再迁移。数据库与文件库必须是同一维护窗口的一致备份。
4. 后端目录使用 `.venv/Scripts/python.exe -m alembic current` 核对 revision，再执行 `.venv/Scripts/python.exe -m alembic upgrade head`。本阶段 head 是 `20261005_0039`，依次经过 `20260925_0037`、`20261005_0038`、`20261005_0039`。若现有数据库版本/结构不同，先在它的隔离副本演练，不直接套用。
5. 核对原记录、库存和身份计数；业务未知的历史记录继续 UNKNOWN / NULL 并阻断，历史同版本重复单据保留，不自动清洗、不猜测回填、不伪造审批。检查数据库约束、追加式审查保护及仓库/客户权限。
6. 在尚未发布策略时核对预检 UNKNOWN 与派发阻断；确认测试模块未加载、没有 TEST_ONLY 策略授权。核对上传存储路径/权限、文件完整性、前后端版本与认证。只读检查不授予派发权限。生产业务写入验收需另经批准。

冻结候选的 PostgreSQL 47 场景已实际覆盖全新迁移、0036 代表性数据升级至 0037/0038/0039、0039 DDL 注入失败后的事务回滚及重试、升级前数据库备份与独立恢复。原身份、UNKNOWN 和重复单据保留，没有生成策略或审查。详见冻结候选的 PostgreSQL 日志；本次交付审计只核对这些证据，未重跑。

文件恢复与受控规则发布属于此前隔离演练，详见 [历史演练记录](evidence/dispatch-release-20261007/release-rehearsal.json)，不计为冻结候选回归或本次交付审计新跑通过。历史记录包含两个独立恢复库的 49 张表逐行摘要、配对文件 SHA256 与 storage_key/大小/checksum，以及真实账号拒绝、只读差异、发布失败回滚、旧版本拒绝、撤销和新版本恢复等 16 项检查。文件数量以该记录为准。未使用生产副本。工具 `scripts/rehearse_dispatch_release_isolated.py` 只接受所有权标记、测试角色、临时数据目录均匹配的独占资源。

## 发布、撤销及审计

数据库命令先通过数据库中真实、有效的账号和密码认证，再校验 ADMIN 权限及对应仓库范围；审计身份由已认证账号生成，不再接受 `--actor-id`。使用 `--username` 后在终端隐藏输入密码，或由受控秘密输入通道提供 `--password-stdin`；密码不能放命令参数、配置草稿或日志。工具及数据库访问权限只交给授权发布人员，不暴露为普通页面或公共接口。账号认证仍不能替代真实业务规则批准。

完整草稿校验后，先预览（例中的 confirmed.json 与账号是占位，需替换为核实过的内容）：

```powershell
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py validate --file confirmed.json
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py dry-run --file confirmed.json --username approved_operator
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py publish --file confirmed.json --username approved_operator
```

dry-run 不写库，返回当前/拟发布版本、启用状态、六组规则前后差异和出处；缺项或权限不足立即阻断。人工最后批准具体差异和出处后才能执行生产 publish。本次未执行生产 publish。发布在事务中使用版本比较和锁；旧版本不匹配返回 409，先重新预览、重新批准，不自动重试覆盖。成功写不可变的新策略版本及 PUBLISH 审计，所有旧版本审查失效，业务必须重新审查和审批。

撤销：复制当前获准草稿，填写当前 `expected_version`，将 `confirmation_reference` 更新为真实撤销批准，保留完整规则与出处，再执行：

```powershell
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py dry-run --file revoke-confirmed.json --username approved_operator
backend/.venv/Scripts/python.exe scripts/dispatch_policy.py revoke --file revoke-confirmed.json --username approved_operator
```

撤销追加 enabled=false 的新版本及 REVOKE 审计，保留旧策略/审查/执行历史，并阻断之后的派发。撤销不会撤回已经发生的派发。重新启用必须另建获准版本、预览、发布和重新审查；禁止直接修改历史行。核对 AuditLog 的操作者、前后版本、规则差异、出处及实体 ID，并保存受控操作日志。

TEST_ONLY 只供明确标记的独占验收：环境标记、测试数据库角色、临时 data_directory 前缀及所有权文件必须同时匹配。单独设置环境变量不足以启用；生产环境下即使连接独占测试库也实际拒绝 TEST_ONLY。应用入口不导入测试 seed。不要在生产启动流程添加验收脚本，不得把测试出处改名伪装为批准。

## 故障恢复

- **迁移失败：**停止继续上线并保存受控错误日志和 revision。0039 的 PostgreSQL 事务失败回滚已演练；先核对 schema/data，定位失败原因后在隔离副本重试。0037/0038 若此前已提交则仍保留，不假定整条迁移链自动回退。不要自动 downgrade 或删除旧记录。
- **需要恢复备份：**在新的隔离恢复库和文件目录先恢复数据库及配对文件库，核对 revision、计数和摘要；选用与该 revision 兼容的代码。生产切换需维护窗口及明确授权，不能覆盖运行中的生产库或仅恢复一半。
- **发布失败：**事务回滚，不留下半条策略或审计；实际注入失败已验证。重新读取最新版本、做 dry-run，再重新批准。不要更改 expected_version 后盲重试。已成功但规则需要停用时使用撤销追加版本，而不是删记录。
- **上传失败：**冻结候选正式页面与实际响应共同确认空文件 422、TEST_ONLY 超限 413、归属冲突 409、隔离存储故障 500；取消/重开弹窗清除旧文件与错误，换文件清除旧错误。文件格式限制沿用当前实现，未自行新增业务规则；历史接口格式断言不计作冻结候选页面验收。自动化文件输入已验证，原生选择仍未验证。不得手工造文档记录来消除缺件阻断。

## 仅需业务集中确认的填写表

请只填写 [交付门禁中的唯一决策表](DISPATCH_DELIVERY_GATE_2026-10-07.md)。FBA、私仓分别确认，建议保持待确认、未启用；仓库 ID、版本号、备份目录及端口由操作者核实，不是业务决策。

计划、证据、来源、权限或策略变化使旧审批失效是机制约束，不是待选的宽松选项。生产上线仍需上述批准、受控备份迁移、真实环境验证及最终发布授权。

## 2026-10-07 可重复正式页面回归及上线门槛

[冻结候选运行说明与证据](evidence/dispatch-candidate-final-20261007-1548/README.md)。Windows 前置：项目后端虚拟环境及依赖、前端 npm 依赖、Playwright Chromium、可用的 PostgreSQL 17 二进制；脚本确认临时目录所有权与测试数据库身份，创建独占数据库/文件目录及随机本地端口。首次安装 Chromium 可运行 `npx playwright install chromium`（只用于 Playwright 独占实例，不改用户 Chrome）。

在 `frontend` 目录运行 `npm run test:e2e:dispatch`。默认创建新的时间戳证据目录；可用 `-- --output <新目录>` 或 `-- --grep <测试标题>` 选择证据目录/范围。生成逐项页面及网络结果、截图、浏览器/服务日志、代码 HEAD 与工作区变化摘要；输出只含脱敏信息。正常或失败都停止本次 browser/API/Web/PG，保留日志；清理结果看 run.json，若非 PASS 先检查所有权标记与残留端口，不重启既有服务。

冻结轮自动化正式页面成功不得代替原生文件选择。Chrome L 的 setFiles 历史错误不能证明权限未开；扩展版本/实际权限/用户设置实例仍未知，没有新证据时不重复诊断或请求相同信息。保留原生选择（包括原生取消）未验证，机制验收保持未完成。

冻结轮未增加迁移或事务约束，head 0039。全项目前端严格检查及完整后端等最终回归对应同一冻结候选实际通过，详细通过/跳过数见冻结证据。Windows 的 npm 入口通过 scripts/run_dispatch_ui.mjs 调用后端虚拟环境 Python，参数和退出码转发，继续复用独占资源管理工具；不读取或改动用户 Chrome 配置。本次只做离线交付核对与文档整理，没有重跑完整回归。上线前仍须完成 G0 安全配置、补齐原生选择证据、集中批准上述业务规则，再按受控备份/迁移/核验/发布与故障恢复流程执行。冻结轮已验证数据库备份恢复及 0037–0039 升级回滚；文件恢复与发布演练沿用明确标为历史的记录，不计冻结轮或本次通过。部署与生产切换仍需明确授权，所有测试策略不得发布生产。

### 历史权限开启报告后的实测边界（1055）


[1055 历史实测](evidence/dispatch-ui-20261007/continuation-1055/README.md)：用户报告已开启权限后，一次真实文件选择仍返回工具拒绝 `fileChooser.setFiles failed` 及 Allow access to file URLs 提示。工具错误不证明设置未开启；根因未确定，按用户要求停止重复续验。没有用接口替代上传或改变生产规则，此前通过的 11 项未重跑。后续正式页面自动化已覆盖上传后的完整链路；该历史阻塞仍仅适用于原生文件选择与既有 Chrome 工具，不替代后续页面证据。临时服务已停止，日志保留；本次不重复权限诊断。
