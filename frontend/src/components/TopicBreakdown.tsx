import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import api from "../api/client";

interface TopicBreakdownProps {
  locationId?: string | null;
}

interface TopicCount {
  topic: string;
  count: number;
}

const COLORS = [
  "#0F6E56", "#3C3489", "#993C1D", "#854F0B",
  "#185FA5", "#A32D2D", "#5F5E5A", "#0F6E56", "#3C3489"
];

// Clean up raw topic slugs into readable labels
function formatTopic(raw: string): string {
  return raw
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

export default function TopicBreakdown({ locationId }: TopicBreakdownProps) {
  const [data, setData] = useState<TopicCount[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = { size: "200" };
    if (locationId) params.location_id = locationId;

    api.get("/reviews/topics", { params })
      .then((res) => setData(res.data.slice(0, 10)))
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [locationId]);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <p className="text-sm font-semibold text-slate-600 mb-3">Topics mentioned</p>
        <div className="h-48 animate-pulse bg-slate-50 rounded-lg" />
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <p className="text-sm font-semibold text-slate-600 mb-3">Topics mentioned</p>
        <p className="text-xs text-slate-400 text-center py-8">No topic data yet.</p>
      </div>
    );
  }

  const chartData = data.map((d) => ({ ...d, label: formatTopic(d.topic) }));
  const maxCount = Math.max(...chartData.map((d) => d.count));

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <p className="text-sm font-semibold text-slate-600 mb-1">Topics mentioned</p>
      <p className="text-xs text-slate-400 mb-3">Across all reviews</p>

      {/* Bar chart */}
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 32, top: 4, bottom: 0 }}>
          <XAxis type="number" hide domain={[0, maxCount * 1.1]} />
          <YAxis
            dataKey="label"
            type="category"
            tick={{ fontSize: 11, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
            width={100}
          />
          <Tooltip
            formatter={(value: number) => [value.toLocaleString(), "mentions"]}
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0", boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}
            cursor={{ fill: "#f8fafc" }}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={14} label={{ position: "right", fontSize: 10, fill: "#94a3b8" }}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Topic pills */}
      <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-slate-100">
        {chartData.map((d, i) => (
          <span
            key={d.topic}
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ backgroundColor: COLORS[i % COLORS.length] + "18", color: COLORS[i % COLORS.length] }}
          >
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
}
