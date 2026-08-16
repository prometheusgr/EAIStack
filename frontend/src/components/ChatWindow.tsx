import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { sendChatMessage } from "../api/agentsClient";
import { ChatMessage } from "../types/chat";
import "./ChatWindow.css";

export function ChatWindow() {
  const { keycloak } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string>("");

  const handleSend = async () => {
    if (!inputValue.trim()) {
      return;
    }

    // Try to get token from keycloak.token, fall back to localStorage
    const token = keycloak?.token || localStorage.getItem('access_token');

    if (!token) {
      setError("No auth token available. Please log in.");
      console.error('[Chat] No token available:', { token, keycloak });
      return;
    }

    const userMessage = inputValue;
    const currentThreadId = threadId || undefined;

    try {
      setError(null);
      setIsLoading(true);
      setMessages((prev) => [...prev, { role: "user", text: userMessage }]);
      setInputValue("");

      console.log('[Chat] Sending message with token:', token.substring(0, 20) + '...');
      const response = await sendChatMessage(
        userMessage,
        currentThreadId,
        token
      );

      setThreadId(response.threadId);
      setMessages((prev) => [...prev, { role: "agent", text: response.response }]);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to send message";
      setError(errorMessage);
      console.error('[Chat] Error sending message:', { error: err, errorMessage });
      setMessages((prev) => prev.slice(0, -1)); // Remove added user message on error
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-window">
      <div className="messages-container">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message message-${msg.role}`}>
            <span className="message-role">
              {msg.role === "user" ? "You" : "Agent"}
            </span>
            <p className="message-text">{msg.text}</p>
          </div>
        ))}
        {isLoading && <div className="message-loading">Agent is thinking...</div>}
        {error && <div className="message-error">Error: {error}</div>}
      </div>
      <div className="input-container">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && handleSend()}
          placeholder="Type your message..."
          disabled={isLoading}
        />
        <button onClick={handleSend} disabled={isLoading || !inputValue.trim()}>
          {isLoading ? "Sending..." : "Send"}
        </button>
      </div>
    </div>
  );
}
