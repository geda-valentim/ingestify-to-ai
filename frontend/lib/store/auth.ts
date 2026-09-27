import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { UserResponse } from "@/types/api";

// Where the token used to be kept on its own; still cleared on logout so a
// session from an older build cannot linger.
const LEGACY_TOKEN_KEY = "auth_token";

interface AuthState {
  user: UserResponse | null;
  token: string | null;
  _hasHydrated: boolean;
  setAuth: (user: UserResponse, token: string) => void;
  /** Swap in a renewed token for the same user (see components/session-heartbeat.tsx). */
  setToken: (token: string) => void;
  clearAuth: () => void;
  setHasHydrated: (state: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      _hasHydrated: false,
      setAuth: (user, token) => set({ user, token }),
      setToken: (token) => set({ token }),
      clearAuth: () => {
        try {
          localStorage.removeItem(LEGACY_TOKEN_KEY);
        } catch {
          // Storage blocked: nothing persisted there either.
        }
        set({ user: null, token: null });
      },
      setHasHydrated: (state) => set({ _hasHydrated: state }),
    }),
    {
      name: "auth-storage",
      storage: createJSONStorage(() => localStorage),
      // `_hasHydrated` is runtime state; persisting it would lie on the next load.
      partialize: (state) => ({ user: state.user, token: state.token }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);
