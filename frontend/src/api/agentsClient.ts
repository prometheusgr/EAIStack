import { AvailableWorkflow, ChatRequest, ChatResponse } from "../types/chat";
import { authorizedFetch, type AuthRefresh } from "./authorizedFetch";

export async function sendChatMessage(
  message: string,
  threadId: string | undefined,
  token: string,
  onRefresh?: AuthRefresh,
  workflow?: string
): Promise<ChatResponse> {
  const request: ChatRequest = { message };
  if (threadId) {
    request.thread_id = threadId;
  } else if (workflow) {
    request.workflow = workflow;
  }

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
    sources: { knowledge_base_id: string; title: string; heading_path: string | null }[];
    was_modified: boolean;
    workflow: string;
  };

  return {
    response: data.response,
    threadId: data.thread_id,
    sources: data.sources.map((source) => ({
      knowledgeBaseId: source.knowledge_base_id,
      title: source.title,
      headingPath: source.heading_path,
    })),
    wasModified: data.was_modified,
    workflow: data.workflow,
  };
}

export async function listAvailableWorkflows(
  token: string,
  onRefresh: AuthRefresh
): Promise<AvailableWorkflow[]> {
  const response = await authorizedFetch("/api/agents/workflows", token, onRefresh, {
    method: "GET",
  });
  const data = (await response.json()) as {
    workflows: { name: string; description: string; is_default: boolean }[];
  };
  return data.workflows.map((workflow) => ({
    name: workflow.name,
    description: workflow.description,
    isDefault: workflow.is_default,
  }));
}
