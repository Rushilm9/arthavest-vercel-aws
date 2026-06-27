"""
SMC Routes — FastAPI endpoints for Smart Money Concepts analysis.
Separate API from the main /analysis routes.
"""

from fastapi import APIRouter, HTTPException, status
from app.schemas.smc import SMCRequest, SMCResponse
from app.agents.technical.smc_tools import run_smc_analysis
from app.core.config import logger

router = APIRouter(prefix="/smc", tags=["Smart Money Concepts"])

VALID_STRATEGIES = {"fvg", "liquidity_sweep", "order_flow", "avwap", "volume_profile"}


@router.post("/analyze", response_model=SMCResponse)
def smc_analyze(request: SMCRequest):
    """
    Run Smart Money Concepts (SMC) analysis on a specific stock.

    Strategies available:
    - **fvg**: Fair Value Gaps (3-candle imbalance detection)
    - **liquidity_sweep**: Liquidity Sweeps (stop hunts at swing pivots)
    - **order_flow**: Order Flow approximation via Chaikin Money Flow (CMF)
    - **avwap**: Anchored VWAP from highest volume day
    - **volume_profile**: Volume Profile with POC and Value Area

    You can select one or more strategies. They run in sequence on the
    same OHLCV dataset (downloaded once from yfinance).
    """
    symbol = request.symbol.upper().strip()
    strategies = [s.lower().strip() for s in request.strategies]

    # Validate strategies
    invalid = [s for s in strategies if s not in VALID_STRATEGIES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid strategies: {invalid}. Valid options: {sorted(VALID_STRATEGIES)}",
        )

    if not strategies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one strategy must be selected.",
        )

    logger.info(
        f"[bold cyan]API: /smc/analyze hit for {symbol} with {strategies}[/bold cyan]"
    )

    try:
        result = run_smc_analysis(symbol=symbol, strategies=strategies)

        if result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=result["error"]
            )

        response = SMCResponse(
            symbol=result["symbol"],
            current_price=result.get("current_price"),
            strategies_requested=result["strategies_requested"],
            strategies_results=result["strategies_results"],
            smc_score=result["smc_score"],
            smc_signal=result["smc_signal"],
        )

        logger.info(
            f"[bold green]API: /smc/analyze returned {result['smc_signal']} "
            f"for {symbol} (score: {result['smc_score']})[/bold green]"
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[bold red]API: /smc/analyze failed for {symbol} — {e}[/bold red]"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SMC analysis failed for {symbol}: {str(e)}",
        )
