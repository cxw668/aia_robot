import { createTheme, type Theme } from '@mui/material/styles';
import type { ThemeMode } from '../store/useAppStore';

const FONT = '"DM Sans", "PingFang SC", "Microsoft YaHei", sans-serif';
const MONO = '"JetBrains Mono", "Fira Code", monospace';

export { MONO };

const palette = {
  light: {
    primary: { main: '#1a1a2e', light: '#16213e', dark: '#0f3460' },
    secondary: { main: '#e94560' },
    background: { default: '#f7f7f8', paper: '#ffffff' },
    text: { primary: '#111827', secondary: '#6b7280' },
    divider: 'rgba(0,0,0,0.08)',
  },
  dark: {
    primary: { main: '#e94560', light: '#ff6b81', dark: '#c0392b' },
    secondary: { main: '#0f3460' },
    background: { default: '#0d0d14', paper: '#16161f' },
    text: { primary: '#f1f1f5', secondary: '#9ca3af' },
    divider: 'rgba(255,255,255,0.08)',
  },
};

export function buildTheme(mode: ThemeMode): Theme {
  const p = palette[mode];
  return createTheme({
    palette: {
      mode,
      primary: p.primary,
      secondary: p.secondary,
      background: p.background,
      text: p.text,
      divider: p.divider,
    },
    typography: {
      fontFamily: FONT,
      h1: { fontWeight: 700, letterSpacing: '-0.02em' },
      h2: { fontWeight: 700, letterSpacing: '-0.01em' },
      h3: { fontWeight: 600 },
      h4: { fontWeight: 600 },
      h5: { fontWeight: 600 },
      h6: { fontWeight: 600 },
      body1: { lineHeight: 1.7 },
      body2: { lineHeight: 1.6 },
    },
    shape: { borderRadius: 12 },
    components: {
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            textTransform: 'none',
            fontWeight: 600,
            letterSpacing: '0.01em',
          },
        },
      },
      MuiTextField: {
        defaultProps: { variant: 'outlined' },
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: 10,
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { fontWeight: 500 },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: { borderRadius: 10 },
        },
      },
    },
  });
}
