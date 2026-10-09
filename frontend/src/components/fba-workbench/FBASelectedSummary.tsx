import { Alert, Statistic } from "antd";
import type { FBAWorkbenchRow, FBASummary } from "../../types/fbaWorkbench";
const n = (x: string | number | null | undefined) => Number(x || 0);
const fmt = (x: number, d = 0) =>
  x.toLocaleString(undefined, { maximumFractionDigits: d });
export function FBASelectedSummary({
  all,
  selected,
  capacity,
}: {
  all: FBASummary | undefined;
  selected: FBAWorkbenchRow[];
  capacity: number;
}) {
  const sum = selected.reduce(
    (a, x) => ({
      p: a.p + n(x.total_pallet_qty),
      c: a.c + n(x.total_carton_qty),
      w: a.w + n(x.total_weight_lbs),
      v: a.v + n(x.total_cbm),
      age: a.age + n(x.max_aging_days),
    }),
    { p: 0, c: 0, w: 0, v: 0, age: 0 },
  );
  const util = capacity ? (sum.p / capacity) * 100 : 0;
  return (
    <div className="fba-summary">
      <div className="summary-group">
        <b>全部汇总</b>
        <Statistic title="任务" value={all?.task_count || 0} />
        <Statistic
          title="板数"
          value={fmt(n(all?.total_pallet_qty), 2)}
          suffix="PLT"
        />
        <Statistic
          title="箱数"
          value={fmt(n(all?.total_carton_qty), 0)}
          suffix="CTN"
        />
        <Statistic
          title="重量"
          value={fmt(n(all?.total_weight_lbs), 0)}
          suffix="LB"
        />
        <Statistic
          title="体积"
          value={fmt(n(all?.total_cbm), 2)}
          suffix="CBM"
        />
      </div>
      <div className="summary-group selected">
        <b>已选汇总</b>
        <Statistic title="任务" value={selected.length} />
        <Statistic title="板数" value={fmt(sum.p, 2)} suffix="PLT" />
        <Statistic title="箱数" value={fmt(sum.c)} suffix="CTN" />
        <Statistic
          title="平均库龄"
          value={selected.length ? fmt(sum.age / selected.length, 1) : 0}
          suffix="天"
        />
        <div className="trailer">
          <b>53' Trailer</b>
          <span>
            {fmt(sum.p, 2)} / {capacity} PLT · {fmt(util, 1)}%
          </span>
          {util > 100 && (
            <Alert type="warning" showIcon message="超过默认托盘容量" />
          )}
        </div>
      </div>
    </div>
  );
}
