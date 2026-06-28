<div align="center">
  <img src="LOGO/ArthVest%20logo.png" width="100" alt="ArthaVest Logo" />
  <h1>ArthaVest — Frontend</h1>
  <p><strong>React + Vite + TypeScript + Tailwind CSS</strong></p>
  <p>Deployed on <strong>Vercel</strong> · Prototyped with <strong>v0.dev</strong></p>
</div>

---

## Overview

The ArthaVest frontend is a **single-page application** that serves as the user-facing interface for the Aurora-backed AI investment-research platform. It connects to the FastAPI backend to display recommendations, audit trails, market data, and paper-trade performance — all reconstructed from Amazon Aurora PostgreSQL.

## Tech Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 19.x | UI framework |
| Vite | 8.x | Build tool & dev server |
| TypeScript | 6.x | Type safety |
| Tailwind CSS | 3.4 | Utility-first styling |
| React Router | 7.x | Client-side routing |
| TanStack Query | 5.x | Server state management |
| Axios | 1.x | HTTP client |
| Lucide React | 1.x | Icon library |

## Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Market indices, news feed, portfolio overview |
| `/discovery` | Discovery | Multi-factor stock screening |
| `/history` | History | Full recommendation ledger with filters |
| `/audit/:id` | **Audit Trail** | ★ Decision lineage from Aurora PostgreSQL |
| `/analyse` | Analysis | Deep-dive into individual stock analysis |
| `/login` | Login | User authentication |

## Design System

| Token | Value | Usage |
|-------|-------|-------|
| Primary Text | `#1C2A39` | Dark Navy — headings & body |
| Muted Text | `#5A6E85` | Steel Blue — secondary text |
| Accent | `#B85A10` | Golden Saffron — CTAs & highlights |
| BUY Signal | `#16A34A` | Green |
| SELL Signal | `#DC2626` | Red |
| WAIT Signal | `#B85A10` | Saffron |
| Background | `#F0F4F8` | Ice-blue page background |
| Body Font | Inter | `font-sans` |
| Data Font | JetBrains Mono | `font-mono` — prices, percentages, IDs |

## Getting Started

```bash
# Install dependencies
pnpm install

# Configure environment
cp .env.example .env
# Set VITE_API_BASE_URL to your backend URL

# Start dev server
pnpm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Vercel Deployment

This project is configured for **zero-config Vercel deployment**:

```json
{
  "framework": "vite",
  "buildCommand": "pnpm run build",
  "outputDirectory": "dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

Set `VITE_API_BASE_URL` in Vercel project environment variables.

## v0 Integration

The **Decision Audit Trail** page was prototyped using [Vercel v0](https://v0.dev) — generating the timeline layout, agent signal cards, and paper-trade P&L components using our design system tokens. The generated code was integrated into this Vite project and wired to the backend API.

---

<div align="center">
  <p><em>Part of the ArthaVest submission for H0: Hack the Zero Stack</em></p>
</div>
