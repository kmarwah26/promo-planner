import { useEffect, useRef, useState } from 'react';
import { X, ChevronDown, Check } from 'lucide-react';
import { api } from '../api';
import type { PricingFilters } from '../api';
import { useFilters } from '../store';
import type { PricingFilterState } from '../store';

export default function FilterBar() {
  const { filters, setFilter, clearFilters } = useFilters();
  const [opts, setOpts] = useState<PricingFilters | null>(null);

  useEffect(() => {
    api.getFilters().then(setOpts).catch(() => {});
  }, []);

  const active = Object.keys(filters).length > 0;

  const single: { key: keyof PricingFilterState; label: string; items: { value: string; label: string }[] }[] = [
    { key: 'brand', label: 'Brand Name', items: (opts?.brands || []).map((b) => ({ value: b.code, label: b.name })) },
    { key: 'prc_group', label: 'PRC Group Name', items: (opts?.prc_groups || []).map((p) => ({ value: p.code, label: p.name })) },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <WholesalerMultiSelect
        items={(opts?.wholesalers || []).map((w) => ({ value: w.id, label: `${w.id} — ${w.name}` }))}
        value={filters.wholesaler}
        onChange={(v) => setFilter('wholesaler', v)}
      />
      {single.map((d) => (
        <select
          key={d.key}
          value={filters[d.key] || ''}
          onChange={(e) => setFilter(d.key, e.target.value || undefined)}
          className={`px-3 py-1.5 rounded-lg border text-sm bg-[var(--bg-secondary)] cursor-pointer transition-colors max-w-[16rem] ${
            filters[d.key] ? 'border-[var(--accent)] text-[var(--accent)] font-medium' : 'border-[var(--border)] text-[var(--text-primary)]'
          }`}
        >
          <option value="">{d.label}</option>
          {d.items.map((it) => (
            <option key={it.value} value={it.value}>{it.label}</option>
          ))}
        </select>
      ))}
      {active && (
        <button
          onClick={clearFilters}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-red-50 transition-colors"
        >
          <X className="w-3.5 h-3.5" /> Clear
        </button>
      )}
    </div>
  );
}

// Multi-select for wholesalers. The filter value is stored as a comma-separated
// string of wholesaler ids (so the API query string / IN-clause work unchanged).
function WholesalerMultiSelect({ items, value, onChange }: {
  items: { value: string; label: string }[];
  value?: string;
  onChange: (v: string | undefined) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const selected = value ? value.split(',').filter(Boolean) : [];
  const selectedSet = new Set(selected);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const toggle = (id: string) => {
    const next = new Set(selectedSet);
    next.has(id) ? next.delete(id) : next.add(id);
    const arr = [...next];
    onChange(arr.length ? arr.join(',') : undefined);
  };

  const label = selected.length === 0 ? 'Wholesaler'
    : selected.length === 1 ? (items.find((i) => i.value === selected[0])?.label || selected[0])
    : `${selected.length} wholesalers`;

  const filtered = q
    ? items.filter((i) => i.label.toLowerCase().includes(q.toLowerCase()))
    : items;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm bg-[var(--bg-secondary)] transition-colors max-w-[18rem] ${
          selected.length ? 'border-[var(--accent)] text-[var(--accent)] font-medium' : 'border-[var(--border)] text-[var(--text-primary)]'
        }`}
      >
        <span className="truncate">{label}</span>
        {selected.length > 0 && (
          <span className="shrink-0 rounded-full bg-[var(--accent)] text-black text-[10px] font-bold px-1.5">{selected.length}</span>
        )}
        <ChevronDown className="w-3.5 h-3.5 shrink-0" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-80 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] shadow-xl" style={{ boxShadow: 'var(--shadow-lg)' }}>
          <div className="p-2 border-b border-[var(--border)] flex items-center gap-2">
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search wholesalers…"
              className="flex-1 px-2 py-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] text-sm" />
            {selected.length > 0 && (
              <button onClick={() => onChange(undefined)} className="text-xs text-[var(--text-secondary)] hover:text-[var(--danger)] px-1">Clear</button>
            )}
          </div>
          <div className="max-h-72 overflow-y-auto py-1">
            {filtered.length === 0 && <p className="px-3 py-2 text-xs text-[var(--text-secondary)]">No matches.</p>}
            {filtered.slice(0, 300).map((it) => {
              const on = selectedSet.has(it.value);
              return (
                <button key={it.value} onClick={() => toggle(it.value)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-[var(--bg-tertiary)]">
                  <span className={`w-4 h-4 rounded flex items-center justify-center shrink-0 ${on ? 'bg-[var(--accent)]' : 'border border-[var(--border-strong)]'}`}>
                    {on && <Check className="w-3 h-3 text-black" />}
                  </span>
                  <span className={`truncate ${on ? 'text-[var(--text-primary)] font-medium' : 'text-[var(--text-secondary)]'}`}>{it.label}</span>
                </button>
              );
            })}
            {filtered.length > 300 && <p className="px-3 py-2 text-[11px] text-[var(--text-tertiary)]">Showing first 300 — refine your search.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
