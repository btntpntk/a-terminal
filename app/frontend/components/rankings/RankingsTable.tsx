import { useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useRankings } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { TickerDrawer } from '../ranking/TickerDrawer';
import { fmt, scoreColor, riskColor } from '../../lib/format';
import type { TickerRow } from '../../types/api';

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

  // Derive unique sectors for filter
  const allSectors = rankings
    ? Array.from(new Set(rankings.rows.map((r) => r.sector))).sort()
    : [];

  // Filter rows
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

  // Header
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

  // Empty / loading states
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
          <div style={{ color: 'var(--col-dim)', fontSize: '13px', marginBottom: 12 }}>
            No rankings data
          </div>
          <div style={{ color: 'var(--col-dim)', fontSize: '11px', marginBottom: 20 }}>
            Press <span style={{ color: 'var(--col-amber)' }}>▶ RUN SCAN</span> to generate rankings for {selectedUniverse}
          </div>
        </div>
      </div>
    );
  }

  const items = virtualizer.getVirtualItems();

  return (
    <div className="rankings-wrap">
      <Header />

      {/* Table header */}
      <div style={{ overflowX: 'auto', flexShrink: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--col-amber)', opacity: 0.7 }}>
              {['#','TICKER','SECTOR','SCORE','ALPHA','MOAT','Z','SLOAN','FCF','SORT','β','STRAT','SS','R:R','ENTRY','TP','SL','GATE','VERDICT'].map((h) => (
                <th key={h} style={{
                  color: 'var(--col-amber)', fontSize: '9px', padding: '4px 6px',
                  textAlign: h === '#' || h === 'TICKER' || h === 'SECTOR' || h === 'STRAT' ? 'left' : 'right',
                  whiteSpace: 'nowrap', fontWeight: 500, letterSpacing: '0.5px',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        </table>
      </div>

      {/* Virtual body */}
      <div className="table-scroll-wrap" ref={parentRef} style={{ overflowY: 'auto', overflowX: 'auto' }}>
        <div style={{ height: virtualizer.getTotalSize(), width: '100%', minWidth: 1100, position: 'relative' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100, tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: 32 }} /><col style={{ width: 80 }} /><col style={{ width: 100 }} />
              <col style={{ width: 56 }} /><col style={{ width: 52 }} /><col style={{ width: 52 }} />
              <col style={{ width: 44 }} /><col style={{ width: 52 }} /><col style={{ width: 44 }} />
              <col style={{ width: 48 }} /><col style={{ width: 36 }} /><col style={{ width: 88 }} />
              <col style={{ width: 36 }} /><col style={{ width: 44 }} /><col style={{ width: 64 }} />
              <col style={{ width: 64 }} /><col style={{ width: 64 }} /><col style={{ width: 44 }} />
              <col style={{ width: 72 }} />
            </colgroup>
            <tbody>
              {items.map((vRow) => {
                const row = filteredRows[vRow.index];
                const rank = vRow.index + 1;
                return (
                  <tr
                    key={row.ticker}
                    style={{
                      position: 'absolute', top: vRow.start, left: 0, width: '100%',
                      height: vRow.size, display: 'table', tableLayout: 'fixed',
                      cursor: 'pointer', borderBottom: '1px solid #141414',
                    }}
                    onClick={() => setSelectedTicker(row.ticker)}
                  >
                    <td style={{ fontSize: '10px', padding: '2px 6px', color: 'var(--col-amber)', textAlign: 'left' }}>{rank}</td>
                    <td style={{ fontSize: '11px', padding: '2px 6px', color: 'var(--col-amber)', textAlign: 'left', fontWeight: 500 }}>{row.ticker}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', color: 'var(--col-dim)', textAlign: 'left' }}>{row.sector}</td>
                    <td style={{ fontSize: '11px', padding: '2px 6px', textAlign: 'right', color: scoreColor(row.rank_score), fontWeight: 500 }}>{fmt.score(row.rank_score)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: scoreColor(row.alpha) }}>{fmt.score(row.alpha)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: (row.moat ?? 0) >= 0 ? 'var(--col-buy)' : 'var(--col-red)' }}>{fmt.float2(row.moat)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: (row.z ?? 99) < 1.81 ? 'var(--col-red)' : 'var(--col-body)' }}>{fmt.z(row.z)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: (row.sloan ?? 0) > 0.1 ? 'var(--col-red)' : 'var(--col-body)' }}>{fmt.float2(row.sloan)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right' }}>{fmt.float2(row.fcf_q)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: (row.sortino ?? 0) >= 1 ? 'var(--col-buy)' : 'var(--col-body)' }}>{fmt.float2(row.sortino)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right' }}>{fmt.float2(row.beta)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'left', color: 'var(--col-body)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.strategy}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: riskColor(row.signal_str) }}>{row.signal_str}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: row.rr >= 1.5 ? 'var(--col-buy)' : 'var(--col-dim)' }}>{row.rr.toFixed(1)}x</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: 'var(--col-amber)' }}>{fmt.price(row.entry)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: 'var(--col-buy)' }}>{fmt.price(row.tp)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right', color: 'var(--col-red)' }}>{fmt.price(row.sl)}</td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right' }}><GateCell g3={row.gate3} g4={row.gate4} /></td>
                    <td style={{ fontSize: '10px', padding: '2px 6px', textAlign: 'right' }}><VerdictPill verdict={row.verdict} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
