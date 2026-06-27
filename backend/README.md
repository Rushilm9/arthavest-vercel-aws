<div align="center">
  <h1>ArthaVest — Backend</h1>
  <p><strong>FastAPI · SQLAlchemy · Amazon Aurora PostgreSQL · LangGraph · Amazon Bedrock (Claude)</strong></p>
  <p>Multi-agent AI pipeline with a fully auditable decision ledger</p>

  <p>
    <img src="https://img.shields.io/badge/Amazon-Aurora%20PostgreSQL-FF9900?style=for-the-badge&logo=amazon-rds&logoColor=white" alt="Aurora" />
    <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/LangGraph-Agent%20DAG-4285F4?style=for-the-badge" alt="LangGraph" />
    <img src="https://img.shields.io/badge/LLM-Amazon%20Bedrock%20(Claude)-FF9900?style=for-the-badge&logo=amazon-aws&logoColor=white" alt="Amazon Bedrock" />
  </p>
</div>

---

## Overview

The ArthaVest backend is a **FastAPI application** that orchestrates a multi-agent AI pipeline for Indian stock market analysis. Every decision — from individual agent signals to the final BUY/SELL/WAIT verdict — is persisted in **Amazon Aurora PostgreSQL**, creating a fully reconstructable audit trail.

## Architecture

```
Client Request
      │
      ▼
┌──────────────────────────────┐
│       FastAPI (Uvicorn)      │
│   REST API · Port 8000       │
├──────────────────────────────┤
│   Analysis Dispatcher        │  ← Orchestrates the full pipeline
│   ┌────────────────────────┐ │
│   │    LangGraph DAG       │ │
│   │  ┌──────┐ ┌──────┐    │ │
│   │  │ Tech │ │ Fund │    │ │  ← 4 Specialist Agents (Claude Haiku)
│   │  └──────┘ └──────┘    │ │
│   │  ┌──────┐ ┌──────┐    │ │
│   │  │ Sent │ │Chart │    │ │
│   │  └──────┘ └──────┘    │ │
│   │       ▼                │ │
│   │  Debate Engine         │ │  ← Adversarial review (Claude Sonnet)
│   │       ▼                │ │
│   │  3-Layer Validator     │ │  ← Geometric · Risk:Reward · Sanity
│   └────────────────────────┘ │
├──────────────────────────────┤
│    SQLAlchemy 2.0 ORM        │
│    psycopg2 (connection pool)│
└──────────┬───────────────────┘
           │ SQL/SSL
           ▼
┌──────────────────────────────┐
│  Amazon Aurora PostgreSQL    │
│  Serverless v2 · us-east-1  │
│  19 tables · 706+ records   │
│  sslmode=require             │
└──────────────────────────────┘
```

## Database Schema (Aurora PostgreSQL)

The 19-table normalized schema is the backbone of the platform. Key tables in the decision lineage:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `runs` | Top-level analysis run | `id`, `symbol`, `status`, `model`, `created_at` |
| `agent_logs` | Individual agent signals | `run_id` (FK), `agent_name`, `signal`, `confidence`, `latency_ms`, `full_output` (JSONB) |
| `recommendations` | Final AI verdict | `run_id` (FK), `recommendation`, `confidence`, `narrative`, `debate_summary`, `validator_status`, `full_response` (JSONB) |
| `paper_trades` | Tracked P&L | `recommendation_id` (FK), `entry_price`, `current_price`, `target`, `stop_loss`, `status` |
| `stocks` | Stock master data | `symbol`, `company_name`, `sector`, `market_cap` |
| `discovery_results` | Screening results | Multi-factor discovery output |
| `market_regimes` | Market condition tracking | `regime` (CHECK: BULL/BEAR/CRISIS/SIDEWAYS) |

**Schema highlights:**
- Foreign keys enforce referential integrity across the lineage
- JSONB columns store full LLM outputs for queryable introspection
- Check constraints enforce valid verdict types (`BUY`/`SELL`/`WAIT`/`HOLD`)
- Connection pooling: `pool_pre_ping=True`, `pool_recycle=300`, `pool_size=20`

## Key API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/api/analysis/run` | Trigger a full analysis pipeline for a stock |
| `GET` | `/api/analysis/history` | Paginated recommendation history with filters |
| `GET` | `/api/analysis/history/{id}` | Full recommendation detail with agent logs |
| `GET` | `/api/audit/{id}` | Decision audit trail (Aurora JOIN lineage) |
| `GET` | `/api/market/dashboard` | Market indices + portfolio summary |
| `GET` | `/api/market/news` | Paginated financial news feed |
| `GET` | `/api/discovery/scan` | Run stock discovery scanner |
| `POST` | `/auth/login` | User authentication |

## Environment Configuration

```dotenv
# Database — Amazon Aurora PostgreSQL
DATABASE_URL=postgresql://<user>:<password>@<cluster>.cluster-xxxx.<region>.rds.amazonaws.com:5432/arthavest?sslmode=require

# LLM — Amazon Bedrock (configured via IAM Role / Environment Variables)
AWS_ACCESS_KEY_ID=<your_aws_access_key>
AWS_SECRET_ACCESS_KEY=<your_aws_secret_access_key>
AWS_DEFAULT_REGION=us-east-1

# Feature flags (disabled for this hackathon)
ARIZE_ENABLED=false
ARIZE_MCP_ENABLED=false
USE_VERTEX=false
```

## Quick Start

```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate       # macOS/Linux

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Aurora connection string + AWS Bedrock configuration

# For Aurora: enable uuid extension
# psql: CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

# Run
uvicorn app.main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`

## Docker

```bash
docker build -t arthavest-backend .
docker run -p 8000:10000 --env-file .env arthavest-backend
```

The multi-stage Dockerfile produces a slim image (~200MB) with `libpq5` for Postgres connectivity and NLTK `vader_lexicon` for sentiment analysis.

## AWS Deployment (EC2)

The backend runs on an **AWS EC2 t3.small (Ubuntu 24.04)** instance in the same VPC as Aurora PostgreSQL, enabling private-network database access:

```bash
# On EC2
git clone <repo-url>
cd backend
pip install -r requirements.txt
# Set environment variables
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

<div align="center">
  <p><em>Part of the ArthaVest submission for H0: Hack the Zero Stack</em></p>
</div>
