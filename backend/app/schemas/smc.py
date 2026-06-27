"""
SMC Schemas — Pydantic models for the /smc/analyze endpoint.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SMCRequest(BaseModel):
    """Request for running SMC analysis on a specific stock."""

    symbol: str = Field(..., description="Stock symbol, e.g. 'RELIANCE'")
    strategies: list[str] = Field(
        default=["fvg", "liquidity_sweep", "order_flow", "avwap", "volume_profile"],
        description="List of SMC strategies to run: fvg, liquidity_sweep, order_flow, avwap, volume_profile",
    )


class SMCResponse(BaseModel):
    """Response from the SMC analysis endpoint."""

    symbol: str
    current_price: Optional[float] = None
    strategies_requested: list[str] = []
    strategies_results: dict = Field(
        default_factory=dict, description="Results per strategy key"
    )
    smc_score: float = Field(0, description="Overall SMC score (0-100)")
    smc_signal: str = Field(
        "NEUTRAL", description="STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL"
    )
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
