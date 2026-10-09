import type { QueryClient } from '@tanstack/react-query'

type Session = { accessToken: string | null }
type SessionStore = {
  subscribe: (listener: (next: Session, previous: Session) => void) => () => void
}

// Clear both cached permissions and business records before rendering a new session.
// Token refresh within a signed-in session preserves active requests and mutations.
export function bindAuthQueryCache(store: SessionStore, cache: QueryClient) {
  return store.subscribe((next, previous) => {
    if (next.accessToken !== previous.accessToken &&
        (next.accessToken === null || previous.accessToken === null)) cache.clear()
  })
}
