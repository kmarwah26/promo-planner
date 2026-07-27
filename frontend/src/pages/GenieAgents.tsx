import { useEffect, useRef, useState } from 'react';
import { Loader2, Send, Sparkles, Database, ChevronDown, ChevronRight, AlertCircle } from 'lucide-react';
import { api } from '../api';
import type { GenieRoom } from '../api';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  sql?: string;
  columns?: string[];
  rows?: any[][];
  error?: boolean;
}

const SUGGESTIONS = [
  'Which promotions have the lowest ROI and highest trade spend?',
  'Where are we overspending with low incrementality?',
  'What is total trade spend and net promo profit by market?',
  'Which brands deliver the best promotion ROI?',
  'Show promotions in Q2 with negative net profit we could move to Q3',
];

function extract(data: any): { columns: string[]; rows: any[][] } {
  const cols = (data?.manifest?.schema?.columns || []).map((c: any) => c.name);
  const rows = data?.result?.data_array || data?.result?.result?.data_array || [];
  return { columns: cols, rows };
}

export default function GenieAgents() {
  const [rooms, setRooms] = useState<GenieRoom[]>([]);
  const [roomId, setRoomId] = useState<string>('');
  const [convId, setConvId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [roomsLoading, setRoomsLoading] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listGenieRooms()
      .then((r) => {
        setRooms(r.rooms);
        // Prefer a room whose title mentions promo/RGM
        const preferred = r.rooms.find((rm) => /promo|rgm|revenue|planning/i.test(rm.title));
        setRoomId((preferred || r.rooms[0])?.id || '');
      })
      .catch(() => {})
      .finally(() => setRoomsLoading(false));
  }, []);

  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, [msgs, loading]);

  const ask = async (question: string) => {
    if (!question.trim() || !roomId || loading) return;
    setInput('');
    setMsgs((m) => [...m, { role: 'user', content: question }]);
    setLoading(true);
    try {
      const resp = convId
        ? await api.sendMessage(roomId, convId, question)
        : await api.startConversation(roomId, question);
      if (!convId) setConvId(resp.conversation_id);
      const r = resp.result || {};
      const { columns, rows } = extract(r.query_result);
      setMsgs((m) => [...m, {
        role: 'assistant',
        content: r.text || r.description || (rows.length ? '' : 'No answer returned.'),
        sql: r.query || undefined,
        columns: columns.length ? columns : undefined,
        rows: rows.length ? rows : undefined,
      }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: 'assistant', content: e.message || 'Something went wrong.', error: true }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 pt-6 pb-4 border-b border-[var(--border)] flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)] flex items-center gap-2"><Sparkles className="w-5 h-5 text-[var(--accent)]" /> RGM Genie Agents</h2>
          <p className="text-sm text-[var(--text-secondary)]">Ask about promotions, trade spend and ROI in plain English — powered by Genie over governed data.</p>
        </div>
        {rooms.length > 1 && (
          <select value={roomId} onChange={(e) => { setRoomId(e.target.value); setConvId(null); setMsgs([]); }}
            className="px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-sm">
            {rooms.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
          </select>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {roomsLoading ? (
            <div className="flex items-center justify-center py-20 text-[var(--text-secondary)]"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Connecting to Genie…</div>
          ) : !roomId ? (
            <div className="flex flex-col items-center py-16 text-center text-[var(--text-secondary)]">
              <AlertCircle className="w-10 h-10 mb-3 opacity-40" />
              <p className="font-medium">No Genie space found</p>
              <p className="text-sm">Create a Genie space over the promotion data to enable the Genie Agents.</p>
            </div>
          ) : msgs.length === 0 ? (
            <div className="py-8">
              <p className="text-sm text-[var(--text-secondary)] mb-3">Try asking:</p>
              <div className="grid gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => ask(s)}
                    className="text-left px-4 py-3 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] hover:border-[var(--accent)] hover:bg-[var(--accent-dim)] text-sm text-[var(--text-primary)] transition-colors">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            msgs.map((m, i) => <MessageBubble key={i} msg={m} />)
          )}
          {loading && (
            <div className="flex items-center gap-2 text-[var(--text-secondary)] text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Genie is thinking…</div>
          )}
        </div>
      </div>

      <div className="px-8 py-4 border-t border-[var(--border)]">
        <div className="max-w-3xl mx-auto flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') ask(input); }}
            disabled={loading || !roomId}
            placeholder="Ask about promotions, trade spend, ROI…"
            className="flex-1 px-4 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] text-sm focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
          />
          <button onClick={() => ask(input)} disabled={loading || !input.trim() || !roomId}
            className="px-4 py-2.5 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white disabled:opacity-50 transition-colors">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  const [showSql, setShowSql] = useState(false);
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-br-sm bg-[var(--accent)] text-white text-sm">{msg.content}</div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className={`max-w-[90%] w-full px-4 py-3 rounded-2xl rounded-bl-sm border ${msg.error ? 'bg-red-50 border-red-200 text-red-700' : 'bg-[var(--bg-secondary)] border-[var(--border)]'}`}>
        {msg.content && <p className="text-sm text-[var(--text-primary)] whitespace-pre-wrap mb-2">{msg.content}</p>}
        {msg.sql && (
          <div className="mb-2">
            <button onClick={() => setShowSql(!showSql)} className="inline-flex items-center gap-1 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
              {showSql ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />} <Database className="w-3 h-3" /> SQL
            </button>
            {showSql && <pre className="mt-1.5 p-2.5 rounded-lg bg-[var(--bg-tertiary)] text-[11px] overflow-x-auto text-[var(--text-primary)]">{msg.sql}</pre>}
          </div>
        )}
        {msg.columns && msg.rows && (
          <div className="overflow-x-auto rounded-lg border border-[var(--border)] mt-1">
            <table className="w-full text-xs">
              <thead className="bg-[var(--bg-tertiary)]">
                <tr>{msg.columns.map((c) => <th key={c} className="text-left px-2.5 py-1.5 font-semibold text-[var(--text-secondary)]">{c}</th>)}</tr>
              </thead>
              <tbody>
                {msg.rows.slice(0, 50).map((r, i) => (
                  <tr key={i} className="border-t border-[var(--border)]">
                    {r.map((v, j) => <td key={j} className="px-2.5 py-1.5 text-[var(--text-primary)]">{v == null ? '—' : String(v)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
            {msg.rows.length > 50 && <p className="text-[11px] text-[var(--text-secondary)] px-2.5 py-1.5">Showing 50 of {msg.rows.length} rows</p>}
          </div>
        )}
      </div>
    </div>
  );
}
