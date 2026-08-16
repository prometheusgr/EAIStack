import { ChatRequest, ChatResponse } from "../types/chat";

export async function sendChatMessage(
  message: string,
  threadId: string | undefined,
  token: string
): Promise<ChatResponse> {
  const request: ChatRequest = {
    message,
    threadId,
  };

  console.log('[agentsClient] Sending request to /api/agents/chat', {
    message,
    threadId,
    tokenLength: token.length,
  });

  const response = await fetch("/api/agents/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(request),
  });

  console.log('[agentsClient] Response status:', response.status);

  if (!response.ok) {
    const errorText = await response.text();
    console.error('[agentsClient] Error response:', errorText);
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
