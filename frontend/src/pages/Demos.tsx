import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Presentation, Scissors, Shuffle, Sparkles, ArrowRight, Clock, Target,
  CheckCircle2, ChevronDown, ChevronRight, Database, MessageSquareText,
  SlidersHorizontal, LayoutGrid,
} from 'lucide-react';

interface Step {
  goto?: { to: string; label: string };
  text: string;
}

interface Demo {
  id: string;
  icon: any;
  color: string;
  title: string;
  duration: string;
  audience: string;
  hook: string;
  question: string;
  steps: Step[];
  payoff: string;
  proves: string[];
}

const DEMOS: Demo[] = [
  {
    id: 'trim-overspend',
    icon: Scissors,
    color: 'from-rose-500 to-orange-600',
    title: 'Trim the overspend',
    duration: '3–4 min',
    audience: 'Revenue managers, RGM leads',
    hook: 'Not every promotion pays back. Find the ones burning trade spend for too little lift and fix them in seconds.',
    question: '“Where are we overspending with low incrementality — and what happens if we pull back?”',
    steps: [
      { goto: { to: '/impact', label: 'Impact Analysis' }, text: 'Open Impact Analysis and scroll to “Underperforming — overspending for low lift”. Point out the red, negative-ROI promotions (typically Loyalty Coupon / Price Reduction at deep discounts).' },
      { goto: { to: '/builder', label: 'Scenario Builder' }, text: 'Go to Scenario Builder. Find one of those losing promotions and drag its discount slider down — watch Fcst Lift, Trade $, Net Profit and ROI recompute instantly in the row, with the ▲/▼ delta vs the current plan.' },
      { text: 'Note the live portfolio summary at the top updating as you edit — trade spend drops and blended ROI ticks up.' },
      { text: 'Hit “Save scenario”. Read the confirmation panel showing exactly which Lakebase tables were written.' },
      { goto: { to: '/impact', label: 'Impact Analysis' }, text: 'Return to Impact Analysis — the net-profit bridge and “Biggest scenario moves” now reflect your saved change vs the committed plan.' },
    ],
    payoff: 'A losing promotion becomes profitable in three clicks, and the impact is quantified across the portfolio — no spreadsheet, no analyst round-trip.',
    proves: ['Live what-if modeling', 'Governed write-back to Lakebase', 'Current-vs-scenario impact'],
  },
  {
    id: 'reallocate',
    icon: Shuffle,
    color: 'from-indigo-500 to-teal-500',
    title: 'Reallocate the budget',
    duration: '4–5 min',
    audience: 'RGM + finance, commercial planning',
    hook: 'Same total trade budget, better return. Shift depth toward high-elasticity mechanics and markets that convert.',
    question: '“If we hold spend flat but move it to what works, how much more profit do we get?”',
    steps: [
      { goto: { to: '/impact', label: 'Impact Analysis' }, text: 'Start in Impact Analysis. Toggle the breakdown between Brand, Market and Channel — highlight that Club/Warehouse and Display-driven promos return the best ROI.' },
      { goto: { to: '/builder', label: 'Scenario Builder' }, text: 'In Scenario Builder, deepen discounts on 2–3 high-ROI (green) promotions and trim the low-ROI ones by a similar amount — keeping total trade spend roughly flat (watch the summary tile).' },
      { text: 'Point out that lift responds more per point of discount on high-elasticity mechanics (Display + Feature, Multi-Buy) — that is where the extra depth pays back.' },
      { text: 'Save all edits with “Save scenario”.' },
      { goto: { to: '/impact', label: 'Impact Analysis' }, text: 'Back in Impact Analysis, use the net-profit bridge to show margin gained vs spend moved, and the KPI cards to show net profit up at (roughly) flat spend.' },
    ],
    payoff: 'The same trade budget generates more incremental profit — a concrete “work smarter, not harder” story backed by the elasticity model.',
    proves: ['Portfolio optimization', 'Breakdowns by brand / market / channel', 'Net-profit bridge'],
  },
  {
    id: 'ask-genie',
    icon: Sparkles,
    color: 'from-violet-500 to-fuchsia-600',
    title: 'Ask the Genie Agents',
    duration: '2–3 min',
    audience: 'Any business user, execs',
    hook: 'No dashboards, no SQL. Ask questions in plain English and get governed answers with the query and data behind them.',
    question: '“Which brands deliver the best promotion ROI?” · “Where are we overspending with low incrementality?”',
    steps: [
      { goto: { to: '/genie-agents', label: 'Genie Agents' }, text: 'Open Genie Agents. Click one of the suggested questions, or type: “Which promotions have the lowest ROI and highest trade spend?”' },
      { text: 'When the answer returns, expand the SQL toggle — show that Genie generated governed SQL against Unity Catalog, not a black box.' },
      { text: 'Ask a follow-up in the same thread, e.g. “Now show that by market.” Emphasize it keeps context.' },
      { goto: { to: '/promos', label: 'Promotions' }, text: 'Tie it back to action: open the Promotions workspace, find a promo the copilot flagged, and approve or lock it — closing the loop from insight to decision.' },
    ],
    payoff: 'Natural-language analytics over trusted data, with the SQL shown for transparency — then acted on in the same app.',
    proves: ['Genie over Unity Catalog', 'Explainable SQL', 'Insight → action in one app'],
  },
];

