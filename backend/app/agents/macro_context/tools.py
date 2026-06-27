"""
Macro Context Agent — Tools
"""

from app.services.macro_service import get_indian_macro_data
from app.services.news_service import get_macro_headlines


def fetch_macro_context() -> dict:
    """Combines Indian economic data and Macro News."""
    return {"economy": get_indian_macro_data(), "headlines": get_macro_headlines()}
