export function startSplitDrag(cursor: string) {
  document.body.dataset.splitDragging = "1";
  document.body.style.userSelect = "none";
  document.body.style.cursor = cursor;
}

export function stopSplitDrag() {
  delete document.body.dataset.splitDragging;
  document.body.style.userSelect = "";
  document.body.style.cursor = "";
}

export function rafThrottle(fn: (value: number) => void) {
  let frame = 0;
  let next = 0;
  return (value: number) => {
    next = value;
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      fn(next);
    });
  };
}
