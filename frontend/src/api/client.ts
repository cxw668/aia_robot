import axios from 'axios';
import { useAppStore } from '../store/useAppStore';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 60000,
});

const APP_STORE_KEY = 'aia-app-store';

type PersistedAppStore = {
  state?: {
    user?: {
      token?: string;
    } | null;
  };
};

export function getAuthToken(): string | null {
  const stateToken = useAppStore.getState().user?.token;
  if (stateToken) return stateToken;

  const raw = window.localStorage.getItem(APP_STORE_KEY);
  if (!raw) return null;

  try {
    const persisted = JSON.parse(raw) as PersistedAppStore;
    return persisted.state?.user?.token ?? null;
  } catch {
    return null;
  }
}

client.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const url: string = err.config?.url ?? '';
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register');
    if (err.response?.status === 401 && !isAuthEndpoint) {
      useAppStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default client;
