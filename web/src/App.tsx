import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth";
import { useNativePlatform } from "./hooks/useNativePlatform";

import AppLayout from "./components/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import ScannerPage from "./pages/ScannerPage";
import ChartsPage from "./pages/ChartsPage";
import RealTradesPage from "./pages/RealTradesPage";
import SettingsPage from "./pages/SettingsPage";
import AlertsPage from "./pages/AlertsPage";
import WatchlistPage from "./pages/WatchlistPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** Rehydrate persisted auth on app boot (native + web). */
function AuthGate({ children }: { children: React.ReactNode }) {
  const hydrated = useAuthStore((s) => s.hydrated);
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  if (!hydrated) {
    return null;
  }

  return <>{children}</>;
}

export default function App() {
  useNativePlatform();

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthGate>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />

              {/* Protected routes with sidebar layout */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
                <Route path="scanner" element={<ErrorBoundary><ScannerPage /></ErrorBoundary>} />
                <Route path="watchlist" element={<ErrorBoundary><WatchlistPage /></ErrorBoundary>} />
                <Route path="charts" element={<ErrorBoundary><ChartsPage /></ErrorBoundary>} />
                <Route path="trades" element={<ErrorBoundary><RealTradesPage /></ErrorBoundary>} />
                <Route path="alerts" element={<ErrorBoundary><AlertsPage /></ErrorBoundary>} />
                <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthGate>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
