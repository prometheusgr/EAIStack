import { useEffect, useState } from "react";
import { useChatService } from "../hooks/useChatService";
import { useThreadsService } from "../hooks/useThreadsService";
import { useIsMounted } from "../hooks/useIsMounted";
import { ChatMessage } from "../types/chat";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { ApiErrorImpl } from "../api/authorizedFetch";

const GENERIC_ERROR_MESSAGE = "Something went wrong and your message failed to send. Please try again.";

// A raw HTTP status/reason string (ApiErrorImpl's fallback when the backend
// doesn't supply a human-readable message, e.g. a 500) is not fit to show a
// user -- only a guardrail-style 4xx rejection carries a message worth
// displaying, so anything else still falls back to the generic text.
function describeSendError(error: unknown): string {
  if (error instanceof ApiErrorImpl && error.status >= 400 && error.status < 500 && error.message) {
    return error.message;
  }
  return GENERIC_ERROR_MESSAGE;
}

export function ChatWindow() {
  const { mutateAsync: sendMessage, isPending } = useChatService();
  const { listThreads, getThreadHistory } = useThreadsService();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [threadId, setThreadId] = useState<string>("");
  const [hasLoadedInitialThread, setHasLoadedInitialThread] = useState(false);
  const [sendErrorMessage, setSendErrorMessage] = useState<string | null>(null);
  const isMounted = useIsMounted();

  useEffect(() => {
    listThreads.execute();
  }, []);

  useEffect(() => {
    if (hasLoadedInitialThread || !listThreads.data) {
      return;
    }
    setHasLoadedInitialThread(true);

    const mostRecentThread = listThreads.data.threads[0];
    if (mostRecentThread) {
      loadThread(mostRecentThread.id);
    }
  }, [listThreads.data, hasLoadedInitialThread]);

  const loadThread = async (id: string) => {
    const history = await getThreadHistory.mutateAsync(id);
    if (isMounted()) setThreadId(history.id);
    if (isMounted()) setMessages(history.messages);
  };

  const handleSelectThread = (id: string) => {
    if (id === threadId) {
      return;
    }
    setSendErrorMessage(null);
    if (!id) {
      setThreadId("");
      setMessages([]);
      return;
    }
    loadThread(id);
  };

  const handleSend = async () => {
    if (!inputValue.trim() || isPending) {
      return;
    }

    const userMessage = inputValue;
    const currentThreadId = threadId || undefined;

    try {
      setSendErrorMessage(null);
      setMessages((prev) => [...prev, { role: "user", text: userMessage }]);
      setInputValue("");

      const result = await sendMessage({ message: userMessage, threadId: currentThreadId });
      if (isMounted()) setThreadId(result.threadId);
      if (isMounted()) setMessages((prev) => [...prev, { role: "agent", text: result.response }]);
      listThreads.execute();
    } catch (error) {
      if (isMounted()) setMessages((prev) => prev.slice(0, -1));
      if (isMounted()) setSendErrorMessage(describeSendError(error));
    }
  };

  return (
    <Card className="flex flex-col h-96">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Chat</CardTitle>
        <div className="flex items-center gap-2">
          <select
            aria-label="Select conversation"
            value={threadId}
            onChange={(e) => handleSelectThread(e.target.value)}
            className="text-sm border border-input rounded-md bg-background text-foreground px-2 py-1"
          >
            <option value="">New chat</option>
            {listThreads.data?.threads.map((thread) => (
              <option key={thread.id} value={thread.id}>
                {new Date(thread.updatedAt).toLocaleString()}
              </option>
            ))}
          </select>
          <Button variant="outline" size="sm" onClick={() => handleSelectThread("")}>
            New chat
          </Button>
        </div>
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
          {isPending && (
            <div className="flex justify-start gap-2">
              <div className="bg-card border border-border px-4 py-2 rounded-lg rounded-bl-none">
                <span className="text-xs font-semibold opacity-70">Agent</span>
                <p className="text-sm mt-1 text-muted-foreground italic">
                  Agent is thinking...
                </p>
              </div>
            </div>
          )}
          {sendErrorMessage && (
            <div className="bg-destructive/10 border border-destructive text-destructive px-4 py-2 rounded-md text-sm">
              {sendErrorMessage}
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && !isPending && handleSend()}
            placeholder="Type your message..."
            disabled={isPending}
            className="flex-1 px-4 py-2 border border-input rounded-md bg-background text-foreground placeholder-muted-foreground disabled:opacity-50"
          />
          <Button
            onClick={handleSend}
            disabled={isPending || !inputValue.trim()}
          >
            {isPending ? "Sending..." : "Send"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
