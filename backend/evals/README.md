# PM Copilot benchmark

This benchmark contains 25 Chinese product-requirement cases across consumer AI, enterprise AI, industrial, commerce, healthcare, safety and developer-tool scenarios.

It tests the product claim that PM Copilot improves **decision quality and review coverage**, rather than merely generating longer documents.

## Evaluation protocol

Run each case twice with the same model, temperature and prompt version:

1. **Single-agent baseline**: one direct model call that returns a decision and PRD from the raw requirement. Do not use retrieval, clarification, Critic, Evaluator or Stress Test.
2. **PM Copilot multi-agent**: use the full pipeline with `skip_clarify=true`; keep the same raw requirement. Use no organization memory for the primary comparison. Run a separate RAG ablation when evaluating organization memory.

Save one JSON object per case in a JSONL file. Required shape:

```json
{
  "case_id": "E01",
  "decision": {"recommendation": "PIVOT", "reasoning": "...", "risks": ["..."]},
  "prd": "# PRD ...",
  "stress_test": [{"role": "user", "challenge": "..."}],
  "citations": []
}
```

The baseline may omit `stress_test` and `citations`. Do not hand-edit model outputs after collection; record prompt/model/version metadata in a separate experiment note.

## Score a comparison

```bash
python evals/score.py \
  --baseline evals/results/baseline.jsonl \
  --multi-agent evals/results/multi_agent.jsonl \
  --out evals/results/report.md
```

## Run the 5-case preflight

```bash
python evals/run_experiment.py --limit 5 --output-dir evals/results/preflight
python evals/score.py \
  --baseline evals/results/preflight/baseline.jsonl \
  --multi-agent evals/results/preflight/multi_agent.jsonl \
  --out evals/results/preflight/report.md
```

Use `--limit 0` only after the preflight succeeds. The runner writes each case
as soon as it completes, so partial outputs remain available if a later model
call fails.

The scorer reports:

- **Decision accuracy**: agreement with the pre-labelled GO/PIVOT/KILL decision.
- **Risk coverage**: coverage of case-specific critical risks across decision, PRD and review output.
- **PRD section coverage**: required sections present in the generated PRD.
- **Stress-test coverage**: expected review perspectives represented in red-team output.
- **Citation rate**: percentage of outputs that include memory citations. This is meaningful only in the separate RAG experiment.

## Portfolio-safe wording

Use the actual generated report values, for example: “On a 25-case internal benchmark, the multi-agent workflow improved risk coverage from X% to Y%.” Never write this sentence until the experiment has been run and the raw JSONL files are retained.
