import React from "react";
import { Search, Sparkles } from "lucide-react";

interface FilterBarProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  sentiment: string;
  onSentimentChange: (s: string) => void;
  platform: string;
  onPlatformChange: (p: string) => void;
  semanticMode: boolean;
  onSemanticToggle: () => void;
}

const SENTIMENTS = ["all", "positive", "negative", "neutral"];
const PLATFORMS  = ["all", "google", "zomato", "swiggy", "trustpilot", "glassdoor"];

export default function FilterBar({
  searchQuery, onSearchChange,
  sentiment, onSentimentChange,
  platform, onPlatformChange,
  semanticMode, onSemanticToggle,
}: FilterBarProps) {
  return (
    <div className="flex flex-col sm:flex-row gap-2 mb-4">
      {/* Search input */}
      <div className="relative flex-1">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={semanticMode ? "Search by meaning, e.g. 'complaints about hygiene'..." : "Search reviews..."}
          className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
        />
      </div>

      {/* Semantic toggle */}
      <button
        onClick={onSemanticToggle}
        className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap
          ${semanticMode
            ? "bg-purple-50 border-purple-300 text-purple-700"
            : "bg-white border-slate-200 text-slate-500 hover:bg-slate-50"}`}
      >
        <Sparkles size={13} />
        Semantic search
      </button>

      {/* Sentiment filter */}
      <select
        value={sentiment}
        onChange={(e) => onSentimentChange(e.target.value)}
        className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500"
      >
        {SENTIMENTS.map((s) => (
          <option key={s} value={s}>{s === "all" ? "All sentiment" : s.charAt(0).toUpperCase() + s.slice(1)}</option>
        ))}
      </select>

      {/* Platform filter */}
      <select
        value={platform}
        onChange={(e) => onPlatformChange(e.target.value)}
        className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500"
      >
        {PLATFORMS.map((p) => (
          <option key={p} value={p}>{p === "all" ? "All platforms" : p.charAt(0).toUpperCase() + p.slice(1)}</option>
        ))}
      </select>
    </div>
  );
}
