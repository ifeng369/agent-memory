/**
 * 记忆系统客户端
 * 使用 Node 18+ 原生 fetch，无需额外依赖。
 */
import {
  MemoryClientConfig,
  MemoryInput,
  Memory,
  SearchMemory,
  SearchOptions,
  QueryOptions,
  ApiResponse
} from './types';

export class MemoryClient {
  private config: MemoryClientConfig;
  private cache: Map<string, any>;

  constructor(config: MemoryClientConfig) {
    this.config = {
      timeout: 30000,
      enableCache: true,
      ...config
    };
    this.cache = new Map();
  }

  /**
   * 创建记忆
   */
  async add(input: MemoryInput): Promise<Memory> {
    const response = await this.request<ApiResponse<Memory>>(
      '/memories',
      'POST',
      {
        content: input.content,
        type: input.type || 'long_term',
        ...(input.importance !== undefined ? { importance: input.importance } : {}),
        ...(input.tags ? { tags: input.tags } : {}),
        ...(input.metadata ? { metadata: input.metadata } : {}),
        ...(input.expiresAt ? { expires_at: input.expiresAt } : {})
      }
    );

    if (!response.success || !response.data) {
      throw new Error(response.error || 'Failed to create memory');
    }

    // 清除列表缓存
    this.clearListCache();

    return response.data;
  }

  /**
   * 获取记忆
   */
  async get(id: string): Promise<Memory> {
    // 检查缓存
    const cacheKey = `memory:${id}`;
    if (this.config.enableCache && this.cache.has(cacheKey)) {
      return this.cache.get(cacheKey);
    }

    const response = await this.request<ApiResponse<Memory>>(`/memories/${id}`);

    if (!response.success || !response.data) {
      throw new Error(response.error || 'Memory not found');
    }

    // 写入缓存
    if (this.config.enableCache) {
      this.cache.set(cacheKey, response.data);
    }

    return response.data;
  }

  /**
   * 查询记忆列表
   */
  async list(options?: QueryOptions): Promise<Memory[]> {
    const params = new URLSearchParams();

    if (options?.type) {
      params.append('type', options.type);
    }

    if (options?.tags && options.tags.length > 0) {
      params.append('tags', options.tags.join(','));
    }

    if (options?.limit) {
      params.append('limit', options.limit.toString());
    }

    if (options?.offset) {
      params.append('offset', options.offset.toString());
    }

    if (options?.orderBy) {
      params.append('order_by', options.orderBy);
    }

    if (options?.desc !== undefined) {
      params.append('desc', options.desc.toString());
    }

    const response = await this.request<ApiResponse<Memory[]>>(`/memories?${params.toString()}`);

    if (!response.success || !response.data) {
      throw new Error(response.error || 'Failed to list memories');
    }

    return response.data;
  }

  /**
   * 语义搜索
   */
  async search(query: string, options?: SearchOptions): Promise<SearchMemory[]> {
    const params = new URLSearchParams({ query });

    if (options?.type) {
      params.append('type', options.type);
    }

    if (options?.limit) {
      params.append('limit', options.limit.toString());
    }

    if (options?.threshold) {
      params.append('threshold', options.threshold.toString());
    }

    const response = await this.request<ApiResponse<SearchMemory[]>>(
      `/memories/search?${params.toString()}`,
      'POST'
    );

    if (!response.success || !response.data) {
      throw new Error(response.error || 'Search failed');
    }

    return response.data;
  }

  /**
   * 更新记忆
   */
  async update(id: string, updates: Partial<MemoryInput>): Promise<Memory> {
    const response = await this.request<ApiResponse<Memory>>(
      `/memories/${id}`,
      'PUT',
      {
        ...(updates.content ? { content: updates.content } : {}),
        ...(updates.importance !== undefined ? { importance: updates.importance } : {}),
        ...(updates.tags ? { tags: updates.tags } : {}),
        ...(updates.metadata ? { metadata: updates.metadata } : {})
      }
    );

    if (!response.success || !response.data) {
      throw new Error(response.error || 'Failed to update memory');
    }

    // 清除缓存
    this.clearMemoryCache(id);

    return response.data;
  }

