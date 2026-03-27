import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useRankings } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { TickerDrawer } from '../ranking/TickerDrawer';
import { fmt, scoreColor, riskColor } from '../../lib/format';
import type { TickerRow } from '../../types/api';

const COL_PX    = [32, 80, 100, 56, 52, 52, 44, 52, 44, 48, 36, 88, 36, 44, 64, 64, 64, 44, 72];
const COL_TOTAL = COL_PX.reduce((a, b) => a + b, 0);
const COL_PCT   = COL_PX.map((w) => `${((w / COL_TOTAL) * 100).toFixed(3)}%`);
const COL_HEADS = ['#','TICKER','SECTOR','SCORE','ALPHA','MOAT','Z','SLOAN','FCF','SORT','β','STRAT','SS','R:R','ENTRY','TP','SL','GATE','VERDICT'];
const LEFT_ALIGN = new Set(['#', 'TICKER', 'SECTOR', 'STRAT']);

const VERDICT_LABELS: Record<string, string> = {
  BUY: 'BUY', FUND_ONLY: 'FUND', TECH_ONLY: 'TECH', FAIL: 'FAIL',
};

function VerdictPill({ verdict }: { verdict: TickerRow['verdict'] }) {
  const cls = verdict === 'BUY' ? 'pill-buy'
    : verdict === 'FUND_ONLY' ? 'pill-fund'
    : verdict === 'TECH_ONLY' ? 'pill-tech'
    : 'pill-fail';
  return <span className={cls}>{VERDICT_LABELS[verdict]}</span>;
}

function GateCell({ g3, g4 }: { g3: boolean; g4: boolean }) {
  return (
    <span>
      <span style={{ color: g3 ? 'var(--col-buy)' : 'var(--col-red)' }}>✓</span>
      <span style={{ color: g4 ? 'var(--col-buy)' : 'var(--col-red)' }}>✓</span>
    </span>
  );
}

// Shared cell style helper
function cell(i: number, extra?: React.CSSProperties): React.CSSProperties {
  return {
    width: COL_PCT[i],
    flexShrink: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    padding: '0 6px',
    textAlign: LEFT_ALIGN.has(COL_HEADS[i]) ? 'left' : 'right',
    ...extra,
  };
}

