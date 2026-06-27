"""
LLM Singleton — backward-compat shim.
All agents should import from model_router instead:
    from app.core.model_router import get_model, ModelTier

get_llm() / get_json_llm() are kept so existing code doesn't break —
they delegate to ModelTier.FLASH now.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import logger
from app.core.model_router import get_model, ModelTier


def get_llm() -> ChatGoogleGenerativeAI:
    """Returns a FLASH-tier Gemini instance (backward compat)."""
    return get_model(ModelTier.FLASH)


def get_json_llm() -> ChatGoogleGenerativeAI:
    """Returns a FLASH-tier Gemini instance in JSON mode (backward compat)."""
    return get_model(ModelTier.FLASH, json_mode=True)


def log_llm_invocation(model_name: str, symbol: str, agent_name: str):
    logger.info(
        f"[bold magenta]LLM Invoked[/bold magenta] | "
        f"[cyan]{agent_name}[/cyan] | "
        f"Symbol: [bold white]{symbol}[/bold white] | "
        f"Model: [dim]{model_name}[/dim]"
    )


def extract_content(response) -> str:
    """
    Safely extract text from an LLM response.
    Gemini 3.x models can return response.content as a list of content blocks
    instead of a plain string. This helper normalises both cases.
    """
    content = response.content
    if isinstance(content, list):
        # Join text parts from the list of content blocks
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts).strip()
    return (content or "").strip()
