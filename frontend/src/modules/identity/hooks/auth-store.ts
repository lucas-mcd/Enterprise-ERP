import { create } from "zustand";
import type { Session } from "../types/auth";
type AuthState = {
  session: Session | null;
  generation: number;
  setSession: (session: Session) => void;
  clear: () => void;
};
// Access token in memory. Refresh uses an HttpOnly cookie.
export const useAuth = create<AuthState>((set) => ({
  session: null,
  generation: 0,
  setSession: (session) =>
    set((s) => ({ session, generation: s.generation + 1 })),
  clear: () => set((s) => ({ session: null, generation: s.generation + 1 })),
}));
