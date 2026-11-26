import { create } from "zustand";
type ShellState = { compact: boolean; toggle: () => void };
export const useShell = create<ShellState>((set) => ({
  compact: false,
  toggle: () => set((state) => ({ compact: !state.compact })),
}));
