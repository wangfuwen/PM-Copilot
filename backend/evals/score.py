"""Deterministic scorer for PM Copilot benchmark outputs.

The scorer intentionally evaluates only observable evidence. It does not call an
LLM, so the same raw outputs always produce the same report.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalise(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(map(str, value))
    if isinstance(value, dict):
        value = " ".join(f"{k} {v}" for k, v in value.items())
    return str(value or "").lower().replace(" ", "")


def record_text(record: dict[str, Any]) -> str:
    decision = record.get("decision") or {}
    stress = record.get("stress_test") or record.get("stress_test_results") or []
    return normalise(
        [
            decision.get("reasoning", ""),
            decision.get("risks", []),
            record.get("prd", ""),
            stress,
        ]
    )


def has_term(text: str, term: str) -> bool:
    return normalise(term) in text


STRESS_ROLE_ALIASES = {
    "boss": ("boss", "老板", "投资人"),
    "engineer": ("engineer", "技术负责人", "技术", "研发"),
    "user": ("user", "真实用户", "用户"),
    "competitor": ("competitor", "竞品", "竞争"),
    "compliance": ("compliance", "合规", "风控"),
}


def has_stress_perspective(stress: list[dict[str, Any]], perspective: str) -> bool:
    """Recognise the fixed role set in either the Chinese product output or English."""
    aliases = STRESS_ROLE_ALIASES.get(perspective.lower(), (perspective,))
    roles = normalise([item.get("role", "") for item in stress if isinstance(item, dict)])
    return any(has_term(roles, alias) for alias in aliases)


def score_record(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    decision = record.get("decision") or {}
    recommendation = str(decision.get("recommendation", "")).upper()
    evidence = record_text(record)
    risks = case["expected_risks"]
    sections = case["required_prd_sections"]
    stress = record.get("stress_test") or record.get("stress_test_results") or []

    return {
        "case_id": case["id"],
        "decision_correct": recommendation == case["expected_recommendation"],
        "risk_coverage": sum(has_term(evidence, risk) for risk in risks) / len(risks),
        "prd_section_coverage": sum(
            has_term(normalise(record.get("prd", "")), section) for section in sections
        ) / len(sections),
        "stress_coverage": sum(
            has_stress_perspective(stress, perspective)
            for perspective in case["stress_perspectives"]
        ) / len(case["stress_perspectives"]),
        "has_citations": bool(record.get("citations") or record.get("memory_citations")),
    }


def aggregate(cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {record.get("case_id"): record for record in records}
    rows = [score_record(case, by_id[case["id"]]) for case in cases if case["id"] in by_id]
    missing = [case["id"] for case in cases if case["id"] not in by_id]
    if not rows:
        raise ValueError("No benchmark records matched the dataset case IDs.")

    def average(key: str) -> float:
        return round(sum(float(row[key]) for row in rows) / len(rows), 3)

    return {
        "cases_scored": len(rows),
        "cases_missing": missing,
        "decision_accuracy": average("decision_correct"),
        "risk_coverage": average("risk_coverage"),
        "prd_section_coverage": average("prd_section_coverage"),
        "stress_coverage": average("stress_coverage"),
        "citation_rate": average("has_citations"),
        "rows": rows,
    }


def render_markdown(baseline: dict[str, Any], multi_agent: dict[str, Any]) -> str:
    metrics = [
        ("Decision accuracy", "decision_accuracy"),
        ("Risk coverage", "risk_coverage"),
        ("PRD section coverage", "prd_section_coverage"),
        ("Stress-test coverage", "stress_coverage"),
        ("Citation rate", "citation_rate"),
    ]
    lines = [
        "# PM Copilot benchmark report",
        "",
        f"Scored cases: {baseline['cases_scored']} (baseline) / {multi_agent['cases_scored']} (multi-agent)",
        "",
        "| Metric | Single-agent baseline | PM Copilot multi-agent | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in metrics:
        base, multi = baseline[key], multi_agent[key]
        lines.append(f"| {label} | {base:.1%} | {multi:.1%} | {multi - base:+.1%} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Compare outputs produced with the same model, temperature, case order and no hidden context.",
            "- Do not claim a multi-agent improvement unless both files contain complete, real model outputs.",
            "- Inspect per-case rows before using aggregate metrics in a portfolio or resume.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score PM Copilot baseline vs multi-agent outputs")
    parser.add_argument("--cases", type=Path, default=ROOT / "cases.jsonl")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--multi-agent", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "report.md")
    args = parser.parse_args()

    cases = read_jsonl(args.cases)
    baseline = aggregate(cases, read_jsonl(args.baseline))
    multi_agent = aggregate(cases, read_jsonl(args.multi_agent))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(baseline, multi_agent), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
