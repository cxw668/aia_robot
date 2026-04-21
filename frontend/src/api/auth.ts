import client from './client';
import axios from 'axios';

export interface LoginPayload {
  username: string;
  password: string;
}

export interface AuthResponse {
  token: string;
  username: string;
}

// Mock auth — replace with real endpoints when backend is ready
const MOCK_USER = { username: 'admin', password: 'admin123' };

function getAuthErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const message = error.response?.data?.error?.message;
    if (typeof message === 'string' && message.trim()) {
      return message;
    }
  }
  return fallback;
}

export async function login(payload: LoginPayload): Promise<AuthResponse> {
  // Try real API first; fall back to mock
  try {
    const res = await client.post<AuthResponse>('/auth/login', payload);
    return res.data;
  } catch (error: unknown) {
    if (
      payload.username === MOCK_USER.username &&
      payload.password === MOCK_USER.password
    ) {
      return { token: 'mock-token-admin', username: payload.username };
    }
    throw new Error(getAuthErrorMessage(error, 'Invalid credentials'));
  }
}

export async function register(payload: LoginPayload): Promise<AuthResponse> {
  try {
    const res = await client.post<AuthResponse>('/auth/register', payload);
    return res.data;
  } catch (error: unknown) {
    throw new Error(getAuthErrorMessage(error, 'Registration failed'));
  }
}
