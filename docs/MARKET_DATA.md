# Market-data integration

Commands such as `stock IBM`, `market data AAPL`, `quote TSLA` and
`what is the stock price of SHOP.TO` use the Alpha Vantage `TIME_SERIES_DAILY` endpoint
([documentation](https://www.alphavantage.co/documentation/#daily)). The result is raw,
unadjusted **daily end-of-day** data, **not** a live or 15-minute-delayed quote. The compact
response covers up to the latest 100 daily observations.

## Setup

Put `ALPHA_VANTAGE_API_KEY` in `.env`. The market-data fetch does not need the AI key: without
it you still get the source facts and calculations, and a note that AI commentary is
unavailable.

## What the answer contains

The result keeps three things strictly apart:

- **Source facts**: provider and reference, date-only observation date, UTC retrieval time,
  data and adjustment status, freshness, and the OHLCV values.
- **Derived metrics** calculated by AURIX: close-to-close change and percentage change,
  `((latest_close - previous_close) / previous_close) * 100`, rounded to two decimals. They are
  never presented as provider-reported.
- **AI commentary** (optional): at most about 120 words, given only the facts and metrics,
  forbidden from forecasting, advice or outside facts.

Unknown currency or exchange stays "unknown". A five-minute in-memory cache is on by default;
cache hits keep the original retrieval time and recompute freshness. Set
`AURIX_MARKET_DATA_CACHE_TTL_SECONDS=0` to disable it.

## Limits

- No exchange calendar: an old bar may be a holiday, an outage, or missing data, and AURIX
  cannot tell which. Freshness is an age threshold (`AURIX_MARKET_DATA_MAX_AGE_DAYS`), not proof
  that a market is open.
- Alpha Vantage's free tier documents a small daily quota; real-time US quotes are premium.
  Check the current plan and licence terms before commercial use.
- AI commentary is not verified claim by claim. This is information, not financial advice.
- Tests use mocked provider data; no live request is made without credentials.
