import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Loader2, RotateCcw, Send, Check, Percent, DollarSign, X, Database,
  ArrowRight, CheckCircle2, Download, Info,
} from 'lucide-react';
import { api } from '../api';
import type { IsoWeek, GridLine, Budget, CellEdit, SubmitResult, FinalExport } from '../api';
import { useFilters, TAB_PLAN_YEAR } from '../store';
import type { PlanTab, PlanView } from '../store';
import FilterBar from '../components/FilterBar';
import { fmtInt, fmtMoney, fmtPct, fmtPrice, discountColor, cellDepth, recPptr } from '../format';

const PAGE = 100;
const ROW_H = 34;
const CELL_W = 52;
const OVERSCAN = 8;

// Stable per-browser sandbox id so in-progress edits survive reloads.
function getSandboxId(): string {
  const KEY = 'promo1yp_sandbox';
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = 'sbx-' + Math.random().toString(36).slice(2, 10);
    localStorage.setItem(KEY, id);
  }
  return id;
}

const VIEWS: { id: PlanView; label: string }[] = [
  { id: 'incremental', label: 'Incremental Discount Plan' },
  { id: 'absolute', label: 'Absolute Discount Plan' },
  { id: 'rec_pptr', label: 'REC PPTR Plan' },
];

// Left (frozen) metadata columns and their widths.
const LEFT_COLS: { key: keyof GridLine | 'brand'; label: string; w: number }[] = [
  { key: 'wholesaler_id', label: 'Wholesaler', w: 190 },
  { key: 'brand_code', label: 'Brand', w: 52 },
  { key: 'brand_name', label: 'Brand Name', w: 150 },
  { key: 'prc_code', label: 'PRC', w: 60 },
  { key: 'prc_group_name', label: 'PRC Group', w: 130 },
  { key: 'qd_min', label: 'QD Min', w: 56 },
  { key: 'qd_max', label: 'QD Max', w: 56 },
  { key: 'deal_description', label: 'Deal', w: 120 },
];
const LEFT_W = LEFT_COLS.reduce((s, c) => s + c.w, 0);
const CHECK_W = 34;

