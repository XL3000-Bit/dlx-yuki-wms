import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ReactNode,
} from 'react'

const KEY_WIDTH = 'dlx_wms:outbound_dispatch:left_width'
const OLD_KEYS = ['dlx_wms_outbound_dispatch_split_left_width']
const KEY_COLLAPSED = 'dlx_wms:outbound_dispatch:right_collapsed'
const KEY_TOP_HEIGHT = 'dlx_wms:outbound_dispatch:right_top_height'
const DEFAULT_LEFT_RATIO = 0.4
const DEFAULT_TOP_RATIO = 0.42
const MIN_LEFT = 420
const MIN_RIGHT = 600
const MIN_TOP = 190
const MIN_BOTTOM = 240
const SPLITTER = 8

function clampHorizontal(px: number, available: number) {
  const max = Math.max(MIN_LEFT, available - MIN_RIGHT - SPLITTER)
  return Math.min(Math.max(px, MIN_LEFT), max)
}

function readPersistedWidth(available: number) {
  for (const key of [KEY_WIDTH, ...OLD_KEYS]) {
    const raw = localStorage.getItem(key)
    if (raw == null) continue
    const value = Number(raw)
    const max = available - MIN_RIGHT - SPLITTER
    if (Number.isFinite(value) && value >= MIN_LEFT && value <= max && max >= MIN_LEFT) {
      localStorage.setItem(KEY_WIDTH, String(value))
      if (key !== KEY_WIDTH) localStorage.removeItem(key)
      return value
    }
    localStorage.removeItem(key)
  }
  return 0
}

export type OutboundSplitLayoutHandle = {
  reset: () => void
  toggleRight: () => void
}

type OutboundSplitLayoutProps = {
  left: ReactNode
  right: ReactNode
  showControls?: boolean
  onCollapsedChange?: (collapsed: boolean) => void
}

export const OutboundSplitLayout = forwardRef<OutboundSplitLayoutHandle, OutboundSplitLayoutProps>(function OutboundSplitLayout(
  { left, right, showControls = true, onCollapsedChange },
  ref,
) {
  const root = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const leftWidthRef = useRef(0)
  const [available, setAvailable] = useState(window.innerWidth)
  const [leftWidth, setLeftWidth] = useState(0)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(KEY_COLLAPSED) === '1')
  const expanded = !collapsed

  const updateLeftWidth = useCallback((next: number, width = available) => {
    const clamped = clampHorizontal(next, width)
    leftWidthRef.current = clamped
    setLeftWidth(clamped)
    return clamped
  }, [available])

  useEffect(() => {
    const update = () => {
      const width = root.current?.clientWidth || window.innerWidth
      setAvailable(width)
      updateLeftWidth(
        leftWidthRef.current || readPersistedWidth(width) || width * DEFAULT_LEFT_RATIO,
        width,
      )
    }
    update()
    const observer = root.current ? new ResizeObserver(update) : null
    if (root.current) observer?.observe(root.current)
    window.addEventListener('resize', update)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [updateLeftWidth])

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!dragging.current || collapsed) return
      const rect = root.current?.getBoundingClientRect()
      if (rect) updateLeftWidth(event.clientX - rect.left)
    }
    const stop = () => {
      if (dragging.current) localStorage.setItem(KEY_WIDTH, String(leftWidthRef.current))
      dragging.current = false
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [collapsed, updateLeftWidth])

  const reset = () => {
    const next = updateLeftWidth(available * DEFAULT_LEFT_RATIO)
    setCollapsed(false)
    localStorage.setItem(KEY_WIDTH, String(next))
    localStorage.setItem(KEY_COLLAPSED, '0')
  }

  const toggleRight = () => {
    setCollapsed((current) => {
      const next = !current
      localStorage.setItem(KEY_COLLAPSED, next ? '1' : '0')
      return next
    })
  }

  useEffect(() => {
    onCollapsedChange?.(collapsed)
  }, [collapsed, onCollapsedChange])

  useImperativeHandle(ref, () => ({ reset, toggleRight }))

  return (
    <div ref={root} className={`outbound-split-layout ${collapsed ? 'is-collapsed' : ''}`}>
      <div
        className="outbound-split-left"
        style={{
          width: expanded ? leftWidth : 'calc(100% - 36px)',
          flex: expanded ? `0 0 ${leftWidth}px` : '0 0 calc(100% - 36px)',
        }}
      >
        {showControls && <div className="outbound-left-window-controls">
          <button className="outbound-reset-window" onClick={reset}>Reset Window</button>
          {expanded && (
            <button
              className="outbound-collapse"
              aria-label="Collapse right panel"
              onClick={() => {
                setCollapsed(true)
                localStorage.setItem(KEY_COLLAPSED, '1')
              }}
            >
              Hide Right Panel
            </button>
          )}
        </div>}
        {left}
      </div>
      <div
        className="outbound-splitter"
        role="separator"
        aria-label="Resize outbound orders and detail panels"
        aria-orientation="vertical"
        aria-valuemin={MIN_LEFT}
        aria-valuemax={Math.max(MIN_LEFT, available - MIN_RIGHT - SPLITTER)}
        aria-valuenow={Math.round(leftWidth)}
        tabIndex={0}
        title="Drag to resize; double-click to restore the default split"
        onPointerDown={(event) => {
          if (!expanded) return
          dragging.current = true
          event.currentTarget.setPointerCapture?.(event.pointerId)
          document.body.style.userSelect = 'none'
          document.body.style.cursor = 'col-resize'
        }}
        onDoubleClick={reset}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
          const step = event.shiftKey ? 48 : 16
          updateLeftWidth(leftWidth + (event.key === 'ArrowRight' ? step : -step))
          event.preventDefault()
        }}
      >
        <span className="outbound-splitter-handle" aria-hidden="true"><i /><i /><i /></span>
      </div>
      <div
        className="outbound-split-right"
        style={{ width: expanded ? undefined : 28, flex: expanded ? '1 1 auto' : '0 0 28px' }}
      >
        {expanded ? right : (
          <button
            className="outbound-expand"
            aria-label="Expand right panel"
            title="Show right panel"
            onClick={() => {
              setCollapsed(false)
              localStorage.setItem(KEY_COLLAPSED, '0')
            }}
          >
            &#x276F;
          </button>
        )}
      </div>
    </div>
  )
})

