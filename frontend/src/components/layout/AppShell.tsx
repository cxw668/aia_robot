import { useState } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Divider,
  useMediaQuery,
  useTheme,
  Tooltip,
  Avatar,
  Typography,
} from '@mui/material';
import {
  Chat as ChatIcon,
  MenuBook,
  Menu as MenuIcon,
  Close,
  Logout,
} from '@mui/icons-material';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '../../store/useAppStore';
import Logo from '../atoms/Logo';
import ThemeToggle from '../atoms/ThemeToggle';
import LangToggle from '../atoms/LangToggle';

const DRAWER_WIDTH = 220;
const RAIL_WIDTH = 64;

export default function AppShell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, logout } = useAppStore();

  const navItems = [
    { label: t('chat'), icon: <ChatIcon />, path: '/chat' },
    { label: t('knowledge'), icon: <MenuBook />, path: '/knowledge' },
  ];

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const drawerContent = (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        py: 2,
        px: isMobile ? 1 : 0,
      }}
    >
      {/* Logo */}
      <Box sx={{ px: 2, pb: 2 }}>
        <Logo size="sm" showText={isMobile} />
      </Box>
      <Divider sx={{ mb: 1 }} />

      {/* Nav */}
      <List sx={{ flex: 1, px: 0.5 }}>
        {navItems.map((item) => {
          const active = location.pathname.startsWith(item.path);
          return (
            <ListItem key={item.path} disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                selected={active}
                onClick={() => {
                  navigate(item.path);
                  if (isMobile) setMobileOpen(false);
                }}
                sx={{
                  borderRadius: 2,
                  minHeight: 44,
                  justifyContent: isMobile ? 'initial' : 'center',
                  px: isMobile ? 2 : 1.5,
                  '&.Mui-selected': {
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                    '&:hover': { bgcolor: 'primary.dark' },
                  },
                }}
              >
                <ListItemIcon
                  sx={{
                    minWidth: 0,
                    mr: isMobile ? 2 : 'auto',
                    justifyContent: 'center',
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                {isMobile && <ListItemText primary={item.label} />}
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>

      <Divider sx={{ mb: 1 }} />

      {/* Bottom controls */}
      <Box
        sx={{
          px: 1,
          display: 'flex',
          flexDirection: isMobile ? 'row' : 'column',
          alignItems: 'center',
          gap: 0.5,
        }}
      >
        <LangToggle />
        <ThemeToggle />
        <Tooltip title={t('logout')}>
          <IconButton size="small" onClick={handleLogout} color="inherit">
            <Logout fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {isMobile && user && (
        <Box sx={{ px: 2, pt: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Avatar sx={{ width: 28, height: 28, bgcolor: 'primary.main', fontSize: 12 }}>
            {user.username[0]?.toUpperCase()}
          </Avatar>
          <Typography variant="caption" color="text.secondary">
            {user.username}
          </Typography>
        </Box>
      )}
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', height: '100dvh', overflow: 'hidden' }}>
      {/* Mobile top bar */}
      {isMobile && (
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            height: 56,
            zIndex: 1200,
            bgcolor: 'background.paper',
            borderBottom: 1,
            borderColor: 'divider',
            display: 'flex',
            alignItems: 'center',
            px: 2,
            gap: 1,
          }}
        >
          <IconButton onClick={() => setMobileOpen(true)} size="small">
            <MenuIcon />
          </IconButton>
          <Logo size="sm" />
        </Box>
      )}

      {/* Sidebar */}
      {isMobile ? (
        <Drawer
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          PaperProps={{ sx: { width: DRAWER_WIDTH } }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', p: 1 }}>
            <IconButton onClick={() => setMobileOpen(false)} size="small">
              <Close />
            </IconButton>
          </Box>
          {drawerContent}
        </Drawer>
      ) : (
        <Box
          sx={{
            width: RAIL_WIDTH,
            flexShrink: 0,
            borderRight: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {drawerContent}
        </Box>
      )}

      {/* Main content */}
      <Box
        component="main"
        sx={{
          flex: 1,
          overflow: 'hidden',
          mt: isMobile ? '56px' : 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Outlet />
      </Box>
    </Box>
  );
}
