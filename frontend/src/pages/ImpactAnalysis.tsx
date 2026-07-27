import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, TrendingUp, TrendingDown, Info, Trophy, AlertTriangle, SlidersHorizontal } from 'lucide-react';
import { api } from '../api';
import type { ImpactAnalysis as IA, EconTotals, ImpactBreakdownRow, ImpactPromo } from '../api';
import { useFilters } from '../store';
import FilterBar from '../components/FilterBar';
import { fmtMoneyShort, fmtInt, fmtPct, roiColor } from '../format';

type Dim = 'by_market' | 'by_channel' | 'by_brand';

export default function ImpactAnalysis() {
  const { filters } = useFilters();
  const navigate = useNavigate();
  const [data, setData] = useState<IA | null>(null);
  const [loading, setLoading] = useState(true);
  const [dim, setDim] = useState<Dim>('by_brand');

  useEffect(() => {
    setLoading(true);
    api.impactAnalysis(filters).then(setData).finally(() => setLoading(false));
  }, [JSON.stringify(filters)]);

  const cur = data?.current_totals;
  const scen = data?.scenario_totals;
  const hasScenario = (data?.n_scenarios ?? 0) > 0;

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 pt-6 pb-4 border-b border-[var(--border)] space-y-4">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)]">Impact Analysis</h2>
          <p className="text-sm text-[var(--text-secondary)]">
            How your saved scenario changes the portfolio vs the current committed plan — on volume, trade spend, margin and ROI.
          </p>
        </div>
        <FilterBar showStatus={false} />
      </div>

      <div className="flex-1 overflow-auto px-8 py-6">
        {loading || !cur || !scen ? (
          <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Computing…</div>
        ) : (
          <div className="max-w-6xl space-y-6">
            {!hasScenario && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-800">
                <Info className="w-4 h-4 shrink-0" />
                <span>No saved scenario yet — the scenario columns mirror the current plan. Edit discounts in the <button onClick={() => navigate('/builder')} className="underline font-medium">Scenario Builder</button> and save to see the impact here.</span>
              </div>
            )}

            {/* KPI delta cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <DeltaCard label="Trade Spend" cur={cur.trade_spend} scen={scen.trade_spend} money goodLow />
              <DeltaCard label="Incremental Volume" cur={cur.incremental_volume} scen={scen.incremental_volume} />
              <DeltaCard label="Net Promo Profit" cur={cur.net_profit} scen={scen.net_profit} money />
              <DeltaCard label="Blended ROI" cur={cur.roi} scen={scen.roi} pct />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <ProfitBridge cur={cur} scen={scen} />
              <VolumeCompare cur={cur} scen={scen} />
            </div>

            {/* Breakdown */}
            <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">Net profit & ROI — current vs scenario</h3>
                <div className="flex items-center gap-1 rounded-lg bg-[var(--bg-tertiary)] p-0.5">
                  {([['by_brand', 'Brand'], ['by_market', 'Market'], ['by_channel', 'Channel']] as [Dim, string][]).map(([k, label]) => (
                    <button key={k} onClick={() => setDim(k)}
                      className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${dim === k ? 'bg-[var(--bg-secondary)] text-[var(--accent)] shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <BreakdownTable rows={data[dim]} />
            </div>

            {/* Winners / Losers */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <PromoCallout title="Top ROI promotions" icon={Trophy} tone="good" promos={data.winners} onOpen={(id) => navigate(`/promos/${id}`)} />
              <PromoCallout title="Underperforming — overspending for low lift" icon={AlertTriangle} tone="bad" promos={data.losers} onOpen={(id) => navigate(`/promos/${id}`)} />
            </div>

            {/* Movers (only if scenario edits exist) */}
            {data.movers.length > 0 && (
              <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
                <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1 flex items-center gap-1.5"><SlidersHorizontal className="w-4 h-4 text-[var(--accent)]" /> Biggest scenario moves</h3>
                <p className="text-[11px] text-[var(--text-secondary)] mb-3">Promotions whose saved discount changes net profit the most vs the current plan.</p>
                <div className="space-y-1.5">
                  {data.movers.map((p) => (
                    <button key={p.promotion_id} onClick={() => navigate(`/promos/${p.promotion_id}`)}
                      className="w-full flex items-center gap-3 text-left px-3 py-2 rounded-lg hover:bg-[var(--bg-tertiary)] transition-colors">
                      <span className="text-xs font-medium text-[var(--text-primary)] w-40 truncate">{p.brand} <span className="text-[var(--text-secondary)]">· {p.market}</span></span>
                      <span className="text-[11px] text-[var(--text-secondary)] w-28">disc {fmtPct(p.scenario_discount)}</span>
                      <span className="text-[11px] text-[var(--text-secondary)] flex-1">ROI {fmtPct(p.roi)}</span>
                      <span className={`text-xs font-semibold ${p.profit_delta >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                        {p.profit_delta >= 0 ? '▲' : '▼'} {fmtMoneyShort(Math.abs(p.profit_delta))} profit
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DeltaCard({ label, cur, scen, money, pct, goodLow }: { label: string; cur: number; scen: number; money?: boolean; pct?: boolean; goodLow?: boolean }) {
  const delta = scen - cur;
  const changed = Math.abs(delta) > (pct ? 0.001 : 1);
  const improved = goodLow ? delta < 0 : delta > 0;
  const fmt = (v: number) => pct ? fmtPct(v) : money ? fmtMoneyShort(v) : fmtInt(v);
  return (
    <div className="p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
      <p className="text-[11px] text-[var(--text-secondary)]">{label}</p>
      <p className="text-xl font-bold tracking-tight text-[var(--text-primary)]">{fmt(scen)}</p>
      {changed ? (
        <p className={`text-[11px] font-medium ${improved ? 'text-emerald-600' : 'text-red-600'}`}>
          {delta > 0 ? '▲' : '▼'} {fmt(Math.abs(delta))} vs current
        </p>
      ) : (
        <p className="text-[11px] text-[var(--text-secondary)]">current: {fmt(cur)}</p>
      )}
    </div>
  );
}

function VolumeCompare({ cur, scen }: { cur: EconTotals; scen: EconTotals }) {
  const max = Math.max(cur.proposed_volume, scen.proposed_volume, cur.baseline_volume, 1);
  const rows = [
    { label: 'Baseline (no promo)', val: scen.baseline_volume, color: 'bg-zinc-400' },
    { label: 'Current plan', val: cur.proposed_volume, color: 'bg-blue-400' },
    { label: 'Scenario', val: scen.proposed_volume, color: 'bg-indigo-500' },
  ];
  return (
    <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Volume (cases)</h3>
      {rows.map((r) => (
        <div key={r.label} className="mb-3">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-[var(--text-secondary)]">{r.label}</span>
            <span className="font-medium text-[var(--text-primary)]">{fmtInt(r.val)}</span>
          </div>
          <div className="h-3 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
            <div className={`h-full ${r.color} rounded-full`} style={{ width: `${(r.val / max) * 100}%` }} />
          </div>
        </div>
      ))}
      <div className="mt-3 pt-3 border-t border-[var(--border)] flex justify-between text-sm">
        <span className="text-[var(--text-secondary)]">Incremental vs baseline</span>
        <span className="font-semibold text-emerald-600">+{fmtInt(scen.incremental_volume)} ({fmtPct(scen.incremental_volume / (scen.baseline_volume || 1))})</span>
      </div>
    </div>
  );
}

function ProfitBridge({ cur, scen }: { cur: EconTotals; scen: EconTotals }) {
  // Bridge: current net profit -> (margin change) -> (spend change) -> scenario net profit
  const marginDelta = scen.incremental_margin - cur.incremental_margin;
  const spendDelta = -(scen.trade_spend - cur.trade_spend); // reducing spend adds to profit
  const items = [
    { label: 'Current net profit', value: cur.net_profit, kind: 'total' as const },
    { label: 'Δ Incremental margin', value: marginDelta, kind: 'delta' as const },
    { label: 'Δ Trade spend', value: spendDelta, kind: 'delta' as const },
    { label: 'Scenario net profit', value: scen.net_profit, kind: 'total' as const },
  ];
  const maxAbs = Math.max(...items.map((i) => Math.abs(i.value)), 1);
  return (
    <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">Net profit bridge</h3>
      <p className="text-[11px] text-[var(--text-secondary)] mb-4">What moves profit from the current plan to your scenario.</p>
      <div className="space-y-2.5">
        {items.map((it) => {
          const isTotal = it.kind === 'total';
          const positive = it.value >= 0;
          return (
            <div key={it.label} className="flex items-center gap-3">
              <span className={`w-40 shrink-0 text-xs ${isTotal ? 'font-semibold text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>{it.label}</span>
              <div className="flex-1 h-5 rounded-md bg-[var(--bg-tertiary)] overflow-hidden">
                <div className={`h-full rounded-md ${isTotal ? 'bg-[var(--accent)]' : positive ? 'bg-emerald-500' : 'bg-red-400'}`}
                  style={{ width: `${(Math.abs(it.value) / maxAbs) * 100}%` }} />
              </div>
              <span className={`w-20 text-right text-xs font-medium ${isTotal ? 'text-[var(--text-primary)]' : positive ? 'text-emerald-600' : 'text-red-600'}`}>
                {!isTotal && positive ? '+' : ''}{fmtMoneyShort(it.value)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function BreakdownTable({ rows }: { rows: ImpactBreakdownRow[] }) {
  const maxProfit = Math.max(1, ...rows.flatMap((r) => [Math.abs(r.current.net_profit), Math.abs(r.scenario.net_profit)]));
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-3 text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
        <span className="w-32 shrink-0">Group</span>
        <span className="flex-1">Net profit (current ▪ scenario)</span>
        <span className="w-24 text-right">Scenario ROI</span>
        <span className="w-16 text-right">Δ ROI</span>
      </div>
      {rows.map((r) => (
        <div key={r.name} className="flex items-center gap-3">
          <span className="w-32 shrink-0 text-xs text-[var(--text-primary)] truncate">{r.name}</span>
          <div className="flex-1 space-y-1">
            <Bar val={r.current.net_profit} max={maxProfit} tone="current" />
            <Bar val={r.scenario.net_profit} max={maxProfit} tone="scenario" />
          </div>
          <span className="w-24 text-right text-xs font-medium">
            <span className="px-1.5 py-0.5 rounded text-white" style={{ background: roiColor(r.scenario.roi) }}>{fmtPct(r.scenario.roi)}</span>
          </span>
          <span className={`w-16 text-right text-xs font-medium ${Math.abs(r.roi_delta) < 0.005 ? 'text-[var(--text-secondary)]' : r.roi_delta > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
            {Math.abs(r.roi_delta) < 0.005 ? '—' : `${r.roi_delta > 0 ? '+' : ''}${fmtPct(r.roi_delta)}`}
          </span>
        </div>
      ))}
    </div>
  );
}

function Bar({ val, max, tone }: { val: number; max: number; tone: 'current' | 'scenario' }) {
  const neg = val < 0;
  const color = tone === 'current' ? (neg ? 'bg-red-300' : 'bg-zinc-400') : (neg ? 'bg-red-500' : 'bg-emerald-500');
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-3.5 rounded bg-[var(--bg-tertiary)] overflow-hidden">
        <div className={`h-full rounded ${color}`} style={{ width: `${(Math.abs(val) / max) * 100}%` }} />
      </div>
      <span className={`w-16 text-right text-[10px] ${tone === 'scenario' ? 'font-medium text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>{fmtMoneyShort(val)}</span>
    </div>
  );
}

function PromoCallout({ title, icon: Icon, tone, promos, onOpen }: {
  title: string; icon: any; tone: 'good' | 'bad'; promos: ImpactPromo[]; onOpen: (id: number) => void;
}) {
  return (
    <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3 flex items-center gap-1.5">
        <Icon className={`w-4 h-4 ${tone === 'good' ? 'text-emerald-600' : 'text-amber-600'}`} /> {title}
      </h3>
      <div className="space-y-1.5">
        {promos.map((p) => (
          <button key={p.promotion_id} onClick={() => onOpen(p.promotion_id)}
            className="w-full flex items-center gap-3 text-left px-3 py-2 rounded-lg hover:bg-[var(--bg-tertiary)] transition-colors">
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-[var(--text-primary)] truncate">{p.brand} <span className="text-[var(--text-secondary)]">· {p.market} · {p.channel}</span></div>
              <div className="text-[10px] text-[var(--text-secondary)]">{p.promo_mechanic} · disc {fmtPct(p.scenario_discount)} · spend {fmtMoneyShort(p.trade_spend)}</div>
            </div>
            <span className="px-2 py-0.5 rounded-full text-white text-xs font-semibold shrink-0" style={{ background: roiColor(p.roi) }}>{fmtPct(p.roi)}</span>
            {tone === 'good' ? <TrendingUp className="w-3.5 h-3.5 text-emerald-600 shrink-0" /> : <TrendingDown className="w-3.5 h-3.5 text-red-500 shrink-0" />}
          </button>
        ))}
      </div>
    </div>
  );
}
