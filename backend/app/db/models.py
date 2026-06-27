from typing import Optional
import datetime
import decimal
import uuid
import os

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Double,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy import JSON, Integer

if "postgresql" in os.getenv("DATABASE_URL", "") or "postgres" in os.getenv(
    "DATABASE_URL", ""
):
    from sqlalchemy.dialects.postgresql import JSONB, OID

    _IS_PG = True
else:
    JSONB = JSON
    OID = Integer
    _IS_PG = False
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# For UUID primary keys: use uuid_generate_v4() on Postgres, Python-side uuid4 on SQLite
_uuid_server_default = text("uuid_generate_v4()") if _IS_PG else None


class Base(DeclarativeBase):
    pass


class AgentPerformanceStats(Base):
    __tablename__ = "agent_performance_stats"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="agent_performance_stats_pkey"),
        UniqueConstraint(
            "period_start",
            "period_end",
            "agent_name",
            name="agent_performance_stats_period_start_period_end_agent_name_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    total_signals: Mapped[Optional[int]] = mapped_column(Integer)
    correct_signals: Mapped[Optional[int]] = mapped_column(Integer)
    accuracy_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    avg_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2))
    overconfident_count: Mapped[Optional[int]] = mapped_column(Integer)
    underconfident_count: Mapped[Optional[int]] = mapped_column(Integer)
    avg_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    total_retries: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True), server_default=text("CURRENT_TIMESTAMP")
    )


class EconomicSnapshots(Base):
    __tablename__ = "economic_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="economic_snapshots_pkey"),
        UniqueConstraint("snapshot_date", name="economic_snapshots_snapshot_date_key"),
        Index("idx_econ_date", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    repo_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    cpi: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    wpi: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    gdp_growth: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    fii_net_flow: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))
    dii_net_flow: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))
    usd_inr: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    crude_oil: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 2))
    gold_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    india_vix: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    us_fed_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    fiscal_deficit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    nifty_level: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    nifty_change_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    advance_decline_ratio: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(5, 2)
    )
    economic_score: Mapped[Optional[int]] = mapped_column(Integer)
    economic_regime: Mapped[Optional[str]] = mapped_column(Text)
    llm_analysis: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True), server_default=text("CURRENT_TIMESTAMP")
    )


class MarketRegimes(Base):
    __tablename__ = "market_regimes"
    # Note: F1 final regimes are BULL/SIDEWAYS/BEAR/CRISIS. SQLite ignores check constraints.
    # For Postgres, run:
    #   ALTER TABLE market_regimes DROP CONSTRAINT market_regimes_regime_check;
    #   ALTER TABLE market_regimes ADD CONSTRAINT market_regimes_regime_check
    #     CHECK (regime = ANY (ARRAY['BULL','SIDEWAYS','BEAR','CRISIS','VOLATILE']));
    __table_args__ = (
        CheckConstraint(
            "regime IN ('BULL', 'SIDEWAYS', 'BEAR', 'CRISIS', 'VOLATILE')",
            name="market_regimes_regime_check",
        ),
        PrimaryKeyConstraint("id", name="market_regimes_pkey"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Double(53))
    triggers: Mapped[Optional[dict]] = mapped_column(JSONB)
    market_pulse_score: Mapped[Optional[int]] = mapped_column(Integer)
    evaluated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )


