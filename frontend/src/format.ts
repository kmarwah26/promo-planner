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

export const statusColor = (status: string): string => {
  switch (status) {
    case 'Locked': return 'bg-violet-100 text-violet-700 border-violet-200';
    case 'Approved': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    case 'Proposed': return 'bg-blue-100 text-blue-700 border-blue-200';
    default: return 'bg-zinc-100 text-zinc-600 border-zinc-200';
  }
};
