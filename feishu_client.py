import time
import httpx
from config import FEISHU_APP_ID, FEISHU_APP_SECRET

BASE_URL = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
SEND_MSG_URL = f"{BASE_URL}/im/v1/messages"
GET_MSG_URL = f"{BASE_URL}/im/v1/messages"

_cache = {"token": "", "expires_at": 0}


async def get_tenant_access_token() -> str:
    now = time.time()
    if _cache["token"] and _cache["expires_at"] > now + 60:
        return _cache["token"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get token: {data}")

        _cache["token"] = data["tenant_access_token"]
        _cache["expires_at"] = now + data.get("expire", 7200)
        return _cache["token"]


async def send_message(receive_id_type: str, receive_id: str, content: str) -> dict:
    """Send a text message to a chat or user.

    receive_id_type: "chat_id" for group, "open_id" for user
    """
    token = await get_tenant_access_token()
    body = {
        "receive_id": receive_id,
        "msg_type": "text",
        "content": content,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SEND_MSG_URL}?receive_id_type={receive_id_type}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to send message: {data}")
        return data


async def get_message_content(message_id: str) -> dict:
    token = await get_tenant_access_token()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GET_MSG_URL}/{message_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get message: {data}")
        return data


async def reply_to_message(
    chat_type: str, chat_id: str, open_id: str, root_message_id: str, text: str
):
    """Reply to a message. In p2p chat, use open_id; in group, use chat_id."""
    if chat_type == "p2p":
        receive_id_type = "open_id"
        receive_id = open_id
    else:
        receive_id_type = "chat_id"
        receive_id = chat_id

    body = {
        "receive_id": receive_id,
        "msg_type": "text",
        "content": text,
        "root_id": root_message_id,
    }
    token = await get_tenant_access_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SEND_MSG_URL}?receive_id_type={receive_id_type}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to reply: {data}")
        return data
