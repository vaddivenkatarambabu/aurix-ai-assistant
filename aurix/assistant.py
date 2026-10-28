"""AI conversation engine for AURIX, compatible with OpenAI-style APIs."""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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

from aurix.actions.desktop import try_handle_desktop_command
from aurix.config import (
    AI_API_KEY,
    AI_BASE_URL,
    AURIX_MAX_API_RETRIES,
    AURIX_MAX_HISTORY_TURNS,
    AURIX_MAX_RESPONSE_TOKENS,
    AURIX_REQUEST_TIMEOUT_SECONDS,
    OPENAI_MODEL,
)
from aurix.integrations.market_data import (
    MarketDataError,
    extract_market_data_symbol,
    fetch_daily_market_data,
    format_market_data_response,
)
from aurix.intent import (
    ActionIntent,
    execute_action_intent,
    interpret_action_intent,
    should_attempt_desktop_interpretation,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are AURIX, a personal AI assistant that talks with the user. Answer the way a "
    "knowledgeable person would explain something out loud: natural, direct, and friendly. "
    "Match the length to the question: one to three sentences for simple questions; for a "
    "concept such as 'What is software engineering?' explain it clearly in plain language "
    "with one short concrete example, then stop and let the user ask for more. Use the "
    "conversation so far to answer follow-up questions. Avoid filler openers and "
    "repetition. Write plain sentences: no Markdown headings, tables, asterisks, or emoji, "
    "and use a list only if the user asks for one. "
    "Respond in the same language and script as the user's latest message when possible. "
    "Support multilingual conversation including Telugu, Spanish, Hindi, and other languages. "
    "Be honest about uncertainty and say when you do not know instead of guessing. "
    "Do not claim to have launched an application unless the local "
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


_MARKET_ANALYSIS_MAX_TOKENS = 220


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


@dataclass(frozen=True)
class _ErrorText:
    """User-facing wording for each failure mode of one kind of model request."""

    quota: str
    rate_limit: str
    auth: str
    permission: str
    unreachable: str
    status: str  # may contain {code}


_CHAT_ERRORS = _ErrorText(
    quota=(
        "The API quota or billing limit may have been reached. "
        "Check your provider's usage and billing dashboard."
    ),
    rate_limit="The AI provider is rate-limiting requests. Wait briefly and retry.",
    auth="The provider rejected the API key. Check AI_API_KEY in .env.",
    permission=(
        "The API project cannot access this model or endpoint. "
        "Check the provider, model ID, and project permissions."
    ),
    unreachable=(
        "The AI service timed out or could not be reached. "
        "Check internet access and provider status."
    ),
    status=(
        "The AI provider returned HTTP {code}. "
        "Check the model name, base URL, and request configuration."
    ),
)

_MARKET_ERRORS = _ErrorText(
    quota="AI market commentary is unavailable because the API quota may be exhausted.",
    rate_limit="AI market commentary is temporarily rate-limited.",
    auth="AI market commentary could not authenticate; check AI_API_KEY.",
    permission="The AI provider denied access to the configured model.",
    unreachable="AI market commentary timed out or the provider could not be reached.",
    status="The AI provider returned HTTP {code} during market analysis.",
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
        max_response_tokens: int | None = None,
    ) -> None:
        # Inject a mock client in tests so they never make paid requests.
        self.client = client
        self.api_key = AI_API_KEY if api_key is None else api_key.strip()
        self.base_url = AI_BASE_URL if base_url is None else base_url.strip()
        self.model = (model or OPENAI_MODEL).strip()
        self.max_history_turns = max_history_turns or AURIX_MAX_HISTORY_TURNS
        self.timeout_seconds = timeout_seconds or AURIX_REQUEST_TIMEOUT_SECONDS
        self.max_api_retries = AURIX_MAX_API_RETRIES if max_api_retries is None else max_api_retries
        self.max_response_tokens = max_response_tokens or AURIX_MAX_RESPONSE_TOKENS
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

    def _complete(self, messages: list[dict[str, str]], max_tokens: int, errors: _ErrorText) -> Any:
        """Run one chat completion with bounded retries; map provider errors to plain messages."""
        client = self._get_client()
        for attempt in range(self.max_api_retries + 1):
            try:
                return client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                )
            except RateLimitError as exc:
                if _looks_like_quota_error(exc):
                    raise AIServiceError(errors.quota) from exc
                if attempt >= self.max_api_retries:
                    raise AIServiceError(errors.rate_limit) from exc
                reason = "Rate limited"
            except AuthenticationError as exc:
                raise AIServiceError(errors.auth) from exc
            except PermissionDeniedError as exc:
                raise AIServiceError(errors.permission) from exc
            except (APITimeoutError, APIConnectionError, InternalServerError) as exc:
                if attempt >= self.max_api_retries:
                    raise AIServiceError(errors.unreachable) from exc
                reason = f"Temporary API failure ({type(exc).__name__})"
            except APIStatusError as exc:
                request_id = getattr(exc, "request_id", None)
                suffix = f" Request ID: {request_id}." if request_id else ""
                raise AIServiceError(errors.status.format(code=exc.status_code) + suffix) from exc

            delay = min(2**attempt, 3)
            logger.warning("%s; retrying in %s second(s).", reason, delay)
            time.sleep(delay)

        raise AIServiceError("AURIX could not complete the request.")

    def ask(self, user_message: str) -> str:
        prompt = user_message.strip()
        if not prompt:
            return "Please tell me what you need."

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self.history,
            {"role": "user", "content": prompt},
        ]
        result = self._complete(messages, self.max_response_tokens, _CHAT_ERRORS)

        choice = result.choices[0]
        content = choice.message.content
        answer = content.strip() if isinstance(content, str) else ""
        finish_reason = getattr(choice, "finish_reason", None)
        if not answer:
            if finish_reason == "length":
                raise AIServiceError(
                    "The model used its whole response budget before answering. "
                    "Increase AURIX_MAX_RESPONSE_TOKENS in .env."
                )
            raise AIServiceError("The AI service returned an empty answer. Please try again.")
        if finish_reason == "length":
            logger.warning("Answer was cut off at the response-token limit.")

        # Store history only after a successful response.
        self.history.extend(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ]
        )
        self.history = self.history[-(self.max_history_turns * 2) :]
        return answer

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
        result = self._complete(messages, _MARKET_ANALYSIS_MAX_TOKENS, _MARKET_ERRORS)
        content = result.choices[0].message.content
        answer = content.strip() if isinstance(content, str) else ""
        if not answer:
            raise AIServiceError("The AI service returned empty market commentary.")
        return answer

    def interpret_desktop_intent(self, prompt: str) -> ActionIntent | None:
        """Interpret action-like text; execution remains in the safe desktop router."""
        return interpret_action_intent(prompt, client=self._get_client(), model=self.model)

    def clear_history(self) -> None:
        """Clear the in-memory conversation history."""
        self.history.clear()