class PerformanceAnalysis(Base):
    __tablename__ = "performance_analysis"
    __table_args__ = (
        CheckConstraint(
            "analysis_type IN ('LOSS_PATTERN', 'WIN_PATTERN', 'AGENT_BIAS', 'SECTOR_WEAKNESS', 'HORIZON_ISSUE', 'REGIME_MISMATCH', 'IMPROVEMENT_SUGGESTION')",
            name="performance_analysis_analysis_type_check",
        ),
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="performance_analysis_severity_check",
        ),
        PrimaryKeyConstraint("id", name="performance_analysis_pkey"),
        Index("idx_perf_analysis_date", "analysis_date"),
        Index("idx_perf_analysis_severity", "severity"),
        Index("idx_perf_analysis_type", "analysis_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    analysis_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    analysis_type: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_description: Mapped[str] = mapped_column(Text, nullable=False)
    trades_analyzed: Mapped[Optional[int]] = mapped_column(Integer)
    win_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    avg_pnl_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    affected_trades: Mapped[Optional[dict]] = mapped_column(JSONB)
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[Optional[str]] = mapped_column(Text)
    is_addressed: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default=text("false")
    )
    addressed_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True), server_default=text("CURRENT_TIMESTAMP")
    )


t_pg_stat_statements = Table(
    "pg_stat_statements",
    Base.metadata,
    Column("userid", OID),
    Column("dbid", OID),
    Column("toplevel", Boolean),
    Column("queryid", BigInteger),
    Column("query", Text),
    Column("plans", BigInteger),
    Column("total_plan_time", Double(53)),
    Column("min_plan_time", Double(53)),
    Column("max_plan_time", Double(53)),
    Column("mean_plan_time", Double(53)),
    Column("stddev_plan_time", Double(53)),
    Column("calls", BigInteger),
    Column("total_exec_time", Double(53)),
    Column("min_exec_time", Double(53)),
    Column("max_exec_time", Double(53)),
    Column("mean_exec_time", Double(53)),
    Column("stddev_exec_time", Double(53)),
    Column("rows", BigInteger),
    Column("shared_blks_hit", BigInteger),
    Column("shared_blks_read", BigInteger),
    Column("shared_blks_dirtied", BigInteger),
    Column("shared_blks_written", BigInteger),
    Column("local_blks_hit", BigInteger),
    Column("local_blks_read", BigInteger),
    Column("local_blks_dirtied", BigInteger),
    Column("local_blks_written", BigInteger),
    Column("temp_blks_read", BigInteger),
    Column("temp_blks_written", BigInteger),
    Column("shared_blk_read_time", Double(53)),
    Column("shared_blk_write_time", Double(53)),
    Column("local_blk_read_time", Double(53)),
    Column("local_blk_write_time", Double(53)),
    Column("temp_blk_read_time", Double(53)),
    Column("temp_blk_write_time", Double(53)),
    Column("wal_records", BigInteger),
    Column("wal_fpi", BigInteger),
    Column("wal_bytes", Numeric),
    Column("jit_functions", BigInteger),
    Column("jit_generation_time", Double(53)),
    Column("jit_inlining_count", BigInteger),
    Column("jit_inlining_time", Double(53)),
    Column("jit_optimization_count", BigInteger),
    Column("jit_optimization_time", Double(53)),
    Column("jit_emission_count", BigInteger),
    Column("jit_emission_time", Double(53)),
    Column("jit_deform_count", BigInteger),
    Column("jit_deform_time", Double(53)),
    Column("stats_since", DateTime(True)),
    Column("minmax_stats_since", DateTime(True)),
)


t_pg_stat_statements_info = Table(
    "pg_stat_statements_info",
    Base.metadata,
    Column("dealloc", BigInteger),
    Column("stats_reset", DateTime(True)),
)


