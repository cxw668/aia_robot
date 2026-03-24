import { Navigate, Outlet } from 'react-router-dom';
import { useAppStore } from '../../store/useAppStore';

export default function ProtectedRoute() {
  const user = useAppStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}
