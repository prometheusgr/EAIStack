import { useEffect, useRef, useState } from "react";
import { ShieldAlert, Clock, AlertCircle } from "lucide-react";
import { useChatService } from "../hooks/useChatService";
import { useThreadsService } from "../hooks/useThreadsService";
import { useIsMounted } from "../hooks/useIsMounted";
import { useRetryCountdown } from "../hooks/useRetryCountdown";
import { ChatMessage } from "../types/chat";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { ApiErrorImpl } from "../api/authorizedFetch";
import { SourceDocumentModal } from "./SourceDocumentModal";

const GENERIC_ERROR_MESSAGE = "Something went wrong and your message failed to send. Please try again.";

/** A send failure, classified so the UI can show a distinguishable signal
 * (issue #47) instead of one undifferentiated red banner for every 4xx:
 * - "guardrail": the input was content-filtered (400, see input_guardrail.py).
 * - "rate_limit": the request was throttled (429, see rate_limiter_service.py)
 *   -- carries retryAfterSeconds when the backend's Retry-After header was
 *   present, for the countdown below.
 * - "generic": anything else (5xx, an unmapped 4xx with no message, a plain
 *   FastAPI HTTPException) -- never shows the raw backend detail/message,
 *   since those aren't guaranteed fit for a user to read.
 */
type SendErrorInfo =
  | { kind: "guardrail"; text: string }
  | { kind: "rate_limit"; text: string; retryAfterSeconds?: number }
  | { kind: "generic"; text: string };

// rate_limit_exceeded_response's detail is always this exact literal (see
// backend/app/services/rate_limiter_service.py) -- checking it directly,
// rather than relying on status === 429 alone, keeps this classification
// tied to the one backend contract that actually promises the shape, in
// case a future 429 from an unrelated source doesn't carry Retry-After.
const RATE_LIMIT_DETAIL = "rate_limit_exceeded";

function classifySendError(error: unknown): SendErrorInfo {
  if (error instanceof ApiErrorImpl && error.status === 429 && error.detail === RATE_LIMIT_DETAIL) {
    return {
      kind: "rate_limit",
      text: error.message || GENERIC_ERROR_MESSAGE,
      retryAfterSeconds: error.retryAfterSeconds,
    };
  }
  // A raw HTTP status/reason string (ApiErrorImpl's fallback when the
  // backend doesn't supply a human-readable message, e.g. a 500) is not fit
  // to show a user -- only a guardrail-style 4xx rejection carries a
  // message worth displaying, so anything else falls back to generic text.
  if (error instanceof ApiErrorImpl && error.status >= 400 && error.status < 500 && error.message) {
    return { kind: "guardrail", text: error.message };
  }
  return { kind: "generic", text: GENERIC_ERROR_MESSAGE };
}