class Stocks(Base):
    __tablename__ = "stocks"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="stocks_pkey"),
        UniqueConstraint("symbol", name="stocks_symbol_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(Text)
    exchange: Mapped[Optional[str]] = mapped_column(Text)

    alerts: Mapped[list["Alerts"]] = relationship("Alerts", back_populates="stock")
    runs: Mapped[list["Runs"]] = relationship("Runs", back_populates="stock")
    stock_historical_data: Mapped[list["StockHistoricalData"]] = relationship(
        "StockHistoricalData", back_populates="stock"
    )
    watchlist: Mapped[list["Watchlist"]] = relationship(
        "Watchlist", back_populates="stock"
    )
    recommendations: Mapped[list["Recommendations"]] = relationship(
        "Recommendations", back_populates="stock"
    )


class Users(Base):
    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="users_pkey"),
        UniqueConstraint("email", name="users_email_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    name: Mapped[Optional[str]] = mapped_column(Text)

    alerts: Mapped[list["Alerts"]] = relationship("Alerts", back_populates="user")
    dashboard_snapshots: Mapped[list["DashboardSnapshots"]] = relationship(
        "DashboardSnapshots", back_populates="user"
    )
    portfolio_holdings: Mapped[list["PortfolioHoldings"]] = relationship(
        "PortfolioHoldings", back_populates="user"
    )
    watchlist: Mapped[list["Watchlist"]] = relationship(
        "Watchlist", back_populates="user"
    )
    portfolio_transactions: Mapped[list["PortfolioTransactions"]] = relationship(
        "PortfolioTransactions", back_populates="user"
    )
    paper_trades: Mapped[list["PaperTrades"]] = relationship(
        "PaperTrades", back_populates="user"
    )


class Alerts(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('TARGET_HIT', 'STOP_LOSS', 'SENTIMENT_DROP', 'NEWS_SPIKE', 'REVIEW_NEEDED')",
            name="alerts_alert_type_check",
        ),
        ForeignKeyConstraint(
            ["stock_id"], ["stocks.id"], ondelete="CASCADE", name="alerts_stock_id_fkey"
        ),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="alerts_user_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="alerts_pkey"),
        Index("idx_alerts_user_is_read", "user_id", "is_read"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    alert_type: Mapped[Optional[str]] = mapped_column(Text)
    message: Mapped[Optional[str]] = mapped_column(Text)
    is_read: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default=text("false")
    )
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )

    stock: Mapped[Optional["Stocks"]] = relationship("Stocks", back_populates="alerts")
    user: Mapped[Optional["Users"]] = relationship("Users", back_populates="alerts")


class DashboardSnapshots(Base):
    __tablename__ = "dashboard_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="dashboard_snapshots_user_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="dashboard_snapshots_pkey"),
        UniqueConstraint(
            "snapshot_date",
            "user_id",
            name="dashboard_snapshots_snapshot_date_user_id_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    total_trades: Mapped[Optional[int]] = mapped_column(Integer)
    open_trades: Mapped[Optional[int]] = mapped_column(Integer)
    closed_trades: Mapped[Optional[int]] = mapped_column(Integer)
    win_count: Mapped[Optional[int]] = mapped_column(Integer)
    loss_count: Mapped[Optional[int]] = mapped_column(Integer)
    win_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    total_pnl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))
    total_pnl_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    best_trade_symbol: Mapped[Optional[str]] = mapped_column(Text)
    best_trade_pnl_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    worst_trade_symbol: Mapped[Optional[str]] = mapped_column(Text)
    worst_trade_pnl_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(6, 2)
    )
    avg_hold_duration_hours: Mapped[Optional[int]] = mapped_column(Integer)
    sector_exposure: Mapped[Optional[dict]] = mapped_column(JSONB)
    regime_at_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    economic_score_at_snapshot: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True), server_default=text("CURRENT_TIMESTAMP")
    )

    user: Mapped[Optional["Users"]] = relationship(
        "Users", back_populates="dashboard_snapshots"
    )


class PortfolioHoldings(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="portfolio_holdings_user_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="portfolio_holdings_pkey"),
        UniqueConstraint(
            "user_id", "symbol", name="portfolio_holdings_user_id_symbol_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default=text("0")
    )
    avg_buy_price: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default=text("0")
    )
    total_invested: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default=text("0")
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    company_name: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )

    user: Mapped[Optional["Users"]] = relationship(
        "Users", back_populates="portfolio_holdings"
    )
    portfolio_transactions: Mapped[list["PortfolioTransactions"]] = relationship(
        "PortfolioTransactions", back_populates="holding"
    )


