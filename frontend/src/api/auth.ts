import client from './client';

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

export async function login(payload: LoginPayload): Promise<AuthResponse> {
  // Try real API first; fall back to mock
  try {
    const res = await client.post<AuthResponse>('/auth/login', payload);
    return res.data;
  } catch {
    if (
      payload.username === MOCK_USER.username &&
      payload.password === MOCK_USER.password
    ) {
      return { token: 'mock-token-admin', username: payload.username };
    }
    throw new Error('invalid_credentials');
  }
}

export async function register(payload: LoginPayload): Promise<AuthResponse> {
  try {
    const res = await client.post<AuthResponse>('/auth/register', payload);
    return res.data;
  } catch {
    // Mock: allow admin/admin123 registration
    if (payload.username && payload.password) {
      return { token: 'mock-token-' + payload.username, username: payload.username };
    }
    throw new Error('register_failed');
  }
}
