"""Deterministic unit tests for market-data validation and calculations."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

import requests

from aurix.integrations.market_data import (
    AlphaVantageProvider,
    MarketDataConfigurationError,
    MarketDataProviderError,
    MarketDataValidationError,
    extract_market_data_symbol,
)

FIXED_NOW = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)


def bar(open_, high, low, close, volume="1000"):
    return {
        "1. open": str(open_),
        "2. high": str(high),
        "3. low": str(low),
        "4. close": str(close),
        "5. volume": str(volume),
    }


def valid_payload(
    latest_date="2026-10-23",
    previous_date="2026-10-22",
    *,
    timezone_name="US/Eastern",
    latest_close="100",
    previous_close="80",
):
    metadata = {"2. Symbol": "IBM"}
    if timezone_name is not None:
        metadata["5. Time Zone"] = timezone_name
    series = {
        latest_date: bar("95", "101", "94", latest_close),
        previous_date: bar("78", "82", "77", previous_close),
    }
    return {"Meta Data": metadata, "Time Series (Daily)": series}


class FakeResponse:
    def __init__(self, payload, status_error=None):
        self.payload = payload
        self.status_error = status_error
        self.status_code = 200

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


class TestMarketData(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session.get.return_value = FakeResponse(valid_payload())
        self.provider = AlphaVantageProvider(
            api_key="test-key",
            session=self.session,
            clock=lambda: FIXED_NOW,
            max_age_days=7,
            max_retries=1,
            cache_ttl_seconds=300,
            cache_clock=lambda: 100.0,
            sleeper=lambda _delay: None,
        )

    def test_fetch_uses_daily_compact_and_timeout(self):
        snapshot = self.provider.fetch_daily("ibm")
        self.assertEqual(snapshot.symbol, "IBM")
        kwargs = self.session.get.call_args.kwargs
        self.assertEqual(kwargs["params"]["function"], "TIME_SERIES_DAILY")
        self.assertEqual(kwargs["params"]["outputsize"], "compact")
        self.assertNotIn("test-key", str(snapshot.to_payload()))
        self.assertEqual(kwargs["timeout"], 8.0)

    def test_cache_hit_preserves_provider_retrieval_timestamp(self):
        first = self.provider.fetch_daily("IBM")
        second = self.provider.fetch_daily("IBM")
        self.assertEqual(self.session.get.call_count, 1)
        self.assertEqual(first.retrieved_at, second.retrieved_at)
        self.assertEqual(second.cache_status, "cache_hit")
        self.assertEqual(
            first.to_payload()["source_facts"]["retrieval_timestamp_utc"],
            second.to_payload()["source_facts"]["retrieval_timestamp_utc"],
        )

    def test_expired_cache_refetches_provider_data(self):
        tick = [100.0]
        session = Mock()
        session.get.side_effect = [FakeResponse(valid_payload()), FakeResponse(valid_payload())]
        provider = AlphaVantageProvider(
            api_key="test-key",
            session=session,
            clock=lambda: FIXED_NOW,
            cache_clock=lambda: tick[0],
            cache_ttl_seconds=5,
            max_retries=0,
            sleeper=lambda _delay: None,
        )
        provider.fetch_daily("IBM")
        tick[0] += 5
        result = provider.fetch_daily("IBM")
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(result.cache_status, "provider_response")

    def test_cache_hit_recomputes_freshness_but_keeps_original_retrieval_time(self):
        now = [FIXED_NOW]
        session = Mock()
        session.get.return_value = FakeResponse(valid_payload("2026-10-19", "2026-10-16"))
        provider = AlphaVantageProvider(
            api_key="test-key",
            session=session,
            clock=lambda: now[0],
            cache_clock=lambda: 100.0,
            cache_ttl_seconds=300,
            max_age_days=7,
            max_retries=0,
            sleeper=lambda _delay: None,
        )
        first = provider.fetch_daily("IBM")
        self.assertEqual(first.freshness_status, "within_threshold")
        now[0] = datetime(2026, 10, 27, 5, 0, tzinfo=timezone.utc)
        second = provider.fetch_daily("IBM")
        self.assertEqual(second.freshness_status, "stale")
        self.assertEqual(second.observation_age_days, 8)
        self.assertEqual(second.retrieved_at, first.retrieved_at)
        self.assertEqual(session.get.call_count, 1)

    def test_payload_separates_source_facts_and_derived_metrics(self):
        payload = self.provider.fetch_daily("IBM").to_payload(calculated_at=FIXED_NOW)
        self.assertEqual(payload["source_facts"]["ohlcv"]["close"], "100")
        self.assertEqual(payload["source_facts"]["currency"], None)
        self.assertEqual(payload["source_facts"]["data_status"], "end_of_day")
        self.assertEqual(payload["source_facts"]["adjustment_status"], "unadjusted_raw")
        self.assertEqual(payload["source_facts"]["validation_status"], "validated")
        self.assertEqual(payload["derived_metrics"]["close_to_close_change"]["value"], "20")
        self.assertEqual(
            payload["derived_metrics"]["close_to_close_change_percent"]["value"], "25.00"
        )
        self.assertEqual(payload["generated_analysis"]["status"], "not_generated")
        self.assertEqual(
            payload["source_facts"]["observation_timestamp"]["semantics"],
            "date-only trading-session date; not a UTC instant",
        )
        self.assertEqual(payload["source_facts"]["retrieval_timestamp_utc"], "2026-10-26T18:00:00Z")

    def test_stale_observation_is_marked(self):
        self.session.get.return_value = FakeResponse(valid_payload("2026-10-01", "2026-09-30"))
        snapshot = self.provider.fetch_daily("IBM")
        self.assertEqual(snapshot.freshness_status, "stale")
        self.assertEqual(snapshot.observation_age_days, 25)

    def test_missing_timezone_does_not_invent_freshness(self):
        self.session.get.return_value = FakeResponse(valid_payload(timezone_name=None))
        snapshot = self.provider.fetch_daily("IBM")
        payload = snapshot.to_payload()
        self.assertEqual(snapshot.freshness_status, "unknown_timezone_missing")
        self.assertIsNone(payload["source_facts"]["observation_timestamp"]["time_zone"])

    def test_future_date_rejected(self):
        self.session.get.return_value = FakeResponse(valid_payload("2026-10-27", "2026-10-26"))
        with self.assertRaises(MarketDataValidationError):
            self.provider.fetch_daily("IBM")

    def test_out_of_order_observations_rejected(self):
        payload = valid_payload()
        payload["Time Series (Daily)"] = dict(
            reversed(list(payload["Time Series (Daily)"].items()))
        )
        self.session.get.return_value = FakeResponse(payload)
        with self.assertRaises(MarketDataValidationError):
            self.provider.fetch_daily("IBM")

    def test_symbol_mismatch_rejected(self):
        payload = valid_payload()
        payload["Meta Data"]["2. Symbol"] = "AAPL"
        self.session.get.return_value = FakeResponse(payload)
        with self.assertRaises(MarketDataValidationError):
            self.provider.fetch_daily("IBM")

    def test_missing_provider_symbol_metadata_rejected(self):
        payload = valid_payload()
        payload["Meta Data"].pop("2. Symbol")
        self.session.get.return_value = FakeResponse(payload)
        with self.assertRaisesRegex(MarketDataValidationError, "missing symbol metadata"):
            self.provider.fetch_daily("IBM")

    def test_inconsistent_ohlc_rejected(self):
        payload = valid_payload()
        payload["Time Series (Daily)"]["2026-10-23"] = bar("105", "101", "94", "100")
        self.session.get.return_value = FakeResponse(payload)
        with self.assertRaises(MarketDataValidationError):
            self.provider.fetch_daily("IBM")

    def test_missing_field_rejected(self):
        payload = valid_payload()
        del payload["Time Series (Daily)"]["2026-10-23"]["4. close"]
        self.session.get.return_value = FakeResponse(payload)
        with self.assertRaises(MarketDataValidationError):
            self.provider.fetch_daily("IBM")

    def test_non_numeric_volume_rejected(self):
        payload = valid_payload()
        payload["Time Series (Daily)"]["2026-10-23"]["5. volume"] = "1.2"
        self.session.get.return_value = FakeResponse(payload)
        with self.assertRaises(MarketDataValidationError):
            self.provider.fetch_daily("IBM")

    def test_zero_previous_close_has_no_percentage_calculation(self):
        payload = valid_payload(latest_close="10", previous_close="0")
        payload["Time Series (Daily)"]["2026-10-23"] = bar("5", "10", "0", "10")
        payload["Time Series (Daily)"]["2026-10-22"] = bar("0", "0", "0", "0", "0")
        self.session.get.return_value = FakeResponse(payload)
        result = self.provider.fetch_daily("IBM").to_payload()
        self.assertEqual(result["derived_metrics"]["close_to_close_change"]["value"], "10")
        pct = result["derived_metrics"]["close_to_close_change_percent"]
        self.assertEqual(pct["status"], "unavailable")

    def test_one_observation_has_no_derived_percent_change(self):
        payload = valid_payload()
        payload["Time Series (Daily)"] = {
            "2026-10-23": payload["Time Series (Daily)"]["2026-10-23"]
        }
        self.session.get.return_value = FakeResponse(payload)
        metrics = self.provider.fetch_daily("IBM").to_payload()["derived_metrics"]
        self.assertEqual(metrics["close_to_close_change_percent"]["status"], "unavailable")

    def test_missing_key_prevents_network_request(self):
        provider = AlphaVantageProvider(api_key="", session=self.session, clock=lambda: FIXED_NOW)
        with self.assertRaises(MarketDataConfigurationError):
            provider.fetch_daily("IBM")
        self.session.get.assert_not_called()

    def test_non_provider_endpoint_is_rejected_before_api_key_can_be_sent(self):
        with self.assertRaisesRegex(MarketDataConfigurationError, "official Alpha Vantage"):
            AlphaVantageProvider(
                api_key="test-key",
                base_url="https://attacker.example/query",
                session=self.session,
                clock=lambda: FIXED_NOW,
            )
        self.session.get.assert_not_called()

    def test_usage_limit_notice_is_reported_without_retry(self):
        self.session.get.return_value = FakeResponse({"Note": "rate limit reached"})
        with self.assertRaisesRegex(MarketDataProviderError, "usage-limit"):
            self.provider.fetch_daily("IBM")
        self.session.get.assert_called_once()

    def test_transient_timeout_retries_once_and_succeeds(self):
        self.session.get.side_effect = [requests.Timeout(), FakeResponse(valid_payload())]
        snapshot = self.provider.fetch_daily("IBM")
        self.assertEqual(snapshot.symbol, "IBM")
        self.assertEqual(self.session.get.call_count, 2)

    def test_http_rate_limit_is_not_retried(self):
        rate_limited = requests.HTTPError(
            "HTTP 429", response=type("ResponseMeta", (), {"status_code": 429})()
        )
        self.session.get.return_value = FakeResponse(valid_payload(), status_error=rate_limited)
        with self.assertRaisesRegex(MarketDataProviderError, "rate limit reached"):
            self.provider.fetch_daily("IBM")
        self.session.get.assert_called_once()

    def test_timeout_is_wrapped_after_bounded_retries(self):
        self.session.get.side_effect = [requests.Timeout(), requests.Timeout()]
        with self.assertRaisesRegex(MarketDataProviderError, "timed out"):
            self.provider.fetch_daily("IBM")
        self.assertEqual(self.session.get.call_count, 2)

    def test_invalid_symbol_is_rejected_before_network(self):
        with self.assertRaises(MarketDataValidationError):
            self.provider.fetch_daily("../../secrets")
        self.session.get.assert_not_called()

    def test_market_command_parser_requires_explicit_intent(self):
        self.assertEqual(extract_market_data_symbol("stock aapl"), "AAPL")
        self.assertEqual(extract_market_data_symbol("market data for IBM"), "IBM")
        self.assertEqual(
            extract_market_data_symbol("what is the stock price of SHOP.TO?"), "SHOP.TO"
        )
        self.assertEqual(extract_market_data_symbol("stock price of IBM"), "IBM")
        self.assertIsNone(extract_market_data_symbol("Should I buy IBM tomorrow?"))
        self.assertIsNone(extract_market_data_symbol("hello there"))


if __name__ == "__main__":
    unittest.main()
