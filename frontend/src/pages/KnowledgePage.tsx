import { useCallback, useEffect, useState } from 'react';
import {
  Box, Typography, TextField, Button, Tab, Tabs, Paper, Chip,
  CircularProgress, Divider, IconButton, Tooltip, Dialog,
  DialogTitle, DialogActions, InputAdornment, useTheme,
  Table, TableBody, TableCell, TableHead, TableRow,
} from '@mui/material';
import { Refresh, FolderOpen, Link as LinkIcon, Upload, Search, DeleteForever } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import {
  ingestDir, ingestUrl, uploadFile, getJobs, getDocs,
  deleteDoc, deleteAllDocs, getHealth,
  type IngestJob, type KbDoc,
} from '../api/knowledge';
import { StatusChip, DocCard, DropZone } from '../components/knowledge/KbWidgets';
import SnackbarAlert from '../components/atoms/SnackbarAlert';

const LIMIT = 20;

export default function KnowledgePage() {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const [mainTab, setMainTab] = useState(0);
  const [ingestTab, setIngestTab] = useState(0);
  const [dirPath, setDirPath] = useState('');
  const [url, setUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [health, setHealth] = useState<{status:string;doc_count:number;last_updated:string}|null>(null);
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [searchQ, setSearchQ] = useState('');
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [snack, setSnack] = useState<{open:boolean;msg:string;sev:'success'|'error'}>({open:false,msg:'',sev:'success'});
  const toast = (msg:string,sev:'success'|'error'='success') => setSnack({open:true,msg,sev});

  const fetchHealth = useCallback(async()=>{ try{setHealth(await getHealth());}catch{/***/} },[]);
  const fetchJobs = useCallback(async()=>{
    setLoadingJobs(true);
    try{setJobs(await getJobs());}catch{/***/}finally{setLoadingJobs(false);}
  },[]);
  const fetchDocs = useCallback(async(q:string,off:number,append=false)=>{
    setLoadingDocs(true);
    try{
      const res=await getDocs({q:q||undefined,limit:LIMIT,offset:off});
      setTotal(res.total);
      setDocs(prev=>append?[...prev,...res.docs]:res.docs);
    }catch{/***/}finally{setLoadingDocs(false);}
  },[]);

  useEffect(()=>{
    fetchHealth();fetchJobs();fetchDocs('',0);
    const t=setInterval(()=>{fetchJobs();fetchHealth();},10000);
    return()=>clearInterval(t);
  },[]);

  const handleSearch=()=>{setSearchQ(searchInput);setOffset(0);fetchDocs(searchInput,0);};
  const handleLoadMore=()=>{const nx=offset+LIMIT;setOffset(nx);fetchDocs(searchQ,nx,true);};
  const handleIngestSubmit=async()=>{
    setSubmitting(true);
    try{
      if(ingestTab===0)await ingestDir(dirPath.trim());else await ingestUrl(url.trim());
      toast(t('ingestSuccess'));setDirPath('');setUrl('');
      setTimeout(()=>{fetchJobs();fetchHealth();},1200);
    }catch{toast(t('ingestError'),'error');}finally{setSubmitting(false);}
  };
  const handleUpload=async(file:File)=>{
    setSubmitting(true);
    try{
      await uploadFile(file);toast(t('ingestSuccess'));
      setTimeout(()=>{fetchJobs();fetchHealth();fetchDocs(searchQ,0);},1500);
    }catch{toast(t('ingestError'),'error');}finally{setSubmitting(false);}
  };
  const handleDeleteDoc=async(id:string)=>{
    try{
      await deleteDoc(id);
      setDocs(prev=>prev.filter(d=>d.id!==id));
      setTotal(p=>p-1);fetchHealth();
    }catch{toast(t('ingestError'),'error');}
  };
  const handleClearAll=async()=>{
    setConfirmClear(false);
    try{await deleteAllDocs();setDocs([]);setTotal(0);fetchHealth();toast(t('statusDone'));}
    catch{toast(t('ingestError'),'error');}
  };
  const hasMore=!searchQ&&docs.length<total;

  return (
    <Box sx={{height:'100%',overflowY:'auto',p:{xs:2,sm:3},maxWidth:960,mx:'auto',width:'100%'}}>
      {/* Header */}
      <Box sx={{mb:3,display:'flex',alignItems:'flex-start',justifyContent:'space-between',flexWrap:'wrap',gap:1}}>
        <Box>
          <Typography variant="h5" fontWeight={700} sx={{letterSpacing:'-0.02em'}}>{t('knowledgeTitle')}</Typography>
          {health&&(<Box sx={{display:'flex',gap:1,mt:0.75,flexWrap:'wrap'}}>
            <Chip size="small" label={`${t('totalDocs')}: ${health.doc_count}`} variant="outlined"/>
            <Chip size="small" color={health.status==='ok'?'success':'error'} label={health.status}/>
            <Chip size="small" variant="outlined" label={health.last_updated} sx={{fontSize:'0.65rem'}}/>
          </Box>)}
        </Box>
        <Tooltip title={t('refresh')}>
          <IconButton size="small" onClick={()=>{fetchHealth();fetchJobs();fetchDocs(searchQ,0);}}><Refresh fontSize="small"/></IconButton>
        </Tooltip>
      </Box>
      {/* Main tabs */}
      <Tabs value={mainTab} onChange={(_,v)=>setMainTab(v)} sx={{mb:2}}>
        <Tab label={t('docBrowser')} sx={{fontWeight:600}}/>
        <Tab label={t('ingest')} sx={{fontWeight:600}}/>
      </Tabs>
      {mainTab===0&&(<Box>
        <Box sx={{display:'flex',gap:1,mb:2}}>
          <TextField fullWidth size="small" placeholder={t('searchDocs')}
            value={searchInput} onChange={e=>setSearchInput(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&handleSearch()}
            InputProps={{startAdornment:<InputAdornment position="start"><Search sx={{fontSize:18,color:'text.disabled'}}/></InputAdornment>}}
            sx={{'\u0026 .MuiOutlinedInput-root':{borderRadius:2}}}/>
          <Button variant="contained" onClick={handleSearch} disabled={loadingDocs}
            sx={{flexShrink:0,borderRadius:2,background:'linear-gradient(135deg,#e94560,#0f3460)','\u0026:hover':{background:'linear-gradient(135deg,#c73652,#0a2440)'}}}>
            {loadingDocs?<CircularProgress size={16} color="inherit"/>:<Search fontSize="small"/>}
          </Button>
          <Tooltip title={t('deleteAll')}>
            <IconButton size="small" color="error" onClick={()=>setConfirmClear(true)} sx={{flexShrink:0}}><DeleteForever/></IconButton>
          </Tooltip>
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{mb:1.5,display:'block'}}>{total} {t('totalDocs')}</Typography>
        {docs.length===0&&!loadingDocs&&(<Box sx={{py:6,textAlign:'center',opacity:0.4}}><Typography variant="body2" color="text.secondary">{t('noDocsFound')}</Typography></Box>)}
        <Box sx={{display:'flex',flexDirection:'column',gap:1}}>
          {docs.map(d=><DocCard key={d.id} doc={d} onDelete={handleDeleteDoc}/>)}
        </Box>
        {hasMore&&(<Box sx={{textAlign:'center',mt:2}}>
          <Button variant="outlined" onClick={handleLoadMore} disabled={loadingDocs} sx={{borderRadius:2}}>
            {loadingDocs?<CircularProgress size={16}/>:t('loadMore')}
          </Button>
        </Box>)}
      </Box>)}
      {mainTab===1&&(<Box>
        <Paper elevation={0} sx={{border:1,borderColor:'divider',borderRadius:3,p:3,mb:3}}>
          <Tabs value={ingestTab} onChange={(_,v)=>setIngestTab(v)} sx={{mb:2}}>
            <Tab icon={<FolderOpen fontSize="small"/>} iconPosition="start" label={t('ingestDir')} sx={{fontWeight:600,minHeight:40}}/>
            <Tab icon={<LinkIcon fontSize="small"/>} iconPosition="start" label={t('ingestUrl')} sx={{fontWeight:600,minHeight:40}}/>
            <Tab icon={<Upload fontSize="small"/>} iconPosition="start" label={t('ingestFile')} sx={{fontWeight:600,minHeight:40}}/>
          </Tabs>
          {ingestTab===2?(<DropZone onFile={handleUpload} disabled={submitting}/>):(
            <Box sx={{display:'flex',gap:1.5,alignItems:'center'}}>
              {ingestTab===0
                ?<TextField fullWidth size="small" label={t('dirPath')} value={dirPath} onChange={e=>setDirPath(e.target.value)} placeholder="E:\\aia_data" sx={{'\u0026 .MuiOutlinedInput-root':{borderRadius:2}}}/>
                :<TextField fullWidth size="small" label={t('url')} value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://example.com/data.json" sx={{'\u0026 .MuiOutlinedInput-root':{borderRadius:2}}}/>
              }
              <Button variant="contained"
                startIcon={submitting?<CircularProgress size={14} color="inherit"/>:<Upload/>}
                disabled={submitting||(ingestTab===0?!dirPath.trim():!url.trim())}
                onClick={handleIngestSubmit}
                sx={{flexShrink:0,borderRadius:2,px:3,background:'linear-gradient(135deg,#e94560,#0f3460)','\u0026:hover':{background:'linear-gradient(135deg,#c73652,#0a2440)'},'\u0026.Mui-disabled':{opacity:0.5}}}>
                {t('startIngest')}
              </Button>
            </Box>
          )}
        </Paper>
        <Paper elevation={0} sx={{border:1,borderColor:'divider',borderRadius:3,overflow:'hidden'}}>
          <Box sx={{px:3,py:2,display:'flex',alignItems:'center',justifyContent:'space-between'}}>
            <Typography variant="subtitle1" fontWeight={600}>{t('jobList')}</Typography>
            <Tooltip title={t('refresh')}>
              <IconButton size="small" onClick={fetchJobs} disabled={loadingJobs}>{loadingJobs?<CircularProgress size={16}/>:<Refresh fontSize="small"/>}</IconButton>
            </Tooltip>
          </Box>
          <Divider/>
          {jobs.length===0
            ?<Box sx={{py:5,textAlign:'center'}}><Typography variant="body2" color="text.secondary">{t('noJobs')}</Typography></Box>
            :<Box sx={{overflowX:'auto'}}><Table size="small">
              <TableHead><TableRow sx={{'\u0026 th':{fontWeight:700,fontSize:'0.78rem',color:'text.secondary',bgcolor:isDark?'rgba(255,255,255,0.03)':'rgba(0,0,0,0.02)'}}}>
                <TableCell>{t('jobId')}</TableCell><TableCell>Type</TableCell><TableCell>Source</TableCell>
                <TableCell>{t('status')}</TableCell><TableCell>Docs</TableCell><TableCell>{t('createdAt')}</TableCell>
              </TableRow></TableHead>
              <TableBody>{jobs.map(j=>(
                <TableRow key={j.job_id} sx={{'\u0026:last-child td':{border:0},'\u0026:hover':{bgcolor:isDark?'rgba(255,255,255,0.02)':'rgba(0,0,0,0.01)'}}}>
                  <TableCell sx={{fontFamily:'"JetBrains Mono",monospace',fontSize:'0.75rem'}}>{j.job_id}</TableCell>
                  <TableCell><Chip size="small" label={j.type} variant="outlined" sx={{fontSize:'0.7rem',height:20}}/></TableCell>
                  <TableCell sx={{maxWidth:180,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',fontSize:'0.8rem'}}>{j.source}</TableCell>
                  <TableCell><StatusChip status={j.status}/></TableCell>
                  <TableCell sx={{fontSize:'0.8rem'}}>{j.doc_count}</TableCell>
                  <TableCell sx={{fontSize:'0.78rem',color:'text.secondary'}}>{new Date(j.created_at).toLocaleString()}</TableCell>
                </TableRow>
              ))}</TableBody>
            </Table></Box>
          }
        </Paper>
      </Box>)}
      {/* Confirm clear */}
      <Dialog open={confirmClear} onClose={()=>setConfirmClear(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{fontSize:'1rem'}}>{t('confirmDeleteAll')}</DialogTitle>
        <DialogActions>
          <Button onClick={()=>setConfirmClear(false)}>{t('cancel')}</Button>
          <Button variant="contained" color="error" onClick={handleClearAll}>{t('confirm')}</Button>
        </DialogActions>
      </Dialog>
      <SnackbarAlert open={snack.open} message={snack.msg} severity={snack.sev} onClose={()=>setSnack(s=>({...s,open:false}))}/>
    </Box>
  );
}
