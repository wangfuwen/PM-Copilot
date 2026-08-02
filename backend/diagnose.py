"""
PM Copilot 诊断脚本
直接运行 workflow，不经过 API/SSE 层。
用法：python diagnose.py
"""
import asyncio
import logging
import sys
import json

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("diagnose")

def check_env():
    """检查环境变量配置"""
    from app.config import settings
    
    print("=" * 60)
    print("📋 环境配置检查")
    print("=" * 60)
    
    issues = []
    
    # Check OpenAI key
    if not settings.openai_api_key:
        issues.append("❌ OPENAI_API_KEY 未设置！")
    else:
        print(f"✅ OpenAI API Key: {settings.openai_api_key[:20]}...{settings.openai_api_key[-4:]}")
    
    # Check Anthropic key (optional)
    if settings.anthropic_api_key:
        print(f"✅ Anthropic API Key: 已配置")
    else:
        print(f"⚠️  Anthropic API Key: 未配置（使用 OpenAI 方案，正常）")
    
    # Check model routing
    print()
    print("📌 Agent 模型路由:")
    models = settings.get_agent_model_summary()
    for agent, model in models.items():
        provider = model.split(":")[0] if ":" in model else "unknown"
        status = "✅" if provider == "openai" or settings.anthropic_api_key else "❌ 需要 Anthropic Key"
        print(f"   {status} {agent}: {model}")
    
    # Validate all models can use OpenAI
    for agent, model in models.items():
        provider = model.split(":")[0] if ":" in model else ""
        if provider == "anthropic" and not settings.anthropic_api_key:
            issues.append(f"❌ {agent} 使用 Anthropic 模型 {model}，但未配置 ANTHROPIC_API_KEY")
    
    if issues:
        print()
        print(" 发现问题:")
        for issue in issues:
            print(f"   {issue}")
        print()
        print("请修改 backend/.env 文件，将所有 AGENT_*_MODEL 改为 openai:xxx")
        return False
    
    print()
    print("✅ 环境配置检查通过")
    return True

async def test_workflow():
    """测试完整 workflow 执行"""
    from app.graph.workflow import build_workflow, run_workflow_streaming
    
    print("=" * 60)
    print(" Workflow 测试")
    print("=" * 60)
    print()
    
    test_message = "我想做一个AI驱动的读书笔记助手，帮我分析这个需求"
    print(f"测试消息: \"{test_message}\"")
    print()
    
    logger.info("Building workflow...")
    wf = build_workflow()
    logger.info("Workflow built successfully")
    print()
    
    logger.info("Starting workflow execution...")
    event_count = 0
    
    try:
        async for event in run_workflow_streaming(
            workflow=wf,
            user_message=test_message,
            session_id="diagnose-test",
            phase="auto",
        ):
            event_count += 1
            etype = event["type"]
            agent = event["data"].get("agent", "N/A")
            
            if etype == "agent_start":
                print(f"  🟡 [{agent}] 开始执行")
            elif etype == "agent_output":
                output = event["data"].get("output", {})
                if output.get("decision"):
                    rec = output["decision"].get("recommendation", "N/A")
                    print(f"  🟢 [{agent}] 输出: 决策建议 = {rec}")
                elif output.get("prd"):
                    print(f"  🟢 [{agent}] 输出: PRD 已生成 ({len(output['prd'])} 字)")
                elif output.get("stress_test"):
                    n = len(output["stress_test"])
                    print(f"  🟢 [{agent}] 输出: {n} 个压力测试挑战")
                else:
                    print(f"  🟢 [{agent}] 输出: (无关键输出)")
            elif etype == "agent_complete":
                print(f"  ✅ [{agent}] 完成")
            elif etype == "error":
                print(f"  ❌ 错误: {event['data']}")
            elif etype == "done":
                agents = event["data"].get("agents_executed", [])
                print(f"  🏁 工作流完成! 执行了 {len(agents)} 个 agent: {agents}")
    
    except Exception as e:
        print(f"  💥 Workflow 执行异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    print(f"总事件数: {event_count}")
    
    if event_count == 0:
        print("🚨 没有收到任何事件！workflow 可能没有正常执行。")
        return False
    
    if event_count >= 10:  # 5 agents × 3 events (start+output+complete) + done
        print("✅ Workflow 测试通过！")
        return True
    else:
        print(f"⚠️  只收到 {event_count} 个事件（期望至少 10 个），可能部分 agent 未执行。")
        return False

async def main():
    print()
    print("🔧 PM Copilot 诊断工具")
    print()
    
    env_ok = check_env()
    if not env_ok:
        print("环境配置有问题，请先修复 .env 文件再运行测试。")
        return
    
    print()
    workflow_ok = await test_workflow()
    
    print()
    print("=" * 60)
    print("📊 诊断结果")
    print("=" * 60)
    print(f"环境配置: {'✅ 通过' if env_ok else '❌ 失败'}")
    print(f"Workflow:  {'✅ 通过' if workflow_ok else '❌ 失败'}")
    print()
    
    if env_ok and workflow_ok:
        print(" 一切正常！问题可能出在前端或 SSE 层。")
        print("请检查:")
        print("  1. 前端 API_BASE 是否正确指向 http://localhost:8000/api")
        print("  2. 浏览器开发者工具 Network 面板，查看 /api/chat 的响应内容")
        print("  3. 后端日志是否有 workflow 执行记录")
    else:
        print("🔧 请按上述提示修复问题后重新运行诊断。")

if __name__ == "__main__":
    asyncio.run(main())
