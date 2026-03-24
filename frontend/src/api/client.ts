import axios from 'axios';
import { useAppStore } from '../store/useAppStore';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 60000,
});

client.interceptors.request.use((config) => {
  const user = useAppStore.getState().user;
  if (user?.token) {
    config.headers.Authorization = `Bearer ${user.token}`;
  }
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      useAppStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default client;
