import { useState, useEffect } from 'react';
import { CalendarRange, User } from 'lucide-react';
import { api } from './api';
import type { CurrentUser } from './api';
import PricingGrid from './pages/PricingGrid';
import type { PlanTab } from './store';

const TABS: { id: PlanTab; label: string }[] = [
  { id: 'ran2026', label: '2026 Promotions Ran' },
  { id: 'builder2027', label: '2027 Plan Builder' },
  { id: 'final', label: 'Final Plan' },
];

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [tab, setTab] = useState<PlanTab>('builder2027');

  useEffect(() => {
    api.getCurrentUser().then(setUser).catch(() => {});
  }, []);

  const initials = user?.display_name
    ? user.display_name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()
    : '?';

  return (
    <div className="h-screen overflow-hidden flex flex-col">
      <header className="shrink-0 h-14 bg-[var(--bg-secondary)] border-b border-[var(--border)] flex items-center px-5 gap-6" style={{ boxShadow: 'var(--shadow-sm)' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center shadow-sm" style={{ background: 'var(--grad-brand)' }}>
            <CalendarRange className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-[var(--text-primary)] leading-none">Promo 1YP</h1>
            <span className="text-[10px] text-[var(--text-secondary)]">Wholesale Pricing Planner</span>
          </div>
        </div>

        {/* Top tabs: the three plan stages */}
        <nav className="flex items-center gap-1 ml-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'bg-[var(--accent)] text-white shadow-sm'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-[var(--bg-tertiary)]">
          <div className="w-6 h-6 rounded-full flex items-center justify-center" style={{ background: 'var(--grad-brand)' }}>
            {user ? <span className="text-[9px] font-bold text-white">{initials}</span> : <User className="w-3 h-3 text-white" />}
          </div>
          <div className="hidden sm:block">
            <p className="text-xs font-medium text-[var(--text-primary)] leading-tight">{user?.display_name || 'Loading…'}</p>
            <p className="text-[10px] text-[var(--text-secondary)] leading-tight">{user?.user_name || ''}</p>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <PricingGrid tab={tab} />
      </main>
    </div>
  );
}
