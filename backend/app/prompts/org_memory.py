"""
Prompt templates for the Org Memory Agent.
Handles retrieval and storage of organizational knowledge.
"""

ORG_MEMORY_RETRIEVAL_PROMPT = """以下是从组织记忆库中检索到的相关历史信息，请将其作为上下文参考：

{retrieved_context}

---
请在你的回答中适当参考以上历史信息，避免重复犯过去的错误，并利用过去成功的经验。
"""

ORG_MEMORY_SUMMARIZE_PROMPT = """你是一位知识管理专家。请将以下文档内容总结为关键要点，以便存入组织记忆库供未来参考。

要求：
1. 提取核心决策和结论
2. 记录关键上下文和约束条件
3. 标注可复用的经验教训
4. 总结控制在 300 字以内

文档内容：
{document_content}
"""
