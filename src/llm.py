"""Shared model setup: OpenAI gpt-6-luna through the Portkey gateway.

Every model call gets a fresh HTTP client that is created and closed inside the same
event loop (run_with_fresh_model). Each API call made through it is recorded once in the
usage log (src/usage_log.py). Dash runs each request in its own thread and event
loop, so a client must not be shared across calls:
- creating clients without closing them logged "Event loop is closed" errors (P29);
- sharing one client failed with "bound to a different event loop" (P29).
"""
import asyncio

from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from portkey_ai import PORTKEY_GATEWAY_URL, createHeaders
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from src import config
from src.usage_log import CallCapture, record_run


class AgentError(RuntimeError):
    """Raised with a staff-friendly message; the UI shows it as an error bubble."""


def new_model(capture=None):
    """A new PydanticAI model for config.MODEL via Portkey, with its own HTTP client.

    capture: optional CallCapture whose hooks record each API response's usage (no content)."""
    if not config.PORTKEY_API_KEY:
        raise AgentError("PORTKEY_API_KEY is not set. Add it to .env (see .env.example)")
    client = AsyncOpenAI(
        base_url=PORTKEY_GATEWAY_URL,
        api_key=config.PORTKEY_API_KEY,
        default_headers=createHeaders(api_key=config.PORTKEY_API_KEY),
        timeout=config.AGENT_TIMEOUT_SECONDS,
        max_retries=1,
        http_client=DefaultAsyncHttpxClient(event_hooks=capture.hooks()) if capture else None,
    )
    # Responses API: on this deployment, Chat Completions rejects tools combined with reasoning
    return OpenAIResponsesModel(config.MODEL, provider=OpenAIProvider(openai_client=client))


def run_with_fresh_model(agent, content, **kwargs):
    """Run a PydanticAI agent synchronously. If the agent has no model of its own, a fresh
    Portkey model is created for this run and its client is closed in the same event loop."""
    async def go():
        if agent.model is not None:          # e.g. a test model; never replace it with a real one
            return await agent.run(content, **kwargs)
        capture = CallCapture()
        model = new_model(capture)
        result, outcome = None, "ok"
        try:
            result = await agent.run(content, model=model, **kwargs)
            return result
        except BaseException as exc:
            outcome = f"error: {type(exc).__name__}"
            raise
        finally:
            await model.client.close()
            record_run(capture, agent.name, outcome, result)   # one log line per API call; never raises
    return asyncio.run(go())
