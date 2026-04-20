import { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  IconButton,
  Divider,
  Collapse,
  useTheme,
  Menu,
  MenuItem,
} from '@mui/material';
import {
  Article,
  Delete,
  ExpandMore,
  ExpandLess,
  CloudUpload,
  MoreVert,
  Category,
} from '@mui/icons-material';
import { CheckCircle, Error as ErrorIcon } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import type { KbDoc } from '../../api/knowledge';
import { STATUS_COLORS } from '../../types/constants';

function formatDocContent(content: unknown): string {
  if (typeof content === 'string') return content;
  if (content == null) return '';
  if (typeof content === 'object') {
    return JSON.stringify(content, null, 2);
  }
  return String(content);
}

export function StatusChip({ status }: { status: string }) {
  const { t } = useTranslation();
  const map: Record<string, string> = {
    pending: t('statusPending'),
    running: t('statusRunning'),
    done: t('statusDone'),
    failed: t('statusFailed'),
  };
  const icon = status === 'done' ? <CheckCircle sx={{ fontSize: 12 }} /> : status === 'failed' ? <ErrorIcon sx={{ fontSize: 12 }} /> : undefined;
  return (
    <Chip
      size="small"
      color={STATUS_COLORS[status] ?? 'default'}
      label={map[status] ?? status}
      icon={icon}
      sx={{ fontWeight: 600, fontSize: '0.72rem' }}
    />
  );
}

export function DocCard({
  doc,
  onDelete,
  onFilterCategory,
  onClearCategory,
}: {
  doc: KbDoc;
  onDelete: (id: string) => void;
  onFilterCategory?: (category: string) => void;
  onClearCategory?: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const contentText = formatDocContent(doc.content);

  return (
    <Paper
      elevation={0}
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 2,
        overflow: 'hidden',
        transition: 'box-shadow 0.2s',
        '&:hover': {
          boxShadow: isDark ? '0 4px 20px rgba(0,0,0,0.4)' : '0 4px 20px rgba(0,0,0,0.08)',
        },
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1, cursor: 'pointer' }} onClick={() => setOpen(!open)}>
        <Article sx={{ fontSize: 18, color: 'primary.main', flexShrink: 0 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" fontWeight={600} noWrap>
            {doc.title || doc.id}
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.75, mt: 0.25, flexWrap: 'wrap' }}>
            {doc.source_file && <Chip onClick={()=>{ window.open('https://www.aia.com.cn' + (doc.source_url ? doc.source_url : doc.service_url))}} size="small" title={doc.source_url ? doc.source_url : doc.service_url } label={doc.source_url ? '前往下载' : '前往服务'} variant="outlined" sx={{ fontSize: '0.63rem', height: 18, '&:hover': { backgroundColor: isDark ? '#fff' : '#f38181' } }} />}
            {doc.category && <Chip size="small" label={doc.category} sx={{ fontSize: '0.63rem', height: 18 }} />}
            {doc.score != null && <Chip size="small" color="secondary" label={`${Math.round(doc.score * 100)}%`} sx={{ fontSize: '0.63rem', height: 18 }} />}
          </Box>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
          {hover && doc.category && (
            <IconButton
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                setMenuAnchor(e.currentTarget);
              }}
              sx={{ opacity: 0.7, '&:hover': { opacity: 1 } }}
            >
              <MoreVert sx={{ fontSize: 16 }} />
            </IconButton>
          )}

          <IconButton
            size="small"
            color="error"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(doc.id);
            }}
            sx={{ opacity: 0.5, '&:hover': { opacity: 1 } }}
          >
            <Delete sx={{ fontSize: 16 }} />
          </IconButton>
          {open ? <ExpandLess sx={{ fontSize: 18, color: 'text.secondary' }} /> : <ExpandMore sx={{ fontSize: 18, color: 'text.secondary' }} />}
        </Box>
      </Box>

      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
        <MenuItem
          onClick={() => {
            if (doc.category && onFilterCategory) onFilterCategory(doc.category);
            setMenuAnchor(null);
          }}
        >
          <Category sx={{ fontSize: 16, mr: 1 }} />
          {t('filterByCategory')}：{doc.category}
        </MenuItem>
        <MenuItem
          onClick={() => {
            onClearCategory?.();
            setMenuAnchor(null);
          }}
        >
          {t('allCategories')}
        </MenuItem>
      </Menu>

      <Collapse in={open}>
        <Divider />
        <Box sx={{ px: 2, py: 1.5, bgcolor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.01)' }}>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, display: 'block', maxHeight: 200, overflowY: 'auto' }}
          >
            {contentText}
          </Typography>
        </Box>
      </Collapse>
    </Paper>
  );
}

export function DropZone({ onFile, disabled }: { onFile: (f: File) => void; disabled?: boolean }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const [dragging, setDragging] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith('.json')) onFile(f);
  };

  return (
    <Box
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      sx={{
        border: 2,
        borderStyle: 'dashed',
        borderColor: dragging ? 'primary.main' : 'divider',
        borderRadius: 2,
        py: 3,
        px: 2,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 1,
        transition: 'all 0.2s',
        opacity: disabled ? 0.5 : 1,
        bgcolor: dragging ? (isDark ? 'rgba(233,69,96,0.08)' : 'rgba(26,26,46,0.04)') : 'transparent',
      }}
    >
      <CloudUpload sx={{ fontSize: 32, color: dragging ? 'primary.main' : 'text.disabled' }} />
      <Typography variant="body2" color="text.secondary">
        {t('uploadHint')}
      </Typography>
      <label>
        <input
          key={inputKey}
          type="file"
          accept=".json"
          disabled={disabled}
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            setInputKey((k) => k + 1);
          }}
        />
        <Chip label={t('uploadFile')} size="small" clickable={!disabled} />
      </label>
    </Box>
  );
}
