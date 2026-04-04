import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth";
import { useNativePlatform } from "./hooks/useNativePlatform";

import AppLayout from "./components/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import LandingPage from "./pages/LandingPage";
import LearnPage from "./pages/LearnPage";
import LearnDetailPage from "./pages/LearnDetailPage";
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import TradingPage from "./pages/TradingPage";
import RealTradesPage from "./pages/RealTradesPage";
import SettingsPage from "./pages/SettingsPage";
import { ToastContainer } from "./components/Toast";
import BillingPage from "./pages/BillingPage";

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
  if (!user) return <Navigate to="/" replace />;
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
        <ToastContainer />
        <AuthGate>
          <BrowserRouter>
            <Routes>
              {/* Public routes */}
              <Route path="/" element={<LandingPage />} />
              <Route path="/learn" element={<LearnPage />} />
              <Route path="/learn/:categoryId" element={<LearnDetailPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/onboarding" element={<ProtectedRoute><OnboardingPage /></ProtectedRoute>} />

              {/* Protected routes with sidebar layout */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="dashboard" element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
                <Route path="trading" element={<ErrorBoundary><TradingPage /></ErrorBoundary>} />
                <Route path="trades" element={<ErrorBoundary><RealTradesPage /></ErrorBoundary>} />
                <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
                <Route path="billing" element={<ErrorBoundary><BillingPage /></ErrorBoundary>} />

                {/* Legacy redirects */}
                <Route path="scanner" element={<Navigate to="/trading" replace />} />
                <Route path="charts" element={<Navigate to="/trading" replace />} />
                <Route path="alerts" element={<Navigate to="/trading" replace />} />
                <Route path="watchlist" element={<Navigate to="/settings" replace />} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthGate>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
