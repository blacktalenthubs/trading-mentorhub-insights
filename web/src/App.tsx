import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/auth";

import AppLayout from "./components/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import ScannerPage from "./pages/ScannerPage";
import ChartsPage from "./pages/ChartsPage";
import RealTradesPage from "./pages/RealTradesPage";
import ScorecardPage from "./pages/ScorecardPage";
import HistoryPage from "./pages/HistoryPage";
import ImportPage from "./pages/ImportPage";
import PaperTradingPage from "./pages/PaperTradingPage";
import BacktestPage from "./pages/BacktestPage";

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

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
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
              <Route path="charts" element={<ErrorBoundary><ChartsPage /></ErrorBoundary>} />
              <Route path="trades" element={<ErrorBoundary><RealTradesPage /></ErrorBoundary>} />
              <Route path="scorecard" element={<ErrorBoundary><ScorecardPage /></ErrorBoundary>} />
              <Route path="history" element={<ErrorBoundary><HistoryPage /></ErrorBoundary>} />
              <Route path="import" element={<ErrorBoundary><ImportPage /></ErrorBoundary>} />
              <Route path="paper-trading" element={<ErrorBoundary><PaperTradingPage /></ErrorBoundary>} />
              <Route path="backtest" element={<ErrorBoundary><BacktestPage /></ErrorBoundary>} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
