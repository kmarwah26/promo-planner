import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Lock } from 'lucide-react';
import { api } from '../api';
import type { CalendarPromo, CalendarWeek } from '../api';
import { useFilters } from '../store';
import FilterBar from '../components/FilterBar';
import KpiTiles from '../components/KpiTiles';
import { roiColor, fmtMoneyShort, fmtPct } from '../format';

export default function CalendarView() {
  const { filters } = useFilters();
  const navigate = useNavigate();
  const [promos, setPromos] = useState<CalendarPromo[]>([]);
  const [weeks, setWeeks] = useState<CalendarWeek[]>([]);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<CalendarPromo | null>(null);

  useEffect(() => {
    setLoading(true);
    api.calendar(filters)
      .then((r) => { setPromos(r.promos); setWeeks(r.weeks); })
      .finally(() => setLoading(false));
  }, [JSON.stringify(filters)]);

  // Group promos into lanes by market > brand for readability
  const rows = useMemo(() => {
    const sorted = [...promos].sort((a, b) =>
      a.market.localeCompare(b.market) || a.brand.localeCompare(b.brand) || a.start_week - b.start_week);
    return sorted;
  }, [promos]);

  // Quarter boundaries for header
  const quarterSpans = useMemo(() => {
    const spans: { q: string; start: number; count: number }[] = [];
    weeks.forEach((w) => {
      const last = spans[spans.length - 1];
      if (last && last.q === w.quarter) last.count++;
      else spans.push({ q: w.quarter, start: w.week_number, count: 1 });
    });
    return spans;
  }, [weeks]);

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 pt-6 pb-4 border-b border-[var(--border)] space-y-4">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)]">52-Week Planning Calendar</h2>
          <p className="text-sm text-[var(--text-secondary)]">Each bar is a promotion, positioned on its active weeks and colored by ROI.</p>
        </div>
        <KpiTiles filters={filters} />
        <div className="flex items-center justify-between gap-4">
          <FilterBar />
          <div className="flex items-center gap-3 text-[11px] text-[var(--text-secondary)] shrink-0">
            <span>ROI:</span>
            {[['≥50%', '#15803d'], ['≥20%', '#22c55e'], ['≥0%', '#a3e635'], ['<0%', '#fbbf24'], ['≤-20%', '#ef4444']].map(([l, c]) => (
              <span key={l} className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: c }} />{l}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto px-8 py-4 relative">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading calendar…</div>
        ) : rows.length === 0 ? (
          <div className="text-center py-20 text-[var(--text-secondary)]">No promotions match these filters.</div>
        ) : (
          <div className="min-w-[1100px]">
            {/* Quarter + week header */}
            <div className="flex sticky top-0 z-10 bg-[var(--bg-primary)]">
              <div className="w-56 shrink-0" />
              <div className="flex-1 grid" style={{ gridTemplateColumns: `repeat(52, minmax(0, 1fr))` }}>
                {quarterSpans.map((s) => (
                  <div key={s.q + s.start} style={{ gridColumn: `span ${s.count}` }}
                    className="text-center text-[11px] font-semibold text-[var(--text-secondary)] border-l border-[var(--border)] py-1">
                    {s.q}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex mb-1">
              <div className="w-56 shrink-0" />
              <div className="flex-1 grid" style={{ gridTemplateColumns: `repeat(52, minmax(0, 1fr))` }}>
                {weeks.map((w) => (
                  <div key={w.week_number} className="text-center text-[8px] text-[var(--text-secondary)] border-l border-[var(--border)]/40">
                    {w.week_number % 4 === 1 ? w.week_number : ''}
                  </div>
                ))}
              </div>
            </div>

            {/* Rows */}
            <div className="space-y-1">
              {rows.map((p) => {
                const locked = p.plan_state?.locked;
                return (
                  <div key={p.promotion_id} className="flex items-center group">
                    <div className="w-56 shrink-0 pr-3 truncate">
                      <span className="text-xs font-medium text-[var(--text-primary)]">{p.brand}</span>
                      <span className="text-[10px] text-[var(--text-secondary)]"> · {p.market}</span>
                    </div>
                    <div className="flex-1 grid relative h-6" style={{ gridTemplateColumns: `repeat(52, minmax(0, 1fr))` }}>
                      {weeks.map((w) => (
                        <div key={w.week_number} className="border-l border-[var(--border)]/30 h-full" />
                      ))}
                      <button
                        onClick={() => navigate(`/promos/${p.promotion_id}`)}
                        onMouseEnter={() => setHover(p)}
                        onMouseLeave={() => setHover(null)}
                        className="absolute h-4 top-1 rounded-md flex items-center justify-center hover:ring-2 hover:ring-offset-1 hover:ring-[var(--accent)] transition-all cursor-pointer"
                        style={{
                          left: `${((p.start_week - 1) / 52) * 100}%`,
                          width: `${((p.end_week - p.start_week + 1) / 52) * 100}%`,
                          background: roiColor(p.promo_roi),
                        }}
                        title={`${p.promotion_code} · ${p.promo_mechanic}`}
                      >
                        {locked && <Lock className="w-2.5 h-2.5 text-white/90" />}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Hover tooltip */}
        {hover && (
          <div className="fixed bottom-6 right-8 z-20 w-72 p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] shadow-2xl pointer-events-none">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-[var(--text-primary)]">{hover.promotion_code}</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full text-white" style={{ background: roiColor(hover.promo_roi) }}>ROI {fmtPct(hover.promo_roi)}</span>
            </div>
            <p className="text-xs text-[var(--text-secondary)] mb-2">{hover.brand} · {hover.pack}</p>
            <div className="grid grid-cols-2 gap-y-1 text-[11px]">
              <span className="text-[var(--text-secondary)]">Market</span><span className="text-right text-[var(--text-primary)]">{hover.market}</span>
              <span className="text-[var(--text-secondary)]">Channel</span><span className="text-right text-[var(--text-primary)]">{hover.channel}</span>
              <span className="text-[var(--text-secondary)]">Mechanic</span><span className="text-right text-[var(--text-primary)]">{hover.promo_mechanic}</span>
              <span className="text-[var(--text-secondary)]">Weeks</span><span className="text-right text-[var(--text-primary)]">{hover.start_week}–{hover.end_week}</span>
              <span className="text-[var(--text-secondary)]">Trade spend</span><span className="text-right text-[var(--text-primary)]">{fmtMoneyShort(hover.trade_spend)}</span>
              <span className="text-[var(--text-secondary)]">Net profit</span><span className="text-right text-[var(--text-primary)]">{fmtMoneyShort(hover.net_promo_profit)}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
