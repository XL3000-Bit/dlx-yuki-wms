import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
} from "@ant-design/icons";
import type { FBAWorkflowStep } from "../../types/fbaWorkbench";
export function FBAWorkflow({ steps }: { steps: FBAWorkflowStep[] }) {
  return (
    <div className="fba-workflow">
      {steps.map((x, i) => (
        <div className={`workflow-step ${x.status}`} key={x.key}>
          {x.status === "completed" ? (
            <CheckCircleFilled />
          ) : x.status === "exception" ? (
            <CloseCircleFilled />
          ) : (
            <ClockCircleOutlined />
          )}
          <span>{x.label}</span>
          {i < steps.length - 1 && <i />}
        </div>
      ))}
    </div>
  );
}
