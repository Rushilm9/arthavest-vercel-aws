"""
Verdict — the single source of truth for the final BUY/SELL/WAIT label.

Why this module exists
----------------------
The final recommendation used to be normalized in several places independently
(`analysis.py::_verdict`, `analysis_dispatcher.py` inline, `_build_full_response`,
the decision node). Each boundary normalized — or *forgot* to normalize — on its
own, so the verdict a user saw could differ between the list badge, the detail
panel, and the narrative prose. The narrative was the worst offender: it is
written by an LLM that occasionally states a *different* decision than the one the
pipeline actually took (e.g. verdict BUY but the prose says "WAIT, overriding the
initial BUY"). See the decision node for where this is enforced.

Rules:
  * The user-facing verdict label space is exactly {BUY, SELL, WAIT}.
  * Anything neutral / unknown / legacy HOLD collapses to WAIT (a no-trade).
  * Specialist signals (technical/fundamental/sentiment/chart) and the debate's
    *independent* signal are NOT verdicts — do not pass them through here.
"""

import re

VERDICTS = ("BUY", "SELL", "WAIT")


def final_verdict(label) -> str:
    """Normalize a final recommendation to the BUY/SELL/WAIT label space.

    HOLD / None / unknown -> WAIT.
    """
    label = (label or "").upper().strip()
    return label if label in ("BUY", "SELL") else "WAIT"


def narrative_contradicts_verdict(narrative: str, verdict: str) -> bool:
    """True when the narrative's *stated decision* disagrees with the verdict.

    We only look at the explicit decision sentence the prompt is told to emit —
    'The final decision is to <b>WAIT</b>' / 'The final decision is a <b>BUY</b>'.
    A passing BUY narrative may still *mention* WAIT (e.g. "we would WAIT if it
    breaks support"), so we match the declared decision, not raw token counts.
    """
    if not narrative:
        return False
    verdict = final_verdict(verdict)
    text = narrative.upper()

    # Pull the verdict word out of the canonical "final decision is ..." clause.
    m = re.search(
        r"FINAL DECISION IS(?:\s+TO|\s+A|\s+AN)?\s*<?[A-Z]*>?\s*\**\s*(BUY|SELL|WAIT|HOLD)",
        text,
    )
    if not m:
        return False
    stated = final_verdict(m.group(1))
    return stated != verdict
