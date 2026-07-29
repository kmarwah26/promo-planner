import { useEffect, useState } from 'react';
import { X, Database, Server, RefreshCw, ArrowRight, CheckCircle2, AlertCircle, Table2 } from 'lucide-react';
import { api } from '../api';
import type { LakebaseInfo, CatalogInfo } from '../api';
import { fmtInt } from '../format';

export type PanelKind = 'lakebase' | 'catalog';

export default function InfoPanel({ kind, onClose }: { kind: PanelKind; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <aside
        onClick={(e) => e.stopPropagation()}
        className="absolute top-0 right-0 h-full w-[26rem] max-w-[92vw] bg-[var(--bg-secondary)] border-l border-[var(--border)] shadow-2xl flex flex-col animate-[slidein_.18s_ease-out]"
        style={{ boxShadow: 'var(--shadow-lg)' }}
      >
        {kind === 'lakebase' ? <LakebaseBody onClose={onClose} /> : <CatalogBody onClose={onClose} />}
      </aside>
      <style>{`@keyframes slidein{from{transform:translateX(24px);opacity:.4}to{transform:translateX(0);opacity:1}}`}</style>
    </div>
  );
}

function PanelHeader({ icon: Icon, title, subtitle, onClose }: { icon: any; title: string; subtitle: string; onClose: () => void }) {
  return (
    <div className="shrink-0 px-5 py-4 border-b border-[var(--border)] flex items-start gap-3">
      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'var(--grad-brand)' }}>
        <Icon className="w-5 h-5 text-black" />
      </div>
      <div className="flex-1 min-w-0">
        <h2 className="text-base font-bold text-[var(--text-primary)] leading-tight">{title}</h2>
        <p className="text-xs text-[var(--text-secondary)] leading-snug mt-0.5">{subtitle}</p>
      </div>
      <button onClick={onClose} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-5 h-5" /></button>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const ok = status === 'connected';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${ok ? 'bg-[var(--accent-dim)] text-[var(--success)]' : 'bg-[var(--accent-2-dim)] text-[var(--danger)]'}`}>
      {ok ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
      {ok ? 'connected' : status.startsWith('error') ? 'error' : status}
    </span>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline gap-2 text-xs">
      <span className="text-[var(--text-secondary)] w-20 shrink-0">{k}</span>
      <span className="font-mono text-[var(--text-primary)] break-all">{v}</span>
    </div>
  );
}

const actionColor = (a: string) =>
  a === 'submit' ? 'text-[var(--accent)]'
    : a === 'approve' ? 'text-[var(--success)]'
    : a === 'reset' || a === 'unreview' ? 'text-[var(--danger)]'
    : 'text-[var(--text-secondary)]';

