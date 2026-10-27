# Natural-language desktop intent resolution

## Current flow

AURIX first tries deterministic desktop/browser parsing and the explicit market-data integration. If an unhandled request contains an action cue (for example, “bring up”, “take me to”, “I need to use”, or “search”), the configured AI provider is asked to classify it into one of six bounded outcomes: `open_application`, `open_website`, `search_web`, `search_youtube`, `clarify`, or `none`.

The JSON response is validated locally. Unknown action names, invalid confidence values, path-like application targets, script/executable names, malformed JSON, and overlong/control-character payloads are rejected. A low-confidence or explicitly ambiguous result asks a question. `none` falls through to ordinary conversational handling.

The classifier is not an operating-system executor. Accepted intents are rendered into a narrow command and passed back through `try_handle_desktop_command`; existing URL validation, registered website resolution, installed-app discovery, `shell=False` launch behavior, and error reporting remain the execution boundary. No model-generated shell command or launch arguments are accepted.

## Configuration and limitations

The feature reuses AURIX's configured OpenAI-compatible client and therefore requires the existing AI API key/model setup for model-based paraphrase interpretation. Deterministic rules continue to handle known straightforward commands without an extra model call. The action-cue gate is a latency/cost optimization, not proof of intent; requests without recognized cues fall through to the existing conversation path. Model response compatibility depends on the configured provider supporting JSON-object response format. Provider exceptions or invalid output cause the classifier to return no intent; the normal assistant path remains available.

The feature is intentionally limited to launching an application, opening a website, web search, YouTube search, clarification, or ordinary chat. It does not support arbitrary shell commands, deleting files, changing system settings, clicking arbitrary UI controls, file operations, or other consequential actions. Add future capabilities only as explicit validated tools with their own authorization rules and tests.

## Testing

`tests/test_intent.py` uses mocked model results and a mocked executor. It checks paraphrase cue coverage, confidence validation, malformed responses, unsafe targets, clarification, and the handoff to the existing safe router. These are offline unit tests; they do not validate live provider behavior or every natural-language variation.
