import React from "react";
import { AlertTriangle, ThumbsUp, ThumbsDown, Minus, Star } from "lucide-react";
import type { Review } from "../api/client";

const PLATFORM_COLORS: Record<string, string> = {
  google:     "bg-blue-100 text-blue-700",
  zomato:     "bg-red-100 text-red-700",
  swiggy:     "bg-orange-100 text-orange-700",
  trustpilot: "bg-green-100 text-green-700",
  glassdoor:  "bg-emerald-100 text-emerald-700",
  playstore:  "bg-indigo-100 text-indigo-700",
};

const RISK_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-700 border-red-200",
  HIGH:     "bg-orange-100 text-orange-700 border-orange-200",
  MEDIUM:   "bg-yellow-100 text-yellow-700 border-yellow-200",
  LOW:      "bg-blue-100 text-blue-700 border-blue-200",
  NONE:     "",
};

function SentimentIcon({ sentiment }: { sentiment: string }) {
  if (sentiment === "positive") return <ThumbsUp size={13} className="text-emerald-500" />;
  if (sentiment === "negative") return <ThumbsDown size={13} className="text-red-500" />;
  return <Minus size={13} className="text-slate-400" />;
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={11}
          className={i <= Math.round(rating) ? "text-amber-400 fill-amber-400" : "text-slate-200 fill-slate-200"}
        />
      ))}
    </div>
  );
}

interface ReviewCardProps {
  review: Review;
}

export function ReviewCard({ review }: ReviewCardProps) {
  const riskColor = RISK_COLORS[review.risk_level] || "";
  const platformColor = PLATFORM_COLORS[review.source_platform] || "bg-slate-100 text-slate-600";

  return (
    <div className={`bg-white rounded-xl border p-4 transition-all hover:shadow-sm ${review.risk_level !== "NONE" ? "border-l-4 border-l-red-400" : "border-slate-200"}`}>
      {/* Top row */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${platformColor}`}>
            {review.source_platform}
          </span>
          <StarRating rating={review.rating} />
          <SentimentIcon sentiment={review.sentiment} />
          {review.risk_level !== "NONE" && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${riskColor}`}>
              <AlertTriangle size={10} className="inline mr-1" />
              {review.risk_level}
            </span>
          )}
        </div>
        <span className="text-xs text-slate-400 shrink-0">
          {new Date(review.review_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
        </span>
      </div>

      {/* Review text */}
      <p className="text-sm text-slate-700 leading-relaxed line-clamp-3">{review.text_cleaned}</p>

      {/* Bottom row */}
      <div className="flex items-center justify-between mt-3">
        <div className="flex gap-1.5 flex-wrap">
          {review.topics.slice(0, 3).map((t) => (
            <span key={t} className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">{t}</span>
          ))}
        </div>
        <span className="text-xs text-slate-400">{review.reviewer_name || "Anonymous"}</span>
      </div>

      {/* Risk flags */}
      {review.risk_flags.length > 0 && (
        <div className="mt-2 flex gap-1 flex-wrap">
          {review.risk_flags.map((f) => (
            <span key={f} className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full border border-red-100">{f.replace(/_/g, " ")}</span>
          ))}
        </div>
      )}
    </div>
  );
}

interface ReviewFeedProps {
  reviews: Review[];
  loading?: boolean;
}

export default function ReviewFeed({ reviews, loading }: ReviewFeedProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse">
            <div className="h-3 bg-slate-100 rounded w-1/3 mb-3" />
            <div className="h-3 bg-slate-100 rounded w-full mb-2" />
            <div className="h-3 bg-slate-100 rounded w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  if (!reviews.length) {
    return (
      <div className="text-center py-12 text-slate-400">
        <p className="text-sm">No reviews found.</p>
        <p className="text-xs mt-1">Try adjusting your filters or search query.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reviews.map((r) => (
        <ReviewCard key={r.message_id} review={r} />
      ))}
    </div>
  );
}
