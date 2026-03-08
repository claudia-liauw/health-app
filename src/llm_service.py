"""
LLM service layer using LangChain with GitHub Models API.

GitHub Models exposes an OpenAI-compatible endpoint, so we use
langchain-openai's ChatOpenAI with a custom base_url.

Required env vars:
    GITHUB_TOKEN  – GitHub personal access token with Models access
    LLM_MODEL     – model name (default: gpt-4o-mini)
"""

import os
from langchain_openai import ChatOpenAI

GITHUB_MODELS_URL = "https://models.inference.ai.azure.com"
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "You are a friendly, concise health assistant embedded in a Fitbit "
    "health-tracking app called 'Health is Wealth'. "
    "You have access to the user's recent health data below. "
    "Reference specific numbers from the data when answering. "
    "Keep responses concise (2-4 sentences) unless asked for detail. "
    "Never diagnose medical conditions — encourage consulting a healthcare "
    "professional for health concerns. "
    "Convert sleep minutes to hours and minutes for readability. "
    "Be encouraging — celebrate wins, frame shortfalls as opportunities."
)


def get_llm() -> ChatOpenAI:
    """Return a ChatOpenAI instance pointed at GitHub Models."""
    token = os.environ.get("GITHUB_TOKEN", "")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN is not set. Add it to your .env or environment variables."
        )
    return ChatOpenAI(
        model=model,
        api_key=token,
        base_url=GITHUB_MODELS_URL,
        temperature=0.7,
        max_tokens=1024,
    )


def chat(chat_history: list[dict], user_message: str, health_context: str = "") -> str:
    """Send a message to the LLM and return the response text."""
    llm = get_llm()
    system = SYSTEM_PROMPT
    if health_context:
        system += "\n\n---\n\n" + health_context
    messages = [("system", system)]
    messages += [(msg["role"], msg["content"]) for msg in chat_history]
    messages.append(("user", user_message))
    return llm.invoke(messages).content
