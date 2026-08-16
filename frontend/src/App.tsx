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
        <button onClick={login}>Login</button>
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