class Runs(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('STARTED', 'COMPLETED', 'FAILED')", name="runs_status_check"
        ),
        ForeignKeyConstraint(["stock_id"], ["stocks.id"], name="runs_stock_id_fkey"),
        PrimaryKeyConstraint("id", name="runs_pkey"),
        Index("idx_runs_stock", "stock_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    workflow_name: Mapped[Optional[str]] = mapped_column(Text)
    workflow_config: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    stock: Mapped[Optional["Stocks"]] = relationship("Stocks", back_populates="runs")
    agent_logs: Mapped[list["AgentLogs"]] = relationship(
        "AgentLogs", back_populates="run"
    )
    discovery_results: Mapped[list["DiscoveryResults"]] = relationship(
        "DiscoveryResults", back_populates="run"
    )
    recommendations: Mapped[list["Recommendations"]] = relationship(
        "Recommendations", back_populates="run"
    )
    paper_trades: Mapped[list["PaperTrades"]] = relationship(
        "PaperTrades", back_populates="run"
    )


class StockHistoricalData(Base):
    __tablename__ = "stock_historical_data"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
            ondelete="CASCADE",
            name="stock_historical_data_stock_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="stock_historical_data_pkey"),
        UniqueConstraint(
            "stock_id", "date", name="stock_historical_data_stock_id_date_key"
        ),
        Index("idx_historical_stock_date", "stock_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    open: Mapped[Optional[float]] = mapped_column(Double(53))
    high: Mapped[Optional[float]] = mapped_column(Double(53))
    low: Mapped[Optional[float]] = mapped_column(Double(53))
    close: Mapped[Optional[float]] = mapped_column(Double(53))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    fetched_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )

    stock: Mapped[Optional["Stocks"]] = relationship(
        "Stocks", back_populates="stock_historical_data"
    )


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stock_id"],
            ["stocks.id"],
            ondelete="CASCADE",
            name="watchlist_stock_id_fkey",
        ),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="watchlist_user_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="watchlist_pkey"),
        UniqueConstraint("user_id", "stock_id", name="watchlist_user_id_stock_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )

    stock: Mapped[Optional["Stocks"]] = relationship(
        "Stocks", back_populates="watchlist"
    )
    user: Mapped[Optional["Users"]] = relationship("Users", back_populates="watchlist")


class AgentLogs(Base):
    __tablename__ = "agent_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILED')", name="agent_logs_status_check"
        ),
        ForeignKeyConstraint(
            ["run_id"], ["runs.id"], ondelete="CASCADE", name="agent_logs_run_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="agent_logs_pkey"),
        Index("idx_agent_logs_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    agent_name: Mapped[Optional[str]] = mapped_column(Text)
    agent_type: Mapped[Optional[str]] = mapped_column(Text)
    agent_version: Mapped[Optional[str]] = mapped_column(Text)
    input: Mapped[Optional[dict]] = mapped_column(JSONB)
    output: Mapped[Optional[dict]] = mapped_column(JSONB)
    reasoning: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_final: Mapped[Optional[bool]] = mapped_column(
        Boolean, server_default=text("false")
    )
    status: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    latency_ms: Mapped[Optional[float]] = mapped_column(Double(53))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
    model_used: Mapped[Optional[str]] = mapped_column(Text)
    signal: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2))
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer)
    retry_count: Mapped[Optional[int]] = mapped_column(
        Integer, server_default=text("0")
    )
    prompt_template: Mapped[Optional[str]] = mapped_column(Text)
    raw_llm_response: Mapped[Optional[str]] = mapped_column(Text)
    cost_usd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))

    run: Mapped[Optional["Runs"]] = relationship("Runs", back_populates="agent_logs")


