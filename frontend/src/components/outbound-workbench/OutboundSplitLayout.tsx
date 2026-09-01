import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { rafThrottle, startSplitDrag, stopSplitDrag } from './splitDrag'

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

function applyLeftWidth(node: HTMLDivElement | null, px: number, expanded: boolean) {
  if (!node) return
  const left = node.querySelector<HTMLElement>('.outbound-split-left')
  if (!left) return
  if (!expanded) {
    left.style.width = 'calc(100% - 36px)'
    left.style.flex = '0 0 calc(100% - 36px)'
    return
  }
  left.style.width = `${px}px`
  left.style.flex = `0 0 ${px}px`
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
  const availableRef = useRef(window.innerWidth)
  const [available, setAvailable] = useState(window.innerWidth)
  const [leftWidth, setLeftWidth] = useState(0)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(KEY_COLLAPSED) === '1')
  const expanded = !collapsed

  const commitWidth = useCallback((next: number, persist = false) => {
    const clamped = clampHorizontal(next, availableRef.current)
    leftWidthRef.current = clamped
    applyLeftWidth(root.current, clamped, !collapsed)
    if (persist) {
      setLeftWidth(clamped)
      localStorage.setItem(KEY_WIDTH, String(clamped))
    }
    return clamped
  }, [collapsed])

  const dragWidth = useMemo(() => rafThrottle((px: number) => commitWidth(px, false)), [commitWidth])

  useEffect(() => {
    const update = () => {
      if (dragging.current) return
      const width = root.current?.clientWidth || window.innerWidth
      availableRef.current = width
      setAvailable(width)
      const next = leftWidthRef.current || readPersistedWidth(width) || width * DEFAULT_LEFT_RATIO
      commitWidth(next, true)
    }
    update()
    const observer = root.current ? new ResizeObserver(update) : null
    if (root.current) observer?.observe(root.current)
    window.addEventListener('resize', update)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [commitWidth])

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!dragging.current || collapsed) return
      const rect = root.current?.getBoundingClientRect()
      if (rect) dragWidth(event.clientX - rect.left)
    }
    const stop = () => {
      if (!dragging.current) return
      dragging.current = false
      root.current?.classList.remove('is-dragging')
      stopSplitDrag()
      commitWidth(leftWidthRef.current, true)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
  }, [collapsed, commitWidth, dragWidth])

  const reset = () => {
    setCollapsed(false)
    localStorage.setItem(KEY_COLLAPSED, '0')
    commitWidth(availableRef.current * DEFAULT_LEFT_RATIO, true)
  }

  const toggleRight = () => {
    setCollapsed((current) => {
      const next = !current
      localStorage.setItem(KEY_COLLAPSED, next ? '1' : '0')
      return next
    })
  }

  useEffect(() => { onCollapsedChange?.(collapsed) }, [collapsed, onCollapsedChange])
  useImperativeHandle(ref, () => ({ reset, toggleRight }))

  return (
    <div ref={root} className={`outbound-split-layout ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="outbound-split-left" style={{ width: expanded ? leftWidth : 'calc(100% - 36px)', flex: expanded ? `0 0 ${leftWidth}px` : '0 0 calc(100% - 36px)' }}>
        {showControls && <div className="outbound-left-window-controls">
          <button className="outbound-reset-window" onClick={reset}>Reset Window</button>
          {expanded && <button className="outbound-collapse" onClick={() => { setCollapsed(true); localStorage.setItem(KEY_COLLAPSED, '1') }}>Hide Right Panel</button>}
        </div>}
        {left}
      </div>
      <div className="outbound-splitter" role="separator" aria-orientation="vertical" tabIndex={0}
        onPointerDown={(event) => {
          if (!expanded) return
          dragging.current = true
          root.current?.classList.add('is-dragging')
          startSplitDrag('col-resize')
          event.currentTarget.setPointerCapture?.(event.pointerId)
        }}
        onDoubleClick={reset}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
          commitWidth(leftWidthRef.current + (event.key === 'ArrowRight' ? 16 : -16), true)
          event.preventDefault()
        }}
      >
        <span className="outbound-splitter-handle" aria-hidden="true"><i /><i /><i /></span>
      </div>
      <div className="outbound-split-right" style={{ width: expanded ? undefined : 28, flex: expanded ? '1 1 auto' : '0 0 28px' }}>
        {expanded ? right : <button className="outbound-expand" onClick={() => { setCollapsed(false); localStorage.setItem(KEY_COLLAPSED, '0') }}>&#x276F;</button>}
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

function applyTopHeight(node: HTMLDivElement | null, px: number) {
  const top = node?.querySelector<HTMLElement>('.outbound-vertical-top')
  if (!top) return
  top.style.height = `${px}px`
  top.style.flex = `0 0 ${px}px`
}

export type OutboundVerticalSplitLayoutHandle = { reset: () => void }

export const OutboundVerticalSplitLayout = forwardRef<OutboundVerticalSplitLayoutHandle, { top: ReactNode; bottom: ReactNode }>(function OutboundVerticalSplitLayout(
  { top, bottom },
  ref,
) {
  const root = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const topHeightRef = useRef(0)
  const availableRef = useRef(window.innerHeight)
  const [available, setAvailable] = useState(window.innerHeight)
  const [topHeight, setTopHeight] = useState(0)
  const commitHeight = useCallback((next: number, persist = false) => {
    const clamped = clampVertical(next, availableRef.current)
    topHeightRef.current = clamped
    applyTopHeight(root.current, clamped)
    if (persist) {
      setTopHeight(clamped)
      localStorage.setItem(KEY_TOP_HEIGHT, String(clamped))
    }
    return clamped
  }, [])
  const dragHeight = useMemo(() => rafThrottle((px: number) => commitHeight(px, false)), [commitHeight])

  useEffect(() => {
    const update = () => {
      if (dragging.current) return
      const height = root.current?.clientHeight || window.innerHeight
      availableRef.current = height
      setAvailable(height)
      commitHeight(topHeightRef.current || readPersistedTopHeight(height) || height * DEFAULT_TOP_RATIO, true)
    }
    update()
    const observer = root.current ? new ResizeObserver(update) : null
    if (root.current) observer?.observe(root.current)
    window.addEventListener('resize', update)
    return () => { observer?.disconnect(); window.removeEventListener('resize', update) }
  }, [commitHeight])

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!dragging.current) return
      const rect = root.current?.getBoundingClientRect()
      if (rect) dragHeight(event.clientY - rect.top)
    }
    const stop = () => {
      if (!dragging.current) return
      dragging.current = false
      root.current?.classList.remove('is-dragging')
      stopSplitDrag()
      commitHeight(topHeightRef.current, true)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
  }, [commitHeight, dragHeight])

  useImperativeHandle(ref, () => ({ reset: () => commitHeight(availableRef.current * DEFAULT_TOP_RATIO, true) }))

  return (
    <div ref={root} className="outbound-vertical-split">
      <div className="outbound-vertical-top" style={{ height: topHeight, flex: `0 0 ${topHeight}px` }}>{top}</div>
      <div className="outbound-vertical-splitter" role="separator" aria-orientation="horizontal" tabIndex={0}
        onPointerDown={(event) => {
          dragging.current = true
          root.current?.classList.add('is-dragging')
          startSplitDrag('row-resize')
          event.currentTarget.setPointerCapture?.(event.pointerId)
        }}
        onDoubleClick={() => commitHeight(availableRef.current * DEFAULT_TOP_RATIO, true)}
      >
        <span className="outbound-vertical-handle" aria-hidden="true"><i /><i /><i /></span>
      </div>
      <div className="outbound-vertical-bottom">{bottom}</div>
    </div>
  )
})
