import { useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { useAppStore } from './store/useAppStore';
import { buildTheme } from './theme';
import { SnackbarProvider } from 'notistack';
import AppShell from './components/layout/AppShell';
import ProtectedRoute from './components/layout/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import KnowledgePage from './pages/KnowledgePage';

export default function App() {
  const themeMode = useAppStore((s) => s.themeMode);
  const theme = useMemo(() => buildTheme(themeMode), [themeMode]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <SnackbarProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="*" element={<Navigate to="/chat" replace />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </SnackbarProvider>
    </ThemeProvider>
  );
}
