# WPS AirScript 只读连接

目标：保留 WPS 人工录入库位，从本地拉取提柜、OL、DS、出库四张表的业务字段，先生成 JSON 预览。当前工具不连接 YUKI 数据库、不修改 WPS 记录，不代表已完成双向同步。

## 当前验证结果（2026-09-09）

- 最新完整分页：提柜 1,049 条、OL 8,965 条，均 `complete: true`，请求字段无缺失，源记录身份无重复。读取所有客户；完整标准化结果已替换核对页使用的 `inbound-normalized.json` 和 `ol-normalized.json`，旧样本保存为 `*-20-row-backup.json`。以下 20 条记录描述为早期验证历史。

- WPS「美西仓 - 4.0」内的「YUKI只读连接验证」已运行正式脚本：提柜 20 条、存在下一页、缺失字段为空。
- 已实测 GetSheets、GetRecords、PageSize 和 offset。WPS 代理对象通过 JSON 序列化转换后处理。
- 本地 8 项单元测试通过，覆盖分页、截断标识、重复记录、重复游标、字段变化、错表和接口结果格式。
- 用户已提供 webhook，已保存到本地 `.env.wps`。首次外部 POST 返回 HTTP 403 / `ApiTokenNotExists`；使用用户新复制的有效令牌更新本地配置后，外部调用成功，提柜与 OL 各读取 20 条记录、缺失字段为空，均存在下一页。预览文件为 `tmp/wps/inbound-preview.json` 和 `tmp/wps/ol-preview.json`，已校验 JSON、唯一记录 ID 与非空字段对象。尚未导入 YUKI、未修改源表、未配置定时同步。不要提交或分享令牌。
- 用户手动复制 webhook 后仍为空；原因尚未确定。已临时通过逐条运行日志读取提柜前三条完整样本，保存在 Git 忽略的 `tmp/wps/manual-sample.json`，校验 JSON、唯一记录 ID 和柜号。该文件标记 `complete: false`，来源为 UI 日志，不是 webhook 拉取，也未写入 YUKI。验证后已移除临时明细日志代码。

## 文件与运行

- `scripts/wps/airscript_readonly.js`：粘贴到 WPS AirScript 编辑器。
- `scripts/wps/pull_preview.py`：Python 标准库读取工具。
- `.env.wps`：设置 `WPS_AIRSCRIPT_WEBHOOK` 和 `WPS_AIRSCRIPT_TOKEN`。

在项目根目录运行：

```powershell
.\backend\.venv\Scripts\python.exe scripts/wps/pull_preview.py --sheet OL --max-pages 1 --page-size 20 --output tmp/wps/ol-preview.json
.\backend\.venv\Scripts\python.exe -m unittest discover -s scripts/wps -p test_*.py
```

默认只读一页；`complete: false` 表示部分数据，不能当作全量快照。扩大 `--max-pages` 可继续分页；每次命令从第一页开始。记录保留 WPS 原始 ID 和字段值，缺失字段通过 `missingFields` 返回。

读取范围是整张数据表，不是当前名为 YUKI 的筛选视图。用户已确认接入所有客户，不增加 DLX 客户筛选；分页期间 WPS 内容可能变化，当前读取不提供事务快照。

## 所有客户标准化预览

新增 `scripts/wps/normalize_preview.py`，支持 OL 和提柜，离线处理已拉取的 JSON。保留文档 ID、表 ID、记录 ID（旧预览缺失身份时提示重新拉取）、原始字段、所有客户和全部 FBA/PO 值；不推断 FBA/PO 配对。数字保存为十进制字符串，空值保持 null。客户匹配状态为 `not_checked`，不代表已经匹配 YUKI 客户。

```powershell
.\backend\.venv\Scripts\python.exe scripts/wps/normalize_preview.py --input tmp/wps/ol-preview.json --output tmp/wps/ol-normalized.json
.\backend\.venv\Scripts\python.exe scripts/wps/normalize_preview.py --input tmp/wps/inbound-preview.json --output tmp/wps/inbound-normalized.json
```

验证结果：15 项单元测试通过；重新拉取提柜、OL 各 20 条，均为部分分页。标准化后无日期解析错误或身份缺失；OL 有 4 条客户为空、6 条库位为空、1 条带板数后缀库位、13 条目的地需映射、16 条零重量需核实（问题可能重叠）。提柜样本未触发当前字段规则异常，不代表已通过数据库或业务对账。没有自动建立客户、库位或库存，也没有数据库写入、删除和回写。

## YUKI 核对页面

管理员进入「工具 → WPS 数据核对」（`/wps-review`），页面调用 `POST /api/v1/wps/review`，只读取上述两份标准化样本。部署时可用 `WPS_PREVIEW_DIR` 指定私有样本目录。页面不调用 WPS；「重新载入样本」读取最近一次脚本生成的文件。

支持所有客户的代码/名称匹配、逐行手动客户映射、选择目标仓库核对人工库位、查看原始字段和全部 FBA/PO。映射只保留在当前页面，不写入数据库。未知库位或带板数后缀的写法保留为待核对，不自动创建。

同柜件数汇总仅在两表完整、提柜记录唯一且件数齐全时判定一致或差异；部分分页、重复提柜、缺少同柜记录和缺失件数分别提示。完整分页核对有 1,084 个非空柜号：910 个件数一致、141 个缺少对应记录、32 个件数缺失、1 个提柜重复、0 个可判定差异。客户待匹配为 OL 81 条、提柜 22 条。新增问题及同柜状态筛选，已通过浏览器验证；本次前端生产构建通过。此功能没有与 YUKI 库存余额对账、导入、删除或回写。

验证：前端生产构建通过，后端核对服务及接口 11 项测试通过，拉取与标准化脚本 15 项测试通过。

## 后续接入

1. 已完成所有客户提柜和 OL 的完整分页拉取；处理客户匹配及待核查柜号，确定目标仓库后核对人工库位。
2. 对照现有 west_coast_4_0 导入映射，处理出库字段差异、客户映射及关联字段值。
3. 先做少量柜号的导入预览和数量对账，再接入幂等更新与冲突处理。尤其库位由人工维护，应明确 WPS 与 YUKI 哪一端拥有修改权。

当前采用本地主动调用 WPS，避免要求云端脚本访问本机 localhost。尚未配置定时任务、自动导入或回写。

官方参考：[令牌和 webhook](https://airsheet.wps.cn/docs/apitoken/intro.html)、[调用格式](https://airsheet.wps.cn/docs/apitoken/api.html)、[记录分页 API](https://airsheet.wps.cn/docs/api/dbsheet/Record.html)。
