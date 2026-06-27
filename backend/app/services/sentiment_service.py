"""
Sentiment Service — Wraps FinVADER for offline, free sentiment scoring fallback.
"""

try:
    from finvader import finvader

    _FINVADER_AVAILABLE = True
except ImportError:
    finvader = None
    _FINVADER_AVAILABLE = False
from app.core.config import logger


def score_headline(text: str) -> float:
    """
    Scores a financial text snippet using FinVADER.
    Returns:
        float: A composite sentiment score between -1.0 (extremely negative) and 1.0 (extremely positive).
    """
    if finvader is None:
        logger.warning(
            "[yellow]FinVADER is not installed; skipping headline scoring[/yellow]"
        )
        return 0.0
    try:
        # finvader requires the text, and parameters to use standard dictionaries
        score = finvader(
            text,
            use_sentibing=False,
            use_lm=True,  # Loughran-McDonald is critical for finance
            use_vader=True,
        )
        return float(score)

    except Exception as e:
        logger.warning(
            f"[yellow]FinVADER scoring failed for text '{text[:20]}...': {e}[/yellow]"
        )
        return 0.0
