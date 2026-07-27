const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      ...options,
    });
  } catch (e: any) {
    throw new Error(e.message === 'Failed to fetch' ? 'Network error — the server may be restarting. Please try again.' : e.message);
  }
  if (!resp.ok) {
    const text = await resp.text();
    if (text.startsWith('<!') || text.startsWith('<html')) {
      const status = resp.status;
      const label = status === 502 ? 'Bad Gateway' : status === 504 ? 'Gateway Timeout' : `HTTP ${status}`;
      throw new Error(`${label} — the server may be busy or restarting. Please retry in a few seconds.`);
    }
    try {
      const json = JSON.parse(text);
      throw new Error(json.detail || json.message || text);
    } catch (jsonErr) {
      if (jsonErr instanceof SyntaxError) throw new Error(text || resp.statusText);
      throw jsonErr;
    }
  }
  return resp.json();
}

// ── Types ──

export interface CurrentUser {
  id: string;
  user_name: string;
  display_name: string;
}

export interface PlanState {
  promotion_id: string;
  status: string | null;
  adjusted_budget: number | null;
  adjusted_discount: number | null;
  assigned_to: string | null;
  locked: boolean;
  updated_by: string | null;
  updated_at: string | null;
}

export interface Promo {
  promotion_id: number;
  promotion_code: string;
  brand: string;
  pack: string;
  category: string;
  market: string;
  channel: string;
  customer_segment: string;
  promo_mechanic: string;
  start_week: number;
  end_week: number;
  duration_weeks: number;
  quarter: string;
  status: string;
  base_price: number;
  promo_price: number;
  discount_depth: number;
  // Elasticity model parameters (let the grid recompute economics live):
  baseline_volume: number;
  elasticity: number;
  fixed_fee: number;
  margin_per_case: number;
  lift_multiplier: number;
  baseline_volume_total: number;
  proposed_volume_total: number;
  incremental_volume: number;
  trade_spend: number;
  incremental_margin: number;
  net_promo_profit: number;
  promo_roi: number;
  incrementality_pct: number;
  plan_state: PlanState | null;
}

export interface CalendarWeek {
  week_number: number;
  week_start_date: string;
  quarter: string;
  month: string;
}

export interface CalendarPromo {
  promotion_id: number;
  promotion_code: string;
  brand: string;
  pack: string;
  market: string;
  channel: string;
  customer_segment: string;
  promo_mechanic: string;
  status: string;
  start_week: number;
  end_week: number;
  quarter: string;
  promo_roi: number;
  trade_spend: number;
  incremental_volume: number;
  net_promo_profit: number;
  plan_state: PlanState | null;
}

export interface PortfolioKpis {
  n_promos: number;
  total_trade_spend: number;
  total_incremental_volume: number;
  total_net_profit: number;
  blended_roi: number;
  avg_incrementality: number;
  n_negative_roi: number;
}

export interface ScenarioCompare {
  totals: {
    baseline_volume: number;
    proposed_volume: number;
    incremental_volume: number;
    trade_spend: number;
    incremental_margin: number;
    net_profit: number;
    roi: number;
  };
  by_brand: {
    brand: string;
    baseline_volume: number;
    proposed_volume: number;
    trade_spend: number;
    net_profit: number;
    roi: number;
  }[];
}

export interface WeeklySales {
  week_number: number;
  quarter: string;
  baseline_volume: number;
  actual_volume: number;
  is_promo_week: boolean;
}

export interface Comment {
  id: string;
  author: string;
  body: string;
  created_at: string;
}

export interface Activity {
  promotion_id?: string;
  actor: string;
  action: string;
  detail: string;
  created_at: string;
}

export interface GenieRoom {
  id: string;
  title: string;
  description: string;
}

export type Filters = {
  market?: string;
  channel?: string;
  brand?: string;
  segment?: string;
  status?: string;
};

function qs(f: Filters): string {
  const sp = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => { if (v) sp.set(k, v); });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const api = {
  getCurrentUser: () => request<CurrentUser>('/me'),
  getLogoutUrl: () => request<{ logout_url: string }>('/logout-url'),

  // Promotions (Unity Catalog)
  getFilters: () => request<Record<string, string[]>>('/promos/filters'),
  listPromos: (f: Filters = {}) => request<{ promos: Promo[] }>(`/promos${qs(f)}`),
  portfolioKpis: (f: Filters = {}) => request<PortfolioKpis>(`/promos/kpis${qs(f)}`),
  calendar: (f: Filters = {}) => request<{ promos: CalendarPromo[]; weeks: CalendarWeek[] }>(`/promos/calendar${qs(f)}`),
  promoDetail: (id: number) => request<{ promo: Promo & { comments: Comment[] }; weekly: WeeklySales[] }>(`/promos/${id}`),
  scenarioCompare: (f: Filters = {}) => request<ScenarioCompare>(`/promos/scenario/compare${qs(f)}`),

  // Write-back (Lakebase)
  approve: (promotion_id: string) => request<any>('/planning/approve', { method: 'POST', body: JSON.stringify({ promotion_id }) }),
  lock: (promotion_id: string, locked: boolean) => request<any>('/planning/lock', { method: 'POST', body: JSON.stringify({ promotion_id, locked }) }),
  adjustBudget: (promotion_id: string, adjusted_budget: number) => request<any>('/planning/budget', { method: 'POST', body: JSON.stringify({ promotion_id, adjusted_budget }) }),
  saveScenario: (promotion_id: string, adjusted_discount: number, adjusted_budget?: number) => request<any>('/planning/scenario', { method: 'POST', body: JSON.stringify({ promotion_id, adjusted_discount, adjusted_budget }) }),
  assign: (promotion_id: string, assigned_to: string) => request<any>('/planning/assign', { method: 'POST', body: JSON.stringify({ promotion_id, assigned_to }) }),
  addComment: (promotion_id: string, body: string) => request<any>('/planning/comment', { method: 'POST', body: JSON.stringify({ promotion_id, body }) }),
  getComments: (promotion_id: string) => request<{ comments: Comment[] }>(`/planning/${promotion_id}/comments`),
  getActivity: (promotion_id: string) => request<{ activity: Activity[]; db_available: boolean }>(`/planning/${promotion_id}/activity`),
  recentActivity: () => request<{ activity: Activity[]; db_available: boolean }>('/planning/activity/recent'),

  // Genie Agents
  listGenieRooms: () => request<{ rooms: GenieRoom[] }>('/genie/rooms'),
  startConversation: (roomId: string, content: string) =>
    request<any>(`/genie/rooms/${roomId}/conversations`, { method: 'POST', body: JSON.stringify({ content }) }),
  sendMessage: (roomId: string, conversationId: string, content: string) =>
    request<any>(`/genie/rooms/${roomId}/conversations/${conversationId}/messages`, { method: 'POST', body: JSON.stringify({ content }) }),
};
