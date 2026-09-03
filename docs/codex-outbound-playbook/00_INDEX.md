# EasyFreight 出库工作台 — 整套 Codex 流程

仓库：`C:\Users\XL\dlx-yuki-wms`  
远程：`XL3000-Bit/dlx-yuki-wms`  
对照源：EasyFreight `/admin/v2/outbounds`（只读观察，禁止写）  
API 前缀：`/api/v1`

本目录是给 **人 + Codex** 用的执行包。人负责开分支、贴 prompt、验收；Codex 负责读指定文件、改指定范围、写短 diff。

## 你怎么用

1. 先读 `01_STANDING_RULES.md`（每轮都有效，不贴也算约束）。
2. 按 `02_SESSION_RITUAL.md` 开一个 slice 分支。
3. 打开对应 `prompts/SLICE_N.md`，**全文复制**进 Codex。Slice 0 同时提供 `prompts/SLICE_0.md` 与 `prompts/SLICE_0_READ.md`（内容相同）。
4. Codex 完成后，用 `03_REVIEW_GATE.md` 人工过门。
5. 过门再开下一刀。没过门不准合并、不准开下一 slice。

## 文件

| 文件 | 给谁 |
| --- | --- |
| `01_STANDING_RULES.md` | 人 / 也可贴进 Codex 作为永久规则 |
| `02_SESSION_RITUAL.md` | 人：开 session、提交、回滚 |
| `03_REVIEW_GATE.md` | 人：每刀验收 |
| `04_STATUS_AND_API.md` | 人 + Codex：状态映射和接口清单 |
| `prompts/SLICE_0.md` | Codex：只读摸底（安全门别名） |
| `prompts/SLICE_0_READ.md` | 与 SLICE_0.md 相同 |
| `prompts/SLICE_1_SHELL_BATCH.md` | Codex：三区外壳 + readiness + batch |
| `prompts/SLICE_2_CREATE_ALLOCATE.md` | Codex：创建 OB + 挂/卸分配交互 |
| `prompts/SLICE_3_FILTERS_COLUMNS.md` | Codex：筛选/列对照 |
| `prompts/SLICE_4_EXPORT_LOAD.md` | Codex：导出、建 Load、批量拣货/BOL |
| `prompts/SLICE_5_DOC_CLOSE.md` | Codex：对照文档回写 + 收口 |

不要一次把 5 个 slice 全贴给 Codex。

## 总顺序（不许跳）

```
SLICE 0  只读摸底
   ↓ 产出：workbench_batch 真实字段、allowed_actions 形状、页面拆分笔记
SLICE 1  三区标题 + 发运预检 + /workbench/batch
   ↓ Review Gate
SLICE 2  创建后自动选中 + 分配/释放交互稳定
   ↓ Review Gate
SLICE 3  筛选/列：有字段才接，没有就写 MISSING
   ↓ Review Gate
SLICE 4  导出语义 + Create Load + 批量 picking/bol
   ↓ Review Gate
SLICE 5  更新 gap 文档，列出 INTENTIONAL_DIFFERENCE
```

PHASE 11.2 staging 表、11.3 改 readiness 规则、POD、Views、物理删除、Agent/Loading Team 主数据 **不在这套流程里**。