class DiscoveryResults(Base):
    __tablename__ = "discovery_results"
    __table_args__ = (
        CheckConstraint(
            "horizon IN ('SHORT', 'MID', 'LONG')",
            name="discovery_results_horizon_check",
        ),
        ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            ondelete="CASCADE",
            name="discovery_results_run_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="discovery_results_pkey"),
        UniqueConstraint(
            "run_id",
            "horizon",
            "symbol",
            name="discovery_results_run_horizon_symbol_key",
        ),
        Index("idx_disc_cycle_horizon", "cycle_date", "horizon"),
        Index("idx_disc_symbol", "symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cycle_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    horizon: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    discovery_score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    regime: Mapped[Optional[str]] = mapped_column(Text)
    sector: Mapped[Optional[str]] = mapped_column(Text)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    suggested_hold_days: Mapped[Optional[int]] = mapped_column(Integer)
    risk_flags: Mapped[Optional[dict]] = mapped_column(JSONB)
    catalyst: Mapped[Optional[str]] = mapped_column(Text)
    raw_screener: Mapped[Optional[dict]] = mapped_column(JSONB)
    entry_price: Mapped[Optional[float]] = mapped_column(Double(53))
    indicative_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    stop_loss: Mapped[Optional[float]] = mapped_column(Double(53))
    probability: Mapped[Optional[int]] = mapped_column(Integer)
    risk_reward_ratio: Mapped[Optional[float]] = mapped_column(Double(53))
    cost_per_cycle: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))

    run: Mapped["Runs"] = relationship("Runs", back_populates="discovery_results")


