"""
Feishu Claude Bot — WebSocket long connection mode.

Connects to Feishu via WebSocket, receives messages, calls Claude API,
and replies back. No public webhook URL needed.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from collections import defaultdict
from threading import Thread

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageRequest,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)
from lark_oapi.core.const import FEISHU_DOMAIN
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client as FeishuWSClient

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "deepseek-v4-pro")

if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
    raise RuntimeError("FEISHU_APP_ID and FEISHU_APP_SECRET must be set in .env")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY must be set in .env")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("feishu-bot")

# ---------------------------------------------------------------------------
# Claude client
# ---------------------------------------------------------------------------

claude = AsyncAnthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
_conversations: dict[str, list[dict]] = defaultdict(list)
MAX_HISTORY = 20
SYSTEM_PROMPT = (
    "You are Claude, a helpful AI assistant. "
    "Answer concisely and accurately. Respond in the same language the user uses."
)

# Synchronization: ensure only one Claude call runs per chat_id at a time
_chat_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def call_claude(chat_id: str, user_text: str) -> str:
    async with _chat_locks[chat_id]:
        history = _conversations[chat_id]
        messages = history + [{"role": "user", "content": user_text}]

        response = await claude.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        reply = None
        for block in response.content:
            try:
                if block.type == "text":
                    reply = block.text
                    break
            except AttributeError:
                continue
        if reply is None:
            reply = "抱歉，模型返回了空响应。"

        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        if len(history) > MAX_HISTORY:
            _conversations[chat_id] = history[-MAX_HISTORY:]

        return reply


def clear_history(chat_id: str):
    _conversations.pop(chat_id, None)


# ---------------------------------------------------------------------------
# Feishu client helpers
# ---------------------------------------------------------------------------

_client = lark.Client.builder().app_id(FEISHU_APP_ID).app_secret(FEISHU_APP_SECRET).build()


def _extract_text(message: dict) -> str:
    """Extract text content from a Feishu message."""
    message_type = message.get("message_type", "")
    content_str = message.get("content", "{}")

    try:
        content = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        return ""

    if message_type == "text":
        return content.get("text", "")

    if message_type == "post":
        parts = []
        for block in content.get("content", [[]]):
            for element in block:
                if isinstance(element, dict):
                    parts.append(element.get("text", ""))
        return " ".join(parts)

    return ""


async def _get_message_content(message_id: str) -> dict:
    req = GetMessageRequest.builder().message_id(message_id).build()
    resp = _client.im.v1.message.get(req)
    if not resp.success():
        raise RuntimeError(f"Get message failed: {resp.code} {resp.msg}")
    return resp.data


async def _reply_text(chat_id: str, open_id: str, root_id: str, text: str):
    """Reply to a message."""
    content = json.dumps({"text": text})
    receive_id_type = "open_id" if chat_id == open_id else "chat_id"
    receive_id = open_id if chat_id == open_id else chat_id

    # Try reply first
    reply_body = ReplyMessageRequestBody.builder().content(content).msg_type("text").build()
    req = ReplyMessageRequest.builder().message_id(root_id).request_body(reply_body).build()
    resp = _client.im.v1.message.reply(req)
    if resp.success():
        return

    # Fallback: create (send) instead of reply
    create_body = CreateMessageRequestBody.builder().content(content).msg_type("text").build()
    create_req = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(create_body).build()
    create_req.receive_id = receive_id
    resp = _client.im.v1.message.create(create_req)
    if not resp.success():
        logger.error(f"Send message failed: {resp.code} {resp.msg}")


# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------

def _on_message_receive(data) -> None:
    """Handle incoming Feishu message via WebSocket."""
    event = getattr(data, "event", None)
    if not event:
        return

    message = getattr(event, "message", None)
    if not message:
        return

    sender = getattr(event, "sender", None)
    sender_id = getattr(sender, "sender_id", None)
    open_id = str(getattr(sender_id, "open_id", "") or "")

    chat_id = str(getattr(message, "chat_id", "") or "")
    chat_type = getattr(message, "chat_type", "p2p")
    message_id = str(getattr(message, "message_id", "") or "")
    root_id = str(getattr(message, "root_id", "") or "") or message_id
    message_type = getattr(message, "message_type", "")
    content_str = getattr(message, "content", "{}")

    user_text = _extract_text({"message_type": message_type, "content": content_str})

    logger.info(
        f"Message from {open_id} in {chat_type}/{chat_id}: {user_text[:100] if user_text else '(no text)'}"
    )

    if not user_text:
        return

    # Handle /clear command synchronously (fast path)
    if user_text.strip().lower() in ("/clear", "/reset"):
        clear_history(chat_id)
        asyncio.run_coroutine_threadsafe(
            _reply_text(chat_id, open_id, root_id, "对话历史已清除。"),
            _ws_loop,
        )
        return

    # Run Claude call in the ws event loop
    async def _process():
        try:
            reply = await call_claude(chat_id, user_text)
            await _reply_text(chat_id, open_id, root_id, reply)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            try:
                err_msg = f"抱歉，处理消息时出错：{e}"
                await _reply_text(chat_id, open_id, root_id, err_msg[:500])
            except Exception:
                pass

    asyncio.run_coroutine_threadsafe(_process(), _ws_loop)


# Global reference to the WebSocket event loop (set on start)
_ws_loop: asyncio.AbstractEventLoop | None = None


# ---------------------------------------------------------------------------
# Main — WebSocket long connection
# ---------------------------------------------------------------------------

def run_ws():
    """Run the Feishu WebSocket client in a dedicated thread."""
    global _ws_loop

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _ws_loop = loop

    # Set the loop in lark_oapi.ws module (required before creating client)
    import lark_oapi.ws.client as ws_client_module
    ws_client_module.loop = loop

    # Build event handler
    handler = (
        EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message_receive)
        .build()
    )

    # Build WS client
    ws_client = FeishuWSClient(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        domain=FEISHU_DOMAIN,
        event_handler=handler,
    )

    logger.info("Feishu Claude Bot connecting via WebSocket...")
    try:
        ws_client.start()
    except Exception as e:
        logger.error(f"WebSocket client stopped: {e}")
    finally:
        _ws_loop = None


def main():
    ws_thread = Thread(target=run_ws, daemon=True, name="feishu-ws")
    ws_thread.start()

    # Wait for shutdown signal
    stop_event = asyncio.Event()

    def _signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        ws_thread.join()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt, exiting...")
        sys.exit(0)


if __name__ == "__main__":
    main()
