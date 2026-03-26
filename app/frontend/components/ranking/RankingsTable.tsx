import { useState, useMemo, useCallback, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useRankings } from '../../hooks/useQueries'
import { useAppStore } from '../../store/useAppStore'
import { fmt, scoreColor } from '../../lib/format'
import type { TickerRow } from '../../types/api'
import { TickerDrawer } from './TickerDrawer'

type SortKey = keyof TickerRow

function VerdictPill({ verdict }: { verdict: TickerRow['verdict'] }) {
  const cls =
    verdict === 'BUY' ? 'pill-buy'
    : verdict === 'FUND_ONLY' ? 'pill-fund'
    : verdict === 'TECH_ONLY' ? 'pill-tech'
    : 'pill-fail'
  const label = verdict === 'FUND_ONLY' ? 'FUND' : verdict === 'TECH_ONLY' ? 'TECH' : verdict
  return <span className={cls}>{label}</span>
}

function GateBadge({ g3, g4 }: { g3: boolean; g4: boolean }) {
  return (
    <span>
      <span style={{ color: g3 ? 'var(--col-buy)' : 'var(--col-red)' }}>✓</span>
      <span style={{ color: g4 ? 'var(--col-buy)' : 'var(--col-red)' }}>✓</span>
    </span>
  )
}

const COLS = [
  { key: 'rank_score' as SortKey, label: '#',       w: 36  },
  { key: 'ticker'     as SortKey, label: 'TICKER',  w: 82  },
  { key: 'sector'     as SortKey, label: 'SECTOR',  w: 100 },
  { key: 'rank_score' as SortKey, label: 'SCORE',   w: 60  },
  { key: 'alpha'      as SortKey, label: 'ALPHA',   w: 58  },
  { key: 'moat'       as SortKey, label: 'MOAT',    w: 54  },
  { key: 'z'          as SortKey, label: 'Z',        w: 48  },
  { key: 'sloan'      as SortKey, label: 'SLOAN',   w: 58  },
  { key: 'fcf_q'      as SortKey, label: 'FCF',     w: 48  },
  { key: 'sortino'    as SortKey, label: 'SORT',    w: 50  },
  { key: 'beta'       as SortKey, label: 'beta',    w: 40  },
  { key: 'strategy'   as SortKey, label: 'STRAT',   w: 90  },
  { key: 'signal_str' as SortKey, label: 'SS',      w: 42  },
  { key: 'rr'         as SortKey, label: 'R:R',     w: 46  },
  { key: 'entry'      as SortKey, label: 'ENTRY',   w: 68  },
  { key: 'tp'         as SortKey, label: 'TP',      w: 68  },
  { key: 'sl'         as SortKey, label: 'SL',      w: 68  },
  { key: 'gate3'      as SortKey, label: 'GATE',    w: 46  },
  { key: 'verdict'    as SortKey, label: 'VERDICT', w: 72  },
]

const TOTAL_W = COLS.reduce((s, c) => s + c.w, 0)
const ROW_H = 30
const LEFT_ALIGN = new Set(['#', 'TICKER', 'SECTOR', 'STRAT'])

