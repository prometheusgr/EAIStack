import { useEffect, useRef, useState } from 'react'
import { Clock } from 'lucide-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './context/AuthContext'
import { useRetryCountdown } from './hooks/useRetryCountdown'
import { ChatWindow } from './components/ChatWindow'
import { APIKeys } from './components/APIKeys'
import { AuditLog } from './components/AuditLog'
import { Dashboard } from './components/Dashboard'
import { EmbeddingsList } from '@/components/embeddings/EmbeddingsList'
import { EmbeddingsSearch } from '@/components/embeddings/EmbeddingsSearch'
import { Settings } from './components/Settings'
import { Button } from './components/ui/button'
import { MainLayout, type MainLayoutView } from './components/layout/MainLayout'
import { ToastProvider } from './components/ui/toast'
import { TooltipProvider } from './components/ui/tooltip'
import { ErrorBoundary } from './components/ErrorBoundary'
import { useSettingsService } from '@/hooks/useSettingsService'

function AppContent() {
  const { isAuthenticated, isLoading, login, isAdmin, authError } = useAuth()
  const [currentView, setCurrentView] = useState<MainLayoutView>('chat')
  const { get: getSettings, getNavConfig } = useSettingsService()
  const retrySecondsRemaining = useRetryCountdown(authError?.retryAfterSeconds)
  const loginDisabledForRateLimit = authError?.retryAfterSeconds !== undefined && retrySecondsRemaining !== null

  useEffect(() => {
    if (isAdmin) {
      getSettings.execute()
      // A separate, lightweight endpoint (GET /api/settings/nav-config),
      // not GET /api/settings/dashboard -- the nav's "User Management"
      // deep link (issue #40) needs keycloak_users_console_url as soon as
      // an admin logs in, and the dashboard endpoint does real work (a
      // 24h audit-log aggregation query, live rate-limit bucket
      // introspection) that a static nav value shouldn't force every
      // login to pay for. Dashboard.tsx still independently fetches the
      // full dashboard status itself, fresh, when that tab is opened.
      getNavConfig.execute()
    }
  }, [isAdmin])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4 bg-background p-4">
        <h1 className="text-4xl font-bold">EAIStack</h1>
        <p className="text-lg text-muted-foreground">Enterprise AI Stack - Please log in</p>
        {authError && (
          <div
            data-testid="auth-error-banner"
            role="alert"
            className={`flex items-start gap-2 px-4 py-2 rounded-md text-sm max-w-md text-center ${
              loginDisabledForRateLimit
                ? 'bg-amber-50 border border-amber-300 text-amber-900'
                : 'bg-destructive/10 border border-destructive text-destructive'
            }`}
          >
            {loginDisabledForRateLimit && <Clock className="h-4 w-4 mt-0.5 flex-shrink-0" />}
            <p>{authError.message}</p>
          </div>
        )}
        <Button
          data-testid="login-button"
          onClick={login}
          disabled={loginDisabledForRateLimit}
          size="lg"
        >
          {loginDisabledForRateLimit ? `Retry in ${retrySecondsRemaining}s` : 'Login'}
        </Button>
      </div>
    )
  }

  return (
    <MainLayout
      currentView={currentView}
      onViewChange={setCurrentView}
      auditLogUiEnabled={getSettings.data?.audit_log_ui_enabled ?? true}
      keycloakUsersConsoleUrl={getNavConfig.data?.keycloak_users_console_url}
    >
      {currentView === 'chat' && (
        <>
          <h2 className="text-2xl font-semibold mb-4">Phase 2: Agent Chat</h2>
          <ChatWindow />
        </>
      )}
      {currentView === 'apikeys' && (
        <APIKeys />
      )}
      {currentView === 'embeddings' && <EmbeddingsList />}
      {currentView === 'embeddings-search' && (
        <>
          <h2 className="text-2xl font-semibold mb-4">Semantic Search</h2>
          <EmbeddingsSearch />
        </>
      )}
      {currentView === 'settings' && isAdmin && <Settings />}
      {currentView === 'audit' && isAdmin && <AuditLog />}
      {currentView === 'dashboard' && isAdmin && (
        <Dashboard onViewAuditLog={() => setCurrentView('audit')} />
      )}
    </MainLayout>
  )
}

function AppWithProviders() {
  const queryClientRef = useRef<QueryClient | null>(null)
  if (!queryClientRef.current) {
    queryClientRef.current = new QueryClient()
  }

  return (
    <QueryClientProvider client={queryClientRef.current}>
      <AuthProvider>
        <ToastProvider>
          <TooltipProvider delayDuration={200}>
            <AppContent />
          </TooltipProvider>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <AppWithProviders />
    </ErrorBoundary>
  )
}

export default App
