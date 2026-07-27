import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api';
import type { Filters } from '../api';
import { useFilters } from '../store';

const DIMS: { key: keyof Filters; label: string; source: string }[] = [
  { key: 'market', label: 'Market', source: 'market' },
  { key: 'channel', label: 'Channel', source: 'channel' },
  { key: 'brand', label: 'Brand', source: 'brand' },
  { key: 'segment', label: 'Segment', source: 'customer_segment' },
  { key: 'status', label: 'Status', source: 'status' },
];

export default function FilterBar({ showStatus = true }: { showStatus?: boolean }) {
  const { filters, setFilter, clearFilters } = useFilters();
  const [opts, setOpts] = useState<Record<string, string[]>>({});

  useEffect(() => {
    api.getFilters().then(setOpts).catch(() => {});
  }, []);

  const active = Object.keys(filters).length > 0;
  const dims = showStatus ? DIMS : DIMS.filter((d) => d.key !== 'status');

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {dims.map((d) => (
        <select
          key={d.key}
          value={filters[d.key] || ''}
          onChange={(e) => setFilter(d.key, e.target.value || undefined)}
          className={`px-3 py-1.5 rounded-lg border text-sm bg-[var(--bg-secondary)] cursor-pointer transition-colors ${
            filters[d.key] ? 'border-[var(--accent)] text-[var(--accent)] font-medium' : 'border-[var(--border)] text-[var(--text-primary)]'
          }`}
        >
          <option value="">{d.label}: All</option>
          {(opts[d.source] || []).map((v) => (
            <option key={v} value={v}>{v}</option>
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
