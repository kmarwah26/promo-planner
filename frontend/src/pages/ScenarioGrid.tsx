import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Check, RotateCcw, Save, TrendingUp, Sparkles, Database, X, ArrowRight } from 'lucide-react';
import { api } from '../api';
import type { Promo, LakebaseWrite } from '../api';
import { useFilters } from '../store';
import FilterBar from '../components/FilterBar';
import { computeEcon } from '../format';
import { fmtMoneyShort, fmtPct, fmtInt, roiColor } from '../format';

interface Row extends Promo {
  // scenario discount currently in the grid (starts from adjusted_discount or discount_depth)
  scenarioDiscount: number;
  dirty: boolean;
  saving?: boolean;
}

const DISCOUNT_MIN = 0.0;
const DISCOUNT_MAX = 0.4;

export default function ScenarioGrid() {
  const { filters } = useFilters();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingAll, setSavingAll] = useState(false);
  // What the last save wrote to Lakebase (shown in a dismissible panel).
  const [lastSave, setLastSave] = useState<{
    database: string; instance: string; writes: LakebaseWrite[]; promosSaved: number;
  } | null>(null);

  const load = () => {
    setLoading(true);
    api.listPromos(filters).then((r) => {
      setRows(r.promos.map((p) => ({
        ...p,
        scenarioDiscount: p.plan_state?.adjusted_discount ?? p.discount_depth,
        dirty: false,
      })));
    }).finally(() => setLoading(false));
  };
  useEffect(load, [JSON.stringify(filters)]);

  // Live-recomputed economics per row for the current scenario discount.
  const computed = useMemo(() => rows.map((r) => ({
    row: r,
    econ: computeEcon(r, r.scenarioDiscount),
  })), [rows]);

  const setDiscount = (id: number, discount: number) => {
    const d = Math.max(DISCOUNT_MIN, Math.min(DISCOUNT_MAX, discount));
    setRows((prev) => prev.map((r) => r.promotion_id === id
      ? { ...r, scenarioDiscount: d, dirty: Math.abs(d - (r.plan_state?.adjusted_discount ?? r.discount_depth)) > 1e-6 }
      : r));
  };

  const resetRow = (id: number) => setRows((prev) => prev.map((r) => r.promotion_id === id
    ? { ...r, scenarioDiscount: r.discount_depth, dirty: Math.abs(r.discount_depth - (r.plan_state?.adjusted_discount ?? r.discount_depth)) > 1e-6 }
    : r));

  const saveRow = async (r: Row) => {
    const econ = computeEcon(r, r.scenarioDiscount);
    setRows((prev) => prev.map((x) => x.promotion_id === r.promotion_id ? { ...x, saving: true } : x));
    try {
      const res = await api.saveScenario(String(r.promotion_id), r.scenarioDiscount, econ.trade_spend);
      setLastSave({ database: res.lakebase.database, instance: res.lakebase.instance, writes: res.lakebase.writes, promosSaved: 1 });
    } finally {
      load();
    }
  };

  const saveAll = async () => {
    const dirty = rows.filter((r) => r.dirty);
    if (!dirty.length) return;
    setSavingAll(true);
    try {
      let last;
      for (const r of dirty) {
        const econ = computeEcon(r, r.scenarioDiscount);
        last = await api.saveScenario(String(r.promotion_id), r.scenarioDiscount, econ.trade_spend);
      }
      if (last) setLastSave({ database: last.lakebase.database, instance: last.lakebase.instance, writes: last.lakebase.writes, promosSaved: dirty.length });
    } finally {
      setSavingAll(false);
      load();
    }
  };

  // Portfolio totals: baseline (committed discount) vs scenario (edited discount).
  const totals = useMemo(() => {
    let baseSpend = 0, baseProfit = 0, baseIncr = 0;
    let scenSpend = 0, scenProfit = 0, scenIncr = 0;
    computed.forEach(({ row, econ }) => {
      const b = computeEcon(row, row.discount_depth);
      baseSpend += b.trade_spend; baseProfit += b.net_promo_profit; baseIncr += b.incremental_volume;
      scenSpend += econ.trade_spend; scenProfit += econ.net_promo_profit; scenIncr += econ.incremental_volume;
    });
    return {
      baseSpend, baseProfit, baseIncr, scenSpend, scenProfit, scenIncr,
      baseRoi: baseSpend ? baseProfit / baseSpend : 0,
      scenRoi: scenSpend ? scenProfit / scenSpend : 0,
    };
  }, [computed]);

  const dirtyCount = rows.filter((r) => r.dirty).length;

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 pt-6 pb-4 border-b border-[var(--border)] space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-bold text-[var(--text-primary)]">Scenario Planner</h2>
            <p className="text-sm text-[var(--text-secondary)]">Edit the discount for any promotion — forecast lift, trade spend, margin and ROI recompute instantly. Save to write the scenario back to Lakebase.</p>
          </div>
          <button onClick={saveAll} disabled={savingAll || dirtyCount === 0}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-semibold transition-colors disabled:opacity-40">
            {savingAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save scenario{dirtyCount > 0 ? ` (${dirtyCount})` : ''}
          </button>
        </div>
        <ScenarioSummary totals={totals} />
        {lastSave && <LakebaseWritePanel save={lastSave} onClose={() => setLastSave(null)} />}
        <FilterBar showStatus={false} />
      </div>

      <div className="flex-1 overflow-auto px-8 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…</div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            {/* Grid */}
            <div className="xl:col-span-2 overflow-x-auto">
              <table className="w-full text-sm border-separate border-spacing-y-1">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wide text-[var(--text-secondary)]">
                    <th className="text-left font-semibold px-3 py-1">Promotion</th>
                    <th className="text-left font-semibold px-2">Mechanic</th>
                    <th className="text-center font-semibold px-2 w-44">Discount</th>
                    <th className="text-right font-semibold px-2">Fcst Lift</th>
                    <th className="text-right font-semibold px-2">Trade $</th>
                    <th className="text-right font-semibold px-2">Net Profit</th>
                    <th className="text-right font-semibold px-3">ROI</th>
                    <th className="px-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {computed.map(({ row, econ }) => {
                    const roiDelta = econ.promo_roi - computeEcon(row, row.discount_depth).promo_roi;
                    return (
                      <tr key={row.promotion_id} className={`bg-[var(--bg-secondary)] ${row.dirty ? 'ring-1 ring-[var(--accent)]' : ''}`}>
                        <td className="px-3 py-2 rounded-l-lg cursor-pointer" onClick={() => navigate(`/promos/${row.promotion_id}`)}>
                          <div className="font-medium text-[var(--text-primary)]">{row.brand}</div>
                          <div className="text-[11px] text-[var(--text-secondary)]">{row.market} · {row.channel}</div>
                        </td>
                        <td className="px-2 text-xs text-[var(--text-secondary)]">{row.promo_mechanic}</td>
                        {/* Editable discount cell with inline bar + slider */}
                        <td className="px-2">
                          <div className="flex items-center gap-2">
                            <input type="range" min={DISCOUNT_MIN * 100} max={DISCOUNT_MAX * 100} step={1}
                              value={Math.round(row.scenarioDiscount * 100)}
                              onChange={(e) => setDiscount(row.promotion_id, Number(e.target.value) / 100)}
                              className="flex-1 accent-[var(--accent)] cursor-pointer" />
                            <input type="number" min={0} max={40}
                              value={Math.round(row.scenarioDiscount * 100)}
                              onChange={(e) => setDiscount(row.promotion_id, Number(e.target.value) / 100)}
                              className="w-12 px-1 py-0.5 rounded border border-[var(--border)] bg-[var(--bg-primary)] text-xs text-right" />
                            <span className="text-[10px] text-[var(--text-secondary)]">%</span>
                          </div>
                        </td>
                        <td className="px-2 text-right">
                          <span className="text-[var(--text-primary)]">{fmtPct(econ.incrementality_pct)}</span>
                        </td>
                        <td className="px-2 text-right text-[var(--text-primary)]">{fmtMoneyShort(econ.trade_spend)}</td>
                        <td className={`px-2 text-right font-medium ${econ.net_promo_profit < 0 ? 'text-red-600' : 'text-emerald-600'}`}>{fmtMoneyShort(econ.net_promo_profit)}</td>
                        <td className="px-3 text-right">
                          <span className="px-2 py-0.5 rounded-full text-white text-xs font-semibold" style={{ background: roiColor(econ.promo_roi) }}>{fmtPct(econ.promo_roi)}</span>
                          {row.dirty && Math.abs(roiDelta) > 0.005 && (
                            <span className={`ml-1 text-[10px] ${roiDelta > 0 ? 'text-emerald-600' : 'text-red-600'}`}>{roiDelta > 0 ? '▲' : '▼'}{fmtPct(Math.abs(roiDelta))}</span>
                          )}
                        </td>
                        <td className="px-2 rounded-r-lg text-right whitespace-nowrap">
                          {row.dirty && (
                            <>
                              <button onClick={() => resetRow(row.promotion_id)} title="Reset" className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><RotateCcw className="w-3.5 h-3.5" /></button>
                              <button onClick={() => saveRow(row)} disabled={row.saving} title="Save" className="p-1 rounded text-emerald-600 hover:bg-emerald-50">{row.saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-4 h-4" />}</button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Linked charts */}
            <div className="space-y-6">
              <RoiByBrandChart computed={computed} />
              <SpendVsLiftScatter computed={computed} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function LakebaseWritePanel({ save, onClose }: {
  save: { database: string; instance: string; writes: LakebaseWrite[]; promosSaved: number };
  onClose: () => void;
}) {
  const opColor = (op: string) =>
    op === 'INSERT' ? 'bg-emerald-100 text-emerald-700'
      : op === 'UPSERT' ? 'bg-blue-100 text-blue-700'
      : 'bg-zinc-100 text-zinc-700';
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Check className="w-4 h-4 text-emerald-600" />
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Scenario saved to Lakebase
            {save.promosSaved > 1 ? ` — ${save.promosSaved} promotions` : ''}
          </p>
        </div>
        <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-3.5 h-3.5" /></button>
      </div>

      <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)] mt-1.5 ml-6">
        <Database className="w-3 h-3" />
        <span>instance <span className="font-mono text-[var(--text-primary)]">{save.instance}</span></span>
        <ArrowRight className="w-3 h-3" />
        <span>database <span className="font-mono text-[var(--text-primary)]">{save.database}</span></span>
        <span className="text-[var(--text-secondary)]">· Postgres</span>
      </div>

      <div className="mt-3 ml-6 space-y-2">
        {save.writes.map((wr, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className={`px-1.5 py-0.5 rounded font-mono font-semibold shrink-0 ${opColor(wr.operation)}`}>{wr.operation}</span>
            <div className="min-w-0">
              <span className="font-mono font-medium text-[var(--text-primary)]">public.{wr.table}</span>
              <span className="text-[var(--text-secondary)]"> where {wr.row_key}</span>
              <div className="text-[var(--text-secondary)] mt-0.5">
                {Object.entries(wr.columns).map(([k, v], j) => (
                  <span key={k}>
                    {j > 0 && ', '}
                    <span className="font-mono">{k}</span>=<span className="font-mono text-[var(--text-primary)]">{typeof v === 'number' ? v : `"${v}"`}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-[var(--text-secondary)] mt-3 ml-6">
        Analytical promotion data stays in Unity Catalog; only operational plan state is written here. Track the full history under a promotion's Activity log.
      </p>
    </div>
  );
}

function ScenarioSummary({ totals }: { totals: any }) {
  const items = [
    { label: 'Trade Spend', base: totals.baseSpend, scen: totals.scenSpend, money: true, goodLow: true },
    { label: 'Incremental Volume', base: totals.baseIncr, scen: totals.scenIncr, money: false, goodLow: false },
    { label: 'Net Promo Profit', base: totals.baseProfit, scen: totals.scenProfit, money: true, goodLow: false },
    { label: 'Blended ROI', base: totals.baseRoi, scen: totals.scenRoi, pct: true, goodLow: false },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {items.map((it) => {
        const delta = it.scen - it.base;
        const improved = it.goodLow ? delta < 0 : delta > 0;
        const changed = Math.abs(delta) > (it.pct ? 0.001 : 1);
        const fmt = (v: number) => it.pct ? fmtPct(v) : it.money ? fmtMoneyShort(v) : fmtInt(v);
        return (
          <div key={it.label} className="p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
            <p className="text-[11px] text-[var(--text-secondary)]">{it.label}</p>
            <p className="text-xl font-bold tracking-tight text-[var(--text-primary)]">{fmt(it.scen)}</p>
            {changed ? (
              <p className={`text-[11px] font-medium ${improved ? 'text-emerald-600' : 'text-red-600'}`}>
                {delta > 0 ? '▲' : '▼'} {fmt(Math.abs(delta))} vs current
              </p>
            ) : (
              <p className="text-[11px] text-[var(--text-secondary)]">current plan</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function RoiByBrandChart({ computed }: { computed: { row: Promo; econ: any }[] }) {
  const byBrand = useMemo(() => {
    const m = new Map<string, { spend: number; profit: number }>();
    computed.forEach(({ row, econ }) => {
      const e = m.get(row.brand) || { spend: 0, profit: 0 };
      e.spend += econ.trade_spend; e.profit += econ.net_promo_profit;
      m.set(row.brand, e);
    });
    return [...m.entries()].map(([brand, v]) => ({ brand, roi: v.spend ? v.profit / v.spend : 0 }))
      .sort((a, b) => b.roi - a.roi);
  }, [computed]);
  const max = Math.max(0.01, ...byBrand.map((b) => Math.abs(b.roi)));
  return (
    <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3 flex items-center gap-1.5"><TrendingUp className="w-4 h-4 text-[var(--accent)]" /> Scenario ROI by brand</h3>
      <div className="space-y-2">
        {byBrand.map((b) => (
          <div key={b.brand} className="flex items-center gap-2">
            <span className="w-28 shrink-0 text-xs text-[var(--text-primary)] truncate">{b.brand}</span>
            <div className="flex-1 h-5 rounded-md bg-[var(--bg-tertiary)] overflow-hidden">
              <div className="h-full rounded-md" style={{ width: `${(Math.abs(b.roi) / max) * 100}%`, background: roiColor(b.roi) }} />
            </div>
            <span className="w-14 text-right text-xs font-medium text-[var(--text-primary)]">{fmtPct(b.roi)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SpendVsLiftScatter({ computed }: { computed: { row: Promo; econ: any }[] }) {
  // x = trade spend, y = incremental volume, color = ROI
  const pts = computed.map(({ row, econ }) => ({
    x: econ.trade_spend, y: econ.incremental_volume, roi: econ.promo_roi, brand: row.brand, code: row.promotion_code,
  }));
  const maxX = Math.max(1, ...pts.map((p) => p.x));
  const maxY = Math.max(1, ...pts.map((p) => p.y));
  const W = 260, H = 180, pad = 8;
  return (
    <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
      <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1 flex items-center gap-1.5"><Sparkles className="w-4 h-4 text-[var(--accent)]" /> Trade spend vs incremental volume</h3>
      <p className="text-[11px] text-[var(--text-secondary)] mb-2">Each dot is a promotion, colored by ROI. Top-left = efficient (low spend, high lift).</p>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {/* axes */}
        <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="var(--border)" />
        <line x1={pad} y1={pad} x2={pad} y2={H - pad} stroke="var(--border)" />
        {pts.map((p, i) => (
          <circle key={i}
            cx={pad + (p.x / maxX) * (W - 2 * pad)}
            cy={(H - pad) - (p.y / maxY) * (H - 2 * pad)}
            r={4} fill={roiColor(p.roi)} fillOpacity={0.8} stroke="white" strokeWidth={0.5}>
            <title>{p.code} · {p.brand} · ROI {fmtPct(p.roi)}</title>
          </circle>
        ))}
      </svg>
      <div className="flex justify-between text-[10px] text-[var(--text-secondary)] mt-1">
        <span>← trade spend →</span>
        <span>↑ incremental volume</span>
      </div>
    </div>
  );
}
