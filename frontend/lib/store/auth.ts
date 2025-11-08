import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { UserResponse } from "@/types/api";

interface AuthState {
  user: UserResponse | null;
  token: string | null;
  _hasHydrated: boolean;
  setAuth: (user: UserResponse, token: string) => void;
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
      clearAuth: () => set({ user: null, token: null }),
      setHasHydrated: (state) => set({ _hasHydrated: state }),
    }),
    {
      name: "auth-storage",
      storage: createJSONStorage(() => localStorage),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);
