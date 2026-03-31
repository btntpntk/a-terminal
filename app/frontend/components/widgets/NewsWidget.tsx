// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

interface NewsItem {
  id: number;
  headline: string;
  source: string;
  time: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
}

const MOCK_NEWS: NewsItem[] = [
  {
    id: 1,
    headline: "DEMO: Fed holds rates at 4.25–4.50%, signals no cuts before mid-2026.",
    source: "Reuters",
    time: "1h ago",
    sentiment: "neutral",
  },
  {
    id: 2,
    headline: "DEMO: Thailand's SET Index falls 1.3% as foreign investors post net selling for 8th straight session, led by financials and real estate outflows totalling ฿4.2B.",
    source: "Bangkok Post",
    time: "3h ago",
    sentiment: "bearish",
  },
  {
    id: 3,
    headline: "DEMO: NVIDIA reports record Q4 revenue of $39.3B, up 78% YoY, beating estimates by $2.1B. Data center surges on AI chip demand. Stock +8% pre-market.",
    source: "Bloomberg",
    time: "5h ago",
    sentiment: "bullish",
  },
  {
    id: 4,
    headline: "DEMO: Global semiconductor sales rise 18% YoY in February, led by AI/HPC demand. TSMC, Samsung benefit most from sustained order backlog.",
    source: "Wall Street Journal",
    time: "6h ago",
    sentiment: "bullish",
  },
];

const SENTIMENT_COLOR = { bullish: 'var(--col-buy)', bearish: 'var(--col-red)', neutral: 'var(--col-amber)' };
const SENTIMENT_LABEL = { bullish: 'BULL', bearish: 'BEAR', neutral: 'NEUT' };

export function NewsWidget({ tabId: _ }: Props) {
  return (
    <div className="news-widget-wrap">
      {MOCK_NEWS.map(item => {
        const color = SENTIMENT_COLOR[item.sentiment];
        return (
          <div key={item.id} className="news-item">
            <div className="news-accent" style={{ background: color }} />
            <div className="news-content">
              <div className="news-headline">{item.headline}</div>
              <div className="news-meta">
                <span className="news-sentiment" style={{ color }}>{SENTIMENT_LABEL[item.sentiment]}</span>
                <span className="news-source">{item.source}</span>
                <span className="news-time">{item.time}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
