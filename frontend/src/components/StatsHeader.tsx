import React from "react";
import { Building2, MessageSquare, AlertTriangle, TrendingUp } from "lucide-react";
import type { ReputationScore, Alert } from "../api/client";

interface StatsHeaderProps {
  scores: ReputationScore[];
  alerts: Alert[];
}

function StatTile({ icon: Icon, label, value, accent }: { icon: any; label: string; value: string | number; accent: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 px-4 py-3 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${accent}`}>
        <Icon size={16} />
      </div>
      <div>
        <p className="text-xs text-slate-400">{label}</p>
        <p className="text-lg font-bold text-slate-700 tabular-nums">{value}</p>
      </div>
    </div>
  );
}

export default function StatsHeader({ scores, alerts }: StatsHeaderProps) {
  const totalReviews = scores.reduce((sum, s) => sum + s.review_count, 0);
  const avgScore     = scores.length ? scores.reduce((sum, s) => sum + s.score, 0) / scores.length : 0;
  const criticalAlerts = alerts.filter((a) => a.severity === "critical").length;
  const locationCount  = scores.length;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
      <StatTile icon={Building2}      label="Locations"       value={locationCount}             accent="bg-blue-50 text-blue-600" />
      <StatTile icon={MessageSquare}  label="Total reviews"   value={totalReviews}               accent="bg-teal-50 text-teal-600" />
      <StatTile icon={TrendingUp}     label="Avg score"       value={avgScore.toFixed(2)}        accent="bg-emerald-50 text-emerald-600" />
      <StatTile icon={AlertTriangle}  label="Critical alerts" value={criticalAlerts}             accent="bg-red-50 text-red-600" />
    </div>
  );
}
