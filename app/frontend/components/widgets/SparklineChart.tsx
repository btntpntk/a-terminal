import { LineChart, Line, ResponsiveContainer } from 'recharts';

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

  return (
    <div style={{ width, height, display: 'inline-block' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
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
