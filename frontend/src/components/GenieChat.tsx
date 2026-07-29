import { useEffect, useRef, useState } from 'react';
import { Sparkles, X, Send, Loader2, ChevronDown, ChevronRight, Database, AlertCircle, Eraser } from 'lucide-react';
import { api } from '../api';
import type { GenieResult } from '../api';

interface Msg {
  role: 'user' | 'assistant';
  text?: string;
  result?: GenieResult;
  error?: boolean;
}

export default function GenieChat() {
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [spaceErr, setSpaceErr] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Resolve the Genie space the first time the widget opens.
  useEffect(() => {
    if (!open || ready || spaceErr) return;
    api.genieSpace()
      .then((s) => { setSuggestions(s.suggestions || []); setReady(true); })
      .catch((e) => setSpaceErr(e.message || 'Could not reach Genie'));
  }, [open, ready, spaceErr]);

  useEffect(() => { scrollRef.current?.scrollTo({ top: 1e9, behavior: 'smooth' }); }, [msgs, busy]);

  const ask = async (q: string) => {
    if (!q.trim() || busy) return;
    setInput('');
    setMsgs((m) => [...m, { role: 'user', text: q }]);
    setBusy(true);
    try {
      const reply = convId ? await api.genieSend(convId, q) : await api.genieStart(q);
      setConvId(reply.conversation_id);
      const r = reply.result;
      const failed = r.status !== 'COMPLETED';
      setMsgs((m) => [...m, {
        role: 'assistant',
        text: r.text || (failed ? 'I could not answer that one — try rephrasing.' : ''),
        result: r, error: failed,
      }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: 'assistant', text: e.message || 'Something went wrong.', error: true }]);
    } finally {
      setBusy(false);
    }
  };

  // Clear the conversation: wipe messages and start a fresh Genie thread on the next ask.
  const clearChat = () => { setMsgs([]); setConvId(null); setInput(''); };

  return (
    <>
      {/* Floating trigger */}
      {!open && (
        <button onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 px-4 py-3 rounded-full text-black font-semibold shadow-xl hover:brightness-110 transition"
          style={{ background: 'var(--grad-brand)', boxShadow: 'var(--shadow-lg)' }}>
          <Sparkles className="w-5 h-5" /> Ask the data
        </button>
      )}

      {/* Chat pop-over */}
      {open && (
        <div className="fixed bottom-6 right-6 z-40 w-[26rem] max-w-[94vw] h-[34rem] max-h-[82vh] rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] flex flex-col overflow-hidden"
          style={{ boxShadow: 'var(--shadow-lg)' }}>
          <div className="shrink-0 px-4 py-3 border-b border-[var(--border)] flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--grad-brand)' }}>
              <Sparkles className="w-4 h-4 text-black" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-[var(--text-primary)] leading-tight">Pricing Genie</p>
              <p className="text-[11px] text-[var(--text-secondary)] leading-tight">Natural-language questions over the governed data</p>
            </div>
            {msgs.length > 0 && (
              <button onClick={clearChat} disabled={busy} title="Clear chat"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-40">
                <Eraser className="w-3.5 h-3.5" /> Clear
              </button>
            )}
            <button onClick={() => setOpen(false)} className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><X className="w-5 h-5" /></button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {spaceErr ? (
              <div className="flex items-start gap-2 text-sm text-[var(--danger)]">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{spaceErr}</span>
              </div>
            ) : !ready ? (
              <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"><Loader2 className="w-4 h-4 animate-spin" /> Connecting to the pricing data…</div>
            ) : msgs.length === 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-[var(--text-secondary)]">Ask about promo weeks, discounts, REC PPTR, or roll-ups by wholesaler / brand. For example:</p>
                <div className="space-y-2">
                  {suggestions.map((s) => (
                    <button key={s} onClick={() => ask(s)}
                      className="w-full text-left text-sm px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] hover:bg-[var(--bg-hover)] text-[var(--text-primary)] transition-colors">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              msgs.map((m, i) => <Bubble key={i} msg={m} />)
            )}
            {busy && (
              <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"><Loader2 className="w-4 h-4 animate-spin" /> Genie is thinking…</div>
            )}
          </div>

          {/* Sample questions stay available throughout the conversation. */}
          {ready && !spaceErr && msgs.length > 0 && (
            <div className="shrink-0 px-3 pt-2.5 pb-0.5 border-t border-[var(--border)] flex gap-1.5 overflow-x-auto">
              {suggestions.map((s) => (
                <button key={s} onClick={() => ask(s)} disabled={busy} title={s}
                  className="shrink-0 max-w-[14rem] truncate text-[11px] px-2.5 py-1 rounded-full bg-[var(--bg-tertiary)] hover:bg-[var(--bg-hover)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-40 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          )}

          <div className={`shrink-0 p-3 flex items-center gap-2 ${msgs.length > 0 ? '' : 'border-t border-[var(--border)]'}`}>
            <input value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') ask(input); }}
              disabled={!ready || busy} placeholder={ready ? 'Ask a question…' : 'Connecting…'}
              className="flex-1 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] text-sm disabled:opacity-50" />
            <button onClick={() => ask(input)} disabled={!ready || busy || !input.trim()}
              className="p-2 rounded-lg text-black disabled:opacity-40" style={{ background: 'var(--accent)' }}>
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function Bubble({ msg }: { msg: Msg }) {
  const [showSql, setShowSql] = useState(false);
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] px-3 py-2 rounded-2xl rounded-br-sm text-sm text-black" style={{ background: 'var(--accent)' }}>{msg.text}</div>
      </div>
    );
  }
  const r = msg.result;
  return (
    <div className="flex flex-col gap-1.5">
      <div className={`max-w-[92%] px-3 py-2 rounded-2xl rounded-bl-sm text-sm ${msg.error ? 'bg-[var(--accent-2-dim)] text-[var(--danger)]' : 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'}`}>
        {msg.text}
      </div>
      {r && r.rows && r.rows.length > 0 && (
        <div className="rounded-lg border border-[var(--border)] overflow-hidden">
          <div className="max-h-48 overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="bg-[var(--bg-tertiary)] sticky top-0">
                <tr>{r.columns.map((c) => <th key={c} className="text-left font-semibold px-2 py-1 text-[var(--text-secondary)]">{c}</th>)}</tr>
              </thead>
              <tbody>
                {r.rows.slice(0, 50).map((row, i) => (
                  <tr key={i} className="border-t border-[var(--border)]">
                    {row.map((v, j) => <td key={j} className="px-2 py-1 text-[var(--text-primary)] tabular-nums whitespace-nowrap">{v == null ? '—' : String(v)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.rows.length > 50 && <p className="px-2 py-1 text-[10px] text-[var(--text-tertiary)] bg-[var(--bg-tertiary)]">Showing first 50 of {r.rows.length} rows</p>}
        </div>
      )}
      {r && r.query && (
        <div className="text-[11px]">
          <button onClick={() => setShowSql((s) => !s)} className="inline-flex items-center gap-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
            {showSql ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <Database className="w-3 h-3" /> {showSql ? 'Hide' : 'Show'} generated SQL
          </button>
          {showSql && (
            <pre className="mt-1 p-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] overflow-auto text-[10px] font-mono text-[var(--text-primary)] whitespace-pre-wrap">{r.query}</pre>
          )}
        </div>
      )}
    </div>
  );
}
