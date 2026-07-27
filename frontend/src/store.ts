import { create } from 'zustand';
import type { Filters } from './api';

interface FilterStore {
  filters: Filters;
  setFilter: (key: keyof Filters, value: string | undefined) => void;
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

// The Genie space id, resolved once and shared. Set by the copilot on first load.
interface GenieStore {
  roomId: string | null;
  setRoomId: (id: string | null) => void;
}
export const useGenie = create<GenieStore>((set) => ({
  roomId: null,
  setRoomId: (id) => set({ roomId: id }),
}));
