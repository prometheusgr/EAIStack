import { ChatRequest, ChatResponse } from "../types/chat";
import { authorizedFetch, type AuthRefresh } from "./authorizedFetch";

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

  const response = await authorizedFetch(
    "/api/agents/chat",
    token,
    onRefresh || (async () => token),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    }
  );

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