class PortfolioTransactions(Base):
    __tablename__ = "portfolio_transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('BUY', 'SELL')",
            name="portfolio_transactions_transaction_type_check",
        ),
        ForeignKeyConstraint(
            ["holding_id"],
            ["portfolio_holdings.id"],
            ondelete="SET NULL",
            name="portfolio_transactions_holding_id_fkey",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="portfolio_transactions_user_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="portfolio_transactions_pkey"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    price: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    total_value: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    holding_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    realized_pnl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )

    holding: Mapped[Optional["PortfolioHoldings"]] = relationship(
        "PortfolioHoldings", back_populates="portfolio_transactions"
    )
    user: Mapped[Optional["Users"]] = relationship(
        "Users", back_populates="portfolio_transactions"
    )


class Recommendations(Base):
    __tablename__ = "recommendations"
    # F2 final: WAIT signal added. SQLite ignores check constraints.
    # For Postgres, run:
    #   ALTER TABLE recommendations DROP CONSTRAINT recommendations_recommendation_check;
    #   ALTER TABLE recommendations ADD CONSTRAINT recommendations_recommendation_check
    #     CHECK (recommendation = ANY (ARRAY['BUY','SELL','HOLD','WAIT']));
    __table_args__ = (
        CheckConstraint(
            "recommendation IN ('BUY', 'SELL', 'HOLD', 'WAIT')",
            name="recommendations_recommendation_check",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'TARGET_HIT', 'STOP_LOSS_HIT', 'EXPIRED', 'CANCELLED')",
            name="recommendations_status_check",
        ),
        ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            ondelete="CASCADE",
            name="recommendations_run_id_fkey",
        ),
        ForeignKeyConstraint(
            ["stock_id"], ["stocks.id"], name="recommendations_stock_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="recommendations_pkey"),
        Index("idx_recommendations_stock", "stock_id"),
        Index("idx_recommendations_time", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    recommendation: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Double(53))
    entry_price: Mapped[Optional[float]] = mapped_column(Double(53))
    target_price: Mapped[Optional[float]] = mapped_column(Double(53))
    stop_loss: Mapped[Optional[float]] = mapped_column(Double(53))
    timeframe: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'ACTIVE'"))
    reasoning: Mapped[Optional[dict]] = mapped_column(JSONB)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )

    # ── F1/F2 final columns ────────────────────────────────────
    horizon: Mapped[Optional[str]] = mapped_column(Text)
    horizon_override_reason: Mapped[Optional[str]] = mapped_column(Text)

    # F1 pass-through
    f1_horizon: Mapped[Optional[str]] = mapped_column(Text)
    f1_catalyst: Mapped[Optional[str]] = mapped_column(Text)
    f1_reasoning: Mapped[Optional[str]] = mapped_column(Text)

    # Stage 1 — per-agent signals
    technical_signal: Mapped[Optional[str]] = mapped_column(Text)
    technical_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(4, 3)
    )
    technical_narrative: Mapped[Optional[str]] = mapped_column(Text)
    fundamental_signal: Mapped[Optional[str]] = mapped_column(Text)
    fundamental_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(4, 3)
    )
    fundamental_narrative: Mapped[Optional[str]] = mapped_column(Text)
    sentiment_signal: Mapped[Optional[str]] = mapped_column(Text)
    sentiment_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(4, 3)
    )
    sentiment_narrative: Mapped[Optional[str]] = mapped_column(Text)
    chart_signal: Mapped[Optional[str]] = mapped_column(Text)
    chart_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(4, 3))
    chart_narrative: Mapped[Optional[str]] = mapped_column(Text)

    # Stage 3 — Debate
    debate_bull_case: Mapped[Optional[str]] = mapped_column(Text)
    debate_bear_case: Mapped[Optional[str]] = mapped_column(Text)
    debate_agrees: Mapped[Optional[bool]] = mapped_column(Boolean)
    debate_synthesis: Mapped[Optional[str]] = mapped_column(Text)
    debate_missed_risks: Mapped[Optional[dict]] = mapped_column(JSONB)
    debate_signal: Mapped[Optional[str]] = mapped_column(Text)
    debate_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(4, 3))

    # Stage 4 — Decision
    final_signal: Mapped[Optional[str]] = mapped_column(Text)
    final_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(4, 3))
    key_risks: Mapped[Optional[dict]] = mapped_column(JSONB)
    key_catalysts: Mapped[Optional[dict]] = mapped_column(JSONB)
    agent_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB)
    final_narrative: Mapped[Optional[str]] = mapped_column(Text)
    horizon_days: Mapped[Optional[int]] = mapped_column(Integer)

    # Stage 4b — Validator
    validator_issues: Mapped[Optional[dict]] = mapped_column(JSONB)
    validator_status: Mapped[Optional[str]] = mapped_column(Text)

    # Sizing + ratios
    position_size_pct: Mapped[Optional[float]] = mapped_column(Double(53))
    risk_reward: Mapped[Optional[float]] = mapped_column(Double(53))

    # Cost tracking
    cost_per_analysis: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 4))
    cost_per_analysis_inr: Mapped[Optional[decimal.Decimal]] = mapped_column(
        Numeric(10, 2)
    )

    # Full serialized response — enables lossless DB round-trip for history/fallback
    full_response: Mapped[Optional[dict]] = mapped_column(JSONB)

    # F1 pass-through — sector/industry from screener (migration: add_sector_industry_to_recommendations.sql)
    sector: Mapped[Optional[str]] = mapped_column(Text)
    industry: Mapped[Optional[str]] = mapped_column(Text)

    run: Mapped[Optional["Runs"]] = relationship(
        "Runs", back_populates="recommendations"
    )
    stock: Mapped[Optional["Stocks"]] = relationship(
        "Stocks", back_populates="recommendations"
    )
    paper_trades: Mapped[list["PaperTrades"]] = relationship(
        "PaperTrades", back_populates="recommendation"
    )
    recommendation_updates: Mapped[list["RecommendationUpdates"]] = relationship(
        "RecommendationUpdates", back_populates="recommendation"
    )


