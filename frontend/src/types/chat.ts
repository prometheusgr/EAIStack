export interface SourceReference {
  knowledgeBaseId: string;
  title: string;
  headingPath: string | null;
}

export interface ChatMessage {
  role: "user" | "agent";
  text: string;
  sources?: SourceReference[];
  wasModified?: boolean;
}

/** Wire shape of POST /api/agents/chat - snake_case, as the backend reads it. */
export interface ChatRequest {
  message: string;
  thread_id?: string;
}

export interface ChatResponse {
  response: string;
  threadId: string;
  sources: SourceReference[];
  wasModified: boolean;
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
