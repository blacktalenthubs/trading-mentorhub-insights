import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth";
import { useNativePlatform } from "./hooks/useNativePlatform";
import { usePushRegistration } from "./lib/usePushRegistration";

import AppLayout from "./components/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import UpdatePrompt from "./components/UpdatePrompt";
import LandingPage from "./pages/LandingPage";
import PricingPage from "./pages/PricingPage";
import ReplayPage from "./pages/ReplayPage";
import LearnPage from "./pages/LearnPage";
import LearnDetailPage from "./pages/LearnDetailPage";
import PatternDetailPage from "./pages/PatternDetailPage";
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import AdminPage from "./pages/AdminPage";
import RegisterPage from "./pages/RegisterPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import TradingPageV2 from "./pages/TradingPageV2";
import RealTradesPage from "./pages/RealTradesPage";
import SettingsPage from "./pages/SettingsPage";
import { ToastContainer } from "./components/Toast";
import BillingPage from "./pages/BillingPage";
import PublicEODReportPage from "./pages/PublicEODReportPage";
import TrackRecordPage from "./pages/TrackRecordPage";
import WatchlistPage from "./pages/WatchlistPage";
import PremarketPage from "./pages/PremarketPage";
import FocusListPage from "./pages/FocusListPage";

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

// Inner component — placed inside BrowserRouter so useNavigate() in
// usePushRegistration has Router context. Returns null (no UI).
function PushRegistrationListener() {
  usePushRegistration();
  return null;
}

export default function App() {
  useNativePlatform();

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastContainer />
        <UpdatePrompt />
        <AuthGate>
          <BrowserRouter>
            <PushRegistrationListener />
            <Routes>
              {/* Public routes */}
              <Route path="/" element={<LandingPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route path="/learn" element={<LearnPage />} />
              <Route path="/learn/:categoryId" element={<LearnDetailPage />} />
              <Route path="/learn/patterns/:patternId" element={<PatternDetailPage />} />
              <Route path="/replay/:alertId" element={<ReplayPage />} />
              <Route path="/public/eod-report" element={<PublicEODReportPage />} />
              <Route path="/public/eod-report/:date" element={<PublicEODReportPage />} />
              <Route path="/public/eod-report/:date/:symbol" element={<PublicEODReportPage />} />
              <Route path="/track-record" element={<TrackRecordPage />} />
              <Route path="/track-record/:date" element={<TrackRecordPage />} />
              <Route path="/track-record/:date/:symbol" element={<TrackRecordPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/onboarding" element={<ProtectedRoute><OnboardingPage /></ProtectedRoute>} />

              {/* Protected routes with sidebar layout */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                {/* 6-menu structure (2026-05-28) */}
                <Route path="trading"     element={<ErrorBoundary><TradingPageV2 /></ErrorBoundary>} />
                <Route path="trade-ideas" element={<ErrorBoundary><FocusListPage /></ErrorBoundary>} />
                <Route path="watchlist"   element={<ErrorBoundary><WatchlistPage /></ErrorBoundary>} />
                <Route path="premarket"   element={<ErrorBoundary><PremarketPage /></ErrorBoundary>} />
                <Route path="performance" element={<ErrorBoundary><RealTradesPage /></ErrorBoundary>} />
                <Route path="settings"    element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
                <Route path="billing"     element={<ErrorBoundary><BillingPage /></ErrorBoundary>} />
                <Route path="admin"       element={<ErrorBoundary><AdminPage /></ErrorBoundary>} />

                {/* Legacy redirects — deep links + old bookmarks keep working */}
                <Route path="dashboard"   element={<Navigate to="/trade-ideas" replace />} />
                <Route path="focus-list"  element={<Navigate to="/trade-ideas" replace />} />
                <Route path="trades"      element={<Navigate to="/performance" replace />} />
                <Route path="review"      element={<Navigate to="/performance" replace />} />
                <Route path="eod-report"  element={<Navigate to="/performance" replace />} />
                <Route path="trading-v1"  element={<Navigate to="/trading" replace />} />
                <Route path="scanner"     element={<Navigate to="/trading" replace />} />
                <Route path="charts"      element={<Navigate to="/trading" replace />} />
                <Route path="alerts"      element={<Navigate to="/trading" replace />} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthGate>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
