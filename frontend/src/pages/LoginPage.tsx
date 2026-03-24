import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  TextField,
  Button,
  Typography,
  Tab,
  Tabs,
  InputAdornment,
  IconButton,
  CircularProgress,
  Divider,
  useTheme,
} from '@mui/material';
import { Visibility, VisibilityOff } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { login, register } from '../api/auth';
import { useAppStore } from '../store/useAppStore';
import Logo from '../components/atoms/Logo';
import ThemeToggle from '../components/atoms/ThemeToggle';
import LangToggle from '../components/atoms/LangToggle';
import SnackbarAlert from '../components/atoms/SnackbarAlert';

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const theme = useTheme();
  const setUser = useAppStore((s) => s.setUser);
  const isDark = theme.palette.mode === 'dark';

  const [tab, setTab] = useState(0);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [snack, setSnack] = useState<{ open: boolean; msg: string; sev: 'success' | 'error' }>({
    open: false,
    msg: '',
    sev: 'success',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const e: Record<string, string> = {};
    if (!username.trim()) e.username = t('fieldRequired');
    if (!password.trim()) e.password = t('fieldRequired');
    if (tab === 1 && password !== confirmPwd) e.confirmPwd = t('passwordMismatch');
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setLoading(true);
    try {
      const data =
        tab === 0
          ? await login({ username, password })
          : await register({ username, password });
      setUser({ username: data.username, token: data.token });
      setSnack({ open: true, msg: tab === 0 ? t('loginSuccess') : t('registerSuccess'), sev: 'success' });
      setTimeout(() => navigate('/chat'), 800);
    } catch {
      setSnack({ open: true, msg: t('loginError'), sev: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: isDark
          ? 'radial-gradient(ellipse at 20% 80%, #0f3460 0%, #0d0d14 60%)'
          : 'radial-gradient(ellipse at 20% 80%, #e8eaf6 0%, #f7f7f8 60%)',
        p: 2,
        position: 'relative',
      }}
    >
      {/* Top-right controls */}
      <Box sx={{ position: 'absolute', top: 16, right: 16, display: 'flex', gap: 0.5 }}>
        <LangToggle />
        <ThemeToggle />
      </Box>

      {/* Decorative blobs */}
      <Box
        sx={{
          position: 'absolute',
          width: 320,
          height: 320,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(233,69,96,0.15) 0%, transparent 70%)',
          top: '10%',
          right: '15%',
          pointerEvents: 'none',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          width: 200,
          height: 200,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(15,52,96,0.2) 0%, transparent 70%)',
          bottom: '15%',
          left: '10%',
          pointerEvents: 'none',
        }}
      />

      <Card
        elevation={0}
        sx={{
          width: '100%',
          maxWidth: 400,
          p: { xs: 3, sm: 4 },
          border: 1,
          borderColor: 'divider',
          borderRadius: 3,
          backdropFilter: 'blur(12px)',
          background: isDark ? 'rgba(22,22,31,0.9)' : 'rgba(255,255,255,0.92)',
          boxShadow: isDark
            ? '0 24px 64px rgba(0,0,0,0.4)'
            : '0 24px 64px rgba(0,0,0,0.08)',
        }}
      >
        <Box sx={{ mb: 3 }}>
          <Logo size="md" />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {tab === 0 ? t('switchToRegister') : t('switchToLogin')}
          </Typography>
        </Box>

        <Tabs
          value={tab}
          onChange={(_, v) => { setTab(v); setErrors({}); }}
          sx={{ mb: 3 }}
          variant="fullWidth"
        >
          <Tab label={t('login')} sx={{ fontWeight: 600 }} />
          <Tab label={t('register')} sx={{ fontWeight: 600 }} />
        </Tabs>

        <Box component="form" sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}
          onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}
        >
          <TextField
            label={t('username')}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            error={!!errors.username}
            helperText={errors.username}
            fullWidth
            autoComplete="username"
            size="small"
          />
          <TextField
            label={t('password')}
            type={showPwd ? 'text' : 'password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={!!errors.password}
            helperText={errors.password}
            fullWidth
            autoComplete={tab === 0 ? 'current-password' : 'new-password'}
            size="small"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => setShowPwd(!showPwd)} edge="end">
                    {showPwd ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          {tab === 1 && (
            <TextField
              label={t('confirmPassword')}
              type={showPwd ? 'text' : 'password'}
              value={confirmPwd}
              onChange={(e) => setConfirmPwd(e.target.value)}
              error={!!errors.confirmPwd}
              helperText={errors.confirmPwd}
              fullWidth
              autoComplete="new-password"
              size="small"
            />
          )}

          <Button
            type="submit"
            variant="contained"
            fullWidth
            size="large"
            disabled={loading}
            sx={{
              mt: 1,
              py: 1.2,
              background: 'linear-gradient(135deg, #e94560 0%, #0f3460 100%)',
              '&:hover': {
                background: 'linear-gradient(135deg, #c73652 0%, #0a2440 100%)',
              },
            }}
          >
            {loading ? (
              <CircularProgress size={20} color="inherit" />
            ) : tab === 0 ? (
              t('loginBtn')
            ) : (
              t('registerBtn')
            )}
          </Button>
        </Box>

        <Divider sx={{ my: 2 }} />
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center' }}>
          Demo: admin / admin123
        </Typography>
      </Card>

      <SnackbarAlert
        open={snack.open}
        message={snack.msg}
        severity={snack.sev}
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
      />
    </Box>
  );
}
