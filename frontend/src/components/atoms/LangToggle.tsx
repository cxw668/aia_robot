import { Button, Tooltip } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '../../store/useAppStore';
import i18n from '../../i18n';

export default function LangToggle() {
  const { t } = useTranslation();
  const { lang, setLang } = useAppStore();

  const toggle = () => {
    const next = lang === 'zh' ? 'en' : 'zh';
    setLang(next);
    i18n.changeLanguage(next);
    localStorage.setItem('lang', next);
  };

  return (
    <Tooltip title={lang === 'zh' ? t('langEn') : t('langZh')}>
      <Button
        onClick={toggle}
        size="small"
        color="inherit"
        sx={{ minWidth: 0, fontWeight: 600, fontSize: '0.75rem', px: 1 }}
      >
        {lang === 'zh' ? 'EN' : '中'}
      </Button>
    </Tooltip>
  );
}
