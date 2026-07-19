import React, { useState, useMemo } from "react";
import { Building2 } from "lucide-react";
import { useScores, useReviews, useAlerts, useTrend, useSemanticSearch } from "../hooks/useDashboardData";
import StatsHeader from "../components/StatsHeader";
import Tabs, { TabKey } from "../components/Tabs";
import ScoreCard from "../components/ScoreCard";
import TrendChart from "../components/TrendChart";
import TopicBreakdown from "../components/TopicBreakdown";
import ReviewFeed from "../components/ReviewFeed";
import FilterBar from "../components/FilterBar";
import AlertInbox from "../components/AlertInbox";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [sentiment, setSentiment] = useState("all");
  const [platform, setPlatform] = useState("all");
  const [semanticMode, setSemanticMode] = useState(false);

  const { data: scores = [], isLoading: scoresLoading } = useScores();
  const { data: alerts = [], isLoading: alertsLoading } = useAlerts();
  const { data: trend = [], isLoading: trendLoading } = useTrend(selectedLocation);

  const filters = useMemo(() => ({
    sentiment: sentiment === "all" ? undefined : sentiment,
    platform: platform === "all" ? undefined : platform,
    query: semanticMode ? undefined : (searchQuery || undefined),
  }), [sentiment, platform, searchQuery, semanticMode]);

  const { data: standardReviews = [], isLoading: reviewsLoading } = useReviews(filters);
  const { data: semanticReviews = [], isLoading: semanticLoading } = useSemanticSearch(searchQuery, semanticMode);

  const reviews = semanticMode ? semanticReviews : standardReviews;
  const reviewsLoadingState = semanticMode ? semanticLoading : reviewsLoading;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-teal-600 text-white rounded-lg p-1.5">
              <Building2 size={18} />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-800">Reputation Intelligence Platform</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs text-slate-400">Live</span>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6">
        <StatsHeader scores={scores} alerts={alerts} />

        <Tabs active={activeTab} onChange={setActiveTab} alertCount={alerts.filter(a => a.severity === "critical").length} />

        {activeTab === "overview" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-3">
              <p className="text-sm font-semibold text-slate-600">Locations</p>
              {scoresLoading ? (
                <div className="grid sm:grid-cols-2 gap-3">
                  {[1, 2].map((i) => <div key={i} className="h-32 bg-white rounded-xl border border-slate-200 animate-pulse" />)}
                </div>
              ) : scores.length === 0 ? (
                <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-sm text-slate-400">
                  No location scores yet. Publish a review to see data here.
                </div>
              ) : (
                <div className="grid sm:grid-cols-2 gap-3">
                  {scores.map((s) => (
                    <ScoreCard
                      key={s.location_id}
                      score={s}
                      selected={s.location_id === selectedLocation}
                      onClick={() => setSelectedLocation(s.location_id)}
                    />
                  ))}
                </div>
              )}

              {selectedLocation && (
                <div className="mt-4">
                  <TrendChart data={trend} loading={trendLoading} />
                </div>
              )}
            </div>

            <div className="space-y-4">
              <TopicBreakdown locationId={selectedLocation} />
              <div>
                <p className="text-sm font-semibold text-slate-600 mb-3">Recent alerts</p>
                <AlertInbox alerts={alerts.slice(0, 3)} loading={alertsLoading} />
              </div>
            </div>
          </div>
        )}

        {activeTab === "reviews" && (
          <div>
            <FilterBar
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              sentiment={sentiment}
              onSentimentChange={setSentiment}
              platform={platform}
              onPlatformChange={setPlatform}
              semanticMode={semanticMode}
              onSemanticToggle={() => setSemanticMode((v) => !v)}
            />
            <ReviewFeed reviews={reviews} loading={reviewsLoadingState} />
          </div>
        )}

        {activeTab === "alerts" && (
          <AlertInbox alerts={alerts} loading={alertsLoading} />
        )}
      </main>
    </div>
  );
}
