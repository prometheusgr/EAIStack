import { useState } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ChatWindow } from './components/ChatWindow'
import { APIKeys } from './components/APIKeys'
import { Button } from './components/ui/button'
import { MainLayout } from './components/layout/MainLayout'
import { ToastProvider } from './components/ui/toast'
import { ErrorBoundary } from './components/ErrorBoundary'

function AppContent() {
  const { isAuthenticated, isLoading, login } = useAuth()
  const [currentView, setCurrentView] = useState<'chat' | 'apikeys'>('chat')

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
        <Button
          data-testid="login-button"
          onClick={login}
          size="lg"
        >
          Login
        </Button>
      </div>
    )
  }

  return (
    <MainLayout currentView={currentView} onViewChange={setCurrentView}>
      {currentView === 'chat' && (
        <>
          <h2 className="text-2xl font-semibold mb-4">Phase 2: Agent Chat</h2>
          <ChatWindow />
        </>
      )}
      {currentView === 'apikeys' && (
        <APIKeys />
      )}
    </MainLayout>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ToastProvider>
          <AppContent />
        </ToastProvider>
      </AuthProvider>
    </ErrorBoundary>
  )
}

export default App
