import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../../store/useAppStore';
import { useScanStream } from '../../hooks/useScanStream';
import { formatDuration } from '../../lib/format';
import type { ScanStreamEvent } from '../../types/api';

export function ScanProgressOverlay() {
  const { scanJobId, selectedUniverse, clearScan } = useAppStore();
  const [progress, setProgress] = useState<ScanStreamEvent | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [failed, setFailed] = useState<string | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    if (!scanJobId) return;
    setElapsed(0);
    setFailed(null);
    setProgress(null);
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [scanJobId]);

  useScanStream({
    jobId: scanJobId,
    onProgress: (e) => setProgress(e),
    onCompleted: (e) => {
      setProgress(e);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['rankings', selectedUniverse] });
        clearScan();
      }, 800);
    },
    onFailed: (e) => {
      setFailed(e.job_id ? 'Scan failed.' : 'Unknown error.');
    },
  });

  if (!scanJobId) return null;

  const pct = progress?.progress_pct ?? 0;
  const barFilled = Math.round((pct / 100) * 40);
  const completed = progress?.completed ?? 0;
  const total = progress?.total ?? 0;
  const eta = total > 0 && completed > 0 ? Math.round((elapsed / completed) * (total - completed)) : null;

  return (
    <div
      className="overlay-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Scan progress"
    >
      <div className="scan-overlay">
        <div className="scan-title">SCANNING {selectedUniverse} UNIVERSE</div>

        {failed ? (
          <>
            <div style={{ color: 'var(--col-red)', marginTop: 16, fontSize: '12px' }}>{failed}</div>
            <button className="scan-btn" style={{ marginTop: 16 }} onClick={clearScan}>✕ CLOSE</button>
          </>
        ) : (
          <>
            <div className="scan-progress-bar-wrap" aria-live="polite">
              <div className="scan-progress-bar">
                <div className="scan-progress-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="scan-progress-label">
                {completed} / {total || '?'}
              </span>
            </div>

            <div style={{ color: 'var(--col-dim)', fontSize: '11px', marginTop: 8 }}>
              {progress?.current_ticker ? `Current: ${progress.current_ticker}` : 'Initializing…'}
            </div>

            <div style={{ color: 'var(--col-dim)', fontSize: '11px', marginTop: 4 }}>
              Elapsed: {formatDuration(elapsed)}
              {eta != null ? `   ETA: ~${formatDuration(eta)}` : ''}
            </div>

            <button
              className="scan-btn"
              style={{ marginTop: 20, opacity: 0.6 }}
              onClick={clearScan}
            >
              ✕ cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
