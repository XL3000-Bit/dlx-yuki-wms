import { api } from './client'

export type GlobalSearchItem = { type: string; id: number; primary_reference: string; secondary_reference?: string | null; status: string; warehouse?: string | null; customer?: string | null; target_route: string; match_rank: number }
export type GlobalSearchGroup = { type: string; count: number; items: GlobalSearchItem[] }
export type GlobalSearchResponse = { query: string; total: number; groups: GlobalSearchGroup[] }

export async function globalSearch(q: string, limit = 20) {
  return (await api.get<GlobalSearchResponse>('/search', { params: { q, limit } })).data
}
