/**
 * 记忆系统客户端配置
 */
export interface MemoryClientConfig {
  /** 服务器地址 */
  serverUrl: string;
  /** API Key */
  apiKey: string;
  /** 项目 ID (可选) */
  projectId?: string;
  /** Agent 标识 (可选) */
  agentId?: string;
  /** 会话 ID (可选) */
  sessionId?: string;
  /** 请求超时 (毫秒) */
  timeout?: number;
  /** 是否启用缓存 */
  enableCache?: boolean;
}

/**
 * 记忆类型
 */
export type MemoryType = 
  | 'short_term'    // 短期记忆
  | 'long_term'     // 长期记忆
  | 'working'       // 工作记忆
  | 'semantic'      // 语义记忆
  | 'episodic';     // 情景记忆

/**
 * 记忆输入
 */
export interface MemoryInput {
  /** 记忆内容 */
  content: string;
  /** 记忆类型 */
  type?: MemoryType;
  /** 元数据 */
  metadata?: Record<string, any>;
  /** 重要性评分 (0-1) */
  importance?: number;
  /** 标签列表 */
  tags?: string[];
  /** 过期时间（ISO 字符串） */
  expiresAt?: string;
}

/**
 * 记忆对象
 */
export interface Memory extends MemoryInput {
  /** 记忆 ID */
  id: string;
  /** 内容哈希 */
  content_hash?: string;
  /** 访问次数 */
  access_count: number;
  /** 最后访问时间 */
  last_accessed?: string;
  /** 过期时间 */
  expires_at?: string;
  /** 创建时间 */
  created_at: string;
  /** 更新时间 */
  updated_at: string;
}

/**
 * 搜索结果
 */
export interface SearchMemory {
  id: string;
  type: string;
  content: string;
  metadata: Record<string, any>;
  importance: number;
  similarity: number;
  created_at: string;
  updated_at: string;
}

/**
 * 搜索选项
 */
export interface SearchOptions {
  /** 记忆类型过滤 */
  type?: MemoryType;
  /** 返回数量 */
  limit?: number;
  /** 相似度阈值 */
  threshold?: number;
}

/**
 * 查询选项
 */
export interface QueryOptions {
  /** 类型过滤 */
  type?: MemoryType;
  /** 标签过滤 */
  tags?: string[];
  /** 返回数量 */
  limit?: number;
  /** 偏移量 */
  offset?: number;
  /** 排序字段 */
  orderBy?: string;
  /** 降序 */
  desc?: boolean;
}

/**
 * API 响应
 */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
  pagination?: {
    limit: number;
    offset: number;
    total: number;
  };
}
