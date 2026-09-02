import type { PickStep, ScanResult } from "../../api/scanExecution";

export type CameraState = "off" | "starting" | "on" | "denied" | "unsupported";
export type ScanInputSource = "manual" | "camera";
export type ScannablePickStep = Extract<PickStep, "EXPECT_LOCATION" | "EXPECT_LOT">;

export interface CameraScanGuard {
  value: string;
  step: PickStep;
  online: boolean;
  isOpen: boolean;
  requestInFlight: boolean;
  lastAcceptedKey: string | null;
}

export function cameraScanKey(step: PickStep, value: string) {
  return `${step}\u0000${value.trim()}`;
}

export function isScannableStep(step: PickStep): step is ScannablePickStep {
  return step === "EXPECT_LOCATION" || step === "EXPECT_LOT";
}

export function shouldSubmitCameraScan(guard: CameraScanGuard) {
  const value = guard.value.trim();
  return Boolean(
    value
      && guard.isOpen
      && isScannableStep(guard.step)
      && !guard.requestInFlight
      && guard.lastAcceptedKey !== cameraScanKey(guard.step, value),
  );
}

export function scanResultClass(result?: ScanResult) {
  if (!result) return "";
  return result === "ACCEPTED" ? "is-ok" : "is-error";
}
