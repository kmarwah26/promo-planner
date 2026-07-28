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

export interface IsoWeek {
  week_number: number;
  iso_label: string;         // "WK01"
  week_start_date: string;
  week_end_date: string;
  date_range_label: string;  // "12/29-01/04"
}

// A per-week promo cell. Only weeks with a promo (or a sandbox edit) have one.
export interface PromoCell {
  week: number;
  incremental_discount: number | null;
  absolute_discount: number | null;
  rec_pptr: number | null;
  approval_status: string;   // committed | pending | approved | sandbox
  source: 'production' | 'sandbox';
}

// One grid line = (plan_year, wholesaler, brand, prc group).
export interface GridLine {
  line_key: string;          // "wholesaler|brand|prc"
  plan_year: number;
  wholesaler_id: string;
  wholesaler_name: string;
  region: string;
  state: string;
  brand_code: string;
  brand_name: string;
  prc_code: string;
  prc_group_name: string;
  qd_min: number;
  qd_max: number;
  deal_description: string;
  base_pptr: number;
  curr_max_discount: number;
  reviewed: boolean;
  cells: Record<string, PromoCell>;  // keyed by week number (string)
}

export interface GridPage {
  lines: GridLine[];
  limit: number;
  offset: number;
  count: number;
}

export interface PricingFilters {
  wholesalers: { id: string; name: string }[];
  brands: { code: string; name: string }[];
  prc_groups: { code: string; name: string }[];
}

export interface Budget {
  n_lines: number;
  n_promo_weeks: number;
  n_lines_on_promo: number;
  total_discount: number;
  avg_incremental_discount: number;
}

export interface CellEdit {
  wholesaler_id: string;
  brand_code: string;
  prc_code: string;
  week_number: number;
  incremental_discount?: number | null;
  absolute_discount?: number | null;
}

export interface LakebaseWrite {
  table: string;
  operation: string;
  row_key: string;
  columns: Record<string, any>;
}

export interface EditResult {
  ok: boolean;
  written: number;
  lakebase?: { database: string; instance: string; writes: LakebaseWrite[] };
}

export interface SubmitResult {
  ok: boolean;
  submitted: number;
  detail?: string;
  writes?: { target: string; table: string; operation: string; detail: string }[];
}

export interface FinalExport {
  plan_year: number;
  status: string;
  count: number;
  pricing: Record<string, any>[];
}

export type GridQuery = {
  plan_year: number;
  wholesaler?: string;
  brand?: string;
  prc_group?: string;
  limit?: number;
  offset?: number;
  sandbox_id?: string;
};

function qs(f: Record<string, any>): string {
  const sp = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') sp.set(k, String(v)); });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const api = {
  getCurrentUser: () => request<CurrentUser>('/me'),
  getLogoutUrl: () => request<{ logout_url: string }>('/logout-url'),

  // Pricing (Unity Catalog reads)
  getFilters: () => request<PricingFilters>('/pricing/filters'),
  getWeeks: () => request<{ weeks: IsoWeek[] }>('/pricing/weeks'),
  getGrid: (q: GridQuery) => request<GridPage>(`/pricing/grid${qs(q)}`),
  getBudget: (q: Omit<GridQuery, 'limit' | 'offset' | 'sandbox_id'>) =>
    request<Budget>(`/pricing/budget${qs(q)}`),
  getFinalExport: (q: { wholesaler?: string; brand?: string; prc_group?: string } = {}) =>
    request<FinalExport>(`/pricing/final${qs(q)}`),

  // Planning write-back (Lakebase sandbox + UC production)
  saveEdits: (sandbox_id: string, plan_year: number, edits: CellEdit[]) =>
    request<EditResult>('/planning/edit', { method: 'POST', body: JSON.stringify({ sandbox_id, plan_year, edits }) }),
  resetSandbox: (sandbox_id: string, plan_year: number) =>
    request<{ ok: boolean; deleted: number }>('/planning/reset', { method: 'POST', body: JSON.stringify({ sandbox_id, plan_year }) }),
  markReviewed: (sandbox_id: string, plan_year: number, line_keys: string[], reviewed: boolean) =>
    request<{ ok: boolean; reviewed: number }>('/planning/review', { method: 'POST', body: JSON.stringify({ sandbox_id, plan_year, line_keys, reviewed }) }),
  submitSandbox: (sandbox_id: string, plan_year: number) =>
    request<SubmitResult>('/planning/submit', { method: 'POST', body: JSON.stringify({ sandbox_id, plan_year }) }),
  approveFinal: (q: { plan_year: number; wholesaler?: string; brand?: string; prc_group?: string }) =>
    request<{ ok: boolean }>('/planning/approve', { method: 'POST', body: JSON.stringify(q) }),
};
