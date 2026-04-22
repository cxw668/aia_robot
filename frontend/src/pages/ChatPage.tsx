import { useEffect, useRef, useState } from 'react';
import {
  Box, IconButton, TextField, Typography, Tooltip, Divider,
  Chip, Paper, Collapse, Button, Dialog, ToggleButton, ToggleButtonGroup,
  DialogTitle, DialogActions, useTheme, useMediaQuery, Avatar,
} from '@mui/material';
import {
  Send, Add, Delete, ContentCopy, ThumbUp, ThumbDown,
  AutoAwesome, Clear, ExpandMore, Stop,
  KeyboardDoubleArrowRight,
} from '@mui/icons-material';
import { useSnackbar } from 'notistack';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useChatStore, type Message, type Citation, type ChatMode, DEFAULT_CHAT_MODE } from '../store/useChatStore';
import { sendChatStream } from '../api/chat';
function MsgBubble({ msg, convId, isStreamingActive }: { msg: Message; convId: string; isStreamingActive?: boolean }) {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const theme = useTheme();
  const { updateMessage } = useChatStore();
  const isUser = msg.role === 'user';
  const [citOpen, setCitOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const isDark = theme.palette.mode === 'dark';
  const structuredAnswer = msg.structuredAnswer;
  const confidenceLabel =
    structuredAnswer?.confidence === 'high'
      ? t('structuredConfidenceHigh')
      : structuredAnswer?.confidence === 'medium'
        ? t('structuredConfidenceMedium')
        : t('structuredConfidenceLow');

  const copy = () => {
    navigator.clipboard.writeText(msg.content);
    setCopied(true);
    enqueueSnackbar(t('copyMsg'), { variant: 'success' });
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: 1.5, alignItems: 'flex-start', px: { xs: 1, sm: 2 }, mb: 2 }}>
      <Avatar sx={{ width: 32, height: 32, bgcolor: isUser ? 'primary.main' : 'secondary.main', fontSize: 14, flexShrink: 0 }}>
        {isUser ? 'U' : <AutoAwesome sx={{ fontSize: 16 }} />}
      </Avatar>
      <Box sx={{ maxWidth: { xs: '85%', sm: '72%' }, minWidth: 0 }}>
        <Paper elevation={0} sx={{
          px: 2, py: 1.5,
          borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
          bgcolor: isUser ? (isDark ? '#1a1a3e' : 'primary.main') : 'background.paper',
          color: isUser ? '#fff' : 'text.primary',
          border: isUser ? 0 : 1, borderColor: 'divider',
          wordBreak: 'break-word',
          '& p': { m: 0 },
          '& pre': { bgcolor: isDark ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.04)', p: 1.5, borderRadius: 1, overflow: 'auto', fontSize: '0.82rem' },
          '& code': { fontFamily: '"JetBrains Mono",monospace', fontSize: '0.85em', bgcolor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)', px: 0.5, borderRadius: 0.5 },
          '& pre code': { bgcolor: 'transparent', p: 0 },
          '& ul,& ol': { pl: 2.5, my: 0.5 },
          '& table': { borderCollapse: 'collapse', width: '100%' },
          '& th,& td': { border: '1px solid', borderColor: 'divider', px: 1, py: 0.5, fontSize: '0.85rem' },
        }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
          {!isUser && isStreamingActive && (
            <Box
              component="span"
              sx={{
                display: 'inline-block',
                width: '8px',
                height: '1em',
                bgcolor: isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.75)',
                verticalAlign: 'text-bottom',
                ml: 0.4,
                animation: 'cursorBlink 1s steps(1) infinite',
                '@keyframes cursorBlink': {
                  '0%, 50%': { opacity: 1 },
                  '50.01%, 100%': { opacity: 0 },
                },
              }}
            />
          )}
        </Paper>

        {!isUser && !isStreamingActive && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5, ml: 0.5 }}>
            <Tooltip title={copied ? t('copyMsg') : 'Copy'}>
              <IconButton size="small" onClick={copy} sx={{ opacity: 0.5, '&:hover': { opacity: 1 } }}>
                <ContentCopy sx={{ fontSize: 14 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title={t('helpful')}>
              <IconButton
                size="small"
                onClick={() => {
                  updateMessage(convId, msg.id, { feedback: 'helpful' });
                  enqueueSnackbar(t('feedbackSent'), { variant: 'success' });
                }}
                color={msg.feedback === 'helpful' ? 'success' : 'default'}
                sx={{ opacity: 0.5, '&:hover': { opacity: 1 } }}
              >
                <ThumbUp sx={{ fontSize: 14 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title={t('notHelpful')}>
              <IconButton
                size="small"
                onClick={() => {
                  updateMessage(convId, msg.id, { feedback: 'not_helpful' });
                  enqueueSnackbar(t('feedbackSent'), { variant: 'success' });
                }}
                color={msg.feedback === 'not_helpful' ? 'error' : 'default'}
                sx={{ opacity: 0.5, '&:hover': { opacity: 1 } }}
              >
                <ThumbDown sx={{ fontSize: 14 }} />
              </IconButton>
            </Tooltip>
            {msg.citations && msg.citations.length > 0 && (
              <Chip size="small"
                icon={<ExpandMore sx={{ fontSize: '14px !important', transform: citOpen ? 'rotate(180deg)' : 'none', transition: '0.2s' }} />}
                label={`${t('references')} (${msg.citations.length})`}
                onClick={() => setCitOpen(!citOpen)} variant="outlined"
                sx={{ ml: 0.5, height: 22, fontSize: '0.7rem' }} />
            )}
            {structuredAnswer && (
              <Chip
                size="small"
                label={`${t('structuredConfidence')}: ${confidenceLabel}`}
                variant="outlined"
                color={structuredAnswer.confidence === 'high' ? 'success' : structuredAnswer.confidence === 'medium' ? 'warning' : 'default'}
                sx={{ ml: 0.5, height: 22, fontSize: '0.7rem' }}
              />
            )}
          </Box>
        )}

        {structuredAnswer && !isUser && !isStreamingActive && (
          <Paper
            elevation={0}
            sx={{
              mt: 1,
              p: 1.5,
              border: 1,
              borderColor: 'divider',
              borderRadius: 2,
              bgcolor: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.015)',
            }}
          >
            {structuredAnswer.evidence.length > 0 && (
              <Box sx={{ mb: structuredAnswer.nextActions.length > 0 || structuredAnswer.riskTips.length > 0 ? 1.25 : 0 }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary">
                  {t('structuredEvidence')}
                </Typography>
                <Box sx={{ mt: 0.75, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                  {structuredAnswer.evidence.map((item, index) => (
                    <Box key={`${item.title}-${index}`} sx={{ display: 'flex', flexDirection: 'column', gap: 0.3 }}>
                      <Typography variant="caption" fontWeight={600}>
                        {item.title}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {item.snippet}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </Box>
            )}

            {structuredAnswer.nextActions.length > 0 && (
              <Box sx={{ mb: structuredAnswer.riskTips.length > 0 ? 1.25 : 0 }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary">
                  {t('structuredNextActions')}
                </Typography>
                <Box sx={{ mt: 0.75, display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
                  {structuredAnswer.nextActions.map((item, index) => (
                    <Chip
                      key={`${item.label}-${index}`}
                      label={item.label}
                      component={item.url ? 'a' : 'div'}
                      clickable={!!item.url}
                      href={item.url || undefined}
                      target={item.url ? '_blank' : undefined}
                      rel={item.url ? 'noreferrer' : undefined}
                      variant="outlined"
                      color="primary"
                      sx={{ maxWidth: '100%' }}
                    />
                  ))}
                </Box>
              </Box>
            )}

            {structuredAnswer.riskTips.length > 0 && (
              <Box>
                <Typography variant="caption" fontWeight={700} color="text.secondary">
                  {t('structuredRiskTips')}
                </Typography>
                <Box component="ul" sx={{ mt: 0.75, mb: 0, pl: 2 }}>
                  {structuredAnswer.riskTips.map((item, index) => (
                    <Typography key={`${item}-${index}`} component="li" variant="caption" color="text.secondary" sx={{ mb: 0.35 }}>
                      {item}
                    </Typography>
                  ))}
                </Box>
              </Box>
            )}
          </Paper>
        )}

        {msg.citations && msg.citations.length > 0 && (
          <Collapse in={citOpen}>
            <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
              {msg.citations.map((c, i) => (
                <Paper key={i} elevation={0} sx={{ p: 1.5, border: 1, borderColor: 'divider', borderRadius: 2, borderLeft: 3, borderLeftColor: 'secondary.main' }}>
                  <Typography variant="caption" fontWeight={600} color="secondary.main">[{i + 1}] {c.title || c.service_name}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>{c.content?.slice(0, 120)}…</Typography>
                  <Chip size="small" label={`${Math.round(c.score * 100)}%`} sx={{ mt: 0.5, height: 18, fontSize: '0.65rem' }} />
                </Paper>
              ))}
            </Box>
          </Collapse>
        )}
      </Box>
    </Box>
  );
}

export default function ChatPage() {
  const { t } = useTranslation();
  const { enqueueSnackbar } = useSnackbar();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const {
    conversations, activeId, streaming,
    createConversation, setActiveId, setConversationMode,
    addMessage, updateMessage, deleteConversation, clearAll, setStreaming,
  } = useChatStore();
  const messages = useChatStore((s) => s.conversations.find((x) => x.id === s.activeId)?.messages ?? []);
  const convTitle = useChatStore((s) => s.conversations.find((x) => x.id === s.activeId)?.title ?? '');
  const currentMode = useChatStore(
    (s) => s.conversations.find((x) => x.id === s.activeId)?.mode ?? DEFAULT_CHAT_MODE
  );
  const [input, setInput] = useState('');
  const [sideOpen, setSideOpen] = useState(!isMobile);
  const [confirmClear, setConfirmClear] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const streamAssistantIdRef = useRef<string | null>(null);
  const isDark = theme.palette.mode === 'dark';
  const inputPlaceholder =
    currentMode === 'casual' ? t('inputPlaceholderCasual') : t('inputPlaceholderSupport');

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages.length, streaming]);

  useEffect(() => {
    if (!activeId && conversations.length === 0) createConversation();
    else if (!activeId && conversations.length > 0) setActiveId(conversations[0].id);
  }, []);

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
    };
  }, []);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming || !activeId) return;

    setInput('');
    const userMsg: Message = {
      id: Math.random().toString(36).slice(2),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    addMessage(activeId, userMsg);

    // placeholder assistant message for typewriter stream
    const assistantMsgId = Math.random().toString(36).slice(2);
    streamAssistantIdRef.current = assistantMsgId;
    addMessage(activeId, {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      citations: [],
      timestamp: Date.now(),
    });

    setStreaming(true);

    const convId = activeId;

    streamAbortRef.current = sendChatStream(
      { query: text, session_id: activeId, top_k: 5, mode: currentMode },
      {
        onCitations: (citations: Citation[]) => {
          updateMessage(convId, assistantMsgId, { citations });
        },
        onDelta: (chunk: string) => {
          const state = useChatStore.getState();
          const conv = state.conversations.find((c) => c.id === convId);
          const msg = conv?.messages.find((m) => m.id === assistantMsgId);
          if (!msg) return;
          updateMessage(convId, assistantMsgId, { content: msg.content + chunk });
        },
        onStructured: (structuredAnswer) => {
          updateMessage(convId, assistantMsgId, { structuredAnswer });
        },
        onDone: () => {
          setStreaming(false);
          streamAbortRef.current = null;
          streamAssistantIdRef.current = null;
          setTimeout(() => inputRef.current?.focus(), 100);
        },
        onError: () => {
          enqueueSnackbar(t('chatError'), { variant: 'error' });
          if (convId) {
            const state = useChatStore.getState();
            const conv = state.conversations.find((c) => c.id === convId);
            const msg = conv?.messages.find((m) => m.id === assistantMsgId);
            if (msg && !msg.content.trim()) {
              updateMessage(convId, assistantMsgId, { content: '抱歉，请求失败，请稍后重试。' });
            }
          }
          setStreaming(false);
          streamAbortRef.current = null;
          streamAssistantIdRef.current = null;
        },
      }
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <Box sx={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Conversation sidebar */}
      <Box sx={{
        width: sideOpen ? { xs: 260, md: 240 } : 0,
        flexShrink: 0, overflow: 'hidden', transition: 'width 0.22s ease',
        borderRight: 1, borderColor: 'divider', display: 'flex', flexDirection: 'column',
        bgcolor: 'background.paper',
        position: { xs: 'absolute', md: 'relative' },
        height: '100%', zIndex: { xs: 10, md: 'auto' },
        boxShadow: { xs: sideOpen ? '4px 0 20px rgba(0,0,0,0.15)' : 'none', md: 'none' },
      }}>
        <Box sx={{ p: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Button variant="contained" startIcon={<Add />}
            onClick={() => {
              createConversation();
              enqueueSnackbar(t('chatCreated'), { variant: 'success' });
              if (isMobile) setSideOpen(false);
            }}
            fullWidth size="small"
            sx={{ borderRadius: 2, background: 'linear-gradient(135deg,#e94560,#0f3460)', '&:hover': { background: 'linear-gradient(135deg,#c73652,#0a2440)' } }}>
            {t('newChat')}
          </Button>
          <Tooltip title={t('clearHistory')}>
            <IconButton size="small" onClick={() => setConfirmClear(true)}><Clear fontSize="small" /></IconButton>
          </Tooltip>
        </Box>
        <Divider />
        <Box sx={{ flex: 1, overflowY: 'auto', py: 0.5 }}>
          {conversations.length === 0
            ? <Typography variant="caption" color="text.secondary" sx={{ px: 2, py: 1, display: 'block' }}>{t('noHistory')}</Typography>
            : conversations.map((c) => (
              <Box key={c.id} onClick={() => { setActiveId(c.id); if (isMobile) setSideOpen(false); }}
                sx={{
                  px: 2, py: 1.2, cursor: 'pointer', display: 'flex', alignItems: 'center',
                  justifyContent: 'space-between', borderRadius: 1.5, mx: 0.5, mb: 0.25,
                  bgcolor: c.id === activeId ? (isDark ? 'rgba(233,69,96,0.15)' : 'rgba(26,26,46,0.06)') : 'transparent',
                  '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)' },
                  transition: 'background 0.15s',
                }}>
                <Typography variant="body2" noWrap sx={{ flex: 1, fontWeight: c.id === activeId ? 600 : 400 }}>{c.title}</Typography>
                <IconButton size="small" onClick={(e) => { e.stopPropagation(); setDeleteTarget(c.id); }}
                  sx={{ opacity: 0.4, '&:hover': { opacity: 1 }, ml: 0.5, p: 0.25 }}>
                  <Delete sx={{ fontSize: 14 }} />
                </IconButton>
              </Box>
            ))}
        </Box>
      </Box>

      {/* Chat main */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <Box sx={{ px: 2, py: 1.2, borderBottom: 1, borderColor: 'divider', display: 'flex', alignItems: 'center', gap: 1, minHeight: 52, bgcolor: 'background.paper' }}>
          <IconButton size="small" onClick={() => setSideOpen(!sideOpen)}>
            <KeyboardDoubleArrowRight sx={{ transform: sideOpen ? 'rotate(180deg)' : 'none', transition: '0.2s' }} />
          </IconButton>
          <Typography variant="body2" fontWeight={600} noWrap sx={{ flex: 1 }}>{convTitle || t('newChat')}</Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={currentMode}
            onChange={(_, mode: ChatMode | null) => {
              if (!mode || !activeId || streaming) return;
              setConversationMode(activeId, mode);
            }}
            sx={{
              '& .MuiToggleButton-root': {
                px: 1.25,
                py: 0.5,
                fontSize: '0.75rem',
                textTransform: 'none',
              },
            }}
          >
            <ToggleButton value="casual">{t('chatModeCasual')}</ToggleButton>
            <ToggleButton value="support">{t('chatModeSupport')}</ToggleButton>
          </ToggleButtonGroup>
        </Box>

        <Box sx={{ flex: 1, overflowY: 'auto', py: 2 }}>
          {messages.length === 0 && (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 2, opacity: 0.4 }}>
              <AutoAwesome sx={{ fontSize: 52, color: 'primary.main' }} />
              <Typography variant="body1" color="text.secondary">{inputPlaceholder}</Typography>
            </Box>
          )}
          {messages.map((m, idx) => {
            const isLast = idx === messages.length - 1;
            const isStreamingActive = streaming && isLast && m.role === 'assistant';
            return <MsgBubble key={m.id} msg={m} convId={activeId!} isStreamingActive={isStreamingActive} />;
          })}
          <div ref={bottomRef} />
        </Box>

        <Box sx={{ p: { xs: 1.5, sm: 2 }, borderTop: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end', maxWidth: 860, mx: 'auto' }}>
            <TextField inputRef={inputRef} multiline maxRows={6} fullWidth size="small"
              placeholder={inputPlaceholder} value={input}
              onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
              disabled={streaming}
              sx={{ '& .MuiOutlinedInput-root': { borderRadius: 3, bgcolor: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.02)' } }} />
            <IconButton
              onClick={() => {
                if (streaming) {
                  streamAbortRef.current?.abort();
                  streamAbortRef.current = null;
                  if (activeId && streamAssistantIdRef.current) {
                    const currentId = streamAssistantIdRef.current;
                    const state = useChatStore.getState();
                    const conv = state.conversations.find((c) => c.id === activeId);
                    const msg = conv?.messages.find((m) => m.id === currentId);
                    if (msg && !msg.content.trim()) {
                      updateMessage(activeId, currentId, { content: '已停止生成。' });
                    }
                  }
                  streamAssistantIdRef.current = null;
                  setStreaming(false);
                  return;
                }
                handleSend();
              }}
              disabled={!streaming && !input.trim()}
              sx={{
                width: 44, height: 44, flexShrink: 0, borderRadius: 2,
                background: (input.trim() || streaming) ? 'linear-gradient(135deg,#e94560,#0f3460)' : undefined,
                color: (input.trim() || streaming) ? '#fff' : undefined,
                '&:hover': { background: 'linear-gradient(135deg,#c73652,#0a2440)' },
                '&.Mui-disabled': { opacity: 0.3 },
                transition: 'all 0.2s',
              }}>
              {streaming ? <Stop fontSize="small" /> : <Send fontSize="small" />}
            </IconButton>
          </Box>
        </Box>
      </Box>

      {/* Confirm clear */}
      <Dialog open={confirmClear} onClose={() => setConfirmClear(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: '1rem' }}>{t('clearHistory')}</DialogTitle>
        <DialogActions>
          <Button onClick={() => setConfirmClear(false)}>{t('cancel')}</Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => {
              clearAll();
              setConfirmClear(false);
              enqueueSnackbar(t('historyCleared'), { variant: 'success' });
            }}
          >
            {t('confirm')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirm delete */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: '1rem' }}>{t('confirmDelete')}</DialogTitle>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>{t('cancel')}</Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => {
              if (deleteTarget) {
                deleteConversation(deleteTarget);
                enqueueSnackbar(t('chatDeleted'), { variant: 'success' });
              }
              setDeleteTarget(null);
            }}
          >
            {t('confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
