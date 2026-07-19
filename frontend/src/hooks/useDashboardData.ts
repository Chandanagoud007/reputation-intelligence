import { useQuery } from "@tanstack/react-query";
import { fetchScores, fetchReviews, fetchAlerts, fetchTrend, semanticSearch } from "../api/client";

export function useScores() {
  return useQuery({
    queryKey: ["scores"],
    queryFn: fetchScores,
    refetchInterval: 15000, // poll every 15s for near-real-time updates
  });
}

export function useReviews(filters: {
  sentiment?: string;
  platform?: string;
  risk_level?: string;
  query?: string;
}) {
  return useQuery({
    queryKey: ["reviews", filters],
    queryFn: () => fetchReviews(filters),
    refetchInterval: 15000,
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: fetchAlerts,
    refetchInterval: 10000, // alerts need faster polling
  });
}

export function useTrend(locationId: string | null) {
  return useQuery({
    queryKey: ["trend", locationId],
    queryFn: () => fetchTrend(locationId!),
    enabled: !!locationId,
  });
}

export function useSemanticSearch(query: string, enabled: boolean) {
  return useQuery({
    queryKey: ["semantic-search", query],
    queryFn: () => semanticSearch(query),
    enabled: enabled && query.length > 2,
  });
}