export default function PricingGrid({ tab }: { tab: PlanTab }) {
  const planYear = TAB_PLAN_YEAR[tab];
  const editable = tab === 'builder2027';
  const isFinal = tab === 'final';
  const { filters } = useFilters();
  const sandboxId = useMemo(getSandboxId, []);

  const [weeks, setWeeks] = useState<IsoWeek[]>([]);
  const [lines, setLines] = useState<GridLine[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [view, setView] = useState<PlanView>('rec_pptr');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const offsetRef = useRef(0);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [popup, setPopup] = useState<null | 'incremental' | 'absolute'>(null);
  const [busy, setBusy] = useState(false);
  const [submitResult, setSubmitResult] = useState<SubmitResult | null>(null);
  const [finalExport, setFinalExport] = useState<FinalExport | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(600);

  const filterQ = { wholesaler: filters.wholesaler, brand: filters.brand, prc_group: filters.prc_group };

  // Load the 52-week axis once.
  useEffect(() => { api.getWeeks().then((r) => setWeeks(r.weeks)).catch(() => {}); }, []);

  // (Re)load the grid whenever tab / filters change.
  const reload = useCallback(() => {
    setLoading(true);
    setLines([]);
    setSelected(new Set());
    offsetRef.current = 0;
    setHasMore(true);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
    const q = { plan_year: planYear, ...filterQ, limit: PAGE, offset: 0, sandbox_id: editable ? sandboxId : undefined };
    Promise.all([api.getGrid(q), api.getBudget({ plan_year: planYear, ...filterQ })])
      .then(([g, b]) => {
        setLines(g.lines);
        offsetRef.current = g.lines.length;
        setHasMore(g.count === PAGE);
        setBudget(b);
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planYear, editable, sandboxId, JSON.stringify(filterQ)]);

  useEffect(reload, [reload]);

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    const q = { plan_year: planYear, ...filterQ, limit: PAGE, offset: offsetRef.current, sandbox_id: editable ? sandboxId : undefined };
    api.getGrid(q).then((g) => {
      setLines((prev) => [...prev, ...g.lines]);
      offsetRef.current += g.lines.length;
      setHasMore(g.count === PAGE);
    }).finally(() => setLoadingMore(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMore, hasMore, planYear, editable, sandboxId, JSON.stringify(filterQ)]);

  // Manual vertical windowing + infinite scroll.
  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    setScrollTop(el.scrollTop);
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 400) loadMore();
  };
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setViewportH(el.clientHeight));
    ro.observe(el);
    setViewportH(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  const start = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
  const end = Math.min(lines.length, Math.ceil((scrollTop + viewportH) / ROW_H) + OVERSCAN);
  const visible = lines.slice(start, end);

  // ── Selection ──
  const allSelected = lines.length > 0 && selected.size === lines.length;
  const toggleRow = (key: string) => setSelected((prev) => {
    const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n;
  });
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(lines.map((l) => l.line_key)));

  // ── Apply a discount to the selected rows across a week range (mass edit). ──
  const applyDiscount = async (kind: 'incremental' | 'absolute', value: number, wkFrom: number, wkTo: number) => {
    const targets = lines.filter((l) => selected.has(l.line_key));
    if (!targets.length) return;
    setBusy(true);
    const edits: CellEdit[] = [];
    for (const l of targets) {
      for (let wk = wkFrom; wk <= wkTo; wk++) {
        edits.push({
          wholesaler_id: l.wholesaler_id, brand_code: l.brand_code, prc_code: l.prc_code,
          week_number: wk,
          incremental_discount: kind === 'incremental' ? value : null,
          absolute_discount: kind === 'absolute' ? value : null,
        });
      }
    }
    try {
      await api.saveEdits(sandboxId, planYear, edits);
      // Optimistic local overlay.
      setLines((prev) => prev.map((l) => {
        if (!selected.has(l.line_key)) return l;
        const cells = { ...l.cells };
        for (let wk = wkFrom; wk <= wkTo; wk++) {
          const inc = kind === 'incremental' ? value : null;
          const absd = kind === 'absolute' ? value : null;
          cells[String(wk)] = {
            week: wk, incremental_discount: inc, absolute_discount: absd,
            rec_pptr: recPptr(l.base_pptr, inc, absd),
            approval_status: 'sandbox', source: 'sandbox',
          };
        }
        return { ...l, cells };
      }));
      api.getBudget({ plan_year: planYear, ...filterQ }).then(setBudget).catch(() => {});
    } finally {
      setBusy(false);
      setPopup(null);
    }
  };

  const resetAll = async () => {
    setBusy(true);
    try {
      await api.resetSandbox(sandboxId, planYear);
      reload();
    } finally { setBusy(false); }
  };

  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.submitSandbox(sandboxId, planYear);
      setSubmitResult(r);
      reload();
    } finally { setBusy(false); }
  };

  const approve = async () => {
    setBusy(true);
    try {
      await api.approveFinal({ plan_year: planYear, ...filterQ });
      reload();
    } finally { setBusy(false); }
  };

  const pushDownstream = async () => {
    setBusy(true);
    try { setFinalExport(await api.getFinalExport(filterQ)); }
    finally { setBusy(false); }
  };

  const totalH = lines.length * ROW_H;

  return (
    <div className="h-full flex flex-col">
      {/* Header: title, view toggle, actions */}
      <div className="px-6 pt-4 pb-3 border-b border-[var(--border)] space-y-3">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 rounded-lg bg-[var(--bg-tertiary)] p-0.5">
            {VIEWS.map((v) => (
              <button key={v.id} onClick={() => setView(v.id)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  view === v.id ? 'bg-[var(--bg-secondary)] text-[var(--accent)] shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}>
                {v.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {editable && (
              <>
                <span className="text-xs text-[var(--text-secondary)]">{selected.size} selected</span>
                <button disabled={!selected.size || busy} onClick={() => setPopup('incremental')}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm font-medium disabled:opacity-40 hover:border-[var(--accent)]">
                  <Percent className="w-3.5 h-3.5" /> Incremental discount
                </button>
                <button disabled={!selected.size || busy} onClick={() => setPopup('absolute')}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm font-medium disabled:opacity-40 hover:border-[var(--accent)]">
                  <DollarSign className="w-3.5 h-3.5" /> Absolute discount
                </button>
                <button disabled={busy} onClick={resetAll} title="Revert all sandbox edits"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm font-medium disabled:opacity-40 hover:border-[var(--danger)] hover:text-[var(--danger)]">
                  <RotateCcw className="w-3.5 h-3.5" /> Reset {planYear} plan
                </button>
                <button disabled={busy} onClick={submit}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-semibold disabled:opacity-40">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Submit to production
                </button>
              </>
            )}
            {isFinal && (
              <>
                <button disabled={busy} onClick={approve}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-40">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Approve pending
                </button>
                <button disabled={busy} onClick={pushDownstream}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-semibold disabled:opacity-40">
                  <Download className="w-4 h-4" /> Push downstream
                </button>
              </>
            )}
          </div>
        </div>

        <BudgetBar budget={budget} planYear={planYear} />
        <FilterBar />
        {submitResult && <SubmitPanel result={submitResult} onClose={() => setSubmitResult(null)} />}
        {finalExport && <FinalExportPanel data={finalExport} onClose={() => setFinalExport(null)} />}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading grid…</div>
      ) : lines.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-[var(--text-secondary)] text-sm">No lines match the current filters.</div>
      ) : (
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-auto">
          <div style={{ width: CHECK_W + LEFT_W + weeks.length * CELL_W, position: 'relative' }}>
            {/* Sticky header */}
            <div className="sticky top-0 z-20 flex bg-[var(--bg-tertiary)] border-b border-[var(--border)]" style={{ height: ROW_H }}>
              <div className="sticky left-0 z-30 flex items-center justify-center bg-[var(--bg-tertiary)] border-r border-[var(--border)]" style={{ width: CHECK_W }}>
                {editable && <input type="checkbox" checked={allSelected} onChange={toggleAll} className="accent-[var(--accent)] cursor-pointer" />}
              </div>
              <div className="sticky z-30 flex bg-[var(--bg-tertiary)] border-r-2 border-[var(--border-strong)]" style={{ left: CHECK_W }}>
                {LEFT_COLS.map((c) => (
                  <div key={c.key as string} className="flex items-center px-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]" style={{ width: c.w }}>{c.label}</div>
                ))}
              </div>
              {weeks.map((w) => (
                <div key={w.week_number} className="flex flex-col items-center justify-center border-r border-[var(--border)]" style={{ width: CELL_W }}>
                  <span className="text-[10px] font-semibold text-[var(--text-primary)] leading-none">{w.iso_label}</span>
                  <span className="text-[8px] text-[var(--text-tertiary)] leading-none mt-0.5">{w.date_range_label}</span>
                </div>
              ))}
            </div>

            {/* Windowed rows */}
            <div style={{ height: totalH, position: 'relative' }}>
              {visible.map((line, i) => {
                const rowIndex = start + i;
                const isSel = selected.has(line.line_key);
                return (
                  <div key={line.line_key} className={`flex items-stretch absolute left-0 ${isSel ? 'bg-[var(--accent-dim)]' : rowIndex % 2 ? 'bg-[var(--bg-primary)]' : 'bg-[var(--bg-secondary)]'}`}
                    style={{ top: rowIndex * ROW_H, height: ROW_H, width: '100%' }}>
                    {/* checkbox */}
                    <div className={`sticky left-0 z-10 flex items-center justify-center border-r border-b border-[var(--border)] ${isSel ? 'bg-[var(--accent-dim)]' : rowIndex % 2 ? 'bg-[var(--bg-primary)]' : 'bg-[var(--bg-secondary)]'}`} style={{ width: CHECK_W }}>
                      {editable && <input type="checkbox" checked={isSel} onChange={() => toggleRow(line.line_key)} className="accent-[var(--accent)] cursor-pointer" />}
                    </div>
                    {/* frozen metadata */}
                    <div className={`sticky z-10 flex border-r-2 border-b border-[var(--border-strong)] ${isSel ? 'bg-[var(--accent-dim)]' : rowIndex % 2 ? 'bg-[var(--bg-primary)]' : 'bg-[var(--bg-secondary)]'}`} style={{ left: CHECK_W }}>
                      <MetaCell w={LEFT_COLS[0].w} title={line.wholesaler_name}><span className="font-medium">{line.wholesaler_id}</span> <span className="text-[var(--text-tertiary)]">{line.wholesaler_name}</span></MetaCell>
                      <MetaCell w={LEFT_COLS[1].w}>{line.brand_code}</MetaCell>
                      <MetaCell w={LEFT_COLS[2].w} title={line.brand_name}>{line.brand_name}</MetaCell>
                      <MetaCell w={LEFT_COLS[3].w}>{line.prc_code}</MetaCell>
                      <MetaCell w={LEFT_COLS[4].w} title={line.prc_group_name}>{line.prc_group_name}</MetaCell>
                      <MetaCell w={LEFT_COLS[5].w}>{fmtInt(line.qd_min)}</MetaCell>
                      <MetaCell w={LEFT_COLS[6].w}>{fmtInt(line.qd_max)}</MetaCell>
                      <MetaCell w={LEFT_COLS[7].w} title={line.deal_description}>{line.deal_description}</MetaCell>
                    </div>
                    {/* week cells */}
                    {weeks.map((w) => {
                      const cell = line.cells[String(w.week_number)];
                      return <WeekCell key={w.week_number} line={line} week={w} cell={cell} view={view} />;
                    })}
                  </div>
                );
              })}
            </div>
          </div>
          {loadingMore && <div className="flex items-center justify-center py-3 text-[var(--text-secondary)] text-xs"><Loader2 className="w-4 h-4 animate-spin mr-1.5" /> Loading more…</div>}
        </div>
      )}
      {!loading && (
        <div className="shrink-0 px-6 py-1.5 border-t border-[var(--border)] text-[11px] text-[var(--text-secondary)] flex items-center gap-3">
          <span>{fmtInt(lines.length)} lines loaded{hasMore ? ' (scroll for more)' : ''}</span>
          {budget && <span>· {fmtInt(budget.n_lines)} total in filter</span>}
          {editable && <span className="ml-auto inline-flex items-center gap-1"><Info className="w-3 h-3" /> Sandbox edits are private until you Submit</span>}
        </div>
      )}

      {popup && (
        <DiscountPopup kind={popup} weeks={weeks} count={selected.size}
          onClose={() => setPopup(null)} onApply={(v, f, t) => applyDiscount(popup, v, f, t)} busy={busy} />
      )}
    </div>
  );
}

function MetaCell({ w, title, children }: { w: number; title?: string; children: React.ReactNode }) {
  return <div className="flex items-center px-2 text-[11px] text-[var(--text-primary)] truncate" style={{ width: w }} title={title}>{children}</div>;
}

function WeekCell({ line, week, cell, view }: { line: GridLine; week: IsoWeek; cell?: any; view: PlanView }) {
  const hasPromo = !!cell && (cell.incremental_discount != null || cell.absolute_discount != null);
  const depth = hasPromo ? cellDepth(line.base_pptr, cell.incremental_discount, cell.absolute_discount) : 0;
  const bg = hasPromo ? discountColor(depth) : 'transparent';
  const isSandbox = cell?.source === 'sandbox';

  let text = '';
  if (hasPromo) {
    if (view === 'incremental') text = cell.incremental_discount != null ? fmtPct(cell.incremental_discount) : (cell.absolute_discount != null ? `-${fmtPrice(cell.absolute_discount)}` : '');
    else if (view === 'absolute') text = cell.absolute_discount != null ? fmtPrice(cell.absolute_discount) : (cell.incremental_discount != null ? fmtPrice(line.base_pptr - (cell.rec_pptr ?? line.base_pptr)) : '');
    else text = fmtPrice(cell.rec_pptr);
  }
  const tip = hasPromo ? `${line.plan_year}-${week.iso_label} ${week.date_range_label} · REC PPTR ${fmtPrice(cell.rec_pptr)}${isSandbox ? ' (sandbox)' : cell.approval_status ? ` (${cell.approval_status})` : ''}` : `${week.iso_label} ${week.date_range_label}`;

  return (
    <div className={`flex items-center justify-center border-r border-b border-[var(--border)] text-[10px] tabular-nums ${isSandbox ? 'ring-1 ring-inset ring-[var(--accent)] font-semibold' : ''}`}
      style={{ width: CELL_W, background: bg }} title={tip}>
      {text}
    </div>
  );
}

function BudgetBar({ budget, planYear }: { budget: Budget | null; planYear: number }) {
  const items = [
    { label: 'Total discount ($/case)', value: budget ? fmtMoney(budget.total_discount) : '—' },
    { label: 'Avg incremental discount', value: budget ? fmtPct(budget.avg_incremental_discount) : '—' },
    { label: 'Lines on promo', value: budget ? `${fmtInt(budget.n_lines_on_promo)} / ${fmtInt(budget.n_lines)}` : '—' },
    { label: 'Promo weeks', value: budget ? fmtInt(budget.n_promo_weeks) : '—' },
  ];
  return (
    <div className="flex items-stretch gap-3 flex-wrap">
      <div className="flex items-center px-3 rounded-lg bg-[var(--accent)] text-white">
        <span className="text-xs font-semibold">Budget · {planYear}</span>
      </div>
      {items.map((it) => (
        <div key={it.label} className="px-3 py-1.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)]">
          <p className="text-[10px] text-[var(--text-secondary)] leading-tight">{it.label}</p>
          <p className="text-sm font-bold text-[var(--text-primary)] leading-tight">{it.value}</p>
        </div>
      ))}
    </div>
  );
}

function DiscountPopup({ kind, weeks, count, onClose, onApply, busy }: {
  kind: 'incremental' | 'absolute'; weeks: IsoWeek[]; count: number;
  onClose: () => void; onApply: (value: number, wkFrom: number, wkTo: number) => void; busy: boolean;
}) {
  const [value, setValue] = useState(kind === 'incremental' ? 10 : 5);
  const [wkFrom, setWkFrom] = useState(1);
  const [wkTo, setWkTo] = useState(4);
  const maxWk = weeks.length || 52;
  const apply = () => {
    const v = kind === 'incremental' ? value / 100 : value;
    onApply(v, Math.min(wkFrom, wkTo), Math.max(wkFrom, wkTo));
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="w-96 rounded-2xl bg-[var(--bg-secondary)] p-5 shadow-xl" onClick={(e) => e.stopPropagation()} style={{ boxShadow: 'var(--shadow-lg)' }}>
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-base font-bold text-[var(--text-primary)]">{kind === 'incremental' ? 'Incremental discount' : 'Absolute discount'}</h3>
          <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-xs text-[var(--text-secondary)] mb-4">Apply to <span className="font-semibold text-[var(--text-primary)]">{count}</span> selected line{count === 1 ? '' : 's'} across the chosen week range.</p>

        <label className="text-[11px] font-medium text-[var(--text-secondary)]">{kind === 'incremental' ? 'Discount % off base REC PPTR' : 'Dollars off base REC PPTR (per case)'}</label>
        <div className="flex items-center gap-2 mt-1 mb-4">
          <input type="number" value={value} min={0} step={kind === 'incremental' ? 1 : 0.5}
            onChange={(e) => setValue(Number(e.target.value))}
            className="flex-1 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-sm" />
          <span className="text-sm text-[var(--text-secondary)]">{kind === 'incremental' ? '%' : '$'}</span>
        </div>

        <label className="text-[11px] font-medium text-[var(--text-secondary)]">Week range</label>
        <div className="flex items-center gap-2 mt-1 mb-5">
          <input type="number" value={wkFrom} min={1} max={maxWk} onChange={(e) => setWkFrom(Number(e.target.value))} className="w-20 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-sm" />
          <ArrowRight className="w-4 h-4 text-[var(--text-secondary)]" />
          <input type="number" value={wkTo} min={1} max={maxWk} onChange={(e) => setWkTo(Number(e.target.value))} className="w-20 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-sm" />
          <span className="text-xs text-[var(--text-secondary)]">of {maxWk} weeks</span>
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">Cancel</button>
          <button onClick={apply} disabled={busy || !count}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-semibold disabled:opacity-40">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Apply
          </button>
        </div>
      </div>
    </div>
  );
}

function SubmitPanel({ result, onClose }: { result: SubmitResult; onClose: () => void }) {
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {result.submitted > 0 ? `Submitted ${result.submitted} cell(s) to production` : (result.detail || 'Nothing to submit')}
          </p>
        </div>
        <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-3.5 h-3.5" /></button>
      </div>
      {result.writes && (
        <div className="mt-2 ml-6 space-y-1.5">
          {result.writes.map((wr, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className="px-1.5 py-0.5 rounded font-mono font-semibold shrink-0 bg-blue-100 text-blue-700">{wr.operation}</span>
              <div>
                <span className="inline-flex items-center gap-1 text-[10px] font-medium text-[var(--text-secondary)]"><Database className="w-3 h-3" /> {wr.target}</span>
                <span className="font-mono ml-1 text-[var(--text-primary)]">{wr.table}</span>
                <div className="text-[var(--text-secondary)]">{wr.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="text-[10px] text-[var(--text-secondary)] mt-2 ml-6">Sandbox edits promoted to the governed Unity Catalog table as <span className="font-medium">pending</span> — the CSO team approves them in Final Plan.</p>
    </div>
  );
}

function FinalExportPanel({ data, onClose }: { data: FinalExport; onClose: () => void }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Download className="w-4 h-4 text-[var(--accent)]" />
          <p className="text-sm font-semibold text-[var(--text-primary)]">Downstream API payload — {fmtInt(data.count)} approved pricing rows</p>
        </div>
        <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-3.5 h-3.5" /></button>
      </div>
      <p className="text-[11px] text-[var(--text-secondary)] mt-1 ml-6 mb-2">
        <span className="font-mono">GET /api/pricing/final</span> — the JSON another application pulls once pricing is finally approved.
      </p>
      <pre className="ml-6 max-h-52 overflow-auto rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] p-2 text-[10px] font-mono text-[var(--text-primary)]">
{JSON.stringify(data.pricing.slice(0, 20), null, 2)}
{data.pricing.length > 20 ? `\n… ${data.pricing.length - 20} more` : ''}
      </pre>
    </div>
  );
}
