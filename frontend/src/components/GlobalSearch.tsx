import { SearchOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Empty, Input, Spin, Tag, Typography } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { globalSearch } from '../api/search'

const labels: Record<string, string> = { CONTAINER: 'Containers', OUTBOUND: 'Outbound Orders', FBA: 'FBA', PICKING: 'Picking', BOL: 'BOL', LOAD: 'Loads', WORK_ORDER: 'Work Orders', EXCEPTION: 'Exceptions', DOCUMENT: 'Documents' }

export function GlobalSearch() {
  const navigate = useNavigate()
  const location = useLocation()
  const root = useRef<HTMLDivElement>(null)
  const [value, setValue] = useState('')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  useEffect(() => { const timer = window.setTimeout(() => setQuery(value.trim().length >= 2 ? value.trim() : ''), 300); return () => window.clearTimeout(timer) }, [value])
  useEffect(() => { const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }; document.addEventListener('mousedown', close); return () => document.removeEventListener('mousedown', close) }, [])
  const result = useQuery({ queryKey: ['global-search', query], queryFn: () => globalSearch(query), enabled: query.length >= 2, staleTime: 30_000 })
  const items = useMemo(() => result.data?.groups.flatMap(group => group.items) ?? [], [result.data])
  useEffect(() => setActive(0), [query])
  const go = (route: string) => {
    setOpen(false); setValue('')
    const target = new URL(route, window.location.origin)
    if (target.pathname === location.pathname) {
      const preserved = new URLSearchParams(location.search)
      target.searchParams.forEach((value, key) => preserved.set(key, value))
      navigate(`${target.pathname}?${preserved}`)
    } else navigate(`${target.pathname}${target.search}`)
  }
  return <div className="global-search" ref={root} onKeyDown={event => {
    if (event.key === 'Escape') { setOpen(false); return }
    if (!open || !items.length) return
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive(index => (index + 1) % items.length) }
    if (event.key === 'ArrowUp') { event.preventDefault(); setActive(index => (index - 1 + items.length) % items.length) }
    if (event.key === 'Enter') { event.preventDefault(); go(items[active].target_route) }
  }}>
    <Input prefix={<SearchOutlined />} placeholder="Search container, OB, FBA, BOL, ST..." value={value} allowClear onFocus={() => setOpen(true)} onChange={event => { setValue(event.target.value); setOpen(true) }} onPressEnter={() => { if (items[active]) go(items[active].target_route); else setQuery(value.trim()) }} />
    {open && value.trim().length >= 2 && <div className="global-search-results">
      {result.isLoading && <div className="global-search-state"><Spin size="small" /> Searching...</div>}
      {result.isError && <div className="global-search-state global-search-error">Search unavailable. Please try again.</div>}
      {!result.isLoading && !result.isError && result.data?.total === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No matching references" />}
      {result.data?.groups.map(group => <section key={group.type}><div className="global-search-group">{labels[group.type] ?? group.type}<span>{group.count}</span></div>{group.items.map(item => { const index = items.indexOf(item); return <button key={`${item.type}-${item.id}`} className={index === active ? 'active' : ''} onMouseEnter={() => setActive(index)} onClick={() => go(item.target_route)}><div><Typography.Text strong>{item.primary_reference}</Typography.Text>{item.secondary_reference && <Typography.Text type="secondary"> · {item.secondary_reference}</Typography.Text>}</div><div className="global-search-meta"><Tag>{item.status}</Tag>{item.warehouse && <span>{item.warehouse}</span>}{item.customer && <span>{item.customer}</span>}</div></button>})}</section>)}
    </div>}
  </div>
}
