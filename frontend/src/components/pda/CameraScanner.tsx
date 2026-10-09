import { CameraOutlined, StopOutlined } from "@ant-design/icons";
import { Alert, Button } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CameraState } from "./cameraScanPolicy";

interface DetectedBarcode {
  rawValue?: string;
}

interface BarcodeDetectorInstance {
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>;
}

interface BarcodeDetectorConstructor {
  new (options?: { formats?: string[] }): BarcodeDetectorInstance;
  getSupportedFormats?: () => Promise<string[]>;
}

interface CameraScannerProps {
  onDetected: (value: string) => void;
}

const preferredFormats = [
  "qr_code",
  "code_128",
  "code_39",
  "ean_13",
  "ean_8",
  "upc_a",
  "upc_e",
  "itf",
  "codabar",
  "data_matrix",
  "pdf417",
];

function detectorConstructor() {
  return (window as typeof window & { BarcodeDetector?: BarcodeDetectorConstructor }).BarcodeDetector;
}

function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => track.stop());
}

export function CameraScanner({ onDetected }: CameraScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const frameRef = useRef<number | null>(null);
  const runRef = useRef(0);
  const callbackRef = useRef(onDetected);
  const emittedCodeRef = useRef<string | null>(null);
  const emptyFramesRef = useRef(0);
  const [camera, setCamera] = useState<CameraState>("off");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    callbackRef.current = onDetected;
  }, [onDetected]);

  const stop = useCallback(() => {
    runRef.current += 1;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    stopStream(streamRef.current);
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    emittedCodeRef.current = null;
    emptyFramesRef.current = 0;
    setCamera("off");
    setMessage(null);
  }, []);

  useEffect(() => () => {
    runRef.current += 1;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    stopStream(streamRef.current);
  }, []);

  const start = useCallback(async () => {
    const Detector = detectorConstructor();
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !Detector) {
      setCamera("unsupported");
      setMessage("此浏览器无法使用相机识别；请在 HTTPS 安全页面使用支持 BarcodeDetector 的浏览器，或继续手输。");
      return;
    }

    const run = runRef.current + 1;
    runRef.current = run;
    setCamera("starting");
    setMessage(null);

    try {
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
      } catch (requestError) {
        if (requestError instanceof DOMException && requestError.name === "OverconstrainedError") {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } else {
          throw requestError;
        }
      }

      if (runRef.current !== run) {
        stopStream(stream);
        return;
      }

      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) throw new Error("Camera preview is unavailable");
      video.srcObject = stream;
      await video.play();

      const supported = Detector.getSupportedFormats
        ? await Detector.getSupportedFormats()
        : [];
      const formats = preferredFormats.filter((format) => supported.includes(format));
      const detector = formats.length > 0 ? new Detector({ formats }) : new Detector();
      let lastDetectionAt = 0;
      let detecting = false;

      setCamera("on");
      const detectFrame = (timestamp: number) => {
        if (runRef.current !== run) return;
        frameRef.current = requestAnimationFrame(detectFrame);
        if (detecting || timestamp - lastDetectionAt < 180 || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;

        detecting = true;
        lastDetectionAt = timestamp;
        void detector.detect(video).then((barcodes) => {
          const value = barcodes.find((barcode) => barcode.rawValue?.trim())?.rawValue?.trim() ?? null;
          if (!value) {
            emptyFramesRef.current += 1;
            if (emptyFramesRef.current >= 3) emittedCodeRef.current = null;
            return;
          }

          emptyFramesRef.current = 0;
          if (emittedCodeRef.current === value) return;
          emittedCodeRef.current = value;
          callbackRef.current(value);
        }).catch(() => {
          setMessage("当前画面暂时无法识别，请调整距离或继续手输。");
        }).finally(() => {
          detecting = false;
        });
      };
      frameRef.current = requestAnimationFrame(detectFrame);
    } catch (requestError) {
      if (runRef.current !== run) return;
      stopStream(streamRef.current);
      streamRef.current = null;
      const denied = requestError instanceof DOMException
        && (requestError.name === "NotAllowedError" || requestError.name === "SecurityError");
      setCamera(denied ? "denied" : "unsupported");
      setMessage(denied
        ? "相机权限被拒绝；可在浏览器设置中重新授权，手输仍可继续。"
        : "未找到可用相机；请继续手输。");
    }
  }, []);

  return (
    <section className="pda-camera" aria-label="相机扫码">
      <div className={`pda-camera-preview ${camera === "on" ? "is-on" : ""}`}>
        <video ref={videoRef} muted playsInline aria-label="扫码相机预览" />
        {camera !== "on" && (
          <div className="pda-camera-placeholder">
            <CameraOutlined />
            <span>{camera === "starting" ? "正在启动相机…" : "相机未开启"}</span>
          </div>
        )}
        {camera === "on" && <i className="pda-camera-guide" aria-hidden="true" />}
      </div>
      {camera === "on" || camera === "starting" ? (
        <Button block icon={<StopOutlined />} onClick={stop}>停止扫码</Button>
      ) : (
        <Button block icon={<CameraOutlined />} onClick={() => void start()}>开始扫码</Button>
      )}
      {message && <Alert showIcon type={camera === "denied" ? "warning" : "info"} message={message} />}
    </section>
  );
}
