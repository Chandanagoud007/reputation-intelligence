import React from "react";
import { TrendingUp, TrendingDown, Minus, MapPin, Star } from "lucide-react";
import type { ReputationScore } from "../api/client";

interface ScoreCardProps {
  score: ReputationScore;
  onClick?: () => void;
  selected?: boolean;
}

function scoreColor(score: number): string {
  if (score >= 4.0) return "text-emerald-600";
  if (score >= 3.0) return "text-amber-500";
  return "text-red-500";
}

function scoreBg(score: number): string {
  if (score >= 4.0) return "bg-emerald-50 border-emerald-200";
  if (score >= 3.0) return "bg-amber-50 border-amber-200";
  return "bg-red-50 border-red-200";
}

function SentimentBar({ positive, negative, neutral }: { positive: number; negative: number; neutral: number }) {
  const total = positive + negative + neutral || 1;
  return (
    <div className="flex h-1.5 rounded-full overflow-hidden gap-0.5">
      <div className="bg-emerald-400 rounded-full" style={{ width: `${(positive / total) * 100}%` }} />
      <div className="bg-slate-300 rounded-full" style={{ width: `${(neutral / total) * 100}%` }} />
      <div className="bg-red-400 rounded-full" style={{ width: `${(negative / total) * 100}%` }} />
    </div>
  );
}

export default function ScoreCard({ score, onClick, selected }: ScoreCardProps) {
  const sentimentTrend = score.sentiment_avg > 0.3 ? "up" : score.sentiment_avg < -0.1 ? "down" : "flat";

  return (
    <div
      onClick={onClick}
      className={`
        rounded-xl border p-4 cursor-pointer transition-all duration-150
        hover:shadow-md hover:-translate-y-0.5
        ${selected ? "ring-2 ring-teal-500 border-teal-300 bg-white shadow-md" : "bg-white border-slate-200"}
      `}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">{score.brand_name}</p>
          <div className="flex items-center gap-1 mt-0.5">
            <MapPin size={11} className="text-slate-400" />
            <p className="text-sm font-semibold text-slate-700">{score.location_name}</p>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">{score.region_name}</p>
        </div>
        <div className={`rounded-lg px-3 py-1.5 border ${scoreBg(score.score)}`}>
          <p className={`text-2xl font-bold tabular-nums ${scoreColor(score.score)}`}>
            {score.score.toFixed(1)}
          </p>
          <p className="text-xs text-slate-400 text-center">/ 5.0</p>
        </div>
      </div>

      {/* Sentiment bar */}
      <SentimentBar
        positive={score.positive_count}
        negative={score.negative_count}
        neutral={score.neutral_count}
      />

      {/* Stats row */}
      <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
        <div className="flex items-center gap-1">
          <Star size={11} className="text-amber-400 fill-amber-400" />
          <span>{score.rating_avg.toFixed(1)} avg rating</span>
        </div>
        <span>{score.review_count} reviews</span>
        <div className="flex items-center gap-0.5">
          {sentimentTrend === "up" && <TrendingUp size={12} className="text-emerald-500" />}
          {sentimentTrend === "down" && <TrendingDown size={12} className="text-red-500" />}
          {sentimentTrend === "flat" && <Minus size={12} className="text-slate-400" />}
          <span className={sentimentTrend === "up" ? "text-emerald-600" : sentimentTrend === "down" ? "text-red-500" : "text-slate-400"}>
            {(score.sentiment_avg * 100).toFixed(0)}% sentiment
          </span>
        </div>
      </div>
    </div>
  );
}
