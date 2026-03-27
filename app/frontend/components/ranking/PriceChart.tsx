import { useEffect, useRef } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
} from 'lightweight-charts';

interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface PriceChartProps {
  bars: Bar[];
  height?: number;
}

function calcRSI(bars: Bar[], period = 14): Array<{ time: string; value: number }> {
  if (bars.length < period + 1) return [];

  const result: Array<{ time: string; value: number }> = [];
  let avgGain = 0;
  let avgLoss = 0;

  // Initial average over first `period` changes
  for (let i = 1; i <= period; i++) {
    const diff = bars[i].close - bars[i - 1].close;
    if (diff > 0) avgGain += diff;
    else avgLoss += -diff;
  }
  avgGain /= period;
  avgLoss /= period;

  const rsi0 = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  result.push({ time: bars[period].time, value: parseFloat(rsi0.toFixed(2)) });

  // Wilder's smoothing for remaining bars
  for (let i = period + 1; i < bars.length; i++) {
    const diff = bars[i].close - bars[i - 1].close;
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    result.push({ time: bars[i].time, value: parseFloat(rsi.toFixed(2)) });
  }
  return result;
}

export function PriceChart({ bars, height = 340 }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;

    const chartOpts = {
      layout: {
        background: { type: ColorType.Solid, color: '#0d0d0d' },
        textColor: '#555',
        fontSize: 10,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      },
      grid: {
        vertLines: { color: '#161616' },
        horzLines: { color: '#161616' },
      },
      crosshair: {
        vertLine: { color: '#FF8C00', width: 1 as const, style: 3 as const },
        horzLine: { color: '#FF8C00', width: 1 as const, style: 3 as const },
      },
      timeScale: { borderColor: '#222', timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#222' },
      width: containerRef.current.clientWidth,
      height,
    };

    const chart = createChart(containerRef.current, chartOpts);

    // ── Pane 0: Candlesticks ──────────────────────────────────
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:         '#00ff87',
      downColor:       '#ff3b30',
      borderUpColor:   '#00ff87',
      borderDownColor: '#ff3b30',
      wickUpColor:     '#00ff87',
      wickDownColor:   '#ff3b30',
    }, 0);
    candleSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.05, bottom: 0.2 },
    });
    candleSeries.setData(bars);

    // ── Pane 0 overlay: Volume (bottom 20% of price pane) ────
    const volSeries = chart.addSeries(HistogramSeries, {
      color:        '#00ff8744',
      priceFormat:  { type: 'volume' as const },
      priceScaleId: 'volume',
    }, 0);
    volSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volSeries.setData(bars.map((b) => ({
      time:  b.time,
      value: b.volume,
      color: b.close >= b.open ? '#00ff8744' : '#ff3b3044',
    })));

    // ── Pane 1: RSI ───────────────────────────────────────────
    const rsiData = calcRSI(bars);
    if (rsiData.length > 0) {
      const rsiSeries = chart.addSeries(LineSeries, {
        color:       '#FF8C00',
        lineWidth:   1 as const,
        priceFormat: { type: 'price' as const, precision: 1, minMove: 0.1 },
      }, 1);
      rsiSeries.setData(rsiData);
      rsiSeries.priceScale().applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.1 },
        autoScale: false,
      });
      rsiSeries.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) });

      // Overbought / oversold reference lines
      const ob = chart.addSeries(LineSeries, {
        color: '#ff3b3066', lineWidth: 1 as const, lineStyle: 2 as const,
        priceFormat: { type: 'price' as const, precision: 0, minMove: 1 },
        crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      }, 1);
      ob.setData(rsiData.map((d) => ({ time: d.time, value: 70 })));

      const os = chart.addSeries(LineSeries, {
        color: '#00ff8766', lineWidth: 1 as const, lineStyle: 2 as const,
        priceFormat: { type: 'price' as const, precision: 0, minMove: 1 },
        crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false,
      }, 1);
      os.setData(rsiData.map((d) => ({ time: d.time, value: 30 })));
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => { ro.disconnect(); chart.remove(); };
  }, [bars, height]);

  return <div ref={containerRef} style={{ width: '100%', height }} />;
}
