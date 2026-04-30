import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useRankings, useUniverses } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { useTabStore } from '../../store/useTabStore';
import { fmt, scoreColor, riskColor } from '../../lib/format';
import { api } from '../../lib/api';
import type { TickerRow } from '../../types/api';

interface Props { tabId: string }

const COL_PX    = [32, 80, 96, 52, 48, 44, 44, 48, 40, 44, 36, 80, 36, 40, 60, 60, 60, 40, 68];
const COL_TOTAL = COL_PX.reduce((a, b) => a + b, 0);
const COL_PCT   = COL_PX.map(w => `${((w / COL_TOTAL) * 100).toFixed(3)}%`);
const COL_HEADS = ['#','TICKER','SECTOR','SCORE','ALPHA','MOAT','Z','SLOAN','FCF','SORT','β','STRAT','SS','R:R','ENTRY','TP','SL','GATE','VERDICT'];
const LEFT_ALIGN = new Set(['#','TICKER','SECTOR','STRAT']);

const VERDICT_LABELS: Record<string, string> = { BUY:'BUY', FUND_ONLY:'FUND', TECH_ONLY:'TECH', FAIL:'FAIL' };

function VerdictPill({ verdict }: { verdict: TickerRow['verdict'] }) {
  const cls = verdict === 'BUY' ? 'pill-buy' : verdict === 'FUND_ONLY' ? 'pill-fund' : verdict === 'TECH_ONLY' ? 'pill-tech' : 'pill-fail';
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

function cell(i: number, extra?: React.CSSProperties): React.CSSProperties {
  return {
    width: COL_PCT[i], flexShrink: 0, overflow: 'hidden',
    textOverflow: 'ellipsis', whiteSpace: 'nowrap', padding: '0 4px',
    textAlign: LEFT_ALIGN.has(COL_HEADS[i]) ? 'left' : 'right',
    ...extra,
  };
}

export function RankingsWidget({ tabId }: Props) {
  const {
    selectedUniverse, setUniverse,
    verdictFilter, sectorFilter, tickerSearch,
    setFilters, setScanJob,
  } = useAppStore();
  const setActiveTicker = useTabStore(s => s.setActiveTicker);

  const { data: universes } = useUniverses();
  const { data, isLoading, error } = useRankings();
  const rankings = useAppStore(s => s.rankings) ?? data;
  const parentRef = useRef<HTMLDivElement>(null);

  const handleScan = async () => {
    try {
      const { job_id } = await api.startScan(selectedUniverse);
      setScanJob(job_id);
    } catch (e) {
      console.error('Scan failed', e);
    }
  };

  const allSectors = rankings
    ? Array.from(new Set(rankings.rows.map(r => r.sector))).sort()
    : [];

  const filteredRows: TickerRow[] = (rankings?.rows ?? []).filter(r => {
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
    estimateSize: () => 26,
    overscan: 10,
  });

  const verdictButtons: Array<'ALL' | 'BUY' | 'FUND_ONLY' | 'TECH_ONLY' | 'FAIL'> = ['ALL','BUY','FUND_ONLY','TECH_ONLY','FAIL'];

  // ── Toolbar ─────────────────────────────────────────────
  const Toolbar = () => (
    <div className="rw-toolbar">
      {/* Universe selector */}
      <select
        className="universe-select"
        style={{ height: 26, fontSize: '10px' }}
        value={selectedUniverse}
        onChange={e => setUniverse(e.target.value)}
      >
        {universes?.map(u => (
          <option key={u.key} value={u.key}>{u.display_name}</option>
        )) ?? <option value="SET100">SET100 Thailand</option>}
      </select>

      {/* Verdict filters */}
      <div className="filter-group">
        {verdictButtons.map(v => (
          <button
            key={v}
            className={`filter-btn${verdictFilter === v ? ' active' : ''}`}
            onClick={() => setFilters({ verdictFilter: v })}
          >
            {v === 'FUND_ONLY' ? 'FUND' : v === 'TECH_ONLY' ? 'TECH' : v}
          </button>
        ))}
      </div>

      {/* Sector filter */}
      <select
        className="universe-select"
        style={{ height: 24, fontSize: '10px', borderColor: 'var(--col-border)', color: 'var(--col-dim)' }}
        value={sectorFilter}
        onChange={e => setFilters({ sectorFilter: e.target.value })}
      >
        <option value="">All Sectors</option>
        {allSectors.map(s => <option key={s} value={s}>{s}</option>)}
      </select>

      {/* Ticker search */}
      <input
        className="search-input"
        type="text"
        placeholder="Search…"
        value={tickerSearch}
        onChange={e => setFilters({ tickerSearch: e.target.value })}
        style={{ maxWidth: 120 }}
      />

      <div style={{ flex: 1 }} />

      {/* RUN SCAN */}
      <button className="scan-btn" onClick={handleScan}>▶ RUN SCAN</button>
    </div>
  );

  // ── No data state ────────────────────────────────────────
  if (!isLoading && (error || !rankings)) {
    return (
      <div className="rw-wrap">
        <Toolbar />
        <div className="rw-empty">
          <div style={{ color: 'var(--col-dim)', fontSize: '13px', marginBottom: 8 }}>No rankings data</div>
          <div style={{ color: 'var(--col-dim)', fontSize: '11px', marginBottom: 20 }}>
            Press <span style={{ color: 'var(--col-amber)' }}>▶ RUN SCAN</span> to scan {selectedUniverse}
          </div>
          <button className="scan-btn" style={{ fontSize: '13px', padding: '6px 24px' }} onClick={handleScan}>
            ▶ RUN SCAN
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="rw-wrap">
        <Toolbar />
        <div className="widget-loading">Loading rankings…</div>
      </div>
    );
  }

  return (
    <div className="rw-wrap">
      <Toolbar />

      {/* Column header */}
      <div className="rw-col-header">
        {COL_HEADS.map((h, i) => (
          <div key={h} style={{
            width: COL_PCT[i], flexShrink: 0,
            color: 'var(--col-amber)', fontSize: '9px',
            padding: '0 4px',
            textAlign: LEFT_ALIGN.has(h) ? 'left' : 'right',
            whiteSpace: 'nowrap', fontWeight: 500, letterSpacing: '0.5px',
            overflow: 'hidden', opacity: 0.85,
          }}>{h}</div>
        ))}
      </div>

      {/* Virtual rows */}
      <div className="rw-scroll" ref={parentRef}>
        <div style={{ position: 'relative', height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map(vRow => {
            const row = filteredRows[vRow.index];
            return (
              <div
                key={row.ticker}
                style={{
                  position: 'absolute', top: vRow.start, left: 0,
                  width: '100%', height: vRow.size,
                  display: 'flex', alignItems: 'center',
                  cursor: 'pointer', borderBottom: '1px solid #141414',
                }}
                onClick={() => setActiveTicker(tabId, row.ticker)}
              >
                <div style={cell(0,  { fontSize: '10px', color: 'var(--col-amber)' })}>{vRow.index + 1}</div>
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
      <div className="rw-footer">
        {filteredRows.length} / {rankings!.total_scanned} shown
        &nbsp;·&nbsp;BUY: <span style={{ color: 'var(--col-buy)' }}>{rankings!.buy_count}</span>
        &nbsp;·&nbsp;FAIL: {rankings!.failed_count}
      </div>

    </div>
  );
}
