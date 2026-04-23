import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Citation {
  title: string;
  content: string;
  score: number;
  service_name?: string;
  service_url?: string;
  collection?: string;
}

export interface StructuredEvidence {
  title: string;
  snippet: string;
  score: number;
  url?: string;
}

export interface StructuredAction {
  label: string;
  url?: string;
}

export interface StructuredAnswer {
  summary: string;
  evidence: StructuredEvidence[];
  nextActions: StructuredAction[];
  riskTips: string[];
  confidence: string;
}

export interface ProcessingStep {
  stage: string;
  label: string;
  detail?: string;
}

export type ChatMode = 'casual' | 'support';
export const DEFAULT_CHAT_MODE: ChatMode = 'support';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  processingSteps?: ProcessingStep[];
  structuredAnswer?: StructuredAnswer;
  feedback?: 'helpful' | 'not_helpful';
  timestamp: number;
  streaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  mode: ChatMode;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

interface ChatState {
  conversations: Conversation[];
  activeId: string | null;
  streaming: boolean;
  createConversation: () => string;
  setActiveId: (id: string) => void;
  setConversationMode: (convId: string, mode: ChatMode) => void;
  addMessage: (convId: string, msg: Message) => void;
  updateMessage: (convId: string, msgId: string, patch: Partial<Message>) => void;
  deleteConversation: (id: string) => void;
  clearAll: () => void;
  setStreaming: (v: boolean) => void;
}

const genId = () => Math.random().toString(36).slice(2, 10);

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      conversations: [],
      activeId: null,
      streaming: false,
      createConversation: () => {
        const id = genId();
        const now = Date.now();
        set((s) => ({
          conversations: [
              {
                id,
                title: '新对话',
                mode: DEFAULT_CHAT_MODE,
                messages: [],
                createdAt: now,
                updatedAt: now,
              },
              ...s.conversations,
          ],
          activeId: id,
        }));
        return id;
      },
      setActiveId: (id) => set({ activeId: id }),
      setConversationMode: (convId, mode) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId
              ? { ...c, mode, updatedAt: Date.now() }
              : c
          ),
        })),
      addMessage: (convId, msg) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId
              ? {
                  ...c,
                  messages: [...c.messages, msg],
                  title:
                    c.messages.length === 0 && msg.role === 'user'
                      ? msg.content.slice(0, 20)
                      : c.title,
                  updatedAt: Date.now(),
                }
              : c
          ),
        })),
      updateMessage: (convId, msgId, patch) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === msgId ? { ...m, ...patch } : m
                  ),
                }
              : c
          ),
        })),
      deleteConversation: (id) =>
        set((s) => {
          const filtered = s.conversations.filter((c) => c.id !== id);
          const activeId =
            s.activeId === id
              ? filtered.length > 0
                ? filtered[0].id
                : null
              : s.activeId;
          return { conversations: filtered, activeId };
        }),
      clearAll: () => set({ conversations: [], activeId: null }),
      setStreaming: (v) => set({ streaming: v }),
    }),
    { name: 'aia-chat-store' }
  )
);

export const getActiveConversation = (state: ChatState) =>
  state.conversations.find((c) => c.id === state.activeId) ?? null;
