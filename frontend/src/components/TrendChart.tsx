import React from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from "recharts";
import type { TrendPoint } from "../api/client";

interface TrendChartProps {
  data: TrendPoint[];
  loading?: boolean;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-md px-3 py-2 text-xs">
      <p className="font-semibold text-slate-600 mb-1">{label}</p>
      <p className="text-teal-600">Score: <strong>{payload[0]?.value?.toFixed(2)}</strong></p>
      {payload[1] && <p className="text-slate-500">Reviews: <strong>{payload[1].value}</strong></p>}
    </div>
  );
}

export default function TrendChart({ data, loading }: TrendChartProps) {
  if (loading) {
    return <div className="h-64 bg-slate-50 rounded-xl animate-pulse" />;
  }

  if (!data.length) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-400 text-sm bg-slate-50 rounded-xl">
        Not enough data yet for a trend chart.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <p className="text-sm font-semibold text-slate-600 mb-3">Score trend</p>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0F6E56" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#0F6E56" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "#94a3b8" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 5]}
            tick={{ fontSize: 11, fill: "#94a3b8" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="score"
            stroke="#0F6E56"
            strokeWidth={2}
            fill="url(#scoreGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
