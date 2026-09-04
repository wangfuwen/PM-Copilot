"""Run a reproducible single-agent vs PM Copilot quality-workflow benchmark.

The primary comparison deliberately excludes organisation memory so that outputs
depend on the same raw requirement. Run a separate RAG ablation for memory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.critic import CriticAgent
from app.agents.decision import DecisionAgent
from app.agents.evaluator import EvaluatorAgent
from app.agents.prd_writer import PRDWriterAgent
from app.agents.stress_test import StressTestAgent
from app.config import settings
from app.telemetry import ainvoke_with_retry

ROOT = Path(__file__).parent
BASELINE_PROMPT = """You are a senior product manager. Evaluate the raw requirement below in one pass.
Return JSON only with this shape:
{
  "decision": {"recommendation": "GO|PIVOT|KILL", "reasoning": "...", "risks": ["..."]},
  "prd": "A markdown PRD with background, target users, functional requirements, metrics and risks"
}
Do not ask clarifying questions, retrieve documents, use reviewers, or simulate roles."""


def read_cases(path: Path, limit: int) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return cases[:limit] if limit else cases


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if "```" in text:
        text = text.split("```", 2)[1].removeprefix("json").strip()
    return json.loads(text[text.index("{") : text.rindex("}") + 1])


async def run_baseline(case: dict[str, Any], llm) -> dict[str, Any]:
    started = time.perf_counter()
    response = await ainvoke_with_retry(
        llm,
        [SystemMessage(content=BASELINE_PROMPT), HumanMessage(content=case["requirement"])],
        max_retries=1,
        agent="benchmark_baseline",
    )
    data = extract_json(response.content or "")
    return {
        "case_id": case["id"],
        "decision": data.get("decision") or {},
        "prd": data.get("prd") or "",
        "stress_test": [],
        "citations": [],
        "metadata": {"duration_ms": round((time.perf_counter() - started) * 1000)},
    }


async def run_multi_agent(case: dict[str, Any], llm) -> dict[str, Any]:
    """Run all quality-workflow agents without memory to keep comparison fair."""
    started = time.perf_counter()
    requirement = case["requirement"]
    decision = await DecisionAgent(llm).analyze(requirement)
    prd = await PRDWriterAgent(llm).generate(
        requirement, decision.model_dump()
    )
    critic = await CriticAgent(llm).review(prd)
    evaluation = await EvaluatorAgent(llm).evaluate(
        prd, target="prd", user_requirement=requirement
    )
    stress = await StressTestAgent(llm).run_stress_test(prd)
    return {
        "case_id": case["id"],
        "decision": decision.model_dump(),
        "prd": prd,
        "critic": critic,
        "evaluation": evaluation,
        "stress_test": [challenge.model_dump() for challenge in stress.challenges],
        "citations": [],
        "metadata": {"duration_ms": round((time.perf_counter() - started) * 1000)},
    }


async def main_async(args: argparse.Namespace) -> None:
    cases = read_cases(args.cases, args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = args.output_dir / "baseline.jsonl"
    multi_path = args.output_dir / "multi_agent.jsonl"
    provider, model_name = args.model.split(":", 1)
    evaluation_llm = settings._create_llm(provider, model_name, args.temperature)

    with baseline_path.open("w", encoding="utf-8") as baseline_file, multi_path.open(
        "w", encoding="utf-8"
    ) as multi_file:
        for index, case in enumerate(cases, 1):
            print(f"[{index}/{len(cases)}] {case['id']} {case['title']}", flush=True)
            baseline = await run_baseline(case, evaluation_llm)
            multi_agent = await run_multi_agent(case, evaluation_llm)
            baseline_file.write(json.dumps(baseline, ensure_ascii=False) + "\n")
            multi_file.write(json.dumps(multi_agent, ensure_ascii=False) + "\n")
            baseline_file.flush()
            multi_file.flush()

    print(baseline_path)
    print(multi_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PM Copilot benchmark")
    parser.add_argument("--cases", type=Path, default=ROOT / "cases.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "preflight")
    parser.add_argument("--limit", type=int, default=5, help="0 runs all 25 cases")
    parser.add_argument(
        "--model",
        default=settings.agent_decision_model,
        help="One provider:model used for both arms and every workflow agent.",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
