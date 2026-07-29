import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Loader2, RotateCcw, Send, Check, DollarSign, X, Database,
  ArrowRight, CheckCircle2, Download, Info, ClipboardCheck,
} from 'lucide-react';
import { api } from '../api';
import type { IsoWeek, GridLine, PromoCell, Budget, CellEdit, SubmitResult, FinalExport } from '../api';
import { useFilters, TAB_PLAN_YEAR } from '../store';
import type { PlanTab, PlanView } from '../store';
import FilterBar from '../components/FilterBar';
import { fmtInt, fmtMoney, fmtPrice, discountColor, cellDepth, cellOff, recPptr } from '../format';

const PAGE = 100;
const ROW_H = 44;
const CELL_W = 62;
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
const LEFT_COLS: { key: string; label: string; w: number }[] = [
  { key: 'wholesaler_id', label: 'Wholesaler', w: 210 },
  { key: 'brand_code', label: 'Brand', w: 60 },
  { key: 'brand_name', label: 'Brand Name', w: 168 },
  { key: 'prc_code', label: 'PRC', w: 70 },
  { key: 'prc_group_name', label: 'PRC Group', w: 150 },
  { key: 'qd_min', label: 'QD Min', w: 66 },
  { key: 'qd_max', label: 'QD Max', w: 66 },
  { key: 'deal_description', label: 'Deal', w: 138 },
  { key: 'curr_max_discount', label: 'Max Disc', w: 78 },
];
const LEFT_W = LEFT_COLS.reduce((s, c) => s + c.w, 0);
const CHECK_W = 40;
const REVIEW_W = 44;

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
  const [editing, setEditing] = useState<{ key: string; week: number } | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(600);

  const filterQ = { wholesaler: filters.wholesaler, brand: filters.brand, prc_group: filters.prc_group };

  useEffect(() => { api.getWeeks().then((r) => setWeeks(r.weeks)).catch(() => {}); }, []);

  const reload = useCallback(() => {
    setLoading(true);
    setLines([]);
    setSelected(new Set());
    setEditing(null);
    offsetRef.current = 0;
    setHasMore(true);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
    const q = { plan_year: planYear, ...filterQ, limit: PAGE, offset: 0, sandbox_id: editable ? sandboxId : undefined };
    Promise.all([api.getGrid(q), api.getBudget({ plan_year: planYear, ...filterQ, sandbox_id: editable ? sandboxId : undefined })])
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
  const reviewedCount = lines.filter((l) => l.reviewed).length;

  // Overlay a set of cell edits onto local state + refresh budget.
  const overlayCells = (predicate: (l: GridLine) => boolean, weeksList: number[], inc: number | null, absd: number | null) => {
    setLines((prev) => prev.map((l) => {
      if (!predicate(l)) return l;
      const cells = { ...l.cells };
      for (const wk of weeksList) {
        cells[String(wk)] = {
          week: wk, incremental_discount: inc, absolute_discount: absd,
          rec_pptr: recPptr(l.base_pptr, inc, absd),
          approval_status: 'sandbox', source: 'sandbox',
        };
      }
      return { ...l, cells };
    }));
    api.getBudget({ plan_year: planYear, ...filterQ, sandbox_id: editable ? sandboxId : undefined }).then(setBudget).catch(() => {});
  };

  // ── Mass discount apply across selected rows × week range. ──
  const applyDiscount = async (kind: 'incremental' | 'absolute', dollars: number, wkFrom: number, wkTo: number) => {
    const targets = lines.filter((l) => selected.has(l.line_key));
    if (!targets.length) return;
    setBusy(true);
    const edits: CellEdit[] = [];
    const weeksList: number[] = [];
    for (let wk = wkFrom; wk <= wkTo; wk++) weeksList.push(wk);
    for (const l of targets) {
      for (const wk of weeksList) {
        edits.push({
          wholesaler_id: l.wholesaler_id, brand_code: l.brand_code, prc_code: l.prc_code, week_number: wk,
          incremental_discount: kind === 'incremental' ? dollars : null,
          absolute_discount: kind === 'absolute' ? dollars : null,
        });
      }
    }
    try {
      await api.saveEdits(sandboxId, planYear, edits);
      overlayCells((l) => selected.has(l.line_key), weeksList, kind === 'incremental' ? dollars : null, kind === 'absolute' ? dollars : null);
    } finally {
      setBusy(false);
      setPopup(null);
    }
  };

  // ── Inline single-cell edit. The value entered depends on the active view. ──
  const commitCellEdit = (line: GridLine, week: number, raw: string) => {
    setEditing(null);
    const trimmed = (raw ?? '').trim();
    if (trimmed === '') return;                          // empty → cancel, keep prior value
    const val = parseFloat(trimmed);
    if (isNaN(val)) return;
    let inc: number | null = null, absd: number | null = null;
    if (view === 'incremental') inc = val;               // dollars off
    else if (view === 'absolute') absd = val;            // dollars off
    else absd = +(line.base_pptr - val).toFixed(2);      // REC PPTR view: entered price → $ off
    // Apply the optimistic overlay immediately so the cell shows the new value even if
    // the network is slow; the save runs in the background.
    overlayCells((l) => l.line_key === line.line_key, [week], inc, absd);
    api.saveEdits(sandboxId, planYear, [{
      wholesaler_id: line.wholesaler_id, brand_code: line.brand_code, prc_code: line.prc_code,
      week_number: week, incremental_discount: inc, absolute_discount: absd,
    }]).catch(() => reload());                           // on failure, resync from server
  };

  // ── Review (per-row + bulk) ──
  const setReviewed = async (keys: string[], reviewed: boolean) => {
    if (!keys.length) return;
    setBusy(true);
    try {
      await api.markReviewed(sandboxId, planYear, keys, reviewed);
      const ks = new Set(keys);
      setLines((prev) => prev.map((l) => ks.has(l.line_key) ? { ...l, reviewed } : l));
    } finally { setBusy(false); }
  };
  const reviewSelected = () => {
    const keys = lines.filter((l) => selected.has(l.line_key)).map((l) => l.line_key);
    const allReviewed = keys.length > 0 && keys.every((k) => lines.find((l) => l.line_key === k)?.reviewed);
    setReviewed(keys, !allReviewed);
  };

  const resetAll = async () => {
    setBusy(true);
    try { await api.resetSandbox(sandboxId, planYear); reload(); }
    finally { setBusy(false); }
  };
  const submit = async () => {
    setBusy(true);
    try { const r = await api.submitSandbox(sandboxId, planYear); setSubmitResult(r); reload(); }
    finally { setBusy(false); }
  };
  // Final Submission: CSO approves the pending rows, the grid reloads to show them as
  // approved, and the downstream (Pricing Hub) payload is returned in one step.
  const finalSubmit = async () => {
    setBusy(true);
    try {
      await api.approveFinal({ plan_year: planYear, ...filterQ });
      const exp = await api.getFinalExport(filterQ);
      setFinalExport(exp);
      reload();
    } finally { setBusy(false); }
  };

  const totalH = lines.length * ROW_H;
  const selCount = selected.size;

  return (
    <div className="h-full flex flex-col">
      {/* Header: view toggle + actions */}
      <div className="px-6 pt-4 pb-3 border-b border-[var(--border)] space-y-3">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-1 rounded-lg bg-[var(--bg-tertiary)] p-1">
            {VIEWS.map((v) => (
              <button key={v.id} onClick={() => setView(v.id)}
                className={`px-3.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  view === v.id ? 'bg-[var(--accent)] text-black shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}>
                {v.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {editable && (
              <>
                <span className="text-sm text-[var(--text-secondary)]">{selCount} selected</span>
                <button disabled={!selCount || busy} onClick={() => setPopup('incremental')}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm font-medium disabled:opacity-40 hover:border-[var(--accent)]">
                  <DollarSign className="w-4 h-4" /> Incremental $
                </button>
                <button disabled={!selCount || busy} onClick={() => setPopup('absolute')}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm font-medium disabled:opacity-40 hover:border-[var(--accent)]">
                  <DollarSign className="w-4 h-4" /> Absolute $
                </button>
                <button disabled={!selCount || busy} onClick={reviewSelected} title="Mark selected rows reviewed"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm font-medium disabled:opacity-40 hover:border-[var(--success)] hover:text-[var(--success)]">
                  <ClipboardCheck className="w-4 h-4" /> Review selected
                </button>
                <button disabled={busy} onClick={resetAll} title="Revert all sandbox edits"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm font-medium disabled:opacity-40 hover:border-[var(--danger)] hover:text-[var(--danger)]">
                  <RotateCcw className="w-4 h-4" /> Reset {planYear}
                </button>
                <button disabled={busy} onClick={submit}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-black text-sm font-semibold disabled:opacity-40">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Submit for Review
                </button>
              </>
            )}
            {isFinal && (
              <button disabled={busy} onClick={finalSubmit}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--success)] hover:brightness-110 text-black text-sm font-semibold disabled:opacity-40">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Final Submission
              </button>
            )}
          </div>
        </div>

        <BudgetBar budget={budget} planYear={planYear} reviewedCount={editable ? reviewedCount : undefined} />
        <FilterBar />
        {submitResult && <SubmitPanel result={submitResult} onClose={() => setSubmitResult(null)} />}
        {finalExport && <FinalExportPanel data={finalExport} onClose={() => setFinalExport(null)} />}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading grid…</div>
      ) : lines.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-[var(--text-secondary)] text-base">No lines match the current filters.</div>
      ) : (
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-auto">
          <div style={{ width: CHECK_W + REVIEW_W + LEFT_W + weeks.length * CELL_W, position: 'relative' }}>
            {/* Sticky header */}
            <div className="sticky top-0 z-20 flex bg-[var(--bg-tertiary)] border-b border-[var(--border-strong)]" style={{ height: ROW_H }}>
              <div className="sticky left-0 z-30 flex items-center justify-center bg-[var(--bg-tertiary)] border-r border-[var(--border)]" style={{ width: CHECK_W }}>
                {editable && <input type="checkbox" checked={allSelected} onChange={toggleAll} className="w-4 h-4 cursor-pointer" />}
              </div>
              {editable && <div className="sticky z-30 flex items-center justify-center bg-[var(--bg-tertiary)] border-r border-[var(--border)] text-[11px] font-semibold uppercase text-[var(--text-secondary)]" style={{ left: CHECK_W, width: REVIEW_W }}>Rev</div>}
              <div className="sticky z-30 flex bg-[var(--bg-tertiary)] border-r-2 border-[var(--border-strong)]" style={{ left: CHECK_W + (editable ? REVIEW_W : 0) }}>
                {LEFT_COLS.map((c) => (
                  <div key={c.key} className="flex items-center px-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]" style={{ width: c.w }}>{c.label}</div>
                ))}
              </div>
              {weeks.map((w) => (
                <div key={w.week_number} className="flex flex-col items-center justify-center border-r border-[var(--border)]" style={{ width: CELL_W }}>
                  <span className="text-[12px] font-semibold text-[var(--text-primary)] leading-none">{w.iso_label}</span>
                  <span className="text-[9px] text-[var(--text-tertiary)] leading-none mt-0.5">{w.date_range_label}</span>
                </div>
              ))}
            </div>

            {/* Windowed rows */}
            <div style={{ height: totalH, position: 'relative' }}>
              {visible.map((line, i) => {
                const rowIndex = start + i;
                const isSel = selected.has(line.line_key);
                const rowBg = isSel ? 'bg-[var(--accent-dim)]' : rowIndex % 2 ? 'bg-[var(--bg-primary)]' : 'bg-[var(--bg-secondary)]';
                return (
                  <div key={line.line_key} className={`flex items-stretch absolute left-0 ${rowBg}`}
                    style={{ top: rowIndex * ROW_H, height: ROW_H, width: '100%' }}>
                    <div className={`sticky left-0 z-10 flex items-center justify-center border-r border-b border-[var(--border)] ${rowBg}`} style={{ width: CHECK_W }}>
                      {editable && <input type="checkbox" checked={isSel} onChange={() => toggleRow(line.line_key)} className="w-4 h-4 cursor-pointer" />}
                    </div>
                    {editable && (
                      <div className={`sticky z-10 flex items-center justify-center border-r border-b border-[var(--border)] ${rowBg}`} style={{ left: CHECK_W, width: REVIEW_W }}>
                        <button onClick={() => setReviewed([line.line_key], !line.reviewed)} title={line.reviewed ? 'Reviewed — click to clear' : 'Mark reviewed'}
                          className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors ${line.reviewed ? 'bg-[var(--success)] text-black' : 'border border-[var(--border-strong)] text-[var(--text-tertiary)] hover:border-[var(--success)] hover:text-[var(--success)]'}`}>
                          <Check className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                    <div className={`sticky z-10 flex border-r-2 border-b border-[var(--border-strong)] ${rowBg} ${line.reviewed ? 'shadow-[inset_3px_0_0_var(--success)]' : ''}`} style={{ left: CHECK_W + (editable ? REVIEW_W : 0) }}>
                      <MetaCell w={LEFT_COLS[0].w} title={line.wholesaler_name}><span className="font-medium">{line.wholesaler_id}</span> <span className="text-[var(--text-tertiary)]">{line.wholesaler_name}</span></MetaCell>
                      <MetaCell w={LEFT_COLS[1].w}>{line.brand_code}</MetaCell>
                      <MetaCell w={LEFT_COLS[2].w} title={line.brand_name}>{line.brand_name}</MetaCell>
                      <MetaCell w={LEFT_COLS[3].w}>{line.prc_code}</MetaCell>
                      <MetaCell w={LEFT_COLS[4].w} title={line.prc_group_name}>{line.prc_group_name}</MetaCell>
                      <MetaCell w={LEFT_COLS[5].w}>{fmtInt(line.qd_min)}</MetaCell>
                      <MetaCell w={LEFT_COLS[6].w}>{fmtInt(line.qd_max)}</MetaCell>
                      <MetaCell w={LEFT_COLS[7].w} title={line.deal_description}>{line.deal_description}</MetaCell>
                      <MetaCell w={LEFT_COLS[8].w}>{fmtMoney(line.curr_max_discount)}</MetaCell>
                    </div>
                    {weeks.map((w) => {
                      const cell = line.cells[String(w.week_number)];
                      const isEditing = editable && editing?.key === line.line_key && editing?.week === w.week_number;
                      return (
                        <WeekCell key={w.week_number} line={line} week={w} cell={cell} view={view}
                          editable={editable} isEditing={isEditing}
                          onStartEdit={() => editable && setEditing({ key: line.line_key, week: w.week_number })}
                          onCommit={(raw) => commitCellEdit(line, w.week_number, raw)}
                          onCancel={() => setEditing(null)} />
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
          {loadingMore && <div className="flex items-center justify-center py-3 text-[var(--text-secondary)] text-sm"><Loader2 className="w-4 h-4 animate-spin mr-1.5" /> Loading more…</div>}
        </div>
      )}
      {!loading && (
        <div className="shrink-0 px-6 py-2 border-t border-[var(--border)] text-[12px] text-[var(--text-secondary)] flex items-center gap-3">
          <span>{fmtInt(lines.length)} lines loaded{hasMore ? ' (scroll for more)' : ''}</span>
          {budget && <span>· {fmtInt(budget.n_lines)} total in filter</span>}
          {editable && <span>· {fmtInt(reviewedCount)} reviewed</span>}
          {editable && <span className="ml-auto inline-flex items-center gap-1"><Info className="w-3.5 h-3.5" /> Click a week cell to edit · sandbox edits are private until you Submit</span>}
        </div>
      )}

      {popup && (
        <DiscountPopup kind={popup} weeks={weeks} count={selCount}
          onClose={() => setPopup(null)} onApply={(v, f, t) => applyDiscount(popup, v, f, t)} busy={busy} />
      )}
    </div>
  );
}

function MetaCell({ w, title, children }: { w: number; title?: string; children: React.ReactNode }) {
  return <div className="flex items-center px-2 text-[13px] text-[var(--text-primary)] truncate" style={{ width: w }} title={title}>{children}</div>;
}

function WeekCell({ line, week, cell, view, editable, isEditing, onStartEdit, onCommit, onCancel }: {
  line: GridLine; week: IsoWeek; cell?: PromoCell; view: PlanView; editable: boolean;
  isEditing: boolean; onStartEdit: () => void; onCommit: (raw: string) => void; onCancel: () => void;
}) {
  const hasPromo = !!cell && (cell.incremental_discount != null || cell.absolute_discount != null);
  const depth = hasPromo ? cellDepth(line.base_pptr, cell!.incremental_discount, cell!.absolute_discount) : 0;
  const tint = hasPromo ? discountColor(depth) : 'transparent';
  const isSandbox = cell?.source === 'sandbox';
  // Sandbox (just-edited) cells always get a visible accent fill so they never render
  // dark/invisible when the discount depth is small (which makes the tint transparent).
  const bg = isSandbox ? 'var(--accent-dim)' : tint;
  // Dark text only reads on the light production tints; sandbox / transparent cells
  // use the normal light text so the value is always visible on the dark canvas.
  const textColor = isSandbox ? 'var(--accent)' : (hasPromo && tint !== 'transparent' ? '#1a1206' : 'var(--text-primary)');

  // Every view shows a dollar amount.
  let text = '';
  if (hasPromo) {
    if (view === 'rec_pptr') text = fmtPrice(cell!.rec_pptr);
    else text = fmtPrice(cellOff(cell!.incremental_discount, cell!.absolute_discount)); // $ off
  }

  // Editor seed: for an existing promo, prefill the current value for the active view.
  // For a BLANK cell, open empty (placeholder only) so the user types their own value
  // instead of seeing the base price / a stale number.
  const editInit = !hasPromo ? ''
    : view === 'rec_pptr' ? fmtPrice(cell!.rec_pptr)
    : fmtPrice(cellOff(cell!.incremental_discount, cell!.absolute_discount));
  // Placeholder hint: in REC PPTR view show the base price; otherwise "$ off".
  const editPlaceholder = view === 'rec_pptr' ? fmtPrice(line.base_pptr) : '$ off';

  const tip = hasPromo
    ? `${line.plan_year}-${week.iso_label} ${week.date_range_label} · $${fmtPrice(cellOff(cell!.incremental_discount, cell!.absolute_discount))} off · REC PPTR $${fmtPrice(cell!.rec_pptr)}${isSandbox ? ' (sandbox)' : cell!.approval_status ? ` (${cell!.approval_status})` : ''}`
    : `${week.iso_label} ${week.date_range_label}${editable ? ' · click to add a discount' : ''}`;

  if (isEditing) {
    return <CellEditor init={editInit} placeholder={editPlaceholder} onCommit={onCommit} onCancel={onCancel} />;
  }

  return (
    <div onClick={editable ? onStartEdit : undefined}
      className={`flex items-center justify-center border-r border-b border-[var(--border)] text-[13px] tabular-nums ${editable ? 'cursor-pointer hover:ring-1 hover:ring-inset hover:ring-[var(--accent)]' : ''} ${isSandbox ? 'ring-2 ring-inset ring-[var(--accent)] font-semibold' : ''}`}
      style={{ width: CELL_W, background: bg, color: textColor }} title={tip}>
      {text}
    </div>
  );
}

// Inline numeric editor. Guards against the Enter→blur double-commit (Enter fires
// onCommit, which unmounts this input and would otherwise fire onBlur a second time).
function CellEditor({ init, placeholder, onCommit, onCancel }: { init: string; placeholder?: string; onCommit: (raw: string) => void; onCancel: () => void }) {
  const done = useRef(false);
  const commit = (raw: string) => { if (done.current) return; done.current = true; onCommit(raw); };
  const cancel = () => { if (done.current) return; done.current = true; onCancel(); };
  return (
    <div className="flex items-center justify-center border-r border-b border-[var(--border)]" style={{ width: CELL_W, background: 'var(--bg-hover)' }}>
      <input autoFocus defaultValue={init} placeholder={placeholder} type="number" step={0.25}
        onFocus={(e) => e.currentTarget.select()}
        onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); commit((e.target as HTMLInputElement).value); }
          else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
        }}
        className="w-full h-full text-center text-[13px] tabular-nums bg-transparent text-[var(--text-primary)] outline-none ring-2 ring-inset ring-[var(--accent)] rounded-sm px-0.5" />
    </div>
  );
}

function BudgetBar({ budget, planYear, reviewedCount }: { budget: Budget | null; planYear: number; reviewedCount?: number }) {
  const items = [
    { label: 'Total discount ($/case)', value: budget ? fmtMoney(budget.total_discount) : '—' },
    { label: 'Avg discount ($/case)', value: budget ? fmtMoney(budget.avg_incremental_discount) : '—' },
    { label: 'Lines on promo', value: budget ? `${fmtInt(budget.n_lines_on_promo)} / ${fmtInt(budget.n_lines)}` : '—' },
    { label: 'Promo weeks', value: budget ? fmtInt(budget.n_promo_weeks) : '—' },
  ];
  if (reviewedCount !== undefined) items.push({ label: 'Reviewed (loaded)', value: fmtInt(reviewedCount) });
  return (
    <div className="flex items-stretch gap-3 flex-wrap">
      <div className="flex items-center px-4 rounded-lg text-black font-bold text-sm" style={{ background: 'var(--grad-header)' }}>
        Budget · {planYear}
      </div>
      {items.map((it) => (
        <div key={it.label} className="px-3.5 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)]">
          <p className="text-[11px] text-[var(--text-secondary)] leading-tight">{it.label}</p>
          <p className="text-base font-bold text-[var(--text-primary)] leading-tight tabular-nums">{it.value}</p>
        </div>
      ))}
    </div>
  );
}

function DiscountPopup({ kind, weeks, count, onClose, onApply, busy }: {
  kind: 'incremental' | 'absolute'; weeks: IsoWeek[]; count: number;
  onClose: () => void; onApply: (value: number, wkFrom: number, wkTo: number) => void; busy: boolean;
}) {
  const [value, setValue] = useState(kind === 'incremental' ? 1.5 : 2.0);
  const [wkFrom, setWkFrom] = useState(1);
  const [wkTo, setWkTo] = useState(4);
  const maxWk = weeks.length || 52;
  const apply = () => onApply(value, Math.min(wkFrom, wkTo), Math.max(wkFrom, wkTo));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="w-[26rem] rounded-2xl bg-[var(--bg-secondary)] p-6 border border-[var(--border)]" onClick={(e) => e.stopPropagation()} style={{ boxShadow: 'var(--shadow-lg)' }}>
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-bold text-[var(--text-primary)]">{kind === 'incremental' ? 'Incremental discount' : 'Absolute discount'}</h3>
          <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-sm text-[var(--text-secondary)] mb-5">Apply to <span className="font-semibold text-[var(--text-primary)]">{count}</span> selected line{count === 1 ? '' : 's'} across the chosen week range.</p>

        <label className="text-xs font-medium text-[var(--text-secondary)]">Dollars off per case (subtracted from base REC PPTR)</label>
        <div className="flex items-center gap-2 mt-1.5 mb-5">
          <span className="text-base text-[var(--text-secondary)]">$</span>
          <input type="number" value={value} min={0} step={0.25}
            onChange={(e) => setValue(Number(e.target.value))}
            className="flex-1 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-base" />
        </div>

        <label className="text-xs font-medium text-[var(--text-secondary)]">Week range</label>
        <div className="flex items-center gap-2 mt-1.5 mb-6">
          <input type="number" value={wkFrom} min={1} max={maxWk} onChange={(e) => setWkFrom(Number(e.target.value))} className="w-24 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-base" />
          <ArrowRight className="w-4 h-4 text-[var(--text-secondary)]" />
          <input type="number" value={wkTo} min={1} max={maxWk} onChange={(e) => setWkTo(Number(e.target.value))} className="w-24 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-base" />
          <span className="text-sm text-[var(--text-secondary)]">of {maxWk} weeks</span>
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]">Cancel</button>
          <button onClick={apply} disabled={busy || !count}
            className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-black text-sm font-semibold disabled:opacity-40">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Apply
          </button>
        </div>
      </div>
    </div>
  );
}

