import { ChatRequest, ChatResponse } from "../types/chat";
import type { AuthRefresh } from "./authorizedFetch";

export async function sendChatMessage(
  message: string,
  threadId: string | undefined,
  token: string,
  onRefresh?: AuthRefresh
): Promise<ChatResponse> {
  const request: ChatRequest = {
    message,
    threadId,
  };

  let response = await fetch("/api/agents/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(request),
  });

  if (response.status === 401 && onRefresh) {
    const refreshed = await onRefresh();
    if (refreshed) {
      const newToken = localStorage.getItem("access_token");
      if (newToken) {
        response = await fetch("/api/agents/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${newToken}`,
          },
          body: JSON.stringify(request),
        });
      }
    }
  }

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.statusText}`);
  }

  const data = (await response.json()) as {
    response: string;
    thread_id: string;
  };

  return {
    response: data.response,
    threadId: data.thread_id,
  };
}
