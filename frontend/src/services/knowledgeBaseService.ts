import { knowledgeBaseClient, type KnowledgeBase } from '@/api/knowledgeBaseClient'

export class KnowledgeBaseService {
  constructor(private token: string) {}

  async create(title: string, content: string, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    return knowledgeBaseClient.create(title, content, this.token, metadata)
  }

  async list(): Promise<KnowledgeBase[]> {
    return knowledgeBaseClient.list(this.token)
  }

  async get(id: string): Promise<KnowledgeBase> {
    return knowledgeBaseClient.get(id, this.token)
  }

  async update(id: string, title: string, content: string, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    return knowledgeBaseClient.update(id, title, content, this.token, metadata)
  }

  async delete(id: string): Promise<void> {
    return knowledgeBaseClient.delete(id, this.token)
  }
}
