import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'light' | 'dark';
export type Lang = 'zh' | 'en';

export interface User {
  username: string;
  token: string;
}

interface AppState {
  themeMode: ThemeMode;
  lang: Lang;
  user: User | null;
  toggleTheme: () => void;
  setLang: (lang: Lang) => void;
  setUser: (user: User | null) => void;
  logout: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      themeMode: 'light',
      lang: 'zh',
      user: null,
      toggleTheme: () =>
        set((s) => ({ themeMode: s.themeMode === 'light' ? 'dark' : 'light' })),
      setLang: (lang) => set({ lang }),
      setUser: (user) => set({ user }),
      logout: () => set({ user: null }),
    }),
    {
      name: 'aia-app-store',
      partialize: (s) => ({ themeMode: s.themeMode, lang: s.lang, user: s.user }),
    }
  )
);
