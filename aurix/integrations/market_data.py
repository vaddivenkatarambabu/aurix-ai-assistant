"""Validated daily equity-market data from Alpha Vantage.

This integration deliberately provides end-of-day daily bars, not real-time quotes.
Provider observations retain date-only semantics; application retrieval timestamps are
stored separately in UTC. Source facts and application-derived calculations remain
separate objects so generated commentary cannot overwrite either.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from aurix.config import (
    ALPHA_VANTAGE_API_KEY,
    AURIX_MARKET_DATA_BASE_URL,
    AURIX_MARKET_DATA_CACHE_TTL_SECONDS,
    AURIX_MARKET_DATA_MAX_AGE_DAYS,
    AURIX_MARKET_DATA_MAX_RETRIES,
    AURIX_MARKET_DATA_TIMEOUT_SECONDS,
)

PROVIDER_NAME = "Alpha Vantage"
SOURCE_REFERENCE = "Alpha Vantage TIME_SERIES_DAILY"
SOURCE_URL = "https://www.alphavantage.co/documentation/#daily"
logger = logging.getLogger(__name__)
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$")
_SYMBOL_TEXT = r"([A-Za-z0-9][A-Za-z0-9._-]{0,19})"
_MARKET_COMMAND_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"^\s*(?:market(?:\s+data)?|stock(?:\s+(?:price|data))?|quote|price)\s+(?:for\s+)?{_SYMBOL_TEXT}\s*[?.!]*\s*$",
        rf"^\s*(?:show|get|fetch)\s+(?:market(?:\s+data)?|stock(?:\s+(?:price|data))?|quote|price)\s+(?:for\s+)?{_SYMBOL_TEXT}\s*[?.!]*\s*$",
        rf"^\s*(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:stock\s+)?price\s+of|(?:stock\s+)?price\s+of)\s+{_SYMBOL_TEXT}\s*[?.!]*\s*$",
    )
)


class MarketDataError(RuntimeError):
    """Base error for market-data configuration, provider, or validation failures."""


class MarketDataConfigurationError(MarketDataError):
    """Raised when required provider configuration is missing or invalid."""


class MarketDataProviderError(MarketDataError):
    """Raised when the upstream provider cannot return usable data."""


class MarketDataValidationError(MarketDataError):
    """Raised when provider data violates the expected daily-bar schema."""


def extract_market_data_symbol(command: str) -> str | None:
    """Return the ticker from an explicit market-data command, never from free chat."""
    if not isinstance(command, str):
        return None
    for pattern in _MARKET_COMMAND_PATTERNS:
        match = pattern.fullmatch(command)
        if match:
            return match.group(1).upper()
    return None


def _validate_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise MarketDataValidationError("Enter a ticker symbol, for example: stock IBM.")
    normalized = symbol.strip().upper()
    if not _SYMBOL_RE.fullmatch(normalized):
        raise MarketDataValidationError(
            "Invalid ticker format. Use a ticker such as IBM, AAPL, or SHOP.TRT."
        )
    return normalized


def _parse_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise MarketDataValidationError(f"The provider returned an invalid {field} value.")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise MarketDataValidationError(
            f"The provider returned an invalid {field} value."
        ) from exc
    if not result.is_finite() or result < 0:
        raise MarketDataValidationError(
            f"The provider returned an out-of-range {field} value."
        )
    return result


def _decimal_text(value: Decimal) -> str:
    """Serialize Decimal without binary-float conversion or unnecessary trailing zeros."""
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware.")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class DailyBar:
    observation_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @classmethod
    def from_provider_row(cls, raw_date: str, row: Mapping[str, Any]) -> "DailyBar":
        try:
            observed_on = date.fromisoformat(raw_date)
        except (TypeError, ValueError) as exc:
            raise MarketDataValidationError("The provider returned an invalid observation date.") from exc
        if not isinstance(row, Mapping):
            raise MarketDataValidationError("The provider returned a malformed daily observation.")

        opening = _parse_decimal(row.get("1. open"), "open price")
        high = _parse_decimal(row.get("2. high"), "high price")
        low = _parse_decimal(row.get("3. low"), "low price")
        close = _parse_decimal(row.get("4. close"), "close price")
        volume_decimal = _parse_decimal(row.get("5. volume"), "volume")
        if volume_decimal != volume_decimal.to_integral_value():
            raise MarketDataValidationError("The provider returned a non-integer volume value.")
        volume = int(volume_decimal)
        if low > high or low > min(opening, close) or high < max(opening, close):
            raise MarketDataValidationError("The provider returned inconsistent OHLC values.")
        return cls(observed_on, opening, high, low, close, volume)


@dataclass(frozen=True)
class MarketDataSnapshot:
    symbol: str
    latest: DailyBar
    previous: DailyBar | None
    retrieved_at: datetime
    market_timezone: str | None
    freshness_status: str
    observation_age_days: int | None
    max_observation_age_days: int
    cache_status: str = "provider_response"

    def to_payload(self, *, calculated_at: datetime | None = None) -> dict[str, Any]:
        """Return JSON-safe facts and calculations as separate top-level objects."""
        calculated_at = calculated_at or datetime.now(timezone.utc)
        latest = self.latest
        source_facts: dict[str, Any] = {
            "symbol": self.symbol,
            "provider": PROVIDER_NAME,
            "source_reference": SOURCE_REFERENCE,
            "source_url": SOURCE_URL,
            "exchange": None,
            "currency": None,
            "data_status": "end_of_day",
            "adjustment_status": "unadjusted_raw",
            "validation_status": "validated",
            "market_session_status": "not_assessed",
            "market_session_status_reason": (
                "This endpoint response does not provide a verified exchange mapping or market calendar."
            ),
            "observation_timestamp": {
                "value": latest.observation_date.isoformat(),
                "semantics": "date-only trading-session date; not a UTC instant",
                "time_zone": self.market_timezone,
            },
            "retrieval_timestamp_utc": _utc_iso(self.retrieved_at),
            "cache_status": self.cache_status,
            "freshness": {
                "status": self.freshness_status,
                "observation_age_days": self.observation_age_days,
                "max_observation_age_days": self.max_observation_age_days,
            },
            "ohlcv": {
                "open": _decimal_text(latest.open),
                "high": _decimal_text(latest.high),
                "low": _decimal_text(latest.low),
                "close": _decimal_text(latest.close),
                "volume": latest.volume,
            },
        }

        derived_metrics: dict[str, Any] = {}
        if self.previous is None:
            for metric in ("close_to_close_change", "close_to_close_change_percent"):
                derived_metrics[metric] = {
                    "status": "unavailable",
                    "reason": "At least two comparable daily observations are required.",
                }
        else:
            previous = self.previous
            delta = latest.close - previous.close
            common = {
                "calculated_at_utc": _utc_iso(calculated_at),
                "input_refs": [
                    {"observation_date": latest.observation_date.isoformat(), "field": "close"},
                    {"observation_date": previous.observation_date.isoformat(), "field": "close"},
                ],
            }
            derived_metrics["close_to_close_change"] = {
                **common,
                "status": "calculated",
                "value": _decimal_text(delta),
                "unit": "provider price units; currency not supplied by the endpoint",
                "formula_id": "close_to_close_absolute_change_v1",
                "formula": "latest_close - previous_close",
            }
            if previous.close == 0:
                derived_metrics["close_to_close_change_percent"] = {
                    **common,
                    "status": "unavailable",
                    "reason": "Percentage change is undefined because previous close is zero.",
                    "formula_id": "close_to_close_percent_change_v1",
                    "formula": "((latest_close - previous_close) / previous_close) * 100",
                }
            else:
                pct = (delta / previous.close * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                derived_metrics["close_to_close_change_percent"] = {
                    **common,
                    "status": "calculated",
                    "value": format(pct, ".2f"),
                    "unit": "percent",
                    "formula_id": "close_to_close_percent_change_v1",
                    "formula": "((latest_close - previous_close) / previous_close) * 100",
                    "rounding": "2 decimal places, ROUND_HALF_UP",
                }

        return {
            "source_facts": source_facts,
            "derived_metrics": derived_metrics,
            "generated_analysis": {
                "status": "not_generated",
                "text": None,
                "input_refs": ["source_facts", "derived_metrics"],
            },
        }


class AlphaVantageProvider:
    """Small Alpha Vantage daily-bars client; no retries or caching by design."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_age_days: int | None = None,
        max_retries: int | None = None,
        cache_ttl_seconds: int | None = None,
        session: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        cache_clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.api_key = ALPHA_VANTAGE_API_KEY if api_key is None else api_key.strip()
        self.base_url = (base_url or AURIX_MARKET_DATA_BASE_URL).strip()
        self.timeout_seconds = (
            AURIX_MARKET_DATA_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self.max_age_days = (
            AURIX_MARKET_DATA_MAX_AGE_DAYS if max_age_days is None else max_age_days
        )
        requested_retries = AURIX_MARKET_DATA_MAX_RETRIES if max_retries is None else max_retries
        self.max_retries = min(requested_retries, 3)  # hard cap prevents unbounded retry loops
        self.cache_ttl_seconds = (
            AURIX_MARKET_DATA_CACHE_TTL_SECONDS
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        self._cache: dict[str, tuple[float, MarketDataSnapshot]] = {}
        parsed_endpoint = urlparse(self.base_url)
        if (
            parsed_endpoint.scheme != "https"
            or parsed_endpoint.hostname not in {"www.alphavantage.co", "alphavantage.co"}
            or parsed_endpoint.username is not None
            or parsed_endpoint.password is not None
            or parsed_endpoint.path != "/query"
            or parsed_endpoint.query
            or parsed_endpoint.fragment
        ):
            raise MarketDataConfigurationError(
                "Market-data endpoint must be the official Alpha Vantage HTTPS /query endpoint."
            )
        if self.timeout_seconds <= 0:
            raise MarketDataConfigurationError("Market-data timeout must be greater than zero.")
        if self.max_age_days < 0:
            raise MarketDataConfigurationError("Market-data maximum age cannot be negative.")
        if self.max_retries < 0:
            raise MarketDataConfigurationError("Market-data retry count cannot be negative.")
        if self.cache_ttl_seconds < 0:
            raise MarketDataConfigurationError("Market-data cache TTL cannot be negative.")
        self.session = session or requests.Session()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cache_clock = cache_clock or time.monotonic
        self.sleeper = sleeper or time.sleep

    def _cached_snapshot(self, symbol: str) -> MarketDataSnapshot | None:
        entry = self._cache.get(symbol)
        if entry is None or self.cache_ttl_seconds == 0:
            return None
        cached_at, snapshot = entry
        elapsed = self.cache_clock() - cached_at
        if elapsed < 0 or elapsed >= self.cache_ttl_seconds:
            self._cache.pop(symbol, None)
            return None

        # Keep the actual provider retrieval timestamp, but recompute calendar-age
        # status on every cache hit in case the exchange-local date has changed.
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise MarketDataConfigurationError("Market-data clock must return a timezone-aware timestamp.")
        now = now.astimezone(timezone.utc)
        if snapshot.market_timezone:
            local_today = now.astimezone(ZoneInfo(snapshot.market_timezone)).date()
            age_days = (local_today - snapshot.latest.observation_date).days
            if age_days < 0:
                raise MarketDataValidationError("Provider returned a future-dated observation.")
            freshness = "stale" if age_days > self.max_age_days else "within_threshold"
        else:
            if snapshot.latest.observation_date > now.date():
                raise MarketDataValidationError("Provider returned a future-dated observation.")
            age_days = None
            freshness = "unknown_timezone_missing"
        return replace(
            snapshot,
            freshness_status=freshness,
            observation_age_days=age_days,
            cache_status="cache_hit",
        )

    def fetch_daily(self, symbol: str) -> MarketDataSnapshot:
        normalized_symbol = _validate_symbol(symbol)
        if not self.api_key:
            raise MarketDataConfigurationError(
                "ALPHA_VANTAGE_API_KEY is missing. Add your Alpha Vantage key to the local .env file."
            )
        cached = self._cached_snapshot(normalized_symbol)
        if cached is not None:
            return cached

        payload: Any = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    self.base_url,
                    params={
                        "function": "TIME_SERIES_DAILY",
                        "symbol": normalized_symbol,
                        "outputsize": "compact",
                        "apikey": self.api_key,
                    },
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt < self.max_retries:
                    delay = min(2**attempt, 3)
                    logger.warning("Transient market-data network failure; retrying in %s second(s).", delay)
                    self.sleeper(delay)
                    continue
                label = "timed out" if isinstance(exc, requests.Timeout) else "could not connect"
                raise MarketDataProviderError(f"Alpha Vantage request {label} after bounded retries.") from exc
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status >= 500 and attempt < self.max_retries:
                    delay = min(2**attempt, 3)
                    logger.warning("Alpha Vantage server error HTTP %s; retrying in %s second(s).", status, delay)
                    self.sleeper(delay)
                    continue
                if status in (401, 403):
                    raise MarketDataProviderError(
                        f"Alpha Vantage denied access (HTTP {status}); check the API key and plan."
                    ) from exc
                if status == 429:
                    raise MarketDataProviderError(
                        "Alpha Vantage rate limit reached. Wait for quota reset; the request was not retried."
                    ) from exc
                suffix = f" (HTTP {status})" if status is not None else ""
                raise MarketDataProviderError(f"Alpha Vantage request failed{suffix}.") from exc
            except requests.RequestException as exc:
                raise MarketDataProviderError("Alpha Vantage request failed due to a network error.") from exc

            try:
                payload = response.json()
            except (ValueError, TypeError) as exc:
                raise MarketDataProviderError("Alpha Vantage returned invalid JSON.") from exc
            break
        else:
            raise MarketDataProviderError("Alpha Vantage request failed after bounded retries.")

        if not isinstance(payload, Mapping):
            raise MarketDataValidationError("Alpha Vantage returned an unexpected response shape.")
        if payload.get("Error Message"):
            raise MarketDataProviderError(
                f"Alpha Vantage rejected ticker {normalized_symbol}; check the symbol and provider access."
            )
        provider_notice = payload.get("Note") or payload.get("Information")
        if provider_notice:
            raise MarketDataProviderError(
                "Alpha Vantage returned a usage-limit or access notice. Check the provider plan and request limits."
            )

        metadata = payload.get("Meta Data")
        series = payload.get("Time Series (Daily)")
        if not isinstance(metadata, Mapping) or not isinstance(series, Mapping) or not series:
            raise MarketDataValidationError(
                "Alpha Vantage response is missing daily observations or metadata."
            )

        reported_symbol = metadata.get("2. Symbol")
        if not isinstance(reported_symbol, str) or not reported_symbol.strip():
            raise MarketDataValidationError("Provider response is missing symbol metadata.")
        if reported_symbol.strip().upper() != normalized_symbol:
            raise MarketDataValidationError("Provider symbol metadata does not match the requested ticker.")

        raw_dates = list(series.keys())
        try:
            dates = [date.fromisoformat(raw_date) for raw_date in raw_dates]
        except (TypeError, ValueError) as exc:
            raise MarketDataValidationError("Provider returned an invalid daily observation date.") from exc
        if len(set(dates)) != len(dates):
            raise MarketDataValidationError("Provider returned duplicate daily observations.")
        if dates != sorted(dates, reverse=True):
            raise MarketDataValidationError("Provider daily observations are out of order.")

        bars = [DailyBar.from_provider_row(raw_date, row) for raw_date, row in series.items()]
        latest = bars[0]
        previous = bars[1] if len(bars) > 1 else None
        market_timezone = metadata.get("5. Time Zone")
        if market_timezone is not None:
            if not isinstance(market_timezone, str) or not market_timezone.strip():
                raise MarketDataValidationError("Provider returned an invalid market time zone.")
            market_timezone = market_timezone.strip()
            try:
                zone = ZoneInfo(market_timezone)
            except ZoneInfoNotFoundError as exc:
                raise MarketDataValidationError("Provider returned an unknown market time zone.") from exc
        else:
            zone = None

        retrieved_at = self.clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise MarketDataConfigurationError("Market-data clock must return a timezone-aware timestamp.")
        retrieved_at = retrieved_at.astimezone(timezone.utc)
        if zone is not None:
            local_today = retrieved_at.astimezone(zone).date()
            age_days = (local_today - latest.observation_date).days
            if age_days < 0:
                raise MarketDataValidationError("Provider returned a future-dated observation.")
            freshness_status = "stale" if age_days > self.max_age_days else "within_threshold"
        else:
            if latest.observation_date > retrieved_at.date():
                raise MarketDataValidationError("Provider returned a future-dated observation.")
            age_days = None
            freshness_status = "unknown_timezone_missing"

        snapshot = MarketDataSnapshot(
            symbol=normalized_symbol,
            latest=latest,
            previous=previous,
            retrieved_at=retrieved_at,
            market_timezone=market_timezone,
            freshness_status=freshness_status,
            observation_age_days=age_days,
            max_observation_age_days=self.max_age_days,
        )
        if self.cache_ttl_seconds > 0:
            # Bound memory if a user requests many different ticker symbols.
            if normalized_symbol not in self._cache and len(self._cache) >= 100:
                self._cache.pop(next(iter(self._cache)))
            self._cache[normalized_symbol] = (self.cache_clock(), snapshot)
        return snapshot


_default_provider: AlphaVantageProvider | None = None


def fetch_daily_market_data(symbol: str) -> MarketDataSnapshot:
    """Fetch daily bars through a process-local provider with bounded caching."""
    global _default_provider
    if _default_provider is None:
        _default_provider = AlphaVantageProvider()
    return _default_provider.fetch_daily(symbol)


def format_market_data_response(payload: Mapping[str, Any]) -> str:
    """Render source facts, deterministic calculations, and AI analysis separately."""
    facts = payload["source_facts"]
    metrics = payload["derived_metrics"]
    generated = payload.get("generated_analysis") or {"status": "not_generated", "text": None}
    values = facts["ohlcv"]
    observation = facts["observation_timestamp"]
    zone = observation.get("time_zone")
    date_label = observation["value"] + (f" ({zone} session date)" if zone else " (date-only; time zone not supplied)")
    lines = [
        f"Market data — {facts['symbol']} (source-reported daily OHLCV)",
        f"Source: {facts['provider']} / {facts['source_reference']}",
        f"Observation date: {date_label}",
        f"Retrieved at: {facts['retrieval_timestamp_utc']} (cache status: {facts['cache_status']})",
        f"Status: {facts['data_status']}; adjustment: {facts['adjustment_status']}; currency: not supplied by provider.",
        "Market-session status: not assessed; the endpoint response does not verify an exchange calendar.",
        f"Open: {values['open']} | High: {values['high']} | Low: {values['low']} | Close: {values['close']} | Volume: {values['volume']}",
    ]
    freshness = facts["freshness"]
    if freshness["status"] == "stale":
        lines.append(
            f"WARNING: observation is stale ({freshness['observation_age_days']} calendar days old; "
            f"threshold {freshness['max_observation_age_days']} days). Do not treat it as current."
        )
    elif freshness["status"] == "within_threshold":
        lines.append(
            f"Freshness check: within the configured {freshness['max_observation_age_days']}-day age threshold; "
            "this is still end-of-day data, not a live quote."
        )
    else:
        lines.append("Freshness check: unknown because the provider did not supply a market time zone.")

    absolute = metrics.get("close_to_close_change", {})
    percent = metrics.get("close_to_close_change_percent", {})
    if absolute.get("status") == "calculated":
        refs = absolute.get("input_refs", [])
        date_detail = (
            f" from {refs[1]['observation_date']} to {refs[0]['observation_date']}"
            if len(refs) >= 2 else ""
        )
        lines.append(
            f"Calculated close-to-close change{date_detail}: {absolute['value']} provider price units "
            f"(formula: {absolute['formula']}; not a provider-reported field)."
        )
    else:
        lines.append(f"Calculated close-to-close change: unavailable ({absolute.get('reason', 'insufficient inputs')}).")
    if percent.get("status") == "calculated":
        refs = percent.get("input_refs", [])
        date_detail = (
            f" from {refs[1]['observation_date']} to {refs[0]['observation_date']}"
            if len(refs) >= 2 else ""
        )
        lines.append(
            f"Calculated close-to-close percentage change{date_detail}: {percent['value']}% "
            f"(formula: {percent['formula']}; {percent['rounding']})."
        )
    else:
        lines.append(
            "Calculated close-to-close percentage change: unavailable "
            f"({percent.get('reason', 'insufficient inputs')})."
        )

    if generated.get("status") == "generated" and generated.get("text"):
        lines.extend(["AI-generated analysis (separate from source facts and calculations):", generated["text"]])
    elif generated.get("status") == "unavailable" and generated.get("reason"):
        lines.append(f"AI-generated analysis unavailable: {generated['reason']} Source facts and calculations remain available above.")
    else:
        lines.append("AI-generated analysis: not generated; source facts and calculations are shown above.")
    return "\n".join(lines)
