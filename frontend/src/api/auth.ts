import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export interface LoginPayload {
  email: string;
  password: string;
  tenant_slug: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

const TOKEN_KEY = "rip_access_token";

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const { data } = await axios.post<TokenResponse>(`${API_BASE}/auth/login`, payload);
  setToken(data.access_token);
  return data;
}

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