const ARCH = [
  { icon: Database, label: 'Unity Catalog', note: 'governed promotion data & semantics' },
  { icon: MessageSquareText, label: 'Genie', note: 'natural-language analytics' },
  { icon: LayoutGrid, label: 'Databricks App', note: 'React + FastAPI front end' },
  { icon: SlidersHorizontal, label: 'Lakebase', note: 'transactional write-back' },
];

export default function Demos() {
  const [open, setOpen] = useState<string>(DEMOS[0].id);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-8">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--accent-dim)] text-[var(--accent)] text-xs font-semibold mb-4">
          <Presentation className="w-3.5 h-3.5" /> Demo playbook
        </span>
        <h2 className="text-3xl font-bold text-[var(--text-primary)] mb-2 tracking-tight">Three demos you can run today</h2>
        <p className="text-[var(--text-secondary)] max-w-2xl leading-relaxed mb-6">
          Each storyline is a self-contained walkthrough with the business question, the exact clicks,
          and the point it proves. Expand one and follow the steps live — the buttons jump you to the right tab.
        </p>

        {/* Architecture strip */}
        <div className="flex flex-wrap items-center gap-2 mb-8 p-3 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)]" style={{ boxShadow: 'var(--shadow-sm)' }}>
          <span className="text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide mr-1">Under the hood</span>
          {ARCH.map((a, i) => (
            <div key={a.label} className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[var(--bg-tertiary)]">
                <a.icon className="w-3.5 h-3.5 text-[var(--accent)]" />
                <span className="text-xs font-medium text-[var(--text-primary)]">{a.label}</span>
                <span className="text-[10px] text-[var(--text-secondary)] hidden lg:inline">· {a.note}</span>
              </div>
              {i < ARCH.length - 1 && <ArrowRight className="w-3 h-3 text-[var(--text-tertiary)]" />}
            </div>
          ))}
        </div>

        <div className="space-y-4">
          {DEMOS.map((d, i) => (
            <DemoCard key={d.id} demo={d} index={i + 1} open={open === d.id} onToggle={() => setOpen(open === d.id ? '' : d.id)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function DemoCard({ demo, index, open, onToggle }: { demo: Demo; index: number; open: boolean; onToggle: () => void }) {
  const navigate = useNavigate();
  return (
    <div className="rounded-2xl bg-[var(--bg-secondary)] border border-[var(--border)] overflow-hidden transition-shadow" style={{ boxShadow: open ? 'var(--shadow-lg)' : 'var(--shadow-sm)' }}>
      <button onClick={onToggle} className="w-full flex items-center gap-4 p-5 text-left hover:bg-[var(--bg-tertiary)] transition-colors">
        <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${demo.color} flex items-center justify-center shrink-0 shadow-sm`}>
          <demo.icon className="w-6 h-6 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold text-[var(--text-tertiary)]">DEMO {index}</span>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">{demo.title}</h3>
          </div>
          <p className="text-sm text-[var(--text-secondary)] leading-snug mt-0.5">{demo.hook}</p>
        </div>
        <div className="hidden sm:flex flex-col items-end gap-1 shrink-0">
          <span className="inline-flex items-center gap-1 text-[11px] text-[var(--text-secondary)]"><Clock className="w-3 h-3" /> {demo.duration}</span>
          <span className="inline-flex items-center gap-1 text-[11px] text-[var(--text-secondary)]"><Target className="w-3 h-3" /> {demo.audience}</span>
        </div>
        {open ? <ChevronDown className="w-5 h-5 text-[var(--text-secondary)] shrink-0" /> : <ChevronRight className="w-5 h-5 text-[var(--text-secondary)] shrink-0" />}
      </button>

      {open && (
        <div className="px-5 pb-5 pt-1">
          {/* Business question */}
          <div className="mb-5 p-3 rounded-lg bg-[var(--accent-dim)] border-l-2 border-[var(--accent)]">
            <p className="text-[11px] font-semibold text-[var(--accent)] uppercase tracking-wide mb-0.5">The business question</p>
            <p className="text-sm text-[var(--text-primary)] italic">{demo.question}</p>
          </div>

          {/* Steps */}
          <p className="text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-3">Walkthrough</p>
          <ol className="space-y-3 mb-5">
            {demo.steps.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-6 h-6 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
                <div className="flex-1">
                  <p className="text-sm text-[var(--text-primary)] leading-relaxed">{s.text}</p>
                  {s.goto && (
                    <button onClick={() => navigate(s.goto!.to)}
                      className="inline-flex items-center gap-1 mt-1.5 px-2.5 py-1 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-xs font-medium transition-colors">
                      Go to {s.goto.label} <ArrowRight className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>

          {/* Payoff */}
          <div className="flex items-start gap-2 p-3 rounded-lg bg-emerald-50 border border-emerald-200 mb-4">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-[11px] font-semibold text-emerald-700 uppercase tracking-wide mb-0.5">The payoff</p>
              <p className="text-sm text-[var(--text-primary)] leading-relaxed">{demo.payoff}</p>
            </div>
          </div>

          {/* Proves */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide">Proves</span>
            {demo.proves.map((p) => (
              <span key={p} className="px-2.5 py-0.5 rounded-full bg-[var(--accent-2-dim)] text-[var(--accent-2)] text-xs font-medium">{p}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
