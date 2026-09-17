"""AI Repository Overview / Architecture Map (Part 3).

Pipeline: snapshot → deterministic facts → graph/symbol data → redacted,
budgeted evidence → structured LLM synthesis → validated overview → PG.
The LLM synthesizes from supplied facts only; it never invents repository
facts. Observed facts, derived relationships, and AI summaries stay separate.
"""

OVERVIEW_PROMPT_VERSION = "overview-v1"
