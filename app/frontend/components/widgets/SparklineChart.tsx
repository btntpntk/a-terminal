import { LineChart, Line, YAxis, ResponsiveContainer } from 'recharts';

interface Props {
  data: number[];
  positive: boolean;
  width?: number;
  height?: number;
}

export function SparklineChart({ data, positive, width = 80, height = 28 }: Props) {
  if (!data || data.length < 2) return <span style={{ width, display: 'inline-block' }} />;

  const chartData = data.map((v, i) => ({ i, v }));
  const color = positive ? 'var(--col-green)' : 'var(--col-red)';

  const min = Math.min(...data);
  const max = Math.max(...data);
  const pad = (max - min) * 0.05 || min * 0.005;
  const domain: [number, number] = [min - pad, max + pad];

  return (
    <div style={{ width, height, display: 'inline-block' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <YAxis domain={domain} hide />
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
