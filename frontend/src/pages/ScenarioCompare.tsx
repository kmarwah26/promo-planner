import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { api } from '../api';
import type { ScenarioCompare as SC } from '../api';
import { useFilters } from '../store';
import FilterBar from '../components/FilterBar';
import { fmtMoneyShort, fmtInt, fmtPct } from '../format';

export default function ScenarioCompare() {
  const { filters } = useFilters();
  const [data, setData] = useState<SC | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.scenarioCompare(filters).then(setData).finally(() => setLoading(false));
  }, [JSON.stringify(filters)]);

  const t = data?.totals;
  const maxProfit = Math.max(1, ...(data?.by_brand.map((b) => Math.abs(b.net_profit)) || [1]));

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 pt-6 pb-4 border-b border-[var(--border)] space-y-4">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)]">Scenario Comparison</h2>
          <p className="text-sm text-[var(--text-secondary)]">Baseline (no promo) vs proposed plan across the filtered portfolio.</p>
        </div>
        <FilterBar showStatus={false} />
      </div>

      <div className="flex-1 overflow-auto px-8 py-6">
        {loading || !t ? (
          <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Computing…</div>
        ) : (
          <div className="max-w-5xl space-y-8">
            {/* Baseline vs Proposed volume bars */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] md:col-span-2">
                <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Volume: Baseline vs Proposed</h3>
                {[
                  { label: 'Baseline volume', val: t.baseline_volume, color: 'bg-zinc-400' },
                  { label: 'Proposed volume', val: t.proposed_volume, color: 'bg-indigo-500' },
                ].map((row) => (
                  <div key={row.label} className="mb-3">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-[var(--text-secondary)]">{row.label}</span>
                      <span className="font-medium text-[var(--text-primary)]">{fmtInt(row.val)} cases</span>
                    </div>
                    <div className="h-3 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                      <div className={`h-full ${row.color} rounded-full`} style={{ width: `${(row.val / Math.max(t.baseline_volume, t.proposed_volume)) * 100}%` }} />
                    </div>
                  </div>
                ))}
                <div className="mt-3 pt-3 border-t border-[var(--border)] flex justify-between text-sm">
                  <span className="text-[var(--text-secondary)]">Incremental volume</span>
                  <span className="font-semibold text-emerald-600">+{fmtInt(t.incremental_volume)} cases ({fmtPct(t.incremental_volume / t.baseline_volume)})</span>
                </div>
              </div>

              <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] flex flex-col justify-center gap-4">
                <Stat label="Trade Spend" value={fmtMoneyShort(t.trade_spend)} />
                <Stat label="Incremental Margin" value={fmtMoneyShort(t.incremental_margin)} pos />
                <Stat label="Net Promo Profit" value={fmtMoneyShort(t.net_profit)} pos={t.net_profit >= 0} neg={t.net_profit < 0} />
                <Stat label="Blended ROI" value={fmtPct(t.roi)} pos={t.roi >= 0} neg={t.roi < 0} />
              </div>
            </div>

            {/* Per-brand breakdown */}
            <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Net promo profit by brand</h3>
              <div className="space-y-2.5">
                {data.by_brand.map((b) => (
                  <div key={b.brand} className="flex items-center gap-3">
                    <span className="w-32 shrink-0 text-xs text-[var(--text-primary)] truncate">{b.brand}</span>
                    <div className="flex-1 flex items-center">
                      <div className="flex-1 h-5 rounded-md bg-[var(--bg-tertiary)] relative overflow-hidden">
                        <div className={`h-full rounded-md ${b.net_profit < 0 ? 'bg-red-400' : 'bg-emerald-500'}`}
                          style={{ width: `${(Math.abs(b.net_profit) / maxProfit) * 100}%` }} />
                      </div>
                    </div>
                    <span className={`w-20 text-right text-xs font-medium ${b.net_profit < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtMoneyShort(b.net_profit)}</span>
                    <span className="w-16 text-right text-xs text-[var(--text-secondary)]">ROI {fmtPct(b.roi)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, pos, neg }: { label: string; value: string; pos?: boolean; neg?: boolean }) {
  return (
    <div>
      <p className="text-[11px] text-[var(--text-secondary)]">{label}</p>
      <p className={`text-xl font-bold tracking-tight ${neg ? 'text-red-600' : pos ? 'text-emerald-600' : 'text-[var(--text-primary)]'}`}>{value}</p>
    </div>
  );
}
