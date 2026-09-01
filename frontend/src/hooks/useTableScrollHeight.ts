import { useCallback, useEffect, useRef, useState } from "react";

export function useTableScrollHeight(reserved: number, minimum: number) {
  const hostNode = useRef<HTMLDivElement | null>(null);
  const observer = useRef<ResizeObserver | null>(null);
  const last = useRef(minimum);
  const [height, setHeight] = useState(minimum);

  const update = useCallback(() => {
    if (document.body.dataset.splitDragging === "1") return;
    const hostHeight = hostNode.current?.clientHeight || 0;
    const next = Math.max(minimum, Math.floor(hostHeight - reserved));
    if (Math.abs(next - last.current) < 6) return;
    last.current = next;
    setHeight(next);
  }, [minimum, reserved]);

  const hostRef = useCallback(
    (node: HTMLDivElement | null) => {
      observer.current?.disconnect();
      hostNode.current = node;
      if (node) {
        observer.current = new ResizeObserver(update);
        observer.current.observe(node);
        update();
      }
    },
    [update],
  );

  useEffect(() => {
    window.addEventListener("resize", update);
    return () => {
      observer.current?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [update]);

  return [hostRef, height] as const;
}
