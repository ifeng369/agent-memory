-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 记忆表
CREATE TABLE memories (
    id              VARCHAR(64) PRIMARY KEY,
    type            VARCHAR(32) NOT NULL,
    content         TEXT NOT NULL,
    content_hash    VARCHAR(64) UNIQUE,
    embedding       vector(512),
    importance      FLOAT DEFAULT 0.5,
    access_count    INTEGER DEFAULT 0,
    last_accessed   TIMESTAMP,
    expires_at      TIMESTAMP,
    metadata        JSONB,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX idx_memories_type ON memories(type);
CREATE INDEX idx_memories_importance ON memories(importance DESC);
CREATE INDEX idx_memories_expires ON memories(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_memories_created ON memories(created_at DESC);
CREATE INDEX idx_memories_metadata ON memories USING GIN(metadata);

-- 记忆关联表
CREATE TABLE memory_relations (
    id              VARCHAR(64) PRIMARY KEY,
    from_memory_id  VARCHAR(64) REFERENCES memories(id) ON DELETE CASCADE,
    to_memory_id    VARCHAR(64) REFERENCES memories(id) ON DELETE CASCADE,
    relation_type   VARCHAR(32),
    strength        FLOAT DEFAULT 1.0,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_relations_from ON memory_relations(from_memory_id);
CREATE INDEX idx_relations_to ON memory_relations(to_memory_id);

-- 标签表
CREATE TABLE tags (
    id              VARCHAR(64) PRIMARY KEY,
    name            VARCHAR(128) UNIQUE NOT NULL,
    color           VARCHAR(7),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- 记忆 - 标签关联表
CREATE TABLE memory_tags (
    memory_id       VARCHAR(64) REFERENCES memories(id) ON DELETE CASCADE,
    tag_id          VARCHAR(64) REFERENCES tags(id) ON DELETE CASCADE,
    created_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (memory_id, tag_id)
);

CREATE INDEX idx_memory_tags_memory ON memory_tags(memory_id);
CREATE INDEX idx_memory_tags_tag ON memory_tags(tag_id);


