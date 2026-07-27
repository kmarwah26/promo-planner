import { useEffect, useState } from 'react';
import { TrendingUp, DollarSign, Package, Percent, AlertTriangle } from 'lucide-react';
import { api } from '../api';
import type { PortfolioKpis, Filters } from '../api';
import { fmtMoneyShort, fmtInt, fmtPct } from '../format';

export default function KpiTiles({ filters }: { filters: Filters }) {
  const [k, setK] = useState<PortfolioKpis | null>(null);

  useEffect(() => {
    api.portfolioKpis(filters).then(setK).catch(() => setK(null));
  }, [JSON.stringify(filters)]);

  const tiles = [
    { icon: Package, label: 'Promotions', value: k ? fmtInt(k.n_promos) : '—', color: 'text-indigo-600 bg-indigo-50' },
    { icon: DollarSign, label: 'Trade Spend', value: k ? fmtMoneyShort(k.total_trade_spend) : '—', color: 'text-blue-600 bg-blue-50' },
    { icon: TrendingUp, label: 'Net Promo Profit', value: k ? fmtMoneyShort(k.total_net_profit) : '—', color: (k && k.total_net_profit < 0) ? 'text-red-600 bg-red-50' : 'text-emerald-600 bg-emerald-50' },
    { icon: Percent, label: 'Blended ROI', value: k ? fmtPct(k.blended_roi) : '—', color: (k && k.blended_roi < 0) ? 'text-red-600 bg-red-50' : 'text-emerald-600 bg-emerald-50' },
    { icon: AlertTriangle, label: 'Negative-ROI Promos', value: k ? fmtInt(k.n_negative_roi) : '—', color: 'text-amber-600 bg-amber-50' },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {tiles.map((t) => (
        <div key={t.label} className="p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2.5 ${t.color}`}>
            <t.icon className="w-4 h-4" />
          </div>
          <p className="text-xl font-bold text-[var(--text-primary)] tracking-tight">{t.value}</p>
          <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">{t.label}</p>
        </div>
      ))}
    </div>
  );
}
