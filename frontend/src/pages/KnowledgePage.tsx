import { useCallback, useEffect, useState } from 'react';
import {
  Box, Typography, TextField, Button, Tab, Tabs, Paper, Chip,
  CircularProgress, Divider, IconButton, Tooltip, Dialog,
  DialogTitle, DialogActions, InputAdornment, useTheme,
  Table, TableBody, TableCell, TableHead, TableRow,
} from '@mui/material';
import { Refresh, FolderOpen, Link as LinkIcon, Upload, Search, Delete, Inventory2 } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import {
  ingestDir, ingestUrl, uploadFile, getJobs, getDocs, getCollections,
  deleteDoc, deleteCollection, getHealth,
  type IngestJob, type KbDoc, type KbCollection,
} from '../api/knowledge';
import { StatusChip, DocCard, DropZone } from '../components/knowledge/KbWidgets';
import SnackbarAlert from '../components/atoms/SnackbarAlert';

const LIMIT = 10;
const TARGET_COLLECTION = 'aia_knowledge_base';

export default function KnowledgePage() {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const [mainTab, setMainTab] = useState(0);
  const [ingestTab, setIngestTab] = useState(0);
  const [dirPath, setDirPath] = useState('');
  const [url, setUrl] = useState('');
  const ingestCollection = TARGET_COLLECTION;
  const [submitting, setSubmitting] = useState(false);
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [collections, setCollections] = useState<KbCollection[]>([]);
  const [activeCollection, setActiveCollection] = useState<string>(TARGET_COLLECTION);
  const [deleteColTarget, setDeleteColTarget] = useState<string | null>(null);
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [searchQ, setSearchQ] = useState('');
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [health, setHealth] = useState<{ status: string; doc_count: number } | null>(null);
  const [snack, setSnack] = useState<{ open: boolean; msg: string; sev: 'success' | 'error' }>({ open: false, msg: '', sev: 'success' });
  const toast = (msg: string, sev: 'success' | 'error' = 'success') => setSnack({ open: true, msg, sev });

  const fetchHealth = useCallback(async (col: string) => {
    try { setHealth(await getHealth(col)); } catch {/**/}
  }, []);
  const fetchJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      const allJobs = await getJobs();
      setJobs(allJobs.filter((job) => job.collection === TARGET_COLLECTION));
    } catch {/**/} finally { setLoadingJobs(false); }
  }, []);
  const fetchCollections = useCallback(async () => {
    try {
      const allCollections = await getCollections();
      setCollections(allCollections.filter((col) => col.name === TARGET_COLLECTION));
    } catch {/**/}
  }, []);
  const fetchDocs = useCallback(async (q: string, col: string | null, off: number, append = false) => {
    if (!col) { setDocs([]); setTotal(0); return; }
    setLoadingDocs(true);
    try {
      const res = await getDocs({ collection: col, q: q || undefined, limit: LIMIT, offset: off });
      setTotal(res.total);
      setDocs(prev => append ? [...prev, ...res.docs] : res.docs);
    } catch {/**/} finally { setLoadingDocs(false); }
  }, []);

  useEffect(() => {
    fetchCollections(); fetchJobs();
    const timer = setInterval(() => { fetchJobs(); fetchCollections(); }, 10000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (activeCollection) { fetchDocs(searchQ, activeCollection, 0); fetchHealth(activeCollection); }
    else { setDocs([]); setTotal(0); setHealth(null); }
  }, [activeCollection]);

  const handleCollectionSelect = (name: string) => { setActiveCollection(name); setSearchQ(''); setSearchInput(''); setOffset(0); };
  const handleSearch = () => { setSearchQ(searchInput); setOffset(0); fetchDocs(searchInput, activeCollection, 0); };
  const handleLoadMore = () => { const nx = offset + LIMIT; setOffset(nx); fetchDocs(searchQ, activeCollection, nx, true); };
  const handleIngestSubmit = async () => {
    setSubmitting(true);
    try {
      if (ingestTab === 0) await ingestDir(dirPath.trim(), ingestCollection);
      else await ingestUrl(url.trim(), ingestCollection);
      toast(t('ingestSuccess')); setDirPath(''); setUrl('');
      setTimeout(() => { fetchJobs(); fetchCollections(); }, 1200);
    } catch { toast(t('ingestError'), 'error'); } finally { setSubmitting(false); }
  };
  const handleUpload = async (file: File) => {
    setSubmitting(true);
    try {
      await uploadFile(file, ingestCollection); toast(t('ingestSuccess'));
      setTimeout(() => { fetchJobs(); fetchCollections(); fetchDocs(searchQ, activeCollection, 0); }, 1500);
    } catch { toast(t('ingestError'), 'error'); } finally { setSubmitting(false); }
  };
  const handleDeleteDoc = async (id: string) => {
    if (!activeCollection) return;
    try { await deleteDoc(id, activeCollection); setDocs(prev => prev.filter(d => d.id !== id)); setTotal(p => p - 1); fetchCollections(); }
    catch { toast(t('ingestError'), 'error'); }
  };
  const handleDeleteCollection = async () => {
    if (!deleteColTarget) return;
    try {
      await deleteCollection(deleteColTarget); toast(t('statusDone'));
      if (activeCollection === deleteColTarget) { setDocs([]); setTotal(0); setHealth(null); }
      await fetchCollections();
    } catch { toast(t('ingestError'), 'error'); }
    setDeleteColTarget(null);
  };

  const hasMore = docs.length < total;
  const totalAllDocs = collections.reduce((s, c) => s + c.doc_count, 0);

  return (
    <Box sx={{ height: '100%', overflowY: 'auto', p: { xs: 2, sm: 3 }, maxWidth: 960, mx: 'auto', width: '100%' }}>
      <Box sx={{ mb: 3, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          <Box>
            <Typography variant="h5" fontWeight={700} sx={{ letterSpacing: '-0.02em' }}>{t('knowledgeTitle')}</Typography>
            <Box sx={{ display: 'flex', gap: 1, mt: 0.75, flexWrap: 'wrap' }}>
              <Chip size="small" label={TARGET_COLLECTION} color="primary" variant="outlined" />
              <Chip size="small" label={`${t('totalDocs')}: ${totalAllDocs}`} variant="outlined" />
              {health && activeCollection && (
                <Chip size="small" color={health.status === 'ok' ? 'success' : 'error'} label={`${activeCollection}: ${health.doc_count} docs`} />
              )}
          </Box>
        </Box>
        <Tooltip title={t('refresh')}>
          <IconButton size="small" onClick={() => { fetchCollections(); fetchJobs(); if (activeCollection) fetchDocs(searchQ, activeCollection, 0); }}>
            <Refresh fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      <Tabs value={mainTab} onChange={(_, v) => setMainTab(v)} sx={{ mb: 2 }}>
        <Tab label={t('docBrowser')} sx={{ fontWeight: 600 }} />
        <Tab label={t('ingest')} sx={{ fontWeight: 600 }} />
      </Tabs>

      {mainTab === 0 && (
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
          <Paper elevation={0} sx={{ width: 200, flexShrink: 0, border: 1, borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
            <Box sx={{ px: 2, py: 1.5, bgcolor: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)', borderBottom: 1, borderColor: 'divider', display: 'flex', alignItems: 'center', gap: 1 }}>
              <Inventory2 sx={{ fontSize: 15, color: 'text.secondary' }} />
              <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('collections')}
              </Typography>
            </Box>
            {collections.length === 0 ? (
              <Box sx={{ py: 4, textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">{t('noDocsFound')}</Typography>
              </Box>
            ) : collections.map(col => (
              <Box
                key={col.name}
                onClick={() => handleCollectionSelect(col.name)}
                sx={{
                  px: 2, py: 1, cursor: 'pointer', display: 'flex', alignItems: 'center',
                  justifyContent: 'space-between', gap: 0.5,
                  bgcolor: activeCollection === col.name
                    ? (isDark ? 'rgba(233,69,96,0.15)' : 'rgba(26,26,46,0.07)') : 'transparent',
                  borderLeft: 3,
                  borderLeftColor: activeCollection === col.name ? 'primary.main' : 'transparent',
                  '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)' },
                  transition: 'all 0.15s',
                }}
              >
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography variant="body2" fontWeight={activeCollection === col.name ? 700 : 400} noWrap sx={{ fontSize: '0.82rem' }}>
                    {col.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">{col.doc_count} docs</Typography>
                </Box>
                <IconButton size="small" color="error"
                  onClick={e => { e.stopPropagation(); setDeleteColTarget(col.name); }}
                  sx={{ opacity: 0.35, '&:hover': { opacity: 1 }, p: 0.25, flexShrink: 0 }}
                >
                  <Delete sx={{ fontSize: 14 }} />
                </IconButton>
              </Box>
            ))}
          </Paper>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <>
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <TextField fullWidth size="small" placeholder={t('searchDocs')}
                  value={searchInput} onChange={e => setSearchInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  InputProps={{ startAdornment: <InputAdornment position="start"><Search sx={{ fontSize: 18, color: 'text.disabled' }} /></InputAdornment> }}
                  sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }}
                />
                <Button variant="contained" onClick={handleSearch} disabled={loadingDocs}
                  sx={{ flexShrink: 0, borderRadius: 2, background: 'linear-gradient(135deg,#e94560,#0f3460)', '&:hover': { background: 'linear-gradient(135deg,#c73652,#0a2440)' } }}>
                  {loadingDocs ? <CircularProgress size={16} color="inherit" /> : <Search fontSize="small" />}
                </Button>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 1.5, display: 'block' }}>
                {total} {t('totalDocs')} &middot; {activeCollection}
              </Typography>
              {docs.length === 0 && !loadingDocs && (
                <Box sx={{ py: 6, textAlign: 'center', opacity: 0.4 }}>
                  <Typography variant="body2" color="text.secondary">{t('noDocsFound')}</Typography>
                </Box>
              )}
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {docs.map(d => <DocCard key={d.id} doc={d} onDelete={handleDeleteDoc} />)}
              </Box>
              {hasMore && (
                <Box sx={{ textAlign: 'center', mt: 2 }}>
                  <Button variant="outlined" onClick={handleLoadMore} disabled={loadingDocs} sx={{ borderRadius: 2 }}>
                    {loadingDocs ? <CircularProgress size={16} /> : t('loadMore')}
                  </Button>
                </Box>
              )}
            </>
          </Box>
        </Box>
      )}

      {mainTab === 1 && (
        <Box>
          <Paper elevation={0} sx={{ border: 1, borderColor: 'divider', borderRadius: 3, p: 3, mb: 3 }}>
            <Box sx={{ mb: 2.5 }}>
              <Typography variant="subtitle2" fontWeight={700} gutterBottom>{t('collectionName')}</Typography>
              <TextField
                fullWidth size="small"
                placeholder={t('collectionNamePlaceholder')}
                helperText={TARGET_COLLECTION}
                value={ingestCollection}
                disabled
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }}
              />
            </Box>
            <Divider sx={{ mb: 2 }} />
            <Tabs value={ingestTab} onChange={(_, v) => setIngestTab(v)} sx={{ mb: 2 }}>
              <Tab icon={<FolderOpen fontSize="small" />} iconPosition="start" label={t('ingestDir')} sx={{ fontWeight: 600, minHeight: 40 }} />
              <Tab icon={<LinkIcon fontSize="small" />} iconPosition="start" label={t('ingestUrl')} sx={{ fontWeight: 600, minHeight: 40 }} />
              <Tab icon={<Upload fontSize="small" />} iconPosition="start" label={t('ingestFile')} sx={{ fontWeight: 600, minHeight: 40 }} />
            </Tabs>
            {ingestTab === 2 ? (
              <DropZone onFile={handleUpload} disabled={submitting} />
            ) : (
              <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
                {ingestTab === 0
                  ? <TextField fullWidth size="small" label={t('dirPath')} value={dirPath} onChange={e => setDirPath(e.target.value)} placeholder="E:\aia_data" sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }} />
                  : <TextField fullWidth size="small" label={t('url')} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://example.com/data.json" sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }} />
                }
                <Button variant="contained"
                  startIcon={submitting ? <CircularProgress size={14} color="inherit" /> : <Upload />}
                  disabled={submitting || (ingestTab === 0 ? !dirPath.trim() : !url.trim())}
                  onClick={handleIngestSubmit}
                  sx={{ flexShrink: 0, borderRadius: 2, px: 3, color: '#fff !important', background: 'linear-gradient(135deg,#e94560,#0f3460)', '&:hover': { background: 'linear-gradient(135deg,#c73652,#0a2440)' }, '&.Mui-disabled': { opacity: 0.5 } }}>
                  {t('startIngest')}
                </Button>
              </Box>
            )}
          </Paper>

          <Paper elevation={0} sx={{ border: 1, borderColor: 'divider', borderRadius: 3, overflow: 'hidden' }}>
            <Box sx={{ px: 3, py: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="subtitle1" fontWeight={600}>{t('jobList')}</Typography>
              <Tooltip title={t('refresh')}>
                <IconButton size="small" onClick={fetchJobs} disabled={loadingJobs}>
                  {loadingJobs ? <CircularProgress size={16} /> : <Refresh fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
            <Divider />
            {jobs.length === 0
              ? <Box sx={{ py: 5, textAlign: 'center' }}><Typography variant="body2" color="text.secondary">{t('noJobs')}</Typography></Box>
              : <Box sx={{ overflowX: 'auto' }}><Table size="small">
                <TableHead><TableRow sx={{ '& th': { fontWeight: 700, fontSize: '0.78rem', color: 'text.secondary', bgcolor: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)' } }}>
                  <TableCell>{t('jobId')}</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>{t('collections')}</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell>{t('status')}</TableCell>
                  <TableCell>Docs</TableCell>
                  <TableCell>{t('createdAt')}</TableCell>
                </TableRow></TableHead>
                <TableBody>{jobs.map(j => (
                  <TableRow key={j.job_id} sx={{ '&:last-child td': { border: 0 }, '&:hover': { bgcolor: isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.01)' } }}>
                    <TableCell sx={{ fontFamily: '"JetBrains Mono",monospace', fontSize: '0.75rem' }}>{j.job_id}</TableCell>
                    <TableCell><Chip size="small" label={j.type} variant="outlined" sx={{ fontSize: '0.7rem', height: 20 }} /></TableCell>
                    <TableCell><Chip size="small" label={j.collection} color="primary" variant="outlined" sx={{ fontSize: '0.7rem', height: 20 }} /></TableCell>
                    <TableCell sx={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.8rem' }}>{j.source}</TableCell>
                    <TableCell><StatusChip status={j.status} /></TableCell>
                    <TableCell sx={{ fontSize: '0.8rem' }}>{j.doc_count}</TableCell>
                    <TableCell sx={{ fontSize: '0.78rem', color: 'text.secondary' }}>{new Date(j.created_at).toLocaleString()}</TableCell>
                  </TableRow>
                ))}</TableBody>
              </Table></Box>
            }
          </Paper>
        </Box>
      )}

      <Dialog open={!!deleteColTarget} onClose={() => setDeleteColTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: '1rem' }}>{t('deleteCollection')}</DialogTitle>
        <DialogActions>
          <Button onClick={() => setDeleteColTarget(null)}>{t('cancel')}</Button>
          <Button variant="contained" color="error" onClick={handleDeleteCollection}>{t('confirm')}</Button>
        </DialogActions>
      </Dialog>

      <SnackbarAlert open={snack.open} message={snack.msg} severity={snack.sev} onClose={() => setSnack(s => ({ ...s, open: false }))} />
    </Box>
  );
}
