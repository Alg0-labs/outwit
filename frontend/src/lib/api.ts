/**
 * Agent Arena API Client
 * Thin fetch wrapper — auto-attaches JWT, handles token refresh, typed errors.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api';

// ── Token storage ─────────────────────────────────────────────────────────────
export const tokenStore = {
  get: () => localStorage.getItem('aa_access_token'),
  set: (t: string) => localStorage.setItem('aa_access_token', t),
  getRefresh: () => localStorage.getItem('aa_refresh_token'),
  setRefresh: (t: string) => localStorage.setItem('aa_refresh_token', t),
  clear: () => {
    localStorage.removeItem('aa_access_token');
    localStorage.removeItem('aa_refresh_token');
  },
};

// ── Error class ───────────────────────────────────────────────────────────────
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

// ── Core request ──────────────────────────────────────────────────────────────
async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  // Try token refresh on 401
  if (res.status === 401 && retry) {
    const refreshed = await tryRefresh();
    if (refreshed) return request<T>(path, options, false);
    // Refresh failed — force logout via custom event
    window.dispatchEvent(new Event('aa:logout'));
    throw new ApiError(401, 'Session expired. Please log in again.');
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function tryRefresh(): Promise<boolean> {
  const refreshToken = tokenStore.getRefresh();
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${refreshToken}`,
      },
    });
    if (!res.ok) return false;
    const data = await res.json();
    tokenStore.set(data.access_token);
    tokenStore.setRefresh(data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────
export const api = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

// ── Auth endpoints ────────────────────────────────────────────────────────────
export const authApi = {
  sendOtp: (body: { username: string; email: string; password: string }) =>
    api.post<{ message: string; email: string }>('/auth/send-otp', body),

  verifyOtp: (body: { email: string; otp: string }) =>
    api.post<AuthResponse>('/auth/verify-otp', body),

  login: (body: { email: string; password: string }) =>
    api.post<AuthResponse>('/auth/login', body),

  me: () => api.get<MeResponse>('/auth/me'),

  verifyEmail: (token: string) =>
    api.get<{ message: string }>(`/auth/verify-email?token=${token}`),
};

// ── Agent endpoints ───────────────────────────────────────────────────────────
export const agentApi = {
  create: (body: CreateAgentBody) =>
    api.post<AgentResponse>('/agents', body),

  me: () => api.get<AgentResponse>('/agents/me'),

  update: (body: Partial<CreateAgentBody>) =>
    api.patch<AgentResponse>('/agents/me', body),
};

// ── Markets ───────────────────────────────────────────────────────────────────
export const marketApi = {
  list: (params?: { category?: string }) => {
    const qs = params?.category ? `?category=${params.category}` : '';
    return api.get<MarketResponse[]>(`/markets${qs}`);
  },
  get: (id: string) => api.get<MarketResponse>(`/markets/${id}`),
};

// ── Predictions ───────────────────────────────────────────────────────────────
export const predictionApi = {
  create: (marketId: string) =>
    api.post<PredictionApiResponse>('/predictions', { market_id: marketId }),
  get: (id: string) => api.get<PredictionApiResponse>(`/predictions/${id}`),
};

// ── Battles ───────────────────────────────────────────────────────────────────
export const battleApi = {
  list: (params?: { status?: 'active' | 'resolved'; min_participants?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.min_participants !== undefined) qs.set('min_participants', String(params.min_participants));
    const query = qs.toString() ? `?${qs}` : '';
    return api.get<BattleApiResponse[]>(`/battles${query}`);
  },
  get: (id: string) => api.get<BattleApiResponse>(`/battles/${id}`),
  vote: (battleId: string, agentId: string) =>
    api.post<BattleApiResponse>(`/battles/${battleId}/vote`, { agent_id: agentId }),
  liveFeed: (battleId: string) => api.get<LiveFeedResponse>(`/battles/${battleId}/live-feed`),
  thoughts: (battleId: string) => api.get<AgentThought[]>(`/battles/${battleId}/thoughts`),
};

// ── Intel ────────────────────────────────────────────────────────────────────
export const intelApi = {
  balance: () => api.get<{ intel_balance: number; agent_id: string }>('/intel/balance'),
  transactions: () => api.get<Transaction[]>('/intel/transactions'),
  claimDaily: () => api.post<DailyLoginResponse>('/intel/claim-daily'),
};

// ── Types ─────────────────────────────────────────────────────────────────────
export interface UserData {
  id: string;
  username: string;
  email: string;
  login_streak: number;
  is_verified?: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserData;
}

export interface MeResponse {
  user: UserData;
  agent: AgentResponse | null;
}

export interface AgentResponse {
  id: string;
  user_id: string;
  name: string;
  avatar_id: string;
  color_theme: string;
  domain_expertise: string[];
  reasoning_style: string;
  risk_profile: number;
  intel_balance: number;
  reputation_score: number;
  win_count: number;
  loss_count: number;
  current_streak: number;
  win_rate: number;
  total_predictions: number;
  created_at: string;
}

export interface CreateAgentBody {
  name: string;
  avatar_id: string;
  color_theme: string;
  domain_expertise: string[];
  reasoning_style: 'statistical' | 'narrative';
  risk_profile: number;
}

export interface MarketResponse {
  id: string;
  external_id: string;
  source: string;           // "polymarket" | "cricapi"
  question: string;
  yes_price: number;
  no_price: number;
  volume_24h: number;
  category: string;
  closes_at: string;
  is_resolved: boolean;
  time_remaining: string;
}

export interface PredictionApiResponse {
  id: string;
  agent_id: string;
  market_id: string;
  market_question: string;
  market_category: string;
  predicted_outcome: string;   // "YES" | "NO"
  confidence_score: number;    // 0-100
  intel_wagered: number;
  reasoning_text: string;
  key_signal: string;
  status: string;
  created_at: string;
}

export interface BattleParticipant {
  agent_id: string;
  agent_name: string;
  agent_avatar: string;
  agent_color: string;
  agent_owner: string;
  agent_owner_username: string;
  prediction: string;   // "YES" | "NO"
  confidence: number;
  reasoning: string;
  crowd_votes: number;
  crowd_vote_pct: number;
}

export interface BattleApiResponse {
  id: string;
  market_id: string;
  market_question: string;
  market_category: string;
  participants: BattleParticipant[];
  total_votes: number;
  status: string;
  winner_agent_ids: string[];
  resolution_reason: string | null;
  time_remaining: string;
  created_at: string;
}

export interface Transaction {
  _id: string;
  amount: number;
  type: string;
  description: string;
  running_balance: number;
  created_at: string;
}

export interface LiveFeedScore {
  inning: string;
  runs: number;
  wickets: number;
  overs: string | number;
}

export interface LiveFeedNews {
  headline: string;
  source: string;
  published: string;
  url: string;
}

export interface LiveFeedResponse {
  source: string;
  category: string;
  market_question: string;
  match_score: LiveFeedScore[] | null;
  match_status: string | null;
  match_started: boolean;
  match_ended: boolean;
  venue: string;
  toss: string;
  news: LiveFeedNews[];
}

export interface DailyLoginResponse {
  intel_awarded: number;
  new_balance: number;
  streak: number;
  streak_complete: boolean;
  message: string;
}

export interface AgentThought {
  id: string;
  battle_id: string;
  agent_id: string;
  agent_name: string;
  agent_color: string;
  agent_avatar: string;
  prediction: string;
  confidence: number;
  confidence_delta: number;
  thought: string;
  reasoning: string;
  match_context: string;
  created_at: string;
}