export function ChatWindow() {
  const { mutateAsync: sendMessage, isPending } = useChatService();
  const { listThreads, getThreadHistory } = useThreadsService();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [threadId, setThreadId] = useState<string>("");
  const [hasLoadedInitialThread, setHasLoadedInitialThread] = useState(false);
  const [sendError, setSendError] = useState<SendErrorInfo | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const isMounted = useIsMounted();
  const retrySecondsRemaining = useRetryCountdown(
    sendError?.kind === "rate_limit" ? sendError.retryAfterSeconds : undefined
  );
  const sendDisabledForRateLimit = sendError?.kind === "rate_limit" && retrySecondsRemaining !== null;
  // Tracks which thread is currently active, independent of React's render
  // cycle. handleSend's catch block closes over `threadId` state at the
  // moment the send *started* -- if the user switches threads (or starts a
  // new chat) while that send is still in flight, `threadId` state moves on,
  // but the closure's copy is stale. Comparing against this ref (updated
  // synchronously by handleSelectThread/loadThread) lets the catch block
  // detect "the user has since navigated away" and skip mutating whatever
  // thread is now on screen.
  const activeThreadIdRef = useRef<string>("");

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
    activeThreadIdRef.current = id;
    setSendError(null);
    if (!id) {
      setThreadId("");
      setMessages([]);
      return;
    }
    loadThread(id);
  };

  const handleSend = async () => {
    if (!inputValue.trim() || isPending || sendDisabledForRateLimit) {
      return;
    }

    const userMessage = inputValue;
    const currentThreadId = threadId || undefined;
    // Snapshot which thread this send belongs to. If the user switches
    // threads (or starts a new chat) before this request settles, this
    // request's outcome must not be applied to whatever thread is showing
    // by the time it resolves/rejects -- see activeThreadIdRef above.
    const sendThreadId = threadId;
    activeThreadIdRef.current = sendThreadId;

    try {
      setSendError(null);
      setMessages((prev) => [...prev, { role: "user", text: userMessage }]);
      setInputValue("");

      const result = await sendMessage({ message: userMessage, threadId: currentThreadId });
      const stillOnSameThread = activeThreadIdRef.current === sendThreadId;
      if (isMounted() && stillOnSameThread) {
        activeThreadIdRef.current = result.threadId;
        setThreadId(result.threadId);
        setMessages((prev) => [
          ...prev,
          {
            role: "agent",
            text: result.response,
            sources: result.sources,
            wasModified: result.wasModified,
          },
        ]);
      }
      listThreads.execute();
    } catch (error) {
      const stillOnSameThread = activeThreadIdRef.current === sendThreadId;
      if (isMounted() && stillOnSameThread) setMessages((prev) => prev.slice(0, -1));
      // Restore the message the user typed: it was optimistically cleared
      // above, but a rejected send (guardrail, rate limit, or a generic
      // failure) means it was never actually sent. Without this, the input
      // box is left empty and Send stays disabled (!inputValue.trim()) even
      // after a rate-limit countdown elapses -- correctly re-enabled by
      // sendDisabledForRateLimit turning false, but still blocked by an
      // unrelated, now-stale reason the user has no way to see.
      if (isMounted() && stillOnSameThread) setInputValue(userMessage);
      if (isMounted() && stillOnSameThread) setSendError(classifySendError(error));
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
                <p
                  className={`text-sm mt-1 ${msg.role === "user" ? "message-user" : "message-agent"}`}
                >
                  {msg.text}
                </p>
                {msg.role === "agent" && msg.wasModified && (
                  <div className="mt-2 pt-2 border-t border-border/50 text-xs text-muted-foreground">
                    Part of this response was filtered by a content safety rule.
                  </div>
                )}
                {msg.role === "agent" && msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-border/50 text-xs text-muted-foreground">
                    <span className="font-semibold">Sources: </span>
                    {msg.sources.map((source, sourceIdx) => (
                      <span key={source.knowledgeBaseId}>
                        {sourceIdx > 0 && ", "}
                        <button
                          type="button"
                          className="underline hover:text-foreground"
                          onClick={() => setSelectedSourceId(source.knowledgeBaseId)}
                        >
                          {source.title}
                        </button>
                      </span>
                    ))}
                  </div>
                )}
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
          {sendError && sendError.kind === "rate_limit" && (
            <div
              role="alert"
              aria-label="Rate limit reached"
              className="flex items-start gap-2 bg-amber-50 border border-amber-300 text-amber-900 px-4 py-2 rounded-md text-sm"
            >
              <Clock className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <div>
                <p>{sendError.text}</p>
                {retrySecondsRemaining !== null && (
                  <p className="text-xs mt-1 opacity-80">
                    Try again in {retrySecondsRemaining}s
                  </p>
                )}
              </div>
            </div>
          )}
          {sendError && sendError.kind === "guardrail" && (
            <div
              role="alert"
              aria-label="Message rejected by content safety rule"
              className="flex items-start gap-2 bg-destructive/10 border border-destructive text-destructive px-4 py-2 rounded-md text-sm"
            >
              <ShieldAlert className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <p>{sendError.text}</p>
            </div>
          )}
          {sendError && sendError.kind === "generic" && (
            <div
              role="alert"
              aria-label="Message failed to send"
              className="flex items-start gap-2 bg-destructive/10 border border-destructive text-destructive px-4 py-2 rounded-md text-sm"
            >
              <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <p>{sendError.text}</p>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && !isPending && !sendDisabledForRateLimit && handleSend()}
            placeholder="Type your message..."
            disabled={isPending}
            className="flex-1 px-4 py-2 border border-input rounded-md bg-background text-foreground placeholder-muted-foreground disabled:opacity-50"
          />
          <Button
            onClick={handleSend}
            disabled={isPending || !inputValue.trim() || sendDisabledForRateLimit}
          >
            {isPending
              ? "Sending..."
              : sendDisabledForRateLimit
                ? `Retry in ${retrySecondsRemaining}s`
                : "Send"}
          </Button>
        </div>
      </CardContent>
      <SourceDocumentModal
        knowledgeBaseId={selectedSourceId ?? ""}
        open={selectedSourceId !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedSourceId(null);
        }}
      />
    </Card>
  );
}
