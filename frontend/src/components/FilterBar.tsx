import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
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

  const dims: { key: keyof PricingFilterState; label: string; items: { value: string; label: string }[] }[] = [
    { key: 'wholesaler', label: 'Wholesaler', items: (opts?.wholesalers || []).map((w) => ({ value: w.id, label: `${w.id} — ${w.name}` })) },
    { key: 'brand', label: 'Brand Name', items: (opts?.brands || []).map((b) => ({ value: b.code, label: b.name })) },
    { key: 'prc_group', label: 'PRC Group Name', items: (opts?.prc_groups || []).map((p) => ({ value: p.code, label: p.name })) },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {dims.map((d) => (
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
