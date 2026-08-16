import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { sendChatMessage } from "../api/agentsClient";
import { ChatMessage } from "../types/chat";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function ChatWindow() {
  const { token, refreshAccessToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string>("");

  const handleSend = async () => {
    if (!inputValue.trim()) {
      return;
    }

    if (!token) {
      setError("No auth token available. Please log in.");
      return;
    }

    const userMessage = inputValue;
    const currentThreadId = threadId || undefined;

    try {
      setError(null);
      setIsLoading(true);
      setMessages((prev) => [...prev, { role: "user", text: userMessage }]);
      setInputValue("");

      const response = await sendChatMessage(
        userMessage,
        currentThreadId,
        token,
        refreshAccessToken
      );

      setThreadId(response.threadId);
      setMessages((prev) => [...prev, { role: "agent", text: response.response }]);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to send message";
      setError(errorMessage);
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="flex flex-col h-96">
      <CardHeader>
        <CardTitle>Chat</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col flex-1 gap-4">
        <div className="flex-1 overflow-y-auto space-y-3 border border-border rounded-md p-4 bg-muted">
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-8">
              Start a conversation...
            </div>
          )}
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex gap-2 ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-xs px-4 py-2 rounded-lg ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground rounded-br-none"
                    : "bg-card border border-border rounded-bl-none"
                }`}
              >
                <span className="text-xs font-semibold opacity-70">
                  {msg.role === "user" ? "You" : "Agent"}
                </span>
                <p className="text-sm mt-1">{msg.text}</p>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start gap-2">
              <div className="bg-card border border-border px-4 py-2 rounded-lg rounded-bl-none">
                <span className="text-xs font-semibold opacity-70">Agent</span>
                <p className="text-sm mt-1 text-muted-foreground italic">
                  Agent is thinking...
                </p>
              </div>
            </div>
          )}
          {error && (
            <div className="bg-destructive/10 border border-destructive text-destructive px-4 py-2 rounded-md text-sm">
              Error: {error}
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && !isLoading && handleSend()}
            placeholder="Type your message..."
            disabled={isLoading}
            className="flex-1 px-4 py-2 border border-input rounded-md bg-background text-foreground placeholder-muted-foreground disabled:opacity-50"
          />
          <Button
            onClick={handleSend}
            disabled={isLoading || !inputValue.trim()}
          >
            {isLoading ? "Sending..." : "Send"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
