# V4.2 SQL-of-Thought Guided Correction Design

V4.2 upgrades SQL repair from a single free-form retry into a guided correction pipeline.

## Why Change

The previous implementation was:

```text
execute SQL -> failure -> send failed SQL and error message to sql_repair -> retry once
```

This can fix obvious syntax, missing table, and missing column errors, but it is weak for semantic Text-to-SQL errors such as wrong join paths, wrong filters, wrong aggregation, or wrong time ranges.

V4.2 follows the SQL-of-Thought idea: do not let one Agent blindly rewrite SQL. First diagnose the error, then create a repair plan, then rewrite SQL under that plan.

## Pipeline

```text
SQLGenerationAgent
  -> ValidationExecutionAgent
  -> SQLCorrectionPlanAgent
  -> SQLRepairAgent
  -> safety validation
  -> query execution
```

## Error Taxonomy

The first product version keeps a 9-category / 31-subtype taxonomy:

- SQL_SYNTAX
- SCHEMA_LINKING
- JOIN_PATH
- FILTER_CONDITION
- AGGREGATION
- VALUE_GROUNDING
- NESTED_QUERY
- SET_OPERATION
- RESULT_SHAPING

The taxonomy and planning logic live in `app/agents/sql_correction_plan.py`, because this step is an LLM-driven Agent decision.

## Structured Plan

`SQLCorrectionPlanAgent` returns JSON:

```json
{
  "error_category": "SCHEMA_LINKING",
  "error_subtype": "unknown_column",
  "evidence": "missing_column is not in schema",
  "repair_strategy": "Use orders.order_id and aggregate it correctly",
  "must_keep": ["original question", "read-only SQL"],
  "avoid": ["invented columns"],
  "confidence": 0.88
}
```

`SQLRepairAgent` receives this plan through the `sql_repair` prompt and must rewrite SQL according to it.

## Agent / Tool Boundary

- `app/agents/sql_correction_plan.py`: SQLCorrectionPlanAgent. It classifies the failure and creates a structured repair plan.
- `app/agents/sql_generation.py`: SQLGenerationAgent. It owns `GeneratedSQL`, prompt-based SQL generation, and demo fallback SQL.
- `app/agents/sql_repair.py`: SQLRepairAgent. It rewrites the failed SQL under the correction plan.
- `app/tools/sql_tool.py`: deterministic SQL helpers, including extraction, read-only validation, and LIMIT handling.
- `app/tools/query_tool.py`: deterministic query execution.

The rule is simple: if a module owns a prompt, reasoning step, or business decision, it belongs under `app/agents`. If it only performs a stable capability for an Agent, it belongs under `app/tools`.

## Engineering Safeguards

- If the LLM diagnosis fails or returns malformed JSON, the local deterministic classifier creates a fallback plan.
- Repaired SQL still goes through the same server-side read-only validation and LIMIT handling.
- Trace now records `sql_correction_plan`, making the correction chain observable.
- Prompt versions record both `sql_correction_plan@v1` and `sql_repair@v1` when the LLM diagnosis succeeds.

## Next Steps

- Add evaluation cases by error category.
- Surface the correction plan in the conversation timeline.
- Add semantic validation for executable-but-wrong SQL, such as empty-result diagnosis and metric consistency checks.
