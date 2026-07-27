import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Check, Lock, Unlock, ArrowUpDown } from 'lucide-react';
import { api } from '../api';
import type { Promo } from '../api';
import { useFilters } from '../store';
import FilterBar from '../components/FilterBar';
import KpiTiles from '../components/KpiTiles';
import { fmtMoneyShort, fmtPct, fmtInt, roiColor, statusColor } from '../format';

type SortKey = 'promo_roi' | 'trade_spend' | 'net_promo_profit' | 'incrementality_pct';

export default function PromoList() {
  const { filters } = useFilters();
  const navigate = useNavigate();
  const [promos, setPromos] = useState<Promo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [sort, setSort] = useState<SortKey>('promo_roi');
  const [asc, setAsc] = useState(true);

  const load = () => {
    setLoading(true);
    api.listPromos(filters).then((r) => setPromos(r.promos)).finally(() => setLoading(false));
  };
  useEffect(load, [JSON.stringify(filters)]);

  const sorted = [...promos].sort((a, b) => (asc ? 1 : -1) * ((a[sort] as number) - (b[sort] as number)));

  const act = async (id: number, fn: () => Promise<any>) => {
    setBusy(id);
    try { await fn(); load(); } finally { setBusy(null); }
  };

  const effStatus = (p: Promo) => p.plan_state?.status || p.status;
  const isLocked = (p: Promo) => p.plan_state?.locked ?? (p.status === 'Locked');

  const cols: { key: SortKey; label: string }[] = [
    { key: 'trade_spend', label: 'Trade Spend' },
    { key: 'incrementality_pct', label: 'Incrementality' },
    { key: 'net_promo_profit', label: 'Net Profit' },
    { key: 'promo_roi', label: 'ROI' },
  ];

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 pt-6 pb-4 border-b border-[var(--border)] space-y-4">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)]">Promotions Workspace</h2>
          <p className="text-sm text-[var(--text-secondary)]">Review economics and act — approve, lock, or open to adjust budget and comment.</p>
        </div>
        <KpiTiles filters={filters} />
        <FilterBar />
      </div>

      <div className="flex-1 overflow-auto px-8 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…</div>
        ) : (
          <table className="w-full text-sm border-separate border-spacing-y-1.5">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-[var(--text-secondary)]">
                <th className="text-left font-semibold px-3">Promotion</th>
                <th className="text-left font-semibold px-2">Market / Channel</th>
                <th className="text-left font-semibold px-2">Mechanic</th>
                <th className="text-center font-semibold px-2">Weeks</th>
                {cols.map((c) => (
                  <th key={c.key} className="text-right font-semibold px-2">
                    <button onClick={() => { sort === c.key ? setAsc(!asc) : setSort(c.key); }}
                      className={`inline-flex items-center gap-1 hover:text-[var(--text-primary)] ${sort === c.key ? 'text-[var(--accent)]' : ''}`}>
                      {c.label} <ArrowUpDown className="w-3 h-3" />
                    </button>
                  </th>
                ))}
                <th className="text-center font-semibold px-2">Status</th>
                <th className="text-right font-semibold px-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => {
                const locked = isLocked(p);
                const status = effStatus(p);
                return (
                  <tr key={p.promotion_id} className="bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors cursor-pointer" onClick={() => navigate(`/promos/${p.promotion_id}`)}>
                    <td className="px-3 py-2.5 rounded-l-lg">
                      <div className="font-medium text-[var(--text-primary)]">{p.brand}</div>
                      <div className="text-[11px] text-[var(--text-secondary)]">{p.promotion_code} · {p.pack}</div>
                    </td>
                    <td className="px-2 text-[var(--text-secondary)] text-xs">{p.market}<br />{p.channel}</td>
                    <td className="px-2 text-xs text-[var(--text-secondary)]">{p.promo_mechanic}</td>
                    <td className="px-2 text-center text-xs text-[var(--text-secondary)]">{p.start_week}–{p.end_week}</td>
                    <td className="px-2 text-right text-[var(--text-primary)]">{fmtMoneyShort(p.plan_state?.adjusted_budget ?? p.trade_spend)}{p.plan_state?.adjusted_budget != null && <span className="text-[9px] text-[var(--accent)] ml-1">adj</span>}</td>
                    <td className="px-2 text-right text-[var(--text-primary)]">{fmtPct(p.incrementality_pct)}</td>
                    <td className={`px-2 text-right font-medium ${p.net_promo_profit < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtMoneyShort(p.net_promo_profit)}</td>
                    <td className="px-2 text-right font-semibold">
                      <span className="px-2 py-0.5 rounded-full text-white text-xs" style={{ background: roiColor(p.promo_roi) }}>{fmtPct(p.promo_roi)}</span>
                    </td>
                    <td className="px-2 text-center">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-medium border ${statusColor(status)}`}>{status}</span>
                    </td>
                    <td className="px-3 py-2.5 rounded-r-lg text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="inline-flex items-center gap-1.5">
                        {status !== 'Approved' && status !== 'Locked' && (
                          <button disabled={busy === p.promotion_id} onClick={() => act(p.promotion_id, () => api.approve(String(p.promotion_id)))}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-50 text-emerald-700 hover:bg-emerald-100 text-xs font-medium transition-colors disabled:opacity-50">
                            <Check className="w-3 h-3" /> Approve
                          </button>
                        )}
                        <button disabled={busy === p.promotion_id} onClick={() => act(p.promotion_id, () => api.lock(String(p.promotion_id), !locked))}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-50 ${locked ? 'bg-violet-100 text-violet-700 hover:bg-violet-200' : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'}`}>
                          {busy === p.promotion_id ? <Loader2 className="w-3 h-3 animate-spin" /> : locked ? <Unlock className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
                          {locked ? 'Unlock' : 'Lock'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {!loading && <p className="text-xs text-[var(--text-secondary)] mt-3">{sorted.length} promotions · {fmtInt(sorted.filter(p => p.promo_roi < 0).length)} with negative ROI</p>}
      </div>
    </div>
  );
}
