import { useRef, useState } from 'react';
import {
  Box, Typography, Paper, Chip, IconButton, Divider, Collapse, useTheme,
} from '@mui/material';
import { Article, Delete, ExpandMore, ExpandLess, CloudUpload } from '@mui/icons-material';
import { CheckCircle, Error as ErrorIcon } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import type { KbDoc } from '../../api/knowledge';
import {STATUS_COLORS} from '../../types/constants'
export function StatusChip({ status }: { status: string }) {
  const { t } = useTranslation();
  const map: Record<string,string> = {
    pending:t('statusPending'), running:t('statusRunning'),
    done:t('statusDone'), failed:t('statusFailed'),
  };
  const icon = status==='done' ? <CheckCircle sx={{fontSize:12}}/>
    : status==='failed' ? <ErrorIcon sx={{fontSize:12}}/> : undefined;
  return <Chip size="small" color={STATUS_COLORS[status]??'default'}
    label={map[status]??status} icon={icon}
    sx={{fontWeight:600,fontSize:'0.72rem'}}/>;
}

export function DocCard({ doc, onDelete }: { doc: KbDoc; onDelete:(id:string)=>void }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const [open, setOpen] = useState(false);
  return (
    <Paper elevation={0} sx={{
      border:1, borderColor:'divider', borderRadius:2, overflow:'hidden',
      transition:'box-shadow 0.2s',
      '&:hover':{boxShadow: isDark?'0 4px 20px rgba(0,0,0,0.4)':'0 4px 20px rgba(0,0,0,0.08)'},
    }}>
      <Box sx={{px:2,py:1.5,display:'flex',alignItems:'center',gap:1,cursor:'pointer'}}
        onClick={()=>setOpen(!open)}>
        <Article sx={{fontSize:18,color:'primary.main',flexShrink:0}}/>
        <Box sx={{flex:1,minWidth:0}}>
          <Typography variant="body2" fontWeight={600} noWrap>{doc.title||doc.id}</Typography>
          <Box sx={{display:'flex',gap:0.75,mt:0.25,flexWrap:'wrap'}}>
            {doc.source_file && <Chip size="small" label={doc.source_file} variant="outlined" sx={{fontSize:'0.63rem',height:18}}/>}
            {doc.category && doc.category!==doc.source_file && <Chip size="small" label={doc.category} sx={{fontSize:'0.63rem',height:18}}/>}
            {doc.score!=null && <Chip size="small" color="secondary" label={`${Math.round(doc.score*100)}%`} sx={{fontSize:'0.63rem',height:18}}/>}
          </Box>
        </Box>
        <Box sx={{display:'flex',alignItems:'center',gap:0.5,flexShrink:0}}>
          <IconButton size="small" color="error" onClick={(e)=>{e.stopPropagation();onDelete(doc.id);}}
            sx={{opacity:0.5,'&:hover':{opacity:1}}}>
            <Delete sx={{fontSize:16}}/>
          </IconButton>
          {open?<ExpandLess sx={{fontSize:18,color:'text.secondary'}}/>:<ExpandMore sx={{fontSize:18,color:'text.secondary'}}/>}
        </Box>
      </Box>
      <Collapse in={open}>
        <Divider/>
        <Box sx={{px:2,py:1.5,bgcolor:isDark?'rgba(255,255,255,0.02)':'rgba(0,0,0,0.01)'}}>
          <Typography variant="caption" color="text.secondary"
            sx={{whiteSpace:'pre-wrap',lineHeight:1.8,display:'block',maxHeight:200,overflowY:'auto'}}>
            {doc.content}
          </Typography>
        </Box>
      </Collapse>
    </Paper>
  );
}

export function DropZone({ onFile, disabled }: { onFile:(f:File)=>void; disabled?:boolean }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith('.json')) onFile(f);
  };
  return (
    <Box
      onDragOver={(e)=>{e.preventDefault();setDragging(true);}}
      onDragLeave={()=>setDragging(false)}
      onDrop={handleDrop}
      onClick={()=>!disabled&&inputRef.current?.click()}
      sx={{
        border:2, borderStyle:'dashed',
        borderColor:dragging?'primary.main':'divider',
        borderRadius:2, py:3, px:2,
        display:'flex', flexDirection:'column', alignItems:'center', gap:1,
        cursor:disabled?'not-allowed':'pointer', transition:'all 0.2s',
        opacity:disabled?0.5:1,
        bgcolor:dragging?(isDark?'rgba(233,69,96,0.08)':'rgba(26,26,46,0.04)'):'transparent',
        '&:hover':!disabled?{borderColor:'primary.main',bgcolor:isDark?'rgba(255,255,255,0.03)':'rgba(0,0,0,0.02)'}:{},
      }}>
      <CloudUpload sx={{fontSize:32,color:dragging?'primary.main':'text.disabled'}}/>
      <Typography variant="body2" color="text.secondary">{t('uploadHint')}</Typography>
      <input ref={inputRef} type="file" accept=".json" disabled={disabled} style={{display:'none'}}
        onChange={(e)=>{const f=e.target.files?.[0];if(f)onFile(f);e.target.value='';}} />
    </Box>
  );
}