export function RankingsTable() {
  const { isLoading } = useRankings()
  const rankings = useAppStore((s) => s.rankings)
  const { verdictFilter, sectorFilter, tickerSearch, setFilters, setSelectedTicker, selectedTicker } =
    useAppStore()

  const [sortKey, setSortKey] = useState<SortKey>('rank_score')
  const [sortDir, setSortDir] = useState<1 | -1>(-1)
  const scrollRef = useRef<HTMLDivElement>(null)

  const sectorList = useMemo(() => {
    const s = new Set(rankings?.rows.map((r) => r.sector) ?? [])
    return Array.from(s).sort()
  }, [rankings])

  const filtered = useMemo(() => {
    if (!rankings) return []
    return rankings.rows
      .filter((r) => {
        if (verdictFilter !== 'ALL' && r.verdict !== verdictFilter) return false
        if (sectorFilter && r.sector !== sectorFilter) return false
        if (tickerSearch) {
          const q = tickerSearch.toLowerCase()
          if (!r.ticker.toLowerCase().includes(q) && !r.sector.toLowerCase().includes(q)) return false
        }
        return true
      })
      .sort((a, b) => {
        const av = a[sortKey] as number | string | boolean | null
        const bv = b[sortKey] as number | string | boolean | null
        if (av == null) return 1
        if (bv == null) return -1
        return av < bv ? -sortDir : av > bv ? sortDir : 0
      })
  }, [rankings, verdictFilter, sectorFilter, tickerSearch, sortKey, sortDir])

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 12,
  })

  const handleSort = useCallback(
    (key: SortKey) => {
      if (key === sortKey) setSortDir((d) => (d === 1 ? -1 : 1))
      else { setSortKey(key); setSortDir(-1) }
    },
    [sortKey],
  )

  function renderCell(col: typeof COLS[number], row: TickerRow, rank: number): React.ReactNode {
    switch (col.label) {
      case '#':      return <span style={{ color: 'var(--col-amber)' }}>{rank}</span>
      case 'TICKER': return <span style={{ color: 'var(--col-amber)' }}>{row.ticker}</span>
      case 'SECTOR': return <span style={{ color: 'var(--col-dim)' }}>{row.sector}</span>
      case 'SCORE':  return <span style={{ color: scoreColor(row.rank_score) }}>{fmt.score(row.rank_score)}</span>
      case 'ALPHA':  return fmt.score(row.alpha)
      case 'MOAT':   return <span style={{ color: (row.moat ?? 0) >= 0 ? 'var(--col-buy)' : 'var(--col-red)' }}>{fmt.float2(row.moat)}</span>
      case 'Z':      return <span style={{ color: (row.z ?? 99) < 1.81 ? 'var(--col-red)' : 'var(--col-body)' }}>{fmt.z(row.z)}</span>
      case 'SLOAN':  return <span style={{ color: (row.sloan ?? 0) > 0.1 ? 'var(--col-red)' : 'var(--col-body)' }}>{fmt.float2(row.sloan)}</span>
      case 'FCF':    return fmt.float2(row.fcf_q)
      case 'SORT':   return fmt.float2(row.sortino)
      case 'beta':   return fmt.float2(row.beta)
      case 'STRAT':  return <span style={{ color: 'var(--col-dim)', fontSize: '10px' }}>{row.strategy}</span>
      case 'SS':     return String(row.signal_str)
      case 'R:R':    return `${row.rr.toFixed(1)}x`
      case 'ENTRY':  return <span style={{ color: 'var(--col-amber)' }}>{fmt.price(row.entry)}</span>
      case 'TP':     return <span style={{ color: 'var(--col-buy)' }}>{fmt.price(row.tp)}</span>
      case 'SL':     return <span style={{ color: 'var(--col-red)' }}>{fmt.price(row.sl)}</span>
      case 'GATE':   return <GateBadge g3={row.gate3} g4={row.gate4} />
      case 'VERDICT':return <VerdictPill verdict={row.verdict} />
      default:       return '—'
    }
  }

  return (
    <div className="rankings-wrap">
      {/* Header */}
      <div className="panel-section" style={{ flex: 'none', borderBottom: '1px solid var(--col-border)' }}>
        <div className="section-header">
          <span className="section-label">
            RANKINGS · {rankings?.universe ?? '—'} · {rankings?.total_scanned ?? 0} tickers
          </span>
          {rankings && (
            <span style={{ color: 'var(--col-dim)', fontSize: '10px' }}>
              Last: {new Date(rankings.timestamp).toUTCString().slice(5, 22)} UTC · BUY: {rankings.buy_count}
            </span>
          )}
        </div>

        <div className="filter-bar">
          <div className="filter-group">
            {(['ALL', 'BUY', 'FUND_ONLY', 'TECH_ONLY', 'FAIL'] as const).map((v) => (
              <button
                key={v}
                className={`filter-btn${verdictFilter === v ? ' active' : ''}`}
                onClick={() => setFilters({ verdictFilter: v })}
              >
                {v === 'FUND_ONLY' ? 'FUND' : v === 'TECH_ONLY' ? 'TECH' : v}
              </button>
            ))}
          </div>
          <select
            className="universe-select"
            value={sectorFilter}
            onChange={(e) => setFilters({ sectorFilter: e.target.value })}
          >
            <option value="">All Sectors</option>
            {sectorList.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input
            className="search-input"
            placeholder="Search ticker / sector…"
            value={tickerSearch}
            onChange={(e) => setFilters({ tickerSearch: e.target.value })}
          />
        </div>
      </div>

      {/* States */}
      {isLoading && <div className="empty-state"><div className="loading">Loading rankings…</div></div>}

      {!isLoading && !rankings && (
        <div className="empty-state">
          <div style={{ color: 'var(--col-dim)', fontSize: '14px' }}>No rankings data</div>
          <div style={{ color: 'var(--col-amber)', marginTop: 8, fontSize: '12px' }}>▶ RUN SCAN to generate rankings</div>
        </div>
      )}

      {/* Table */}
      {rankings && (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {/* Column headers */}
          <div style={{ overflowX: 'hidden', flex: 'none', borderBottom: '1px solid var(--col-border)', background: 'var(--col-surface)' }}>
            <div style={{ display: 'flex', minWidth: TOTAL_W }}>
              {COLS.map((col) => (
                <div
                  key={col.label}
                  onClick={() => handleSort(col.key)}
                  style={{
                    width: col.w, minWidth: col.w,
                    padding: '5px 6px',
                    fontSize: '10px',
                    fontWeight: 500,
                    color: 'var(--col-amber)',
                    textAlign: LEFT_ALIGN.has(col.label) ? 'left' : 'right',
                    cursor: 'pointer',
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {col.label}{sortKey === col.key ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
                </div>
              ))}
            </div>
          </div>

          {/* Virtual rows */}
          <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', overflowX: 'auto' }}>
            <div style={{ height: virtualizer.getTotalSize(), position: 'relative', minWidth: TOTAL_W }}>
              {virtualizer.getVirtualItems().map((vItem) => {
                const row = filtered[vItem.index]
                if (!row) return null
                const isSelected = selectedTicker === row.ticker
                return (
                  <div
                    key={vItem.key}
                    data-index={vItem.index}
                    ref={virtualizer.measureElement}
                    onClick={() => setSelectedTicker(isSelected ? null : row.ticker)}
                    style={{
                      position: 'absolute',
                      top: vItem.start,
                      left: 0,
                      width: '100%',
                      minWidth: TOTAL_W,
                      height: ROW_H,
                      display: 'flex',
                      alignItems: 'center',
                      borderBottom: '1px solid var(--col-border)',
                      cursor: 'pointer',
                      background: isSelected ? 'rgba(255,140,0,0.06)' : 'transparent',
                    }}
                    onMouseEnter={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = 'var(--col-elevated)' }}
                    onMouseLeave={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                  >
                    {COLS.map((col) => (
                      <div
                        key={col.label}
                        style={{
                          width: col.w, minWidth: col.w,
                          padding: '0 6px',
                          fontSize: '11px',
                          textAlign: LEFT_ALIGN.has(col.label) ? 'left' : 'right',
                          color: 'var(--col-body)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontFamily: 'inherit',
                        }}
                      >
                        {renderCell(col, row, vItem.index + 1)}
                      </div>
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      {rankings && (
        <div className="table-footer">
          Total: {rankings.total_scanned}&nbsp;&nbsp;
          <span style={{ color: 'var(--col-buy)' }}>BUY: {rankings.buy_count}</span>
          &nbsp;({((rankings.buy_count / Math.max(rankings.total_scanned, 1)) * 100).toFixed(0)}%)
          &nbsp;&nbsp;FAIL: {rankings.failed_count}
          {rankings.errors.length > 0 && <>&nbsp;&nbsp;<span style={{ color: 'var(--col-red)' }}>Errors: {rankings.errors.length}</span></>}
          &nbsp;&nbsp;<span style={{ color: 'var(--col-dim)' }}>Showing: {filtered.length}</span>
        </div>
      )}

      {selectedTicker && (
        <TickerDrawer
          ticker={selectedTicker}
          rows={rankings?.rows ?? []}
          onClose={() => setSelectedTicker(null)}
        />
      )}
    </div>
  )
}
