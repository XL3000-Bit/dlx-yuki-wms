# 派发候选交付与唯一上线门禁

更新：2026-10-07。本文件是当前候选的唯一上线门禁和业务填写表；历史验收记录保留，不另构成批准。操作步骤见 [上线准备说明](DISPATCH_RELEASE_PREPARATION_2026-10-05.md)。未执行生产备份、迁移、策略发布或部署，机制验收未结束，当前候选不能称为生产可用。

## 候选与证据

HEAD：`413b6dfd3f08089fe8dd87d2beb1cc232ea40fb9`。冻结运行源码 470 文件，集合 SHA256：`f026e632f0b36dbf8b13994678b171e97385222a6cc1c26582309f2f85262513`。HEAD 本身不包含全部未提交成果，交付必须使用逐文件清单，不能仅导出 HEAD。

[冻结候选](evidence/dispatch-candidate-final-20261007-1548/candidate.json)记录源码、工作树与摘要；[冻结回归](evidence/dispatch-candidate-final-20261007-1548/verification.json)记录实际测试；[本轮离线审计](evidence/dispatch-delivery-audit-20261007/results.json)与[交付清单](evidence/dispatch-delivery-audit-20261007/manifest.json)核对一致性。文档整理不改变运行源码冻结摘要。清单列出文档和原始日志/截图的摘要，生成的清单和结果文件不自我哈希。

冻结结果：后端 421 通过、0 失败、1 跳过；只读预检 21；前端 55；严格类型检查 0 错误；E2E 类型检查与构建通过；隔离 PostgreSQL 47 场景；正式页面 E2E 3 测试、16 场景、29 张截图。后端 11 条配置弃用警告及构建包体警告保留。以上是冻结轮实际运行，本次仅核对，不计为本轮重跑。

后端跳过 `test_concurrent_partial_cannot_overdraw` 因 SQLite 缺少真实行锁。同一测试函数由 `scripts/verify_dispatch_isolated.py` 在隔离 PostgreSQL 执行，日志中的 `partial completion concurrent quantities and duplicate rollback` 为 PASS；验证竞争数量、事务回滚与重复请求。SQLite 的跳过仍保留，不合并为 422 个后端通过。

FBA/私仓计划 v2 内容变化使旧单据、审批、异常复核及装车证据失效，派发 409，刷新重登保持阻断，取得所有有效证据后派发 200及下游详情均有页面与网络记录。上传与拒绝补正等自动化页面成功仅证明 TEST_ONLY 机制。实际附件为 JSON、日志和 PNG，没有 HAR/trace。

## 交付范围

| 类别 | 应交付 | 不交付 / 保留本地 |
| --- | --- | --- |
| 运行源码 | manifest 的 delivery_files 中选定的 backend、frontend、scripts；包括未跟踪的新文件，不能只复制 git diff | .env、认证文件、本地数据库、文件存储、备份、临时目录及下述两份原始配置 |
| 配置 | 清单映射的脱敏 alembic.ini、.env.example，仅为不生效的交付模板；由获准环境安全注入连接与认证秘密 | backend/alembic.ini、backend/.env.example 原文件含连接凭据，保持原状但不随包交付；凭据有效性未知 |
| 数据库 | 完整 Alembic 链，特别是 20260925_0037、20261005_0038、20261005_0039；head 0039 | 不执行历史业务回填、清洗或迁移生产数据 |
| 依赖与 Windows 入口 | backend/requirements.txt；frontend/package.json、package-lock.json；scripts/run_dispatch_ui.mjs；测试/构建配置 | .venv、node_modules、dist、缓存和机器专属运行产物 |
| 受控规则 | scripts/dispatch_policy.py；FBA/PRIVATE 独立未确认模板；模型、服务、权限及隔离守卫 | 不含可启用生产策略；测试 seed 只能由独占隔离脚本调用 |
| 验证工具 | verify_dispatch_isolated.py、verify_dispatch_upgrade.py、rehearse_dispatch_release_isolated.py、start_dispatch_browser_isolated.py、verify_dispatch_browser_evidence.py、verify_dispatch_ui.py、正式页面 E2E 与 Node 入口 | 不把验收工具加入生产启动过程 |
| 交付证据 | 本文件、上线说明、验收记录、模板、冻结证据全部文件、本轮审计报告；历史演练摘要单列来源 | 根目录零散临时日志/截图、恢复补丁、状态快照及无关文件，不自动删除 |

manifest 的 source_files 保留冻结 470 文件的原始校验来源；delivery_files 是待交付逐文件 SHA256 清单，其中两份原始配置由 delivery_replacements 映射至不生效的脱敏副本，两者摘要不能混称。local_workspace_not_selected 列出未选入交付的本地文件路径。发布打包需严格依清单，并将运行代码、受限证据附件、测试工具分别存放；不要把整个工作目录压缩为发布包。清单可包含合成测试身份及已停止的隔离端口记录，它们不是生产凭据或生产配置。离线扫描只输出风险位置；不能据此保证所有潜在秘密不存在，项目 .env 未读取也未选入。两份原始配置与 HEAD 一致，本轮没有改动；未验证凭据有效性，也未注入运行环境秘密。

Windows 重现前置依赖：项目虚拟环境与固定后端依赖、锁定的前端依赖、Playwright Chromium、PostgreSQL 17 二进制。正式页面入口为 frontend 下 `npm run test:e2e:dispatch -- --output <新证据目录>`；脚本使用独占资源、随机端口，并在成功/失败后停止本次资源。环境不齐时先修复独占测试环境，不能借用运行中的生产服务。

## 唯一门禁清单