function clampVertical(px: number, available: number) {
  const max = Math.max(MIN_TOP, available - MIN_BOTTOM - SPLITTER)
  return Math.min(Math.max(px, MIN_TOP), max)
}

function readPersistedTopHeight(available: number) {
  const value = Number(localStorage.getItem(KEY_TOP_HEIGHT))
  const max = available - MIN_BOTTOM - SPLITTER
  if (Number.isFinite(value) && value >= MIN_TOP && value <= max && max >= MIN_TOP) return value
  localStorage.removeItem(KEY_TOP_HEIGHT)
  return 0
}

export type OutboundVerticalSplitLayoutHandle = { reset: () => void }

export const OutboundVerticalSplitLayout = forwardRef<OutboundVerticalSplitLayoutHandle, { top: ReactNode; bottom: ReactNode }>(function OutboundVerticalSplitLayout(
  { top, bottom },
  ref,
) {
  const root = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const topHeightRef = useRef(0)
  const [available, setAvailable] = useState(window.innerHeight)
  const [topHeight, setTopHeight] = useState(0)

  const updateTopHeight = useCallback((next: number, height = available) => {
    const clamped = clampVertical(next, height)
    topHeightRef.current = clamped
    setTopHeight(clamped)
    return clamped
  }, [available])

  useEffect(() => {
    const update = () => {
      const height = root.current?.clientHeight || window.innerHeight
      setAvailable(height)
      updateTopHeight(
        topHeightRef.current || readPersistedTopHeight(height) || height * DEFAULT_TOP_RATIO,
        height,
      )
    }
    update()
    const observer = root.current ? new ResizeObserver(update) : null
    if (root.current) observer?.observe(root.current)
    window.addEventListener('resize', update)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [updateTopHeight])

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!dragging.current) return
      const rect = root.current?.getBoundingClientRect()
      if (rect) updateTopHeight(event.clientY - rect.top)
    }
    const stop = () => {
      if (dragging.current) localStorage.setItem(KEY_TOP_HEIGHT, String(topHeightRef.current))
      dragging.current = false
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [updateTopHeight])

  const reset = () => {
    const next = updateTopHeight(available * DEFAULT_TOP_RATIO)
    localStorage.setItem(KEY_TOP_HEIGHT, String(next))
  }

  useImperativeHandle(ref, () => ({ reset }))

  return (
    <div ref={root} className="outbound-vertical-split">
      <div className="outbound-vertical-top" style={{ height: topHeight, flex: `0 0 ${topHeight}px` }}>{top}</div>
      <div
        className="outbound-vertical-splitter"
        role="separator"
        aria-label="Resize outbound execution and remaining source panels"
        aria-orientation="horizontal"
        aria-valuemin={MIN_TOP}
        aria-valuemax={Math.max(MIN_TOP, available - MIN_BOTTOM - SPLITTER)}
        aria-valuenow={Math.round(topHeight)}
        tabIndex={0}
        title="Drag to resize; double-click to restore the 42/58 split"
        onPointerDown={(event) => {
          dragging.current = true
          event.currentTarget.setPointerCapture?.(event.pointerId)
          document.body.style.userSelect = 'none'
          document.body.style.cursor = 'row-resize'
        }}
        onDoubleClick={reset}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
          const step = event.shiftKey ? 48 : 16
          updateTopHeight(topHeight + (event.key === 'ArrowDown' ? step : -step))
          event.preventDefault()
        }}
      >
        <span className="outbound-vertical-handle" aria-hidden="true"><i /><i /><i /></span>
      </div>
      <div className="outbound-vertical-bottom">{bottom}</div>
    </div>
  )
})
