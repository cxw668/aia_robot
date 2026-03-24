import client from './client';
import type { Citation } from '../store/useChatStore';

export interface ChatRequest {
  query: string;
  session_id?: string;
  top_k?: number;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  session_id: string;
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function sendChat(payload: ChatRequest): Promise<ChatResponse> {
  try {
    const res = await client.post<ChatResponse>('/chat', payload);
    return res.data;
  } catch (err: unknown) {
    // Only fall back to mock when the backend is completely unreachable (network error)
    const isNetworkError =
      typeof err === 'object' &&
      err !== null &&
      'code' in err &&
      (err as { code: string }).code === 'ERR_NETWORK';
    if (!isNetworkError) throw err;
    await new Promise((r) => setTimeout(r, 600));
    return {
      answer:
        '您好！我是 AIA 智能助手。后端服务暂未连接，这是模拟回复。\n\n请启动后端后重试：\n```bash\nuvicorn app.main:app --reload\n```',
      citations: [],
      session_id: payload.session_id || 'mock-' + Date.now(),
    };
  }
}

export async function clearSession(sessionId: string): Promise<void> {
  await client.delete(`/chat/${sessionId}`);
}

export async function getSessionHistory(sessionId: string): Promise<HistoryMessage[]> {
  const res = await client.get<{ messages: HistoryMessage[] }>(`/chat/${sessionId}/history`);
  return res.data.messages;
}
