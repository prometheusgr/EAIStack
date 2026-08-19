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

  if (!onRefresh) {
    throw new Error('Auth refresh callback is required')
  }

  const response = await authorizedFetch(
    "/api/agents/chat",
    token,
    onRefresh,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    }
  );

  const data = (await response.json()) as {
    response: string;
    thread_id: string;
  };

  return {
    response: data.response,
    threadId: data.thread_id,
  };
}
