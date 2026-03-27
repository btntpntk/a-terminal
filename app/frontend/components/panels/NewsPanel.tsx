interface NewsItem {
  id: number;
  headline: string;
  source: string;
  time: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
}

// Mock data — replace with real API feed later
const MOCK_NEWS: NewsItem[] = [
  {
    id: 1,
    headline: "Fed holds rates at 4.25–4.50%, signals no cuts before mid-2026.",
    source: "Reuters",
    time: "1h ago",
    sentiment: "neutral",
  },
  {
    id: 2,
    headline: "Thailand's SET Index falls 1.3% as foreign investors post net selling for 8th straight session, led by financials and real estate outflows totalling ฿4.2B.",
    source: "Bangkok Post",
    time: "3h ago",
    sentiment: "bearish",
  },
  {
    id: 3,
    headline: "NVIDIA reports record Q4 revenue of $39.3B, up 78% YoY, beating estimates by $2.1B. Data center surges on AI chip demand. Stock +8% pre-market on strong FY2026 guidance and $10B buyback announcement.",
    source: "Bloomberg",
    time: "5h ago",
    sentiment: "bullish",
  },
];

const SENTIMENT_COLOR: Record<NewsItem['sentiment'], string> = {
  bullish: 'var(--col-buy)',
  bearish: 'var(--col-red)',
  neutral: 'var(--col-amber)',
};

function QuoteBox({ item }: { item: NewsItem }) {
  const lineColor = SENTIMENT_COLOR[item.sentiment];
  return (
    <div style={{
      display: 'flex',
      gap: 0,
      marginBottom: 10,
    }}>
      {/* Vertical accent line */}
      <div style={{
        width: 3,
        flexShrink: 0,
        background: lineColor,
        borderRadius: 0,
        alignSelf: 'stretch',
      }} />

      {/* Content */}
      <div style={{ paddingLeft: 10, paddingRight: 4 }}>
        <div style={{
          color: 'var(--col-body)',
          fontSize: '11px',
          lineHeight: '1.5',
          marginBottom: 4,
        }}>
          {item.headline}
        </div>
        <div style={{
          color: 'var(--col-dim)',
          fontSize: '10px',
          display: 'flex',
          gap: 6,
        }}>
          <span style={{ color: lineColor, opacity: 0.8 }}>{item.source}</span>
          <span>·</span>
          <span>{item.time}</span>
        </div>
      </div>
    </div>
  );
}

export function NewsPanel() {
  return (
    <div className="panel-section" style={{ height: '100%', overflow: 'auto' }}>
      <div className="section-header" style={{ marginBottom: 10 }}>
        <span className="section-label">MARKET NEWS</span>
      </div>

      {MOCK_NEWS.map((item) => (
        <QuoteBox key={item.id} item={item} />
      ))}
    </div>
  );
}
