import { useEffect, useRef } from 'react';
import { createChart, type IChartApi, type ISeriesApi, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { useActiveTab } from '../../hooks/useActiveTab';
import { useStockHistory } from '../../hooks/useStockHistory';

interface Props { tabId: string }

export function PriceTargetWidget({ tabId: _ }: Props) {
  const { activeTicker } = useActiveTab();
  const { data, isLoading, isError } = useStockHistory(activeTicker, '1y');

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const candleRef    = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volRef       = useRef<ISeriesApi<'Histogram'> | null>(null);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background:  { color: 'transparent' },
        textColor:   '#6B6B6B',
        fontFamily:  "'IBM Plex Mono', monospace",
        fontSize:    10,
      },
      grid: {
        vertLines:   { color: '#1E1E1E' },
        horzLines:   { color: '#1E1E1E' },
      },
      crosshair: {
        vertLine:    { color: '#FF8C00', width: 1, style: 3 },
        horzLine:    { color: '#FF8C00', width: 1, style: 3 },
      },
      timeScale: {
        borderColor: '#1E1E1E',
        timeVisible: true,
      },
      rightPriceScale: { borderColor: '#1E1E1E' },
      handleScroll:    true,
      handleScale:     true,
    });

    const candle = chart.addSeries(CandlestickSeries, {
      upColor:        '#00FF87',
      downColor:      '#FF3B30',
      borderUpColor:  '#00FF87',
      borderDownColor:'#FF3B30',
      wickUpColor:    '#00FF87',
      wickDownColor:  '#FF3B30',
    });

    const vol = chart.addSeries(HistogramSeries, {
      color:      '#FF8C00',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });

    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current  = chart;
    candleRef.current = candle;
    volRef.current    = vol;

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, containerRef.current.clientHeight);
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current  = null;
      candleRef.current = null;
      volRef.current    = null;
    };
  }, []);

  // Feed data when it changes
  useEffect(() => {
    if (!data || !candleRef.current || !volRef.current) return;
    const bars = data.bars;
    candleRef.current.setData(bars.map(b => ({
      time:  b.time as unknown as import('lightweight-charts').Time,
      open:  b.open,
      high:  b.high,
      low:   b.low,
      close: b.close,
    })));
    volRef.current.setData(bars.map(b => ({
      time:  b.time as unknown as import('lightweight-charts').Time,
      value: b.volume,
      color: b.close >= b.open ? 'rgba(0,255,135,0.3)' : 'rgba(255,59,48,0.3)',
    })));
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div className="price-target-wrap">
      {isLoading && <div className="widget-loading">Loading {activeTicker}…</div>}
      {isError   && <div className="widget-error">Failed to load {activeTicker}</div>}
      <div ref={containerRef} className="price-target-chart" style={{ opacity: isLoading ? 0.3 : 1 }} />
    </div>
  );
}
