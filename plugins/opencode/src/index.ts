/**
 * agent-memory - OpenCode V2 服务端插件
 *
 * 三个显式工具 + 两个自动 hook：模型调用前注入相关记忆，每 3 条用户消息抽取一次事实。
 * 配置优先级：插件 options > 环境变量；项目 ID 默认由 git remote 推导，保证跨 Agent 一致。
 */
import { execFileSync } from "node:child_process"
import { basename } from "node:path"
import { Plugin } from "@opencode/plugin"
import { MemoryClient } from "./client"

const CAPTURE_EVERY = 3

function projectIdFromGit(directory?: string): string {
  if (!directory) return "default"
  try {
    const remote = execFileSync("git", ["-C", directory, "remote", "get-url", "origin"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim()
    return remote.replace(/\.git$/, "").replace(/\/+$/, "")
  } catch {
    return basename(directory) || "default"
  }
}

function lastUserText(messages: readonly unknown[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i] as { role?: string; content?: readonly { type?: string; text?: string }[] }
    if (msg?.role !== "user") continue
    const text = (msg.content ?? [])
      .filter((part) => part.type === "text")
      .map((part) => part.text ?? "")
      .join("\n")
      .trim()
    if (text) return text
  }
  return ""
}

export default Plugin.define({
  id: "agent-memory",

  async setup(ctx) {
    const options = (ctx.options ?? {}) as Record<string, unknown>
    const pick = (key: string, env: string): string | undefined => {
      const value = options[key] ?? process.env[env]
      return typeof value === "string" && value.length > 0 ? value : undefined
    }

    const client = new MemoryClient({
      serverUrl: pick("serverUrl", "MEMORY_SERVER_URL") ?? "http://localhost:3000",
      apiKey: pick("apiKey", "MEMORY_API_KEY") ?? "your-secret-key-change-in-production",
      projectId: pick("projectId", "MEMORY_PROJECT_ID") ?? projectIdFromGit(ctx.location.project?.canonical),
      agentId: pick("agentId", "MEMORY_AGENT_ID") ?? "opencode",
    })

    // 模型调用前自动召回：注入 system 而不是改写历史，失败不影响会话
    const recalls = new Map<string, { text: string; lines: string[] }>()
    await ctx.session.hook("context", async (event) => {
      try {
        const text = lastUserText(event.messages)
        if (!text) return
        const cached = recalls.get(event.sessionID)
        let lines = cached?.text === text ? cached.lines : undefined
        if (!lines) {
          const hits = await client.withSession(event.sessionID).search(text, { limit: 5, threshold: 0.5 })
          lines = hits.map((hit) => `- ${hit.content}`)
          recalls.set(event.sessionID, { text, lines })
        }
        if (lines.length === 0) return
        event.system.push({
          type: "text",
          text: [
            "<memory>",
            "同项目历史会话与其他 Agent 沉淀的相关记忆（仅供参考）：",
            ...lines,
            "</memory>",
          ].join("\n"),
        })
      } catch {
        // 记忆服务不可用时静默降级
      }
    })

    // 每 3 条用户消息抽取一次事实；抽取用 Agent 自己的模型，服务端不跑 LLM
    const counts = new Map<string, number>()
    await ctx.session.hook("prompt", async (event) => {
      const text = event.prompt.text.trim()
      if (text.length < 20) return
      const count = (counts.get(event.sessionID) ?? 0) + 1
      counts.set(event.sessionID, count)
      if (count % CAPTURE_EVERY !== 0) return
      try {
        const { text: facts } = await ctx.experimental.generate.text({
          prompt: [
            "从下面的用户消息中抽取值得长期记住的事实：偏好、决定、项目约定、纠错。",
            "每条一行，只输出事实本身；没有可记住的内容就输出空字符串。",
            "",
            text,
          ].join("\n"),
        })
        const scoped = client.withSession(event.sessionID)
        for (const line of facts.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 5)) {
          if (line.length < 4) continue
          await scoped.add({ content: line, metadata: { source: "auto" } })
        }
      } catch {
        // 抽取失败不影响当前 prompt
      }
    })

    await ctx.tool.transform((editor) => {
      editor.namespace({
        name: "memory",
        description: "跨会话、跨 Agent 共享的长期记忆：记住事实、检索相关记忆、删除记忆",
      })

      editor.add({
        name: "remember",
        description: "把一条值得长期保留的信息写入当前项目共享记忆库（用户偏好、项目约定、决定与原因等）。内容相同不会重复写入。",
        input: {
          type: "object",
          properties: {
            content: { type: "string", description: "要记住的内容" },
            type: { type: "string", description: "记忆类型，默认 long_term", enum: ["short_term", "long_term", "working", "semantic", "episodic"] },
            importance: { type: "number", description: "重要性 0-1", minimum: 0, maximum: 1 },
            tags: { type: "array", items: { type: "string" }, description: "标签" },
            expiresAt: { type: "string", description: "过期时间（ISO 8601），过期后不再被检索到" },
          },
          required: ["content"],
          additionalProperties: false,
        },
        options: { namespace: "memory" },
        execute: async (input, context) => {
          try {
            const value = input as {
              content: string
              type?: "short_term" | "long_term" | "working" | "semantic" | "episodic"
              importance?: number
              tags?: string[]
              expiresAt?: string
            }
            const memory = await client.withSession(context.sessionID).add(value)
            return { content: `已记住 [${memory.id}]: ${memory.content}` }
          } catch (error) {
            return { content: `记忆写入失败: ${(error as Error).message}` }
          }
        },
      })

      editor.add({
        name: "recall",
        description: "按语义相似度检索当前项目共享记忆，含其他 Agent 写入的内容。",
        input: {
          type: "object",
          properties: {
            query: { type: "string", description: "检索问题或关键词" },
            limit: { type: "number", description: "返回条数，默认 10" },
            threshold: { type: "number", description: "相似度阈值 0-1，默认 0.7" },
            type: { type: "string", description: "只检索指定类型的记忆" },
          },
          required: ["query"],
          additionalProperties: false,
        },
        options: { namespace: "memory" },
        execute: async (input, context) => {
          try {
            const value = input as { query: string; limit?: number; threshold?: number; type?: string }
            const results = await client.withSession(context.sessionID).search(value.query, {
              limit: value.limit,
              threshold: value.threshold,
              type: value.type as any,
            })
            if (results.length === 0) return { content: "没有找到相关记忆。" }
            return {
              content: results
                .map((r) => `[${r.id}] (相似度 ${r.similarity.toFixed(2)}, ${r.type}) ${r.content}`)
                .join("\n\n"),
            }
          } catch (error) {
            return { content: `记忆检索失败: ${(error as Error).message}` }
          }
        },
      })

      editor.add({
        name: "forget",
        description: "按 ID 删除一条记忆。",
        input: {
          type: "object",
          properties: {
            id: { type: "string", description: "记忆 ID" },
          },
          required: ["id"],
          additionalProperties: false,
        },
        options: { namespace: "memory" },
        execute: async (input, context) => {
          try {
            const { id } = input as { id: string }
            await client.withSession(context.sessionID).delete(id)
            return { content: `已删除记忆 ${id}` }
          } catch (error) {
            return { content: `记忆删除失败: ${(error as Error).message}` }
          }
        },
      })
    })
  },
})
