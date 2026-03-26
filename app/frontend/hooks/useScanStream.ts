import { useEffect, useRef } from 'react';
import { BASE_URL } from '../lib/api';
import type { ScanStreamEvent } from '../types/api';

interface UseScanStreamOptions {
  jobId: string | null;
  onProgress: (event: ScanStreamEvent) => void;
  onCompleted: (event: ScanStreamEvent) => void;
  onFailed: (event: ScanStreamEvent) => void;
}

export function useScanStream({ jobId, onProgress, onCompleted, onFailed }: UseScanStreamOptions) {
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(`${BASE_URL}/api/scan/stream/${jobId}`);
    esRef.current = es;

    const handle = (e: MessageEvent) => {
      try {
        const data: ScanStreamEvent = JSON.parse(e.data);
        if (data.status === 'completed') {
          onCompleted(data);
          es.close();
        } else if (data.status === 'failed') {
          onFailed(data);
          es.close();
        } else {
          onProgress(data);
        }
      } catch {
        // ignore parse errors
      }
    };

    es.addEventListener('message', handle);
    es.addEventListener('progress', handle);
    es.addEventListener('completed', handle);
    es.addEventListener('failed', handle);

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [jobId]);
}
