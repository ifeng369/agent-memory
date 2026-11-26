# agent-memory

供 OpenCode 及其他 Agent 使用的跨会话记忆服务。

- **Docker 端**：镜像 `agent-memory`，FastAPI + PostgreSQL(pgvector) + ONNX Runtime，提供增/删/改/查/语义检索/压缩，附带 Web 管理台（`/web`）。
- **Agent 端插件**：OpenCode V2 插件 `agent-memory-plugin`，注册 `memory_remember` / `memory_recall` / `memory_forget`，自动召回与每 3 条消息抽取；`src/client.ts` 可作其它 Agent 的 TS 客户端。
- **跨 Agent 共享**：同一 `project_id` 下记忆对所有 Agent 可见。项目 ID 默认取 git remote URL（无 remote 用目录名）。

## 启动服务端

```bash
cd memory-system
docker compose up -d --build
curl http://localhost:3000/api/health
# Web 管理台：http://localhost:3000/web
```

端口 `3000`，API 前缀 `/api/v1`，鉴权用 `X-API-Key`（默认占位密钥见 `docker-compose.yml`，生产务必替换）。使用默认占位密钥时不校验；换成真实值后所有接口（除健康检查/文档/Web 页面）都必须带 `X-API-Key`。

镜像与模型：

- 仅支持 ONNX，无 PyTorch 回退。镜像构建分两阶段：builder 安装 CPU 版 torch 导出 `BAAI/bge-small-zh-v1.5` 到 `/app/models/agent-memory-onnx`，runtime 只装 ONNX 相关依赖并复制模型，因此无需运行时下载、体积从约 2.5G 降到约 920MB。
- 国内构建用 `HF_ENDPOINT=https://hf-mirror.com`（compose build arg / workflow build-arg 已设）。
- 运行时环境变量：`DATABASE_URL`（必须 `postgresql+asyncpg://...`）、`API_SECRET`、`MODEL_NAME`（默认 `/app/models/agent-memory-onnx`）、`BATCH_SIZE`、`OMP_NUM_THREADS`。

## 接入 OpenCode

插件目录：`plugins/opencode`（包名 `agent-memory-plugin`）。全局配置 `opencode.jsonc` 示例：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": [
    {
      "package": "E:/开发测试/memory/memory-system/plugins/opencode",
      "options": {
        "serverUrl": "http://localhost:3000",
        "apiKey": "your-secret-key-change-in-production",
        "projectId": "my-project",
        "agentId": "opencode"
      }
    }
  ]
}
```

`options` 可省略，依次回退 `MEMORY_SERVER_URL` / `MEMORY_API_KEY` / `MEMORY_PROJECT_ID` / `MEMORY_AGENT_ID`，再回退默认值；`projectId` 缺省由 git remote URL 推导。加载后：模型调用前自动注入相关记忆（同会话缓存）；每 3 条用户消息抽取事实写入（用 Agent 自己的模型）；也可主动调用三个 `memory_*` 工具。失败均静默降级。构建检查：`npm install && npx tsc --noEmit`。

## 其它 Agent 直接调用 HTTP

```ts
import { createMemoryClient } from './plugins/opencode/src/client'

const client = createMemoryClient({
  serverUrl: 'http://localhost:3000',
  apiKey: 'your-secret-key-change-in-production',
})
await client.add({ content: '用户偏好中文回复', tags: ['preference'], importance: 0.9 })
const hits = await client.search('用户喜欢什么语言？')
```

作用域头 `X-Project-Id` / `X-Agent-Id` / `X-Session-Id` 在写入时存入 `metadata`；检索默认按 `X-Project-Id` 过滤，同项目下所有 Agent 共享，加 `agent_id` 查询参数可只看某个 Agent 的记忆。过期记忆默认不出现在列表/检索，按 ID 仍可读。

主要端点（均带 `/api/v1` 前缀）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/memories` | 创建，JSON body：`{content, type?, importance?, tags?, metadata?, expires_at?}` |
| GET | `/memories` | 列表（type/tags/agent_id/include_expired/limit/offset/order_by） |
| POST | `/memories/search` | 语义检索（query/type/agent_id/include_expired/limit/threshold） |
| GET | `/memories/{id}` | 读取单条 |
| PUT | `/memories/{id}` | 更新，JSON body：任意 `{content?, importance?, tags?, metadata?}` |
| DELETE | `/memories/{id}` | 删除 |
| GET | `/memories/tags` | 所有标签 |
| POST | `/memories/compress` | 压缩多条记忆 |
| GET | `/memories/stats` | 统计 |
| GET | `/api/health` | 健康检查 |

## 镜像发布（GHCR）

仓库私有，但 GHCR 包可设为公开，拉取无需登录：

```bash
docker pull ghcr.io/ifeng369/agent-memory:latest
```

提交任意 tag 时 `.github/workflows/release.yml` 会自动构建并推送镜像到 GHCR，包含 tag 名、`latest`、完整版本号、主版本.次版本。workflow 会尝试把包设为 public；若因权限失败，到 GHCR 包页面手动改可见性即可。

## 已知限制

- 鉴权是单密钥比对：默认占位密钥不校验；拿到真实密钥即可操作全部项目，没有按 key 的权限/限流，也没有按 `project_id` 隔离写删。
- 自动抽取用 Agent 自己的模型；没有 `MEMORY.md` 写入拦截、实体/图谱记忆。
- `expires_at` 只影响列表/检索（按 ID 仍可读），自动过期/压缩未接定时任务。
- 历史记忆（写入前无 `X-Project-Id`）不再出现在检索结果里；`compress` 只创建新记忆+关联，不删原记忆。