  /**
   * 删除记忆
   */
  async delete(id: string): Promise<void> {
    await this.request<ApiResponse<void>>(`/memories/${id}`, 'DELETE');
    
    // 清除缓存
    this.clearMemoryCache(id);
  }

  /**
   * 批量添加
   */
  async batchAdd(memories: MemoryInput[]): Promise<Memory[]> {
    const results: Memory[] = [];
    
    for (const memory of memories) {
      try {
        const result = await this.add(memory);
        results.push(result);
      } catch (error) {
        console.error(`Failed to add memory: ${(error as Error).message}`);
      }
    }

    return results;
  }

  /**
   * 获取所有标签
   */
  async getTags(): Promise<string[]> {
    const response = await this.request<ApiResponse<{ id: string; name: string }[]>>('/memories/tags');

    if (!response.success || !response.data) {
      throw new Error(response.error || 'Failed to get tags');
    }

    return response.data.map(t => t.name);
  }

  /**
   * 获取统计信息
   */
  async getStats(): Promise<{ total: number; byType: Record<string, number> }> {
    const response = await this.request<ApiResponse<{ total_memories: number; by_type: Record<string, number> }>>(
      '/memories/stats'
    );

    if (!response.success || !response.data) {
      throw new Error(response.error || 'Failed to get stats');
    }

    return {
      total: response.data.total_memories,
      byType: response.data.by_type
    };
  }

  /**
   * 清除上下文 (临时实现：删除短期记忆)
   */
  async clearContext(): Promise<void> {
    const memories = await this.list({ type: 'short_term', limit: 100 });
    
    for (const memory of memories) {
      await this.delete(memory.id);
    }
  }

  /**
   * 获取上下文 (按主题搜索)
   */
  async getContext(topic?: string): Promise<Memory[]> {
    if (!topic) {
      return this.list({ type: 'working', limit: 20 });
    }

    const results = await this.search(topic, { limit: 20 });
    // shortcut: 搜索结果不带访问统计，用 0 占位；需要真实统计时改用 get()
    return results.map(r => ({ ...r, type: r.type as Memory['type'], access_count: 0 }));
  }

  /**
   * 派生一个带会话作用域的客户端（同项目不同 Agent/会话共享同一记忆库）
   */
  withSession(sessionId: string): MemoryClient {
    return new MemoryClient({ ...this.config, sessionId });
  }

  /**
   * 发送 HTTP 请求
   */
  private async request<T>(path: string, method: string = 'GET', body?: unknown): Promise<T> {
    const url = `${this.config.serverUrl}/api/v1${path}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

    try {
      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': this.config.apiKey,
          ...(this.config.projectId ? { 'X-Project-Id': this.config.projectId } : {}),
          ...(this.config.agentId ? { 'X-Agent-Id': this.config.agentId } : {}),
          ...(this.config.sessionId ? { 'X-Session-Id': this.config.sessionId } : {})
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Request failed' }));
        throw new Error(error.error || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if ((error as any).name === 'AbortError') {
        throw new Error('Request timeout');
      }
      throw error;
    }
  }

  /**
   * 清除单个记忆缓存
   */
  private clearMemoryCache(id: string): void {
    this.cache.delete(`memory:${id}`);
    this.clearListCache();
  }

  /**
   * 清除列表缓存
   */
  private clearListCache(): void {
    for (const key of this.cache.keys()) {
      if (key.startsWith('memories:')) {
        this.cache.delete(key);
      }
    }
  }
}

// 导出默认实例创建函数
export function createMemoryClient(config: MemoryClientConfig): MemoryClient {
  return new MemoryClient(config);
}
