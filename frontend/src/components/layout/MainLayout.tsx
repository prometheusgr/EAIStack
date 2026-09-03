import { ReactNode } from 'react'
import { useAuth } from '../../context/AuthContext'
import { Button } from '../ui/button'

export type MainLayoutView =
  | 'chat'
  | 'apikeys'
  | 'embeddings'
  | 'embeddings-search'
  | 'settings'
  | 'audit'
  | 'dashboard'

interface MainLayoutProps {
  children: ReactNode
  currentView: MainLayoutView
  onViewChange: (view: MainLayoutView) => void
  /** Admin-configurable (see docs/SECURITY.md's Audit Log section):
   * defaults to true (transparent by default) if the settings response
   * hasn't loaded yet, since the nav should not flash the tab and then
   * hide it a moment later for the common case where it stays enabled.
   */
  auditLogUiEnabled?: boolean
}

export function MainLayout({
  children,
  currentView,
  onViewChange,
  auditLogUiEnabled = true,
}: MainLayoutProps) {
  const { logout, user, isAdmin } = useAuth()

  return (
    <div className="flex flex-col min-h-screen bg-background">
      <header className="border-b border-border bg-card px-4 py-4 md:px-6">
        <div className="flex items-center justify-between max-w-6xl mx-auto">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">EAIStack</h1>
            <p className="text-xs md:text-sm text-muted-foreground">Enterprise AI Stack</p>
          </div>
          <div className="flex items-center gap-2 md:gap-4">
            <span className="text-sm md:text-base text-foreground truncate">
              Welcome, {user?.name || user?.username}
            </span>
            <Button onClick={logout} variant="outline" size="sm" className="text-xs md:text-sm">
              Logout
            </Button>
          </div>
        </div>
      </header>

      <nav className="border-b border-border bg-card px-4 md:px-6 overflow-x-auto">
        <div className="flex gap-2 max-w-6xl mx-auto">
          <Button
            variant={currentView === 'chat' ? 'default' : 'ghost'}
            onClick={() => onViewChange('chat')}
            className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary text-xs md:text-sm"
            data-active={currentView === 'chat'}
          >
            Chat
          </Button>
          <Button
            variant={currentView === 'apikeys' ? 'default' : 'ghost'}
            onClick={() => onViewChange('apikeys')}
            className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary text-xs md:text-sm"
            data-active={currentView === 'apikeys'}
          >
            API Keys
          </Button>
          <Button
            variant={currentView === 'embeddings' ? 'default' : 'ghost'}
            onClick={() => onViewChange('embeddings')}
            className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary text-xs md:text-sm"
            data-active={currentView === 'embeddings'}
          >
            Embeddings
          </Button>
          <Button
            variant={currentView === 'embeddings-search' ? 'default' : 'ghost'}
            onClick={() => onViewChange('embeddings-search')}
            className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary text-xs md:text-sm"
            data-active={currentView === 'embeddings-search'}
          >
            Search
          </Button>
          {isAdmin && (
            <Button
              variant={currentView === 'dashboard' ? 'default' : 'ghost'}
              onClick={() => onViewChange('dashboard')}
              className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary text-xs md:text-sm"
              data-active={currentView === 'dashboard'}
            >
              Dashboard
            </Button>
          )}
          {isAdmin && (
            <Button
              variant={currentView === 'settings' ? 'default' : 'ghost'}
              onClick={() => onViewChange('settings')}
              className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary text-xs md:text-sm"
              data-active={currentView === 'settings'}
            >
              Settings
            </Button>
          )}
          {isAdmin && auditLogUiEnabled && (
            <Button
              variant={currentView === 'audit' ? 'default' : 'ghost'}
              onClick={() => onViewChange('audit')}
              className="rounded-none border-b-2 border-transparent data-[active=true]:border-primary text-xs md:text-sm"
              data-active={currentView === 'audit'}
            >
              Audit Log
            </Button>
          )}
        </div>
      </nav>

      <main className="flex-1 p-4 md:p-6">
        <div className="max-w-6xl mx-auto">
          {children}
        </div>
      </main>

      <footer className="border-t border-border bg-card px-4 py-3 md:px-6 text-center text-xs text-muted-foreground">
        <p>&copy; 2024 Enterprise AI Stack. All rights reserved.</p>
      </footer>
    </div>
  )
}
