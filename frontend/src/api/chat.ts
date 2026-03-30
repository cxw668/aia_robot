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

// SSE event types from /chat/stream
export type SseEvent =
  | { type: 'citations'; citations: Citation[]; session_id: string }
  | { type: 'delta'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

/** Non-streaming chat request */
export async function sendChat(payload: ChatRequest): Promise<ChatResponse> {
  try {
    const res = await client.post<ChatResponse>('/chat', payload);
    return res.data;
  } catch (err: unknown) {
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

/**
 * Streaming chat via SSE.
 *
 * Calls /chat/stream and invokes callbacks as events arrive:
 *   onCitations  — called once with citations + session_id
 *   onDelta      — called for each text chunk
 *   onDone       — called when stream ends
 *   onError      — called on error
 *
 * Returns an AbortController so the caller can cancel mid-stream.
 */
export function sendChatStream(
  payload: ChatRequest,
  callbacks: {
    onCitations: (citations: Citation[], sessionId: string) => void;
    onDelta: (text: string) => void;
    onDone: () => void;
    onError: (msg: string) => void;
  },
): AbortController {
  const ac = new AbortController();
  let doneEmitted = false;

  const baseURL: string =
    (client.defaults.baseURL as string | undefined) ?? 'http://localhost:8000/api';
  const url = `${baseURL}/chat/stream`;

  // Get auth token from localStorage (same key used by the axios client interceptor)
  const token = localStorage.getItem('token') ?? '';

  fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal: ac.signal,
  })
    .then(async (resp) => {
      if (!resp.ok) {
        const text = await resp.text();
        callbacks.onError(`HTTP ${resp.status}: ${text}`);
        return;
      }
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.slice('data:'.length).trim();
          if (!jsonStr) continue;
          try {
            const event = JSON.parse(jsonStr) as SseEvent;
            if (event.type === 'citations') {
              callbacks.onCitations(event.citations, event.session_id);
            } else if (event.type === 'delta') {
              callbacks.onDelta(event.text);
            } else if (event.type === 'done') {
              doneEmitted = true;
              callbacks.onDone();
            } else if (event.type === 'error') {
              callbacks.onError(event.message);
            }
          } catch {
            // ignore malformed SSE lines
          }
        }
      }
      if (!doneEmitted) {
        callbacks.onDone();
      }
    })
    .catch((err: unknown) => {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      callbacks.onError(String(err));
    });

  return ac;
}

export async function clearSession(sessionId: string): Promise<void> {
  await client.delete(`/chat/${sessionId}`);
}

export async function getSessionHistory(sessionId: string): Promise<HistoryMessage[]> {
  const res = await client.get<{ messages: HistoryMessage[] }>(`/chat/${sessionId}/history`);
  return res.data.messages;
}