function LakebaseBody({ onClose }: { onClose: () => void }) {
  const [info, setInfo] = useState<LakebaseInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const load = () => { setLoading(true); api.getLakebaseInfo().then(setInfo).finally(() => setLoading(false)); };
  useEffect(() => {
    load();
    const t = setInterval(load, 5000); // live-refresh the activity feed
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <PanelHeader icon={Database} title="How Lakebase is used" subtitle="Low-latency operational store for in-progress edits" onClose={onClose} />
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        {info && (
          <>
            <p className="text-sm text-[var(--text-primary)] leading-relaxed">{info.role_summary}</p>

            <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-tertiary)] p-3.5 space-y-1.5">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Connection</span>
                <StatusPill status={info.status} />
              </div>
              <KV k="engine" v={info.engine} />
              <KV k="instance" v={info.instance} />
              <KV k="database" v={info.database} />
              {info.host && <KV k="host" v={info.host} />}
              <KV k="role" v={info.role} />
            </section>

            <section>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-2">Tables it maintains</h3>
              <div className="space-y-2">
                {info.tables.map((t) => (
                  <div key={t.table} className="rounded-lg border border-[var(--border)] p-3">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 font-mono text-sm font-semibold text-[var(--text-primary)]"><Table2 className="w-3.5 h-3.5 text-[var(--accent)]" /> {t.table}</span>
                      <span className="text-xs font-semibold text-[var(--accent)] tabular-nums">{t.rows != null ? `${fmtInt(t.rows)} rows` : '—'}</span>
                    </div>
                    <p className="text-xs text-[var(--text-secondary)] leading-snug mt-1">{t.purpose}</p>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Live writes {loading && <RefreshCw className="w-3 h-3 inline animate-spin ml-1" />}</h3>
                <span className="text-[10px] text-[var(--text-tertiary)]">auto-refresh · 5s</span>
              </div>
              {info.activity.length === 0 ? (
                <p className="text-xs text-[var(--text-secondary)]">No activity yet — edit a cell in the 2027 Plan Builder and it appears here instantly.</p>
              ) : (
                <div className="space-y-1.5">
                  {info.activity.map((a, i) => (
                    <div key={i} className="text-xs flex gap-2 items-baseline">
                      <span className={`font-mono font-semibold w-16 shrink-0 ${actionColor(a.action)}`}>{a.action}</span>
                      <span className="text-[var(--text-primary)] flex-1 leading-snug">{a.detail}</span>
                      <span className="text-[10px] text-[var(--text-tertiary)] shrink-0">{new Date(a.created_at).toLocaleTimeString()}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </>
  );
}

function CatalogBody({ onClose }: { onClose: () => void }) {
  const [info, setInfo] = useState<CatalogInfo | null>(null);
  useEffect(() => { api.getCatalogInfo().then(setInfo).catch(() => {}); }, []);

  return (
    <>
      <PanelHeader icon={Server} title="How the main records are stored" subtitle="Governed system of record in Unity Catalog" onClose={onClose} />
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        {info && (
          <>
            <p className="text-sm text-[var(--text-primary)] leading-relaxed">{info.role_summary}</p>

            <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-tertiary)] p-3.5 space-y-1.5">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Location</span>
                <StatusPill status={info.status} />
              </div>
              <KV k="engine" v={info.engine} />
              <KV k="catalog" v={info.catalog} />
              <KV k="schema" v={info.schema} />
              <KV k="warehouse" v={info.warehouse_id} />
            </section>

            <section>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-2">Production tables</h3>
              <div className="space-y-2">
                {info.tables.map((t) => (
                  <div key={t.table} className="rounded-lg border border-[var(--border)] p-3">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 font-mono text-sm font-semibold text-[var(--text-primary)]"><Table2 className="w-3.5 h-3.5 text-[var(--accent)]" /> {t.table}</span>
                      <span className="text-xs font-semibold text-[var(--accent)] tabular-nums">{t.rows != null ? `${fmtInt(t.rows)} rows` : '—'}</span>
                    </div>
                    <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">grain: {t.grain}</p>
                    <p className="text-xs text-[var(--text-secondary)] leading-snug mt-1">{t.purpose}</p>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-2">How a change is maintained</h3>
              <div className="space-y-2">
                {info.lifecycle.map((s, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <div className="w-6 h-6 rounded-full bg-[var(--accent-dim)] text-[var(--accent)] text-xs font-bold flex items-center justify-center shrink-0">{i + 1}</div>
                      {i < info.lifecycle.length - 1 && <div className="w-px flex-1 bg-[var(--border)] my-0.5" />}
                    </div>
                    <div className="pb-1">
                      <p className="text-sm font-semibold text-[var(--text-primary)] leading-tight flex items-center gap-1.5 flex-wrap">
                        {s.stage} <span className="inline-flex items-center gap-1 text-[10px] font-normal text-[var(--text-secondary)]"><ArrowRight className="w-3 h-3" />{s.where}</span>
                      </p>
                      <p className="text-xs text-[var(--text-secondary)] leading-snug mt-0.5">{s.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </>
  );
}
