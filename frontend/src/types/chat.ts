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
  /** The published workflow to start a new conversation with (issue #85).
   * The backend ignores it for an existing thread, which keeps its own. */
  workflow?: string;
}

export interface ChatResponse {
  response: string;
  threadId: string;
  sources: SourceReference[];
  wasModified: boolean;
  /** The workflow that answered: the conversation's bound workflow. */
  workflow: string;
}

/** A published workflow a user can start a conversation with (issue #85). */
export interface AvailableWorkflow {
  name: string;
  description: string;
  isDefault: boolean;
}

export interface ThreadSummary {
  id: string;
  createdAt: string;
  updatedAt: string;
  workflow: string;
}

export interface ThreadListResponse {
  threads: ThreadSummary[];
}

export interface ThreadHistoryResponse {
  id: string;
  messages: ChatMessage[];
  workflow: string;
}
