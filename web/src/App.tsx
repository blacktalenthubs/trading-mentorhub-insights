import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { useAuthStore } from "./stores/auth";
import { useNativePlatform } from "./hooks/useNativePlatform";
import { useTrackPageView } from "./lib/useTrackPageView";

import AppLayout from "./components/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import UpdatePrompt from "./components/UpdatePrompt";
import RouteTitle from "./components/RouteTitle";
import LandingPage from "./pages/LandingPage";
import PricingPage from "./pages/PricingPage";
import PrivacyPage from "./pages/PrivacyPage";
import ReplayPage from "./pages/ReplayPage";
import LearnPage from "./pages/LearnPage";
import PrototypeTodayPage from "./pages/PrototypeTodayPage";  // design prototype (#64 J) — view at /prototype
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
import StartHerePage from "./pages/StartHerePage";
import { ToastContainer } from "./components/Toast";
import BillingPage from "./pages/BillingPage";
import PublicEODReportPage from "./pages/PublicEODReportPage";
import TrackRecordPage from "./pages/TrackRecordPage";
import WatchlistPage from "./pages/WatchlistPage";
import PremarketPage from "./pages/PremarketPage";
import FocusListPage from "./pages/FocusListPage";
import TodayPage from "./pages/TodayPage";
import PatternLearnPage from "./pages/PatternLearnPage";

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

// Inner component — placed inside BrowserRouter so router-context hooks
// (useTrackPageView's useLocation) work. Returns null (no UI). Push setup +
// tap-routing live in usePushNotifications (AppLayout) — the single source of
// truth; the old usePushRegistration tap-handler was removed (it double-routed
// every tap to /trading, fighting the type/route router).
function PushRegistrationListener() {
  useTrackPageView();
  return null;
}

export default function App() {
  useNativePlatform();

  // GoogleOAuthProvider only wraps when a Client ID is configured. With no
  // ID it's a no-op pass-through so dev environments without env keys still
  // render — the Google button just won't be visible.
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
  const withGoogle = (children: React.ReactNode) =>
    googleClientId ? <GoogleOAuthProvider clientId={googleClientId}>{children}</GoogleOAuthProvider> : <>{children}</>;

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastContainer />
        <UpdatePrompt />
        <AuthGate>
          {withGoogle(
          <BrowserRouter>
            <PushRegistrationListener />
            <RouteTitle />
            <Routes>
              {/* Public routes */}
              <Route path="/" element={<LandingPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/learn" element={<LearnPage />} />
              <Route path="/prototype" element={<PrototypeTodayPage />} />
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
                <Route path="today"       element={<ErrorBoundary><TodayPage /></ErrorBoundary>} />
                <Route path="start-here"  element={<ErrorBoundary><StartHerePage /></ErrorBoundary>} />
                <Route path="pattern/:code" element={<ErrorBoundary><PatternLearnPage /></ErrorBoundary>} />
                <Route path="trading"     element={<ErrorBoundary><TradingPageV2 /></ErrorBoundary>} />
                <Route path="trade-ideas" element={<ErrorBoundary><FocusListPage /></ErrorBoundary>} />
                <Route path="conviction"  element={<Navigate to="/trade-ideas" replace />} />
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
          )}
        </AuthGate>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
