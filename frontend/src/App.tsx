import { useState } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ChatWindow } from './components/ChatWindow'
import { APIKeys } from './components/APIKeys'
import { Button } from './components/ui/button'

function AppContent() {
  const { isAuthenticated, isLoading, login, logout, user } = useAuth()
  const [currentView, setCurrentView] = useState<'chat' | 'apikeys'>('chat')

  if (isLoading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4 bg-background">
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
    <div className="flex flex-col min-h-screen bg-background">
      <header className="border-b border-border bg-card px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">EAIStack</h1>
            <p className="text-sm text-muted-foreground">Enterprise AI Stack</p>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-foreground">Welcome, {user?.name || user?.username}</span>
            <Button onClick={logout} variant="outline">
              Logout
            </Button>
          </div>
        </div>
      </header>

      <nav className="border-b border-border bg-card px-6">
        <div className="flex gap-4">
          <Button
            variant={currentView === 'chat' ? 'default' : 'ghost'}
            onClick={() => setCurrentView('chat')}
            className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary"
            data-active={currentView === 'chat'}
          >
            Chat
          </Button>
          <Button
            variant={currentView === 'apikeys' ? 'default' : 'ghost'}
            onClick={() => setCurrentView('apikeys')}
            className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary"
            data-active={currentView === 'apikeys'}
          >
            API Keys
          </Button>
        </div>
      </nav>

      <main className="flex-1 p-6">
        <div className="max-w-4xl mx-auto">
          {currentView === 'chat' && (
            <>
              <h2 className="text-2xl font-semibold mb-4">Phase 2: Agent Chat</h2>
              <ChatWindow />
            </>
          )}
          {currentView === 'apikeys' && (
            <>
              <h2 className="text-2xl font-semibold mb-4">Phase 5: API Key Management</h2>
              <APIKeys />
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App
