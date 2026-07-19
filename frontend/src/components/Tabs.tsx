import React from "react";
import { LayoutGrid, MessageSquare, Bell } from "lucide-react";

export type TabKey = "overview" | "reviews" | "alerts";

interface TabsProps {
  active: TabKey;
  onChange: (tab: TabKey) => void;
  alertCount: number;
}

const TABS: { key: TabKey; label: string; icon: any }[] = [
  { key: "overview", label: "Overview", icon: LayoutGrid },
  { key: "reviews",  label: "Reviews",  icon: MessageSquare },
  { key: "alerts",   label: "Alerts",   icon: Bell },
];

export default function Tabs({ active, onChange, alertCount }: TabsProps) {
  return (
    <div className="flex gap-1 border-b border-slate-200 mb-6">
      {TABS.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`
            flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors relative
            ${active === key
              ? "border-teal-600 text-teal-700"
              : "border-transparent text-slate-400 hover:text-slate-600"}
          `}
        >
          <Icon size={15} />
          {label}
          {key === "alerts" && alertCount > 0 && (
            <span className="ml-1 bg-red-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
              {alertCount > 9 ? "9+" : alertCount}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
