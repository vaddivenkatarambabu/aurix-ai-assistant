"""AI conversation engine for AURIX, compatible with OpenAI-style APIs."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from aurix.actions.desktop import try_handle_desktop_command

from aurix.integrations.market_data import (
    MarketDataError,
    extract_market_data_symbol,
    fetch_daily_market_data,
    format_market_data_response,
)

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from aurix.config import (
    AI_API_KEY,
    AI_BASE_URL,
    AURIX_MAX_API_RETRIES,
    AURIX_MAX_HISTORY_TURNS,
    AURIX_REQUEST_TIMEOUT_SECONDS,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are AURIX, a personal AI assistant. Respond in clear, natural, concise language. "
    "Respond in the same language and script as the user's latest message when possible. "
    "Support multilingual conversation including Telugu, Spanish, Hindi, and other languages. "
    "Be honest about uncertainty. Do not claim to have launched an application unless the local "
    "desktop action router reports that launch succeeded. Do not claim to have sent messages, "
    "changed files, or retrieved live data unless a real integration performed and verified it. "
    "Application launches and direct web/video searches are handled by the local action router. "
    "Do not ask the user to run arbitrary shell commands and do not generate executable shell text."
)

MARKET_ANALYSIS_SYSTEM_PROMPT = (
    "You are AURIX's market-data explainer. You receive a JSON object with source_facts and "
    "derived_metrics supplied by the application. Use only those supplied values. Keep source-reported "
    "observations distinct from application-calculated metrics. Never invent a currency, exchange, quote "
    "timestamp, current/live status, market event, news, causal explanation, forecast, or missing number. "
    "If the observation is stale or freshness is unknown, say so. Do not give buy/sell/hold recommendations. "
    "Do not treat end-of-day data as real-time data. Explain the available facts briefly and acknowledge "
    "when the data cannot support a conclusion. This is informational analysis, not financial advice."
)

class AIConfigurationError(RuntimeError):
    """Raised when required AI configuration is missing."""


class AIServiceError(RuntimeError):
    """Raised when the configured AI service cannot complete a request."""


def _looks_like_quota_error(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    message = f"{body!r} {exc}".lower()
    return any(
        marker in message
        for marker in (
            "insufficient_quota",
            "billing_hard_limit",
            "credit_balance_exhausted",
            "spend_limit_exceeded",
            "usage_limit_exceeded",
            "exceeded your current quota",
        )
    )


class AurixAssistant:
    """Maintain bounded conversation context in the running process."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_history_turns: int | None = None,
        timeout_seconds: float | None = None,
        max_api_retries: int | None = None,
    ) -> None:
        # Inject a mock client in tests so they never make paid requests.
        self.client = client
        self.api_key = AI_API_KEY if api_key is None else api_key.strip()
        self.base_url = AI_BASE_URL if base_url is None else base_url.strip()
        self.model = (model or OPENAI_MODEL).strip()
        self.max_history_turns = max_history_turns or AURIX_MAX_HISTORY_TURNS
        self.timeout_seconds = timeout_seconds or AURIX_REQUEST_TIMEOUT_SECONDS
        self.max_api_retries = (
            AURIX_MAX_API_RETRIES if max_api_retries is None else max_api_retries
        )
        self.history: list[dict[str, str]] = []

    def _get_client(self) -> Any:
        if self.client is not None:
            return self.client

        if not self.api_key:
            raise AIConfigurationError(
                "AI_API_KEY is missing. Add your provider key to the local .env file."
            )
        if not self.model:
            raise AIConfigurationError(
                "OPENAI_MODEL is empty. Set it to a model supported by your provider."
            )

        options: dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout_seconds,
            # Retry logic is implemented here so attempts are bounded and visible.
            "max_retries": 0,
        }
        if self.base_url:
            options["base_url"] = self.base_url

        self.client = OpenAI(**options)
        return self.client

    def ask(self, user_message: str) -> str:
        prompt = user_message.strip()
        if not prompt:
            return "Please tell me what you need."

        client = self._get_client()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self.history,
            {"role": "user", "content": prompt},
        ]

        for attempt in range(self.max_api_retries + 1):
            try:
                result = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=350,
                )
                content = result.choices[0].message.content
                answer = content.strip() if isinstance(content, str) else ""
                if not answer:
                    raise AIServiceError(
                        "The AI service returned an empty answer. Please try again."
                    )

                # Store history only after a successful response.
                self.history.extend(
                    [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": answer},
                    ]
                )
                self.history = self.history[-(self.max_history_turns * 2) :]
                return answer

            except RateLimitError as exc:
                if _looks_like_quota_error(exc):
                    raise AIServiceError(
                        "The API quota or billing limit may have been reached. "
                        "Check your provider's usage and billing dashboard."
                    ) from exc
                if attempt >= self.max_api_retries:
                    raise AIServiceError(
                        "The AI provider is rate-limiting requests. Wait briefly and retry."
                    ) from exc
                delay = min(2**attempt, 3)
                logger.warning("Rate limited; retrying in %s second(s).", delay)
                time.sleep(delay)

            except AuthenticationError as exc:
                raise AIServiceError(
                    "The provider rejected the API key. Check AI_API_KEY in .env."
                ) from exc

            except PermissionDeniedError as exc:
                raise AIServiceError(
                    "The API project cannot access this model or endpoint. "
                    "Check the provider, model ID, and project permissions."
                ) from exc

            except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
                if attempt >= self.max_api_retries:
                    raise AIServiceError(
                        "The AI service timed out or could not be reached. "
                        "Check internet access and provider status."
                    ) from exc
                delay = min(2**attempt, 3)
                logger.warning(
                    "Temporary API failure (%s); retrying in %s second(s).",
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)

            except APIStatusError as exc:
                request_id = getattr(exc, "request_id", None)
                suffix = f" Request ID: {request_id}." if request_id else ""
                raise AIServiceError(
                    f"The AI provider returned HTTP {exc.status_code}. "
                    f"Check the model name, base URL, and request configuration.{suffix}"
                ) from exc

        raise AIServiceError("AURIX could not complete the request.")


    def analyze_market_data(self, market_payload: dict[str, Any]) -> str:
        """Generate commentary from validated source facts without sending chat history."""
        try:
            inputs = {
                "source_facts": market_payload["source_facts"],
                "derived_metrics": market_payload["derived_metrics"],
            }
        except (KeyError, TypeError) as exc:
            raise AIServiceError("Market-data analysis input is missing validated data.") from exc

        messages = [
            {"role": "system", "content": MARKET_ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Explain the following validated market data in at most 120 words. "
                    "State what the figures show without forecasting. The JSON fields below are "
                    "the complete evidence available; do not add external facts.\n"
                    + json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                ),
            },
        ]
        client = self._get_client()
        for attempt in range(self.max_api_retries + 1):
            try:
                result = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=220,
                )
                content = result.choices[0].message.content
                answer = content.strip() if isinstance(content, str) else ""
                if not answer:
                    raise AIServiceError("The AI service returned empty market commentary.")
                return answer
            except RateLimitError as exc:
                if _looks_like_quota_error(exc):
                    raise AIServiceError("AI market commentary is unavailable because the API quota may be exhausted.") from exc
                if attempt >= self.max_api_retries:
                    raise AIServiceError("AI market commentary is temporarily rate-limited.") from exc
                delay = min(2**attempt, 3)
                logger.warning("Market commentary rate-limited; retrying in %s second(s).", delay)
                time.sleep(delay)
            except AuthenticationError as exc:
                raise AIServiceError("AI market commentary could not authenticate; check AI_API_KEY.") from exc
            except PermissionDeniedError as exc:
                raise AIServiceError("The AI provider denied access to the configured model.") from exc
            except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
                if attempt >= self.max_api_retries:
                    raise AIServiceError("AI market commentary timed out or the provider could not be reached.") from exc
                delay = min(2**attempt, 3)
                logger.warning("Temporary market-analysis failure (%s); retrying in %s second(s).", type(exc).__name__, delay)
                time.sleep(delay)
            except APIStatusError as exc:
                raise AIServiceError(f"The AI provider returned HTTP {exc.status_code} during market analysis.") from exc
        raise AIServiceError("AURIX could not generate market commentary.")

    def clear_history(self) -> None:
        """Clear the in-memory conversation history."""
        self.history.clear()


