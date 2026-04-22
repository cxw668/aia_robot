import client, { getAuthToken } from './client';
import type { Citation, ChatMode, StructuredAnswer } from '../store/useChatStore';

export interface ChatRequest {
  query: string;
  session_id?: string;
  top_k?: number;
  mode?: ChatMode;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  structuredAnswer: StructuredAnswer;
  session_id: string;
}

type RawStructuredAnswer = {
  summary: string;
  evidence: Array<{
    title: string;
    snippet: string;
    score: number;
    url?: string;
  }>;
  next_actions: Array<{
    label: string;
    url?: string;
  }>;
  risk_tips: string[];
  confidence: string;
};

type RawChatResponse = {
  answer: string;
  citations: Citation[];
  structured_answer: RawStructuredAnswer;
  session_id: string;
};

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

// SSE event types from /chat/stream
export type SseEvent =
  | { type: 'citations'; citations: Citation[]; session_id: string }
  | { type: 'delta'; text: string }
  | { type: 'structured'; structured_answer: RawStructuredAnswer }
  | { type: 'done' }
  | { type: 'error'; message: string; code?: string; request_id?: string };

type ApiErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
};

function parseApiErrorPayload(payload: unknown): { message: string; code?: string } {
  // Streaming and non-streaming failures now share the same backend envelope,
  // so the client only needs one parser here.
  if (typeof payload === 'string') {
    try {
      return parseApiErrorPayload(JSON.parse(payload) as ApiErrorEnvelope);
    } catch {
      return { message: payload };
    }
  }
  if (typeof payload === 'object' && payload !== null && 'error' in payload) {
    const envelope = payload as ApiErrorEnvelope;
    return {
      message: envelope.error?.message?.trim() || 'Request failed',
      code: envelope.error?.code,
    };
  }
  return { message: 'Request failed' };
}

/** Non-streaming chat request */
export async function sendChat(payload: ChatRequest): Promise<ChatResponse> {
  try {
    const res = await client.post<RawChatResponse>('/chat', payload);
    return normalizeChatResponse(res.data);
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
      structuredAnswer: {
        summary: '后端服务暂未连接，当前展示的是本地模拟回复。',
        evidence: [],
        nextActions: [],
        riskTips: ['请启动后端服务后重试正式问答。'],
        confidence: 'low',
      },
      session_id: payload.session_id || 'mock-' + Date.now(),
    };
  }
}

/**
 * Streaming chat via SSE.
 *
 * Calls /chat/stream and invokes callbacks as events arrive:
 *   onCitations  — called once with citations
 *   onDelta      — called for each text chunk
 *   onDone       — called when stream ends
 *   onError      — called on error
 *
 * Returns an AbortController so the caller can cancel mid-stream.
 */
export function sendChatStream(
  payload: ChatRequest,
  callbacks: {
    onCitations: (citations: Citation[]) => void;
    onDelta: (text: string) => void;
    onStructured: (structuredAnswer: StructuredAnswer) => void;
    onDone: () => void;
    onError: (msg: string, code?: string) => void;
  },
): AbortController {
  const ac = new AbortController();
  let doneEmitted = false;

  const baseURL: string =
    (client.defaults.baseURL as string | undefined) ?? 'http://localhost:8000/api';
  const url = `${baseURL}/chat/stream`;

  const token = getAuthToken();

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
        const parsed = parseApiErrorPayload(text);
        callbacks.onError(parsed.message || `HTTP ${resp.status}`, parsed.code);
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
              callbacks.onCitations(event.citations);
            } else if (event.type === 'delta') {
              callbacks.onDelta(event.text);
            } else if (event.type === 'structured') {
              callbacks.onStructured(normalizeStructuredAnswer(event.structured_answer));
            } else if (event.type === 'done') {
              doneEmitted = true;
              callbacks.onDone();
            } else if (event.type === 'error') {
              callbacks.onError(event.message, event.code);
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

function normalizeChatResponse(payload: RawChatResponse): ChatResponse {
  return {
    answer: payload.answer,
    citations: payload.citations,
    structuredAnswer: normalizeStructuredAnswer(payload.structured_answer),
    session_id: payload.session_id,
  };
}

function normalizeStructuredAnswer(payload: RawStructuredAnswer): StructuredAnswer {
  return {
    summary: payload.summary,
    evidence: payload.evidence,
    nextActions: payload.next_actions,
    riskTips: payload.risk_tips,
    confidence: payload.confidence,
  };
}
