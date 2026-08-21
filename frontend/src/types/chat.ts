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

export interface ThreadSummary {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export interface ThreadListResponse {
  threads: ThreadSummary[];
}

export interface ThreadHistoryResponse {
  id: string;
  messages: ChatMessage[];
}
