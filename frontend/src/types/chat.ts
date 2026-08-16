export interface ChatMessage {
  role: "user" | "agent";
  text: string;
}

export interface ChatRequest {
  message: string;
  threadId?: string;
}

export interface ChatResponse {
  response: string;
  threadId: string;
}