function SubmitPanel({ result, onClose }: { result: SubmitResult; onClose: () => void }) {
  return (
    <div className="rounded-xl border border-[var(--success)] bg-[var(--bg-secondary)] p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-[var(--success)]" />
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {result.submitted > 0 ? `Submitted ${result.submitted} cell(s) to production` : (result.detail || 'Nothing to submit')}
          </p>
        </div>
        <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-4 h-4" /></button>
      </div>
      {result.writes && (
        <div className="mt-2 ml-7 space-y-1.5">
          {result.writes.map((wr, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <span className="px-1.5 py-0.5 rounded font-mono font-semibold shrink-0 bg-[var(--accent-dim)] text-[var(--accent)]">{wr.operation}</span>
              <div>
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--text-secondary)]"><Database className="w-3.5 h-3.5" /> {wr.target}</span>
                <span className="font-mono ml-1 text-[var(--text-primary)]">{wr.table}</span>
                <div className="text-[var(--text-secondary)]">{wr.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="text-[11px] text-[var(--text-secondary)] mt-2 ml-7">Sandbox edits promoted to the governed Unity Catalog table as <span className="font-medium">pending</span> — the CSO team approves them in Final Plan.</p>
    </div>
  );
}

function FinalExportPanel({ data, onClose }: { data: FinalExport; onClose: () => void }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Download className="w-5 h-5 text-[var(--accent)]" />
          <p className="text-sm font-semibold text-[var(--text-primary)]">Downstream API payload — {fmtInt(data.count)} approved pricing rows</p>
        </div>
        <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-4 h-4" /></button>
      </div>
      <p className="text-xs text-[var(--text-secondary)] mt-1 ml-7 mb-2">
        <span className="font-mono">GET /api/pricing/final</span> — the JSON another application pulls once pricing is finally approved.
      </p>
      <pre className="ml-7 max-h-56 overflow-auto rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] p-2.5 text-[11px] font-mono text-[var(--text-primary)]">
{JSON.stringify(data.pricing.slice(0, 20), null, 2)}
{data.pricing.length > 20 ? `\n… ${data.pricing.length - 20} more` : ''}
      </pre>
    </div>
  );
}
