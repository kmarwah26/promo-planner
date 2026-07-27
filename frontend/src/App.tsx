import { useState, useEffect } from 'react';
import { Routes, Route, useNavigate, useLocation, Link } from 'react-router-dom';
import {
  CalendarDays, GitCompareArrows, MessageSquareText, LayoutGrid,
  User, Sparkles, ArrowRight, TrendingUp, Lock, PencilLine,
} from 'lucide-react';
import { api } from './api';
import type { CurrentUser } from './api';
import CalendarView from './pages/CalendarView';
import PromoList from './pages/PromoList';
import ScenarioCompare from './pages/ScenarioCompare';
import GenieAgents from './pages/GenieAgents';
import PromoDetail from './pages/PromoDetail';

const nav = [
  { to: '/calendar', icon: CalendarDays, label: 'Planning Calendar' },
  { to: '/promos', icon: LayoutGrid, label: 'Promotions' },
  { to: '/scenario', icon: GitCompareArrows, label: 'Scenario Compare' },
  { to: '/genie-agents', icon: MessageSquareText, label: 'Genie Agents' },
];

export default function App() {
  const location = useLocation();
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    api.getCurrentUser().then(setUser).catch(() => {});
  }, []);

  const initials = user?.display_name
    ? user.display_name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()
    : '?';

  return (
    <div className="h-screen overflow-hidden flex flex-col">
      <header className="shrink-0 h-14 bg-[var(--bg-secondary)] border-b border-[var(--border)] flex items-center px-5 gap-6">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-[var(--text-primary)] leading-none">Promotion Planning Genie Agents</h1>
            <span className="text-[10px] text-[var(--text-secondary)]">Revenue Growth Management</span>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-1 ml-4">
          {nav.map((n) => {
            const active = location.pathname.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  active ? 'bg-[var(--accent-dim)] text-[var(--accent)]' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
                }`}
              >
                <n.icon className="w-4 h-4" /> {n.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-[var(--bg-tertiary)]">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center">
            {user ? <span className="text-[9px] font-bold text-white">{initials}</span> : <User className="w-3 h-3 text-white" />}
          </div>
          <div className="hidden sm:block">
            <p className="text-xs font-medium text-[var(--text-primary)] leading-tight">{user?.display_name || 'Loading…'}</p>
            <p className="text-[10px] text-[var(--text-secondary)] leading-tight">{user?.user_name || ''}</p>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<Home user={user} />} />
          <Route path="/calendar" element={<CalendarView />} />
          <Route path="/promos" element={<PromoList />} />
          <Route path="/promos/:id" element={<PromoDetail />} />
          <Route path="/scenario" element={<ScenarioCompare />} />
          <Route path="/genie-agents" element={<GenieAgents />} />
        </Routes>
      </main>
    </div>
  );
}

function Home({ user }: { user: CurrentUser | null }) {
  const navigate = useNavigate();
  const firstName = user?.display_name?.split(' ')[0];

  const cards = [
    { to: '/calendar', icon: CalendarDays, title: '52-Week Planning Calendar', desc: 'See every promotion across the year by market, channel and brand. Color-coded by ROI.', color: 'from-indigo-500 to-indigo-700' },
    { to: '/promos', icon: LayoutGrid, title: 'Promotions Workspace', desc: 'Review, approve, adjust budgets, comment and lock promotion plans. Write-back to Lakebase.', color: 'from-blue-500 to-cyan-600' },
    { to: '/scenario', icon: GitCompareArrows, title: 'Scenario Comparison', desc: 'Baseline vs proposed on volume, margin, trade spend and ROI — across the portfolio.', color: 'from-fuchsia-500 to-pink-600' },
    { to: '/genie-agents', icon: MessageSquareText, title: 'RGM Genie Agents', desc: 'Ask in plain English: "Which promos should we move from Q2 to Q3?" Powered by Genie.', color: 'from-violet-500 to-indigo-600' },
  ];

  const highlights = [
    { icon: TrendingUp, title: 'Decide with ROI in view', desc: 'Every plan shows incremental volume, margin, trade spend and ROI so you invest where it pays back.' },
    { icon: PencilLine, title: 'Act inside the app', desc: 'Approve plans, adjust budgets, assign follow-ups and comment — persisted transactionally in Lakebase.' },
    { icon: Lock, title: 'Lock the scenario', desc: 'Freeze an agreed plan so downstream execution works from a single, governed source of truth.' },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-8 py-12">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--accent-dim)] text-[var(--accent)] text-xs font-semibold mb-4">
          <Sparkles className="w-3.5 h-3.5" /> Promote with Purpose
        </span>
        <h2 className="text-4xl font-bold text-[var(--text-primary)] mb-3 tracking-tight">
          {firstName ? `Welcome back, ${firstName}` : 'Promotion Planning Genie Agents'}
        </h2>
        <p className="text-lg text-[var(--text-secondary)] max-w-2xl leading-relaxed">
          Plan, compare and approve trade promotions with granular ROI in view — then act on them
          without leaving the app. Built for Revenue Growth Management.
        </p>
        <div className="flex flex-wrap gap-3 mt-6">
          <button onClick={() => navigate('/calendar')} className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-semibold transition-colors">
            <CalendarDays className="w-4 h-4" /> Open the calendar <ArrowRight className="w-4 h-4" />
          </button>
          <button onClick={() => navigate('/genie-agents')} className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] hover:border-[var(--text-secondary)] text-[var(--text-primary)] text-sm font-semibold transition-colors">
            <MessageSquareText className="w-4 h-4" /> Ask the Genie Agents
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-12 mb-12">
          {highlights.map((h) => (
            <div key={h.title} className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]">
              <div className="w-10 h-10 rounded-lg bg-[var(--accent-dim)] flex items-center justify-center mb-3">
                <h.icon className="w-5 h-5 text-[var(--accent)]" />
              </div>
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">{h.title}</h3>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{h.desc}</p>
            </div>
          ))}
        </div>

        <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">Explore</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {cards.map((c) => (
            <button key={c.to} onClick={() => navigate(c.to)}
              className="group text-left p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] hover:border-[var(--text-secondary)] hover:shadow-lg transition-all duration-200 flex items-start gap-4">
              <div className={`w-11 h-11 rounded-lg bg-gradient-to-br ${c.color} flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform`}>
                <c.icon className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">{c.title}</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{c.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