class PaperTrades(Base):
    __tablename__ = "paper_trades"
    __table_args__ = (
        CheckConstraint("action IN ('BUY', 'SELL')", name="paper_trades_action_check"),
        CheckConstraint(
            "horizon IN ('SHORT', 'MEDIUM', 'LONG')", name="paper_trades_horizon_check"
        ),
        CheckConstraint(
            "status IN ('OPEN', 'CLOSED', 'STOPPED_OUT', 'MONITOR_EXIT', 'EXPIRED')",
            name="paper_trades_status_check",
        ),
        ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            ondelete="SET NULL",
            name="paper_trades_recommendation_id_fkey",
        ),
        ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            ondelete="SET NULL",
            name="paper_trades_run_id_fkey",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="paper_trades_user_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="paper_trades_pkey"),
        Index("idx_paper_trades_opened", "opened_at"),
        Index("idx_paper_trades_status", "status"),
        Index("idx_paper_trades_symbol", "symbol"),
        Index("idx_paper_trades_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entry_price: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    recommendation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    target_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    stop_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    position_value: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))
    status: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'OPEN'"))
    exit_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    pnl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    pnl_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    ai_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2))
    horizon: Mapped[Optional[str]] = mapped_column(Text)
    sector: Mapped[Optional[str]] = mapped_column(Text)
    entry_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    debate_notes: Mapped[Optional[str]] = mapped_column(Text)
    opened_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True), server_default=text("CURRENT_TIMESTAMP")
    )
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    close_reason: Mapped[Optional[str]] = mapped_column(Text)
    max_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    max_profit_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    hold_duration_hours: Mapped[Optional[int]] = mapped_column(Integer)

    recommendation: Mapped[Optional["Recommendations"]] = relationship(
        "Recommendations", back_populates="paper_trades"
    )
    run: Mapped[Optional["Runs"]] = relationship("Runs", back_populates="paper_trades")
    user: Mapped[Optional["Users"]] = relationship(
        "Users", back_populates="paper_trades"
    )
    trade_monitor_logs: Mapped[list["TradeMonitorLogs"]] = relationship(
        "TradeMonitorLogs", back_populates="trade"
    )


class RecommendationUpdates(Base):
    __tablename__ = "recommendation_updates"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('BUY', 'SELL')",
            name="recommendation_updates_direction_check",
        ),
        ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            ondelete="CASCADE",
            name="recommendation_updates_recommendation_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="recommendation_updates_pkey"),
        Index("idx_updates_rec_id", "recommendation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    recommendation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    current_price: Mapped[Optional[float]] = mapped_column(Double(53))
    return_percentage: Mapped[Optional[float]] = mapped_column(Double(53))
    direction: Mapped[Optional[str]] = mapped_column(Text)
    evaluated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )

    recommendation: Mapped[Optional["Recommendations"]] = relationship(
        "Recommendations", back_populates="recommendation_updates"
    )


class TradeMonitorLogs(Base):
    __tablename__ = "trade_monitor_logs"
    __table_args__ = (
        CheckConstraint(
            "action_taken IN ('HOLD', 'TIGHTEN_SL', 'MOVE_TARGET', 'EXIT', 'NO_ACTION')",
            name="trade_monitor_logs_action_taken_check",
        ),
        ForeignKeyConstraint(
            ["trade_id"],
            ["paper_trades.id"],
            ondelete="CASCADE",
            name="trade_monitor_logs_trade_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="trade_monitor_logs_pkey"),
        Index("idx_monitor_time", "checked_at"),
        Index("idx_monitor_trade", "trade_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=_uuid_server_default
    )
    trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True), server_default=text("CURRENT_TIMESTAMP")
    )
    current_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    unrealized_pnl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    unrealized_pnl_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    market_regime: Mapped[Optional[str]] = mapped_column(Text)
    vix_at_check: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    action_taken: Mapped[Optional[str]] = mapped_column(Text)
    old_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    new_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    old_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    new_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(12, 2))
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    model_used: Mapped[Optional[str]] = mapped_column(Text)

    trade: Mapped[Optional["PaperTrades"]] = relationship(
        "PaperTrades", back_populates="trade_monitor_logs"
    )
