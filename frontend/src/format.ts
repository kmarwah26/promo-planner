export const fmtInt = (n: number | null | undefined) =>
  n == null ? '—' : Math.round(n).toLocaleString('en-US');

export const fmtMoney = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits, minimumFractionDigits: digits });

export const fmtMoneyShort = (n: number | null | undefined) => {
  if (n == null) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e6) return `${n < 0 ? '-' : ''}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${n < 0 ? '-' : ''}$${(abs / 1e3).toFixed(0)}K`;
  return `${n < 0 ? '-' : ''}$${abs.toFixed(0)}`;
};

export const fmtPct = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : `${(n * 100).toFixed(digits)}%`;

// ROI-based color for calendar cells / badges. Threshold at 0.
export const roiColor = (roi: number | null | undefined): string => {
  if (roi == null) return '#e4e4e7';
  if (roi >= 0.5) return '#15803d';   // strong green
  if (roi >= 0.2) return '#22c55e';   // green
  if (roi >= 0) return '#a3e635';     // lime
  if (roi >= -0.2) return '#fbbf24';  // amber
  return '#ef4444';                   // red
};

// Recompute promotion economics from a (possibly edited) discount depth, mirroring the
// SQL elasticity model in data/generate_rgm_data.py exactly:
//   lift = 1 + elasticity * discount
export interface PromoEconInputs {
  base_price: number;
  baseline_volume: number;
  duration_weeks: number;
  elasticity: number;
  fixed_fee: number;
  margin_per_case: number;
}
export interface PromoEcon {
  discount_depth: number;
  promo_price: number;
  lift_multiplier: number;
  incrementality_pct: number;
  proposed_volume_total: number;
  incremental_volume: number;
  trade_spend: number;
  incremental_margin: number;
  net_promo_profit: number;
  promo_roi: number;
}
export function computeEcon(p: PromoEconInputs, discount: number): PromoEcon {
  const lift = 1 + p.elasticity * discount;
  const proposed = p.baseline_volume * lift * p.duration_weeks;
  const incremental = p.baseline_volume * (lift - 1) * p.duration_weeks;
  const trade = p.base_price * discount * proposed + p.fixed_fee;
  const margin = incremental * p.margin_per_case;
  const net = margin - trade;
  return {
    discount_depth: discount,
    promo_price: p.base_price * (1 - discount),
    lift_multiplier: lift,
    incrementality_pct: lift - 1,
    proposed_volume_total: Math.round(proposed),
    incremental_volume: Math.round(incremental),
    trade_spend: trade,
    incremental_margin: margin,
    net_promo_profit: net,
    promo_roi: trade ? net / trade : 0,
  };
}

export const statusColor = (status: string): string => {
  switch (status) {
    case 'Locked': return 'bg-violet-100 text-violet-700 border-violet-200';
    case 'Approved': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    case 'Proposed': return 'bg-blue-100 text-blue-700 border-blue-200';
    default: return 'bg-zinc-100 text-zinc-600 border-zinc-200';
  }
};
