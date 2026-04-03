/** Auth store — persists token via storage adapter, rehydrates on launch. */

import { create } from "zustand";
import type { User } from "../types";
import { storage } from "./storage";

const TOKEN_KEY = "ts_access_token";
const USER_KEY = "ts_user";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  /** True once we've attempted to rehydrate from storage. */
  hydrated: boolean;
  setAuth: (user: User, token: string) => void;
  setAccessToken: (token: string) => void;
  logout: () => void;
  /** Load persisted session from storage (called once on app boot). */
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  hydrated: false,

  setAuth: (user, token) => {
    set({ user, accessToken: token });
    // Fire-and-forget persistence
    storage.set(TOKEN_KEY, token);
    storage.set(USER_KEY, JSON.stringify(user));
  },

  setAccessToken: (token) => {
    set({ accessToken: token });
    storage.set(TOKEN_KEY, token);
  },

  logout: () => {
    set({ user: null, accessToken: null });
    storage.remove(TOKEN_KEY);
    storage.remove(USER_KEY);
  },

  hydrate: async () => {
    try {
      const [token, userJson] = await Promise.all([
        storage.get(TOKEN_KEY),
        storage.get(USER_KEY),
      ]);
      if (token && userJson) {
        const user: User = JSON.parse(userJson);
        set({ user, accessToken: token, hydrated: true });
        return;
      }
    } catch {
      // Corrupted storage — start fresh
    }
    set({ hydrated: true });
  },
}));
