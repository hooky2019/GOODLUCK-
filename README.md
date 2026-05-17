# 🍀 GOODLUCK $

Swing-trade dashboard for the Nasdaq 100 with a Gemini-powered agent. Tap a
button on your phone, get 3 short-term (3–10 day) trade ideas with plain-English
thesis, entry/stop/targets, risk-reward, position size, and an optional
defined-risk options play. Chat with Goodluck about any ticker right in the app.

## Quick start (local)

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit secrets.toml and add your GEMINI_API_KEY (free from https://aistudio.google.com/apikey)
streamlit run streamlit_app.py
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to https://share.streamlit.io → New app → pick the repo, main branch, `streamlit_app.py`.
3. In **Settings → Secrets**, paste:
   ```toml
   GEMINI_API_KEY = "AIza..."
   ALPHA_VANTAGE_KEY = "..."
   ```
4. Bookmark the public URL on your phone. Add to Home Screen for an app-like feel.

## What the agent does

Each refresh, the agent calls these tools in order:

1. `get_market_context` — SPY/QQQ trend, VIX, sector ETF performance.
2. `screen_universe` — narrows Nasdaq 100 to ~15 candidates by composite score.
3. For each candidate, `get_technicals`, `get_catalysts`, `get_options_snapshot`, `get_news`, `get_reddit_mentions`, `get_analyst_changes` as needed.
4. Returns top 3 picks with thesis, trade plan, risks, and optional options play, plus a market regime read.

Model: `gemini-2.0-flash`. Free tier covers ~1500 requests/day — enough for many refreshes plus chat each day.

## Data sources

- **yfinance** — prices, options, fundamentals (15-min delayed)
- **Reddit RSS** — r/stocks, r/wallstreetbets sentiment (no auth)
- **Google News RSS + Alpha Vantage** — recent news + sentiment
- **yfinance calendar** — earnings & ex-div dates

Quotes are 15 minutes delayed. The agent never recommends entries tighter than 0.3% of last print.

## Caveats

- Streamlit Cloud sleeps after 7 days idle; cold start ~30 s.
- A full refresh takes 30–90 s while the agent calls tools.
- Yahoo intermittently rate-limits cloud IPs; retries are built in but failures will happen.
- Nasdaq 100 constituents drift quarterly — list is hardcoded in `aurora/universe.py`.
- Gemini free tier has rate limits (15 RPM, 1500 req/day). Won't hit them unless you refresh constantly.

## Disclaimer

Educational tool. Not investment advice. Paper-trade before risking real money.
