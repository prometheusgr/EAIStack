import { AuthProvider, useAuth } from './context/AuthContext'
import { ChatWindow } from './components/ChatWindow'
import './App.css'

function AppContent() {
  const { isAuthenticated, isLoading, login, logout, user } = useAuth()

  if (isLoading) {
    return <div>Loading...</div>
  }

  if (!isAuthenticated) {
    return (
      <div className="App">
        <h1>EAIStack</h1>
        <p>Enterprise AI Stack - Please log in</p>
        <button
          data-testid="login-button"
          onClick={() => {
            console.log('[App] === NOT AUTHENTICATED - Login button clicked ===')
            console.log('[App] isAuthenticated:', isAuthenticated)
            console.log('[App] user:', user)
            console.log('[App] calling login()...')
            login()
            console.log('[App] login() returned')
          }}>Login</button>
      </div>
    )
  }

  return (
    <div className="App">
      <h1>EAIStack</h1>
      <div className="header">
        <span>Welcome, {user?.name || user?.username}</span>
        <button onClick={logout}>Logout</button>
      </div>
      <div className="content">
        <h2>Phase 2: Agent Chat</h2>
        <ChatWindow />
      </div>
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
