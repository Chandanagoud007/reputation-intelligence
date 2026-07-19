import axios from "axios";
import { getToken } from "./auth";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  timeout: 10000,
});

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem("rip_access_token");
      window.location.reload();
    }
    return Promise.reject(error);
  }
);

// ── Types ─────────────────────────────────────────────────────────────────────
export interface ReputationScore {
  location_id: string;
  location_name: string;
  brand_name: string;
  region_name: string;
  score: number;
  rating_avg: number;
  sentiment_avg: number;
  review_count: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
}

export interface Review {
  message_id: string;
  source_platform: string;
  text_cleaned: string;
  reviewer_name: string;
  rating: number;
  sentiment: "positive" | "negative" | "neutral";
  sentiment_score: number;
  topics: string[];
  risk_level: string;
  risk_flags: string[];
  review_date: string;
  location_name: string;
  brand_name: string;
}

export interface Alert {
  alert_id: string;
  rule_name: string;
  location_name: string;
  brand_name: string;
  severity: "low" | "medium" | "high" | "critical";
  risk_level: string;
  risk_flags: string[];
  topics: string[];
  trigger_values: {
    score: number;
    rating_avg: number;
    sentiment_avg: number;
    risk_level: string;
    review_count: number;
  };
  fired_at: string;
}

export interface TrendPoint {
  date: string;
  score: number;
  review_count: number;
  sentiment_avg: number;
}

// ── API calls ─────────────────────────────────────────────────────────────────

// Scores
export const fetchScores = async (): Promise<ReputationScore[]> => {
  const { data } = await api.get("/scores/");
  return data;
};

// Reviews — from OpenSearch
export const fetchReviews = async (params?: {
  sentiment?: string;
  platform?: string;
  risk_level?: string;
  query?: string;
  size?: number;
}): Promise<Review[]> => {
  const { data } = await api.get("/reviews/search", { params });
  return data;
};

// Semantic search — from Qdrant
export const semanticSearch = async (query: string): Promise<Review[]> => {
  const { data } = await api.post("/reviews/semantic-search", { query });
  return data;
};

// Alerts
export const fetchAlerts = async (): Promise<Alert[]> => {
  const { data } = await api.get("/alerts");
  return data;
};

// Trend data — from ClickHouse
export const fetchTrend = async (locationId: string): Promise<TrendPoint[]> => {
  const { data } = await api.get(`/analytics/trend/${locationId}`);
  return data;
};

export default api;