export function RankingsTable() {
  const { data, isLoading, error } = useRankings();
  const {
    selectedUniverse,
    verdictFilter,
    sectorFilter,
    tickerSearch,
    setFilters,
    selectedTicker,
    setSelectedTicker,
  } = useAppStore();

  const rankings = useAppStore((s) => s.rankings) ?? data;
  const parentRef = useRef<HTMLDivElement>(null);

  const allSectors = rankings
    ? Array.from(new Set(rankings.rows.map((r) => r.sector))).sort()
    : [];

  const filteredRows: TickerRow[] = (rankings?.rows ?? []).filter((r) => {
    if (verdictFilter !== 'ALL' && r.verdict !== verdictFilter) return false;
    if (sectorFilter && r.sector !== sectorFilter) return false;
    if (tickerSearch) {
      const q = tickerSearch.toLowerCase();
      if (!r.ticker.toLowerCase().includes(q) && !r.sector.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const virtualizer = useVirtualizer({
    count: filteredRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28,
    overscan: 12,
  });

  const verdictButtons: Array<'ALL' | 'BUY' | 'FUND_ONLY' | 'TECH_ONLY' | 'FAIL'> = [
    'ALL', 'BUY', 'FUND_ONLY', 'TECH_ONLY', 'FAIL',
  ];

  const Header = () => (
    <div className="panel-section" style={{ borderBottom: '1px solid var(--col-border)', paddingBottom: 8 }}>
      <div className="section-header">
        <span className="section-label">
          RANKINGS · {selectedUniverse}
          {rankings ? ` · ${rankings.total_scanned} tickers` : ''}
        </span>
        {rankings && (
          <span style={{ color: 'var(--col-dim)', fontSize: '10px' }}>
            BUY: <span style={{ color: 'var(--col-buy)' }}>{rankings.buy_count}</span>
            &nbsp;· Updated: {new Date(rankings.timestamp).toUTCString().slice(5, 22)}
          </span>
        )}
      </div>

      <div className="filter-bar">
        <div className="filter-group">
          {verdictButtons.map((v) => (
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
          style={{ height: '24px', fontSize: '10px', borderColor: 'var(--col-border)', color: 'var(--col-dim)' }}
          value={sectorFilter}
          onChange={(e) => setFilters({ sectorFilter: e.target.value })}
        >
          <option value="">All Sectors</option>
          {allSectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <input
          className="search-input"
          type="text"
          placeholder="Search ticker…"
          value={tickerSearch}
          onChange={(e) => setFilters({ tickerSearch: e.target.value })}
        />
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="rankings-wrap">
        <Header />
        <div className="center-fill"><div className="loading">Loading rankings…</div></div>
      </div>
    );
  }

  if (error || !rankings) {
    return (
      <div className="rankings-wrap">
        <Header />
        <div className="empty-state">
          <div style={{ color: 'var(--col-dim)', fontSize: '13px', marginBottom: 12 }}>No rankings data</div>
          <div style={{ color: 'var(--col-dim)', fontSize: '11px', marginBottom: 20 }}>
            Press <span style={{ color: 'var(--col-amber)' }}>▶ RUN SCAN</span> to generate rankings for {selectedUniverse}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rankings-wrap">
      <Header />

      <div className="table-scroll-wrap" ref={parentRef} style={{ overflowY: 'auto', overflowX: 'hidden' }}>

        {/* Sticky header row — flex div, same widths as data rows */}
        <div style={{
          position: 'sticky', top: 0, zIndex: 2,
          background: 'var(--col-surface)',
          display: 'flex', alignItems: 'center',
          borderBottom: '1px solid var(--col-amber)',
          height: 26,
        }}>
          {COL_HEADS.map((h, i) => (
            <div key={h} style={{
              width: COL_PCT[i], flexShrink: 0,
              color: 'var(--col-amber)', fontSize: '9px',
              padding: '0 6px',
              textAlign: LEFT_ALIGN.has(h) ? 'left' : 'right',
              whiteSpace: 'nowrap', fontWeight: 500, letterSpacing: '0.5px',
              overflow: 'hidden', opacity: 0.85,
            }}>
              {h}
            </div>
          ))}
        </div>

        {/* Virtual rows container */}
        <div style={{ position: 'relative', height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((vRow) => {
            const row = filteredRows[vRow.index];
            const rank = vRow.index + 1;
            return (
              <div
                key={row.ticker}
                style={{
                  position: 'absolute', top: vRow.start, left: 0,
                  width: '100%', height: vRow.size,
                  display: 'flex', alignItems: 'center',
                  cursor: 'pointer', borderBottom: '1px solid #141414',
                }}
                onClick={() => setSelectedTicker(row.ticker)}
              >
                <div style={cell(0,  { fontSize: '10px', color: 'var(--col-amber)' })}>{rank}</div>
                <div style={cell(1,  { fontSize: '11px', color: 'var(--col-amber)', fontWeight: 500 })}>{row.ticker}</div>
                <div style={cell(2,  { fontSize: '10px', color: 'var(--col-dim)' })}>{row.sector}</div>
                <div style={cell(3,  { fontSize: '11px', color: scoreColor(row.rank_score), fontWeight: 500 })}>{fmt.score(row.rank_score)}</div>
                <div style={cell(4,  { fontSize: '10px', color: scoreColor(row.alpha) })}>{fmt.score(row.alpha)}</div>
                <div style={cell(5,  { fontSize: '10px', color: (row.moat ?? 0) >= 0 ? 'var(--col-buy)' : 'var(--col-red)' })}>{fmt.float2(row.moat)}</div>
                <div style={cell(6,  { fontSize: '10px', color: (row.z ?? 99) < 1.81 ? 'var(--col-red)' : 'var(--col-body)' })}>{fmt.z(row.z)}</div>
                <div style={cell(7,  { fontSize: '10px', color: (row.sloan ?? 0) > 0.1 ? 'var(--col-red)' : 'var(--col-body)' })}>{fmt.float2(row.sloan)}</div>
                <div style={cell(8,  { fontSize: '10px' })}>{fmt.float2(row.fcf_q)}</div>
                <div style={cell(9,  { fontSize: '10px', color: (row.sortino ?? 0) >= 1 ? 'var(--col-buy)' : 'var(--col-body)' })}>{fmt.float2(row.sortino)}</div>
                <div style={cell(10, { fontSize: '10px' })}>{fmt.float2(row.beta)}</div>
                <div style={cell(11, { fontSize: '10px' })}>{row.strategy}</div>
                <div style={cell(12, { fontSize: '10px', color: riskColor(row.signal_str) })}>{row.signal_str}</div>
                <div style={cell(13, { fontSize: '10px', color: row.rr >= 1.5 ? 'var(--col-buy)' : 'var(--col-dim)' })}>{row.rr.toFixed(1)}x</div>
                <div style={cell(14, { fontSize: '10px', color: 'var(--col-amber)' })}>{fmt.price(row.entry)}</div>
                <div style={cell(15, { fontSize: '10px', color: 'var(--col-buy)' })}>{fmt.price(row.tp)}</div>
                <div style={cell(16, { fontSize: '10px', color: 'var(--col-red)' })}>{fmt.price(row.sl)}</div>
                <div style={cell(17, { fontSize: '10px' })}><GateCell g3={row.gate3} g4={row.gate4} /></div>
                <div style={cell(18, { fontSize: '10px' })}><VerdictPill verdict={row.verdict} /></div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="table-footer">
        {filteredRows.length} / {rankings.total_scanned} shown
        &nbsp;·&nbsp;
        BUY: <span style={{ color: 'var(--col-buy)' }}>{rankings.buy_count}</span>
        &nbsp;·&nbsp;
        FUND: {rankings.rows.filter((r) => r.verdict === 'FUND_ONLY').length}
        &nbsp;·&nbsp;
        TECH: {rankings.rows.filter((r) => r.verdict === 'TECH_ONLY').length}
        &nbsp;·&nbsp;
        FAIL: {rankings.failed_count}
        {rankings.errors.length > 0 && (
          <span style={{ color: 'var(--col-red)' }}>
            &nbsp;· Errors: {rankings.errors.length}
          </span>
        )}
      </div>

      {/* Ticker drawer */}
      {selectedTicker && rankings && (
        <TickerDrawer
          ticker={selectedTicker}
          rows={rankings.rows}
          onClose={() => setSelectedTicker(null)}
        />
      )}
    </div>
  );
}
