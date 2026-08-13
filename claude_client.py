from collections import defaultdict
from anthropic import AsyncAnthropic
from config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL

client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)

# Conversation history per chat_id, max 20 messages per conversation
_conversations: dict[str, list[dict]] = defaultdict(list)
MAX_HISTORY = 20

SYSTEM_PROMPT = "You are Claude, a helpful AI assistant. Answer concisely and accurately. Respond in the same language the user uses."


async def chat(chat_id: str, user_message: str) -> str:
    history = _conversations[chat_id]

    messages = history + [{"role": "user", "content": user_message}]

    response = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    reply_text = response.content[0].text

    # Update history
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply_text})

    # Trim history
    if len(history) > MAX_HISTORY:
        _conversations[chat_id] = history[-MAX_HISTORY:]

    return reply_text


def clear_history(chat_id: str):
    _conversations.pop(chat_id, None)