_assistant: AurixAssistant | None = None


def handle_command(command: str, language: str | None = None) -> str:
    """Route local desktop/video actions first; send all other text to the AI."""
    global _assistant
    try:
        action_response = try_handle_desktop_command(command, language=language)
        if action_response is not None:
            logger.info("Handled a local desktop or browser action.")
            return action_response

        symbol = extract_market_data_symbol(command)
        if symbol is not None:
            try:
                snapshot = fetch_daily_market_data(symbol)
            except MarketDataError as exc:
                logger.warning("Market-data request failed: %s", exc)
                return f"Market data unavailable: {exc}"

            payload = snapshot.to_payload()
            try:
                if _assistant is None:
                    _assistant = AurixAssistant()
                analysis = _assistant.analyze_market_data(payload)
                payload["generated_analysis"] = {
                    "status": "generated",
                    "text": analysis,
                    "model": _assistant.model,
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "input_refs": ["source_facts", "derived_metrics"],
                }
            except (AIConfigurationError, AIServiceError) as exc:
                logger.warning("AI analysis unavailable for market data: %s", exc)
                payload["generated_analysis"] = {
                    "status": "unavailable",
                    "text": None,
                    "reason": str(exc),
                    "input_refs": ["source_facts", "derived_metrics"],
                }
            except Exception:
                logger.exception("Unexpected error generating market-data analysis.")
                payload["generated_analysis"] = {
                    "status": "unavailable",
                    "text": None,
                    "reason": "AI analysis could not be generated; source facts and calculations remain available.",
                    "input_refs": ["source_facts", "derived_metrics"],
                }
            return format_market_data_response(payload)

        if _assistant is None:
            _assistant = AurixAssistant()
        return _assistant.ask(command)

    except (AIConfigurationError, AIServiceError) as exc:
        logger.warning("AURIX request failed: %s", exc)
        return f"I couldn't answer that: {exc}"
    except Exception:
        logger.exception("Unexpected error in AURIX command handling.")
        return "AURIX encountered an unexpected error. Check the terminal log."
