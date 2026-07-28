import { create } from 'zustand';

export type PlanTab = 'ran2026' | 'builder2027' | 'final';
export type PlanView = 'incremental' | 'absolute' | 'rec_pptr';

export interface PricingFilterState {
  wholesaler?: string;   // wholesaler_id
  brand?: string;        // brand_code
  prc_group?: string;    // prc_code
}

interface FilterStore {
  filters: PricingFilterState;
  setFilter: (key: keyof PricingFilterState, value: string | undefined) => void;
  clearFilters: () => void;
}

export const useFilters = create<FilterStore>((set) => ({
  filters: {},
  setFilter: (key, value) =>
    set((s) => {
      const next = { ...s.filters };
      if (value) next[key] = value;
      else delete next[key];
      return { filters: next };
    }),
  clearFilters: () => set({ filters: {} }),
}));

// The plan year each tab reads/writes.
export const TAB_PLAN_YEAR: Record<PlanTab, number> = {
  ran2026: 2026,
  builder2027: 2027,
  final: 2027,
};
