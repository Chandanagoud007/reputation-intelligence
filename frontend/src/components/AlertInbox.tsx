import React from "react";
import { AlertTriangle, AlertCircle, Info, CheckCircle, MapPin, Clock } from "lucide-react";
import type { Alert } from "../api/client";

const SEVERITY_CONFIG = {
  critical: { icon: AlertTriangle, bg: "bg-red-50", border: "border-red-300", badge: "bg-red-100 text-red-700", dot: "bg-red-500", label: "Critical" },
  high:     { icon: AlertCircle,   bg: "bg-orange-50", border: "border-orange-300", badge: "bg-orange-100 text-orange-700", dot: "bg-orange-500", label: "High" },
  medium:   { icon: Info,          bg: "bg-yellow-50", border: "border-yellow-300", badge: "bg-yellow-100 text-yellow-700", dot: "bg-yellow-400", label: "Medium" },
  low:      { icon: CheckCircle,   bg: "bg-blue-50", border: "border-blue-200", badge: "bg-blue-100 text-blue-600", dot: "bg-blue-400", label: "Low" },
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface AlertItemProps {
  alert: Alert;
}

function AlertItem({ alert }: AlertItemProps) {
  const cfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.low;
  const Icon = cfg.icon;

  return (
    <div className={`rounded-xl border ${cfg.border} ${cfg.bg} p-4 transition-all hover:shadow-sm`}>
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 p-1.5 rounded-lg bg-white shadow-sm`}>
          <Icon size={14} className={alert.severity === "critical" ? "text-red-500" : alert.severity === "high" ? "text-orange-500" : alert.severity === "medium" ? "text-yellow-500" : "text-blue-500"} />
        </div>

        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.badge}`}>
                {cfg.label}
              </span>
              <span className="text-sm font-semibold text-slate-700">{alert.rule_name}</span>
            </div>
            <div className="flex items-center gap-1 text-xs text-slate-400">
              <Clock size={11} />
              {timeAgo(alert.fired_at)}
            </div>
          </div>

          {/* Location */}
          <div className="flex items-center gap-1 mt-1.5">
            <MapPin size={11} className="text-slate-400" />
            <span className="text-xs text-slate-500">{alert.location_name} · {alert.brand_name}</span>
          </div>

          {/* Trigger values */}
          <div className="flex gap-3 mt-2 text-xs text-slate-500">
            <span>Score <strong className="text-slate-700">{alert.trigger_values.score?.toFixed(2)}</strong></span>
            <span>Rating <strong className="text-slate-700">{alert.trigger_values.rating_avg?.toFixed(1)}</strong></span>
            <span>Reviews <strong className="text-slate-700">{alert.trigger_values.review_count}</strong></span>
          </div>

          {/* Risk flags */}
          {alert.risk_flags.length > 0 && (
            <div className="flex gap-1.5 flex-wrap mt-2">
              {alert.risk_flags.map((f) => (
                <span key={f} className="text-xs bg-white text-red-600 border border-red-200 px-2 py-0.5 rounded-full">
                  {f.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}

          {/* Topics */}
          {alert.topics.length > 0 && (
            <div className="flex gap-1.5 flex-wrap mt-1.5">
              {alert.topics.map((t) => (
                <span key={t} className="text-xs bg-white text-slate-500 border border-slate-200 px-2 py-0.5 rounded-full">{t}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface AlertInboxProps {
  alerts: Alert[];
  loading?: boolean;
}

export default function AlertInbox({ alerts, loading }: AlertInboxProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse">
            <div className="h-3 bg-slate-100 rounded w-1/4 mb-3" />
            <div className="h-3 bg-slate-100 rounded w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  if (!alerts.length) {
    return (
      <div className="text-center py-12 text-slate-400">
        <CheckCircle size={32} className="mx-auto mb-3 text-emerald-300" />
        <p className="text-sm font-medium text-slate-500">No active alerts</p>
        <p className="text-xs mt-1">All locations are within threshold.</p>
      </div>
    );
  }

  const critical = alerts.filter((a) => a.severity === "critical");
  const rest     = alerts.filter((a) => a.severity !== "critical");

  return (
    <div className="space-y-2">
      {critical.length > 0 && (
        <>
          <p className="text-xs font-semibold text-red-500 uppercase tracking-wide px-1">Needs immediate attention</p>
          {critical.map((a) => <AlertItem key={a.alert_id} alert={a} />)}
          {rest.length > 0 && <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide px-1 pt-2">Other alerts</p>}
        </>
      )}
      {rest.map((a) => <AlertItem key={a.alert_id} alert={a} />)}
    </div>
  );
}
