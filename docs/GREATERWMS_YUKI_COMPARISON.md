# GreaterWMS 对 YUKI 的借鉴分析

研究日期：2026-09-09。用户未提供具体版本，本次按官方 [GreaterWMS/GreaterWMS](https://github.com/GreaterWMS/GreaterWMS) 研究，业务代码固定为 V2.1.49。检查了公开源码、页面结构及发布说明，并与当前 YUKI 代码比较；没有部署 GreaterWMS，也没有验证其实际设备兼容性。本文件中的建议尚未实现。

## 结论

值得借鉴的是现场作业组织、库位库存和正式盘点。YUKI 的海运转运、柜次、多目的地、FBA、Cargo BOL 与预约装车流程仍应围绕自身业务完善。无需更换现有 React/FastAPI 技术栈，也无需重复开发已有 PDA、扫码拣货及库存流水。

| 优先级 | GreaterWMS 已核实内容 | YUKI 当前情况 | 建议 |
| --- | --- | --- | --- |
| 1 | 日常和手工盘点分别记录账面数量、实盘数量、差异、状态和操作人 | PDA 已有按库位、LOT 盘点入口，按“可用库存”计算差额并直接调整 | 建立可追溯的盘点任务，明确实物、分配、冻结数量口径 |
| 2 | 出库按新单、缺货、待拣、已拣、拣货单、已发货、POD 等阶段组织入口 | 已有调度工作台、就绪检查和 PDA 作业入口 | 在现有状态之上形成按角色组织的待办队列，突出阻塞原因和下一步 |
| 3 | 库位模型有尺寸、属性、空位标记；库位库存关联货品与数量 | 已有仓库、区域、库位、批次库位数量；库位主数据以编码、名称、启用状态为主 | 增加库位类型、容量与占用视图，提供合适的上架选择 |
| 4 | 移动拣货列表展示库位、待拣数、输入实拣数，支持按货品或出库单扫码筛选 | 已有扫码、数量确认和离线队列相关代码 | 精简任务卡、强化扫描反馈，并做真实设备和弱网验收 |
| 5 | 区分在库、可订、已订、冻结、损坏、待拣、已拣等库存量 | 已有分配量、冻结量和库存交易流水 | 汇总为统一库存状态视图，减少跨页核对 |

## 首先补齐正式盘点

当前 `frontend/src/pages/PdaOperations.tsx` 的盘点面板读取 `available_pallet_qty` 和 `available_carton_qty`，显示“账面可用”，再将输入值减去可用量，以 `COUNT_CORRECTION` 提交库存调整。这是可用数量校正流程。若现场人员实际数的是库位内全部货物，需要明确已分配和冻结货物是否包含在实盘内，不能直接混用口径。

建议流程为：创建任务 → 固定盘点范围及账面快照 → 扫码实盘 → 差异复核 → 审批过账 → 保存调整流水。任务需记录仓库、库位、LOT、单位、盘点人、复核人、版本和原因。盲盘、复盘、审批属于对 YUKI 的设计建议，本次没有证据证明 GreaterWMS 已实现完整流程。

验收至少覆盖：有预留或冻结库存；盘点期间移库或出库；重复提交；零差异；盘点人权限；跨仓库扫描。盘点结果只过账一次，发生并发库存变更时必须重新核对，不覆盖较新的账目。

## 作业待办和异常入口

沿用 YUKI 现有业务状态，由查询规则形成“待收货、待上架、待拣货、待装车、待签收、异常待处理”等队列，按仓库和角色过滤。每项展示剩余数量、任务归属、预约时间、阻塞原因和可执行动作。缺货与冻结应可见，但不能为了界面分类新增一套互相冲突的订单状态。

应继续保持：出库分配预留库存，拣货不重复扣减，完成出库才扣减；取消释放未完成的分配。界面参考不应改变这些规则。

## 库位与移动端

YUKI 的 `backend/app/models/warehouse.py` 已有 Warehouse、WarehouseArea、WarehouseLocation；`backend/app/models/inventory.py` 已有 InventoryLotLocation 和库存流水。可以在这些实体上扩展暂存、存储、拣货、异常区分类，以及容量单位和限制。空位状态应由库存及占用规则计算，避免一个独立布尔值与实际库存不一致。

移动端优先验证连续扫码、重复扫描、错误库位、部分拣货、网络恢复和重复提交。GreaterWMS 的源码证明存在移动作业界面，不能据此认定所有 PDA、蓝牙扫描器或相机都兼容。YUKI 已有离线队列相关实现，其可靠性应通过实际设备验收确认。

## 不宜照搬

- V2.1.49 的 README 使用 Python 3.8、Node 14 等旧环境说明；发布页另有 V2.1.50 框架方向说明。不要按旧快速启动文档替换 YUKI 环境，也不要将框架公告当作业务功能已迁移的证据。
- GreaterWMS 多个可变库存计数字段适合研究业务分类，不宜直接复制成新的权威账本。YUKI 应沿用库存流水和明确的数量约束生成查询视图。
- 本次未验证自动波次优化、完整 LPN、FEFO、智能容量分配或完整盘点审批，不列为已确认能力。
- 海运柜次、Cargo BOL、FBA 预约及拆柜转运继续参考已观察的 Unicang 流程和 YUKI 自身规则。

## 主要证据

- [V2.1.49 代码与环境说明](https://github.com/GreaterWMS/GreaterWMS/tree/V2.1.49)；[发布记录](https://github.com/GreaterWMS/GreaterWMS/releases)。
- [盘点模型](https://github.com/GreaterWMS/GreaterWMS/blob/V2.1.49/cyclecount/models.py)与[盘点接口](https://github.com/GreaterWMS/GreaterWMS/blob/V2.1.49/cyclecount/views.py)：账面、实盘、差异与状态。
- [出库页面](https://github.com/GreaterWMS/GreaterWMS/blob/V2.1.49/templates/src/pages/outbound/outbound.vue)：作业阶段入口。
- [库存模型](https://github.com/GreaterWMS/GreaterWMS/blob/V2.1.49/stock/models.py)与[库位模型](https://github.com/GreaterWMS/GreaterWMS/blob/V2.1.49/binset/models.py)：库存分类、库位与属性。
- [移动拣货列表](https://github.com/GreaterWMS/GreaterWMS/blob/V2.1.49/app/src/pages/dn/PickingList.vue)：任务信息、数量录入与扫码筛选。

本地比较依据为当前代码，而非早期阶段计划：`backend/app/models/inventory.py`、`backend/app/models/warehouse.py`、`frontend/src/pages/PdaOperations.tsx`、`frontend/src/pages/PdaPage.tsx`、`frontend/src/components/pda/`。上述建议是后续工作范围，本轮研究未改动这些模块。
