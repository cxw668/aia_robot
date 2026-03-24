import { IconButton, Tooltip } from '@mui/material';
import { LightMode, DarkMode } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '../../store/useAppStore';

export default function ThemeToggle() {
  const { t } = useTranslation();
  const { themeMode, toggleTheme } = useAppStore();

  return (
    <Tooltip title={themeMode === 'light' ? t('darkMode') : t('lightMode')}>
      <IconButton onClick={toggleTheme} size="small" color="inherit">
        {themeMode === 'light' ? <DarkMode fontSize="small" /> : <LightMode fontSize="small" />}
      </IconButton>
    </Tooltip>
  );
}