_assistant: AurixAssistant | None = None


def _get_assistant() -> AurixAssistant:
    """Return the process-wide assistant, creating it on first use."""
    global _assistant
    if _assistant is None:
        _assistant = AurixAssistant()
    return _assistant


def _market_data_response(symbol: str) -> str:
    """Fetch daily market data and attach optional, clearly separated AI commentary."""
    try:
        snapshot = fetch_daily_market_data(symbol)
    except MarketDataError as exc:
        logger.warning("Market-data request failed: %s", exc)
        return f"Market data unavailable: {exc}"

    payload = snapshot.to_payload()
    input_refs = ["source_facts", "derived_metrics"]
    try:
        assistant = _get_assistant()
        analysis = assistant.analyze_market_data(payload)
        payload["generated_analysis"] = {
            "status": "generated",
            "text": analysis,
            "model": assistant.model,
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "input_refs": input_refs,
        }
    except (AIConfigurationError, AIServiceError) as exc:
        logger.warning("AI analysis unavailable for market data: %s", exc)
        reason = str(exc)
    except Exception:
        logger.exception("Unexpected error generating market-data analysis.")
        reason = (
            "AI analysis could not be generated; source facts and calculations remain available."
        )
    else:
        reason = None
    if reason is not None:
        payload["generated_analysis"] = {
            "status": "unavailable",
            "text": None,
            "reason": reason,
            "input_refs": input_refs,
        }
    return format_market_data_response(payload)


def handle_command(command: str, language: str | None = None) -> str:
    """Route local actions and market data first; send all other text to the AI."""
    try:
        action_response = try_handle_desktop_command(command, language=language)
        if action_response is not None:
            logger.info("Handled a local desktop or browser action.")
            return action_response

        symbol = extract_market_data_symbol(command)
        if symbol is not None:
            return _market_data_response(symbol)

        if should_attempt_desktop_interpretation(command):
            intent = _get_assistant().interpret_desktop_intent(command)
            if intent is not None and intent.action == "clarify":
                return (
                    intent.clarification_question
                    or "Could you clarify which application or website you mean?"
                )
            if intent is not None:
                action_response = execute_action_intent(
                    intent, try_handle_desktop_command, language=language
                )
                if action_response is not None:
                    logger.info("Handled natural-language desktop intent: %s", intent.action)
                    return action_response

        return _get_assistant().ask(command)

    except (AIConfigurationError, AIServiceError) as exc:
        logger.warning("AURIX request failed: %s", exc)
        return f"I couldn't answer that: {exc}"
    except Exception:
        logger.exception("Unexpected error in AURIX command handling.")
        return "AURIX encountered an unexpected error. Check the terminal log."
