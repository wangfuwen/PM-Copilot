import importlib.util
from pathlib import Path


EVAL_DIR = Path(__file__).resolve().parents[1] / "evals"
SPEC = importlib.util.spec_from_file_location("eval_score", EVAL_DIR / "score.py")
score = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(score)


def test_cases_are_25_unique_and_well_formed():
    cases = score.read_jsonl(EVAL_DIR / "cases.jsonl")
    assert len(cases) == 25
    assert len({case["id"] for case in cases}) == 25
    assert {case["expected_recommendation"] for case in cases} == {"GO", "PIVOT", "KILL"}
    assert all(len(case["expected_risks"]) == 3 for case in cases)


def test_scorer_rewards_observable_multi_agent_coverage():
    case = {
        "id": "E99",
        "expected_recommendation": "GO",
        "expected_risks": ["privacy", "hallucination"],
        "required_prd_sections": ["background", "risk"],
        "stress_perspectives": ["user", "compliance"],
    }
    record = {
        "case_id": "E99",
        "decision": {"recommendation": "GO", "risks": ["privacy"]},
        "prd": "background\nrisk\nhallucination",
        "stress_test": [{"role": "user"}, {"role": "compliance"}],
        "citations": [{"chunk_id": "1"}],
    }
    result = score.score_record(case, record)
    assert result == {
        "case_id": "E99",
        "decision_correct": True,
        "risk_coverage": 1.0,
        "prd_section_coverage": 1.0,
        "stress_coverage": 1.0,
        "has_citations": True,
    }


def test_scorer_recognises_chinese_stress_roles():
    stress = [
        {"role": "真实用户"},
        {"role": "竞品分析师"},
        {"role": "合规/风控专家"},
    ]
    assert score.has_stress_perspective(stress, "user")
    assert score.has_stress_perspective(stress, "competitor")
    assert score.has_stress_perspective(stress, "compliance")
