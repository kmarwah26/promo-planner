export const fmtInt = (n: number | null | undefined) =>
  n == null ? '—' : Math.round(n).toLocaleString('en-US');

export const fmtMoney = (n: number | null | undefined, digits = 2) =>
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

// Plain 2-decimal price, no currency symbol — matches the dense grid cells in the screenshots.
export const fmtPrice = (n: number | null | undefined) =>
  n == null ? '' : n.toFixed(2);

// Depth of a promo cell's discount (fraction 0..1) → background tint for the cell.
// Deeper discount = warmer/stronger. Approval-status aware handled by the caller.
export const discountColor = (depth: number | null | undefined): string => {
  if (depth == null || depth <= 0) return 'transparent';
  if (depth >= 0.20) return '#fca5a5';   // red-300 — deep
  if (depth >= 0.12) return '#fdba74';   // orange-300
  if (depth >= 0.06) return '#fde047';   // yell-300
  return '#bef264';                       // lime-300 — shallow
};

// Approval status → small badge classes.
export const statusColor = (status: string): string => {
  switch (status) {
    case 'approved': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    case 'pending': return 'bg-amber-100 text-amber-700 border-amber-200';
    case 'sandbox': return 'bg-indigo-100 text-indigo-700 border-indigo-200';
    case 'committed': return 'bg-slate-100 text-slate-600 border-slate-200';
    default: return 'bg-slate-100 text-slate-600 border-slate-200';
  }
};

// Derive REC PPTR from a base price + discounts (mirrors the SQL/Python model).
export function recPptr(basePptr: number, incremental?: number | null, absolute?: number | null): number {
  if (absolute != null) return +(basePptr - absolute).toFixed(2);
  if (incremental != null) return +(basePptr * (1 - incremental)).toFixed(2);
  return +basePptr.toFixed(2);
}

// Effective discount depth (fraction) for a cell given base price.
export function cellDepth(basePptr: number, incremental?: number | null, absolute?: number | null): number {
  if (absolute != null) return basePptr ? absolute / basePptr : 0;
  if (incremental != null) return incremental;
  return 0;
}
