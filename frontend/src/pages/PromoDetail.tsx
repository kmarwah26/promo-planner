import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2, ArrowLeft, Check, Lock, Unlock, MessageSquare, UserPlus, DollarSign, Send } from 'lucide-react';
import { api } from '../api';
import type { Promo, WeeklySales, Comment, Activity } from '../api';
import { fmtMoney, fmtMoneyShort, fmtInt, fmtPct, roiColor, statusColor } from '../format';

export default function PromoDetail() {
  const { id } = useParams();
  const pid = Number(id);
  const navigate = useNavigate();
  const [promo, setPromo] = useState<(Promo & { comments: Comment[] }) | null>(null);
  const [weekly, setWeekly] = useState<WeeklySales[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState('');
  const [assignee, setAssignee] = useState('');
  const [budget, setBudget] = useState('');

  const load = () => {
    api.promoDetail(pid).then((r) => {
      setPromo(r.promo); setWeekly(r.weekly);
      setBudget(String(Math.round(r.promo?.plan_state?.adjusted_budget ?? r.promo?.trade_spend ?? 0)));
      setAssignee(r.promo?.plan_state?.assigned_to || '');
    }).finally(() => setLoading(false));
    api.getActivity(String(pid)).then((r) => setActivity(r.activity)).catch(() => {});
  };
  useEffect(() => { setLoading(true); load(); }, [pid]);

  const act = async (fn: () => Promise<any>) => { setBusy(true); try { await fn(); load(); } finally { setBusy(false); } };

  if (loading) return <div className="flex items-center justify-center h-full text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…</div>;
  if (!promo) return <div className="p-8 text-[var(--text-secondary)]">Promotion not found.</div>;

  const status = promo.plan_state?.status || promo.status;
  const locked = promo.plan_state?.locked ?? (promo.status === 'Locked');
  const maxVol = Math.max(...weekly.map((w) => w.actual_volume), 1);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-6">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] mb-4"><ArrowLeft className="w-4 h-4" /> Back</button>

        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold text-[var(--text-primary)]">{promo.brand} · {promo.pack}</h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${statusColor(status)}`}>{status}</span>
              {locked && <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-violet-100 text-violet-700"><Lock className="w-3 h-3" /> Locked</span>}
            </div>
            <p className="text-sm text-[var(--text-secondary)] mt-1">{promo.promotion_code} · {promo.market} · {promo.channel} · {promo.customer_segment} · {promo.promo_mechanic}</p>
          </div>
          <span className="px-3 py-1 rounded-full text-white text-sm font-semibold" style={{ background: roiColor(promo.promo_roi) }}>ROI {fmtPct(promo.promo_roi)}</span>
        </div>

        {/* Economics grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <Metric label="Base / Promo price" value={`${fmtMoney(promo.base_price, 2)} → ${fmtMoney(promo.promo_price, 2)}`} sub={`${fmtPct(promo.discount_depth)} off`} />
          <Metric label="Incremental volume" value={`${fmtInt(promo.incremental_volume)} cs`} sub={`+${fmtPct(promo.incrementality_pct)}`} />
          <Metric label="Trade spend" value={fmtMoneyShort(promo.plan_state?.adjusted_budget ?? promo.trade_spend)} sub={promo.plan_state?.adjusted_budget != null ? 'adjusted' : 'planned'} />
          <Metric label="Net promo profit" value={fmtMoneyShort(promo.net_promo_profit)} neg={promo.net_promo_profit < 0} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Weekly chart */}
          <div className="lg:col-span-2 p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
            <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">Weekly volume — baseline vs actual</h3>
            <p className="text-[11px] text-[var(--text-secondary)] mb-4">Promo weeks highlighted. The lift over baseline is the incremental volume.</p>
            <div className="flex items-end gap-1 h-44">
              {weekly.map((w) => (
                <div key={w.week_number} className="flex-1 flex flex-col items-center justify-end h-full group relative">
                  <div className="w-full flex flex-col justify-end h-full">
                    <div className="w-full rounded-t-sm" style={{ height: `${(w.actual_volume / maxVol) * 100}%`, background: w.is_promo_week ? 'var(--accent)' : '#d4d4d8' }} />
                  </div>
                  <div className="absolute bottom-full mb-1 hidden group-hover:block whitespace-nowrap text-[10px] bg-[var(--text-primary)] text-white px-1.5 py-0.5 rounded">
                    Wk {w.week_number}: {fmtInt(w.actual_volume)}
                  </div>
                  <span className="text-[7px] text-[var(--text-secondary)] mt-0.5">{w.week_number}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-4 mt-3 text-[11px] text-[var(--text-secondary)]">
              <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded bg-[var(--accent)]" /> Promo week</span>
              <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded bg-zinc-300" /> Baseline week</span>
            </div>
          </div>

          {/* Write-back actions */}
          <div className="space-y-4">
            <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] space-y-3">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Actions</h3>
              <div className="flex gap-2">
                {status !== 'Approved' && status !== 'Locked' && (
                  <button disabled={busy} onClick={() => act(() => api.approve(String(pid)))}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition-colors disabled:opacity-50">
                    <Check className="w-4 h-4" /> Approve plan
                  </button>
                )}
                <button disabled={busy} onClick={() => act(() => api.lock(String(pid), !locked))}
                  className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${locked ? 'bg-violet-100 text-violet-700 hover:bg-violet-200' : 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'}`}>
                  {locked ? <Unlock className="w-4 h-4" /> : <Lock className="w-4 h-4" />} {locked ? 'Unlock' : 'Lock scenario'}
                </button>
              </div>

              {/* Budget */}
              <div>
                <label className="text-[11px] text-[var(--text-secondary)] flex items-center gap-1 mb-1"><DollarSign className="w-3 h-3" /> Adjust trade-spend budget</label>
                <div className="flex gap-2">
                  <input value={budget} onChange={(e) => setBudget(e.target.value)} type="number"
                    className="flex-1 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-sm" />
                  <button disabled={busy} onClick={() => act(() => api.adjustBudget(String(pid), Number(budget)))}
                    className="px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium disabled:opacity-50">Set</button>
                </div>
              </div>

              {/* Assign */}
              <div>
                <label className="text-[11px] text-[var(--text-secondary)] flex items-center gap-1 mb-1"><UserPlus className="w-3 h-3" /> Assign follow-up</label>
                <div className="flex gap-2">
                  <input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="name@ab-inbev.com"
                    className="flex-1 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-sm" />
                  <button disabled={busy || !assignee} onClick={() => act(() => api.assign(String(pid), assignee))}
                    className="px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium disabled:opacity-50">Assign</button>
                </div>
                {promo.plan_state?.assigned_to && <p className="text-[11px] text-[var(--text-secondary)] mt-1">Currently: {promo.plan_state.assigned_to}</p>}
              </div>
            </div>

            {/* Comments */}
            <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
              <h3 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-1.5 mb-3"><MessageSquare className="w-4 h-4" /> Comments</h3>
              <div className="flex gap-2 mb-3">
                <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add a comment…"
                  onKeyDown={(e) => { if (e.key === 'Enter' && comment.trim()) act(() => api.addComment(String(pid), comment).then(() => setComment(''))); }}
                  className="flex-1 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-sm" />
                <button disabled={busy || !comment.trim()} onClick={() => act(() => api.addComment(String(pid), comment).then(() => setComment('')))}
                  className="px-2.5 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white disabled:opacity-50"><Send className="w-4 h-4" /></button>
              </div>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {promo.comments.length === 0 && <p className="text-[11px] text-[var(--text-secondary)]">No comments yet.</p>}
                {promo.comments.map((c) => (
                  <div key={c.id} className="text-xs">
                    <span className="font-medium text-[var(--text-primary)]">{c.author}</span>
                    <span className="text-[var(--text-secondary)]"> · {new Date(c.created_at).toLocaleString()}</span>
                    <p className="text-[var(--text-primary)]">{c.body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Activity log */}
        {activity.length > 0 && (
          <div className="mt-6 p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
            <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Activity</h3>
            <div className="space-y-1.5">
              {activity.map((a, i) => (
                <div key={i} className="text-xs flex gap-2">
                  <span className="text-[var(--text-secondary)] w-40 shrink-0">{new Date(a.created_at).toLocaleString()}</span>
                  <span className="font-medium text-[var(--accent)] w-24 shrink-0">{a.action}</span>
                  <span className="text-[var(--text-primary)]">{a.detail}</span>
                  <span className="text-[var(--text-secondary)] ml-auto">{a.actor}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, sub, neg }: { label: string; value: string; sub?: string; neg?: boolean }) {
  return (
    <div className="p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
      <p className="text-[11px] text-[var(--text-secondary)]">{label}</p>
      <p className={`text-lg font-bold tracking-tight ${neg ? 'text-red-600' : 'text-[var(--text-primary)]'}`}>{value}</p>
      {sub && <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">{sub}</p>}
    </div>
  );
}
