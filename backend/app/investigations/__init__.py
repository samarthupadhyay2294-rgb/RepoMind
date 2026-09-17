"""AI Debug Investigator (Part 4/5).

Evidence-first debugging on top of the existing bounded LangGraph loop —
no parallel agent. Flow: redacted structured input → snapshot resolution →
debug-framed question → shared ``_run_graph`` → deterministic verdict
mapping → persisted investigation + actions. LLM output is evidence only;
verdicts derive from validated citations, never from model confidence.
"""

INVESTIGATION_PROMPT_VERSION = "investigate-v1"
