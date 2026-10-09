import type { DispatchReadiness, ReadinessStatus } from '../api/loads'

export type ReadinessState =
  | { kind: 'loading' }
  | { kind: 'success'; data: DispatchReadiness }
  | { kind: 'denied' | 'unavailable' }

export const readinessPresentation: Record<ReadinessStatus, { label: string; color: string }> = {
  PASS: { label: 'PASS · 证据充分', color: 'success' },
  BLOCKED: { label: 'BLOCKED · 条件不满足', color: 'error' },
  UNKNOWN: { label: 'UNKNOWN · 尚不能确认', color: 'warning' },
  NOT_APPLICABLE: { label: 'NOT_APPLICABLE · 不适用', color: 'default' },
}
export const planValue = (value: number | null) => value == null ? '缺失' : String(value)

// Each refresh removes previous evidence. Generation checks also cover clients
// that resolve an obsolete request after its signal has been aborted.
export function createReadinessReader(
  fetchReadiness: (id: number, signal: AbortSignal) => Promise<DispatchReadiness>,
  publish: (state: ReadinessState) => void,
) {
  let generation = 0
  let controller: AbortController | undefined
  let disposed = false
  return {
    async refresh(id: number) {
      if (disposed) return
      const current = ++generation
      controller?.abort()
      controller = new AbortController()
      publish({ kind: 'loading' })
      try {
        const data = await fetchReadiness(id, controller.signal)
        if (disposed || current !== generation) return
        publish(data.load_id === id ? { kind: 'success', data } : { kind: 'unavailable' })
      } catch (error: unknown) {
        if (disposed || current !== generation) return
        const status = (error as { response?: { status?: number } } | null)?.response?.status
        publish({ kind: status === 401 || status === 403 || status === 404 ? 'denied' : 'unavailable' })
      }
    },
    dispose() { disposed = true; ++generation; controller?.abort() },
  }
}
