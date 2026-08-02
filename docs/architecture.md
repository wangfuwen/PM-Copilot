# PM Copilot — 架构设计文档

## 1. 系统概览

PM Copilot 采用 Multi-Agent 架构，通过 LangGraph 状态机编排多个专业 Agent 协同工作。

### 设计理念

- **关注点分离**：每个 Agent 专注一个职责，Prompt 精心调优
- **可组合性**：Agent 之间通过 LangGraph 的 StateGraph 松耦合协作
- **可观测性**：前端实时展示 Agent 执行状态，便于调试和演示
- **可扩展性**：新增 Agent 只需定义节点函数 + 路由规则
- **组织记忆**：RAG + Org Profile，让输出对齐公司风格与历史经验

## 2. Agent 职责

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Orchestrator | 意图识别 & 路由 | 用户消息 | 路由决策 |
| Org Memory | 向量检索 & Org Profile 加载 | 用户需求 | context / citations / profile |
| Decision | 需求质量分析 & 决策建议 | 需求 + RAG | 5W1H + GO/PIVOT/KILL |
| PRD Writer | 生成结构化 PRD | 决策 + Org Profile + RAG | 完整 PRD |
| Stress Test Lead | 5 角色红队挑战 + 组织历史视角 | PRD + 历史踩坑 | 挑战报告 + 评分 |
| Memory Writeback | 结果回流知识库 | 决策/PRD/压力测试摘要 | 文档 ID 列表 |
| Critic | 质量审查（v0.2，未挂图） | 任意产出 | 改进建议 |

## 3. LangGraph 工作流

```
START → Orchestrator → Org Memory
           ├── → Decision → PRD Writer → Stress Test → Memory Writeback → END
           ├── → PRD Writer → Stress Test → Memory Writeback → END
           └── → Stress Test → Memory Writeback → END
```

- 所有路径都先经过 Org Memory（检索 + 加载 Org Profile）
- `current_phase` / `next_agent` 控制条件路由
- 流程结束后写回决策摘要、PRD、压力测试结果，形成闭环

## 4. 组织记忆（RAG）数据流

1. **Ingest**：Markdown 上传 → 按标题/段落切片 → OpenAI Embedding → Chroma PersistentClient
2. **Profile**：抽样文档 → LLM 提取 Org Profile JSON → `chroma_data/org_profile.json`
3. **Retrieve**：用户需求 → Top-K 向量检索 → citations + 文本片段
4. **Generate**：System Prompt = 角色设定 + Org Profile + RAG 片段 + 任务指令
5. **Writeback**：流水线产物可选摘要后回流知识库

### API

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/memory/upload` | Markdown 入库（可触发画像重建） |
| POST | `/api/memory/store` | 通用入库 |
| POST | `/api/memory/search` | 语义检索 |
| GET | `/api/memory/docs` | 文档列表 |
| DELETE | `/api/memory/docs/{id}` | 删除文档及 chunks |
| GET | `/api/memory/profile` | 读取 Org Profile |
| POST | `/api/memory/profile/rebuild` | 重建 Org Profile |
| GET | `/api/memory/stats` | 统计 |

### 本地演示冷启动

```bash
cd backend
python seed_memory.py
```

会加载 `sample_memory/*.md` 并生成 Org Profile。

## 5. 前端架构

- **App Router**：Next.js 14 App Router
- **聊天界面**：左侧对话 + 右侧 Agent 面板 + 组织记忆面板
- **实时更新**：SSE 流式更新 Agent 状态与 citations
- **知识库 UI**：Markdown 上传 / 文档列表 / Org Profile 预览 / 检索引用

## 6. Phase 2 未完成能力（规划）

| 优先级 | 能力 | 建议版本 |
|--------|------|----------|
| P0 | Critic 接入图（PRD 后自检） | v0.2 |
| P0 | 决策追问 3–5 轮后再出报告 | v0.2 |
| P1 | 决策联网搜索 | v0.2 |
| P1 | 项目空间 / 会话持久化（checkpointer） | v0.2 |
| P1 | 导出 Markdown/PDF | v0.2 |
| P1 | PRD 模板选择（B/C/AI/通用） | v0.2 |
| P2 | PDF/Word 解析入库 | v0.2 |
| P2 | 一键按压力测试改 PRD | v0.2 |
| P2 | 风格匹配度评分 | v1.0 |
| P2 | Landing / 案例页 | v1.0 |
| P3 | 账号 / 多租户隔离 | v2.0 |
| P3 | 自定义评审角色 / Jira 飞书 | v2.0 |

建议下一迭代优先：**Critic 入图 + 决策追问 + 会话保存**。

## 7. 明确不做（当前版本）

- Reranker、Milvus/Pinecone、知识图谱
- 飞书/Notion 同步、团队权限
- 完整 Landing / 账号体系