| 门禁 | 当前状态与通过标准 | 失败处理 |
| --- | --- | --- |
| G0 交付配置与秘密注入 | 原始两份配置已从交付清单隔离并映射脱敏模板；运行环境注入尚未执行。包内无原始凭据，环境负责人经批准的安全通道配置 DATABASE_URL、JWT_SECRET_KEY 后核对生效才通过 | 停止打包/上线，修正清单或安全注入；不自动改动活动凭据、轮换秘密或把值写入包和日志 |
| G1 候选和工程验证 | 冻结轮上述测试通过；本轮源文件摘要、迁移链、依赖、入口及证据全部一致才可保留结论 | 摘要或证据不一致则停止发布，定位变化，仅重跑受影响范围并重新冻结；不引用旧结果覆盖新失败 |
| G2 原生文件选择 | 未验证；需正式页面由真实原生选择完成上传和取消，并保留结果 | 没有新可核实信息，不重试 Chrome L 或重复诊断。保留未验证，不能以自动化 setInputFiles 替代；不得标记全部机制验收结束 |
| G3 FBA / 私仓业务规则获准 | 未确认、未启用；分别填完下表，真实负责人批准及六组出处可核对，草稿校验通过 | 缺项、无出处、UNKNOWN 或测试建议继续阻断；不补宽松默认值、不伪造批准 |
| G4 生产备份和恢复可用 | 尚未执行；明确生产目标/维护窗口，配对数据库与文件备份，独立恢复核对 revision、行计数及 SHA256 | 停止迁移；修复备份一致性并恢复验证。生产恢复/切换需授权，不能覆盖运行库或只恢复一半 |
| G5 生产迁移和环境验证 | 尚未执行；授权后核对 revision 到 0039、原记录保留、UNKNOWN/重复历史阻断、权限和存储、前后端版本一致、生产拒绝 TEST_ONLY | 记录失败/revision，核对事务回滚；0037/0038 已提交部分不得假定回退。先在副本修复，不自动 downgrade、清洗或回填 |
| G6 生产策略发布 | 尚未执行；真实有效账号、ADMIN 与仓库范围，已批准 PRODUCTION 草稿及 dry-run 差异，版本匹配，单独获得发布授权，审计完整 | 无权限/缺项/409 停止；发布失败确认事务回滚，重新预览并批准。不可盲重试或用 actor-id 代替权限 |
| G7 发布后核验、撤销与恢复 | 尚未执行；获准的实际环境核验，保留审计；撤销追加禁用版本，恢复须新获准版本及重取证据 | 出现问题先受控撤销，保留历史；已发生派发不能靠撤销撤回。数据恢复及服务切换另需授权 |

G0 的安全配置、G1 的隔离测试通过、G3 的业务批准、G4–G7 的生产操作互不替代。ADMIN、FINAL、只读预检 PASS 都不授予绕过业务规则的权限。生产入口不能意外导入测试 seed；TEST_ONLY 必须同时满足隔离环境、数据库角色、临时路径与所有权守卫，生产环境继续拒绝。

历史文件恢复和策略发布演练见 [2026-10-07 release-rehearsal.json](evidence/dispatch-release-20261007/release-rehearsal.json)，并未在冻结轮或本轮重跑，不算新增通过。冻结轮确有数据库备份恢复、0037–0039 代表性升级及失败回滚验证；本轮不宣称再次演练。

## 集中确认的最小业务规则表

每项分别填写两类业务，所有建议均待确认、未启用。仓库 ID、版本、端口、文件目录等由技术操作者核实，不列为业务决策。

| 需业务决定的字段 | 已有依据 | FBA 待填值 | 私仓待填值 | 建议选项及影响（均未确认） |
| --- | --- | --- | --- | --- |
| 必需单据类型、ORDER/LOAD 粒度；是否接受生成 BOL 及允许状态 | 既有上传/BOL 能力；生成证据仅 ORDER BOL；状态 0–4 是技术枚举，不是接受批准 | 类型清单、粒度、接受生成与状态 | 类型清单、粒度、接受生成与状态 | 由业务列明必需清单；每增加一种会增加缺件阻断。若接受生成 BOL 须显式选状态，不默认接受 DRAFT/CANCELED；不支持的生成类型保持阻断 |
| document_review.roles / valid_seconds | 已有权限与追加审查；没有获准的岗位、时限 | 岗位与有效秒数 | 岗位与有效秒数 | 从现有角色确定责任岗位；较短有效期提高重审频率。技术范围 1–31536000 秒不作推荐默认值 |
| approval.roles / valid_seconds / independent_approver | FINAL 只代表锁定；派发审批与计划版本及内容绑定 | 岗位、有效秒数、是否独立 | 岗位、有效秒数、是否独立 | 建议独立于创建/锁定人；增加独立审批人员需求。同人审批只可在明确批准后接受 |
| exception_review.roles / valid_seconds / allow_canceled_exceptions | 活动异常继续阻断；有 RESOLVED/CANCELED 状态与历史，接受条件未获准 | 岗位、有效秒数、是否接受 CANCELED | 岗位、有效秒数、是否接受 CANCELED | 建议仅证据完整 RESOLVED 可复核；CANCELED 的接受必须单独批准。时限较短增加重核频率 |
| provenance.confirmation_reference 及六组 rule_sources | 结构校验不能证明批准材料真实；测试 fixture 不构成出处 | 真实批准记录及逐组出处 | 真实批准记录及逐组出处 | documents、document_review、approval、exception_review、independent_approver、allow_canceled_exceptions 各有可核实依据；缺任何项保持禁用 |

内容/版本/证据/策略变化导致旧审批失效、活动异常阻断、仓库客户权限、业务隔离及数量约束是既有机制约束，不能通过此表改成可绕过选项。
