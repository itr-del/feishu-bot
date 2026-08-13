#!/usr/bin/env python3
"""
Render 医保智能监管核心规划全景图 HTML → PNG screenshot → Send to Feishu (Hermes channel).

Usage:
    python3 send_html_diagram.py
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

# ── Config ──────────────────────────────────────────────────
HTML_FILE = os.environ.get(
    "HTML_FILE",
    "/home/ubuntu/医保智能监管核心规划全景图.html"
)
OUTPUT_PNG = os.environ.get(
    "OUTPUT_PNG",
    "/tmp/yibao_supervision_diagram.png"
)

# ⚠️ Credentials MUST be set via environment variables (NEVER hardcode)
#   export FEISHU_APP_ID="cli_xxxxx"
#   export FEISHU_APP_SECRET="xxxxx"
#   export TARGET_CHAT_ID="oc_xxxxx"
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

# Hermes Feishu home channel
TARGET_CHAT_ID = os.environ.get("TARGET_CHAT_ID", "")

FEISHU_BASE = os.environ.get(
    "FEISHU_BASE",
    "https://open.feishu.cn/open-apis"
)

if not all([FEISHU_APP_ID, FEISHU_APP_SECRET, TARGET_CHAT_ID]):
    raise RuntimeError(
        "❌ Missing required env vars: FEISHU_APP_ID, FEISHU_APP_SECRET, TARGET_CHAT_ID\n"
        "   Set them before running: export FEISHU_APP_ID=cli_xxx ..."
    )


# ── Step 1: Render HTML to PNG ──────────────────────────────
def render_html_to_png(html_path: str, output_path: str) -> str:
    """Use Playwright headless Chromium to render the HTML to a full-page PNG."""
    abs_html = "file://" + os.path.abspath(html_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,  # Retina quality
        )
        page.goto(abs_html, wait_until="networkidle", timeout=30000)

        # Take full-page screenshot
        page.screenshot(path=output_path, full_page=True)
        browser.close()

    file_size = os.path.getsize(output_path)
    print(f"✅ Screenshot saved: {output_path} ({file_size:,} bytes)")
    return output_path


# ── Step 2: Get Feishu tenant_access_token ──────────────────
def get_tenant_token(app_id: str, app_secret: str) -> str:
    """Obtain tenant_access_token from Feishu."""
    resp = httpx.post(
        f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to get token: {data}")
    token = data["tenant_access_token"]
    print(f"✅ Tenant token obtained (expires in {data.get('expire', 7200)}s)")
    return token


# ── Step 3: Upload image to Feishu ──────────────────────────
def upload_image(token: str, image_path: str) -> str:
    """Upload an image to Feishu and return the image_key."""
    with open(image_path, "rb") as f:
        resp = httpx.post(
            f"{FEISHU_BASE}/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "image_type": (None, "message"),
                "image": (os.path.basename(image_path), f, "image/png"),
            },
            timeout=30,
        )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to upload image: {data}")
    image_key = data["data"]["image_key"]
    print(f"✅ Image uploaded, image_key: {image_key}")
    return image_key


# ── Step 4: Send image message to chat ──────────────────────
def send_image_message(token: str, chat_id: str, image_key: str):
    """Send an image message to the specified Feishu chat."""
    content = json.dumps({"image_key": image_key})
    body = {
        "receive_id": chat_id,
        "msg_type": "image",
        "content": content,
    }
    resp = httpx.post(
        f"{FEISHU_BASE}/im/v1/messages?receive_id_type=chat_id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to send message: {data}")
    msg_id = data.get("data", {}).get("message_id", "unknown")
    print(f"✅ Image sent to chat {chat_id}, message_id: {msg_id}")
    return data


# ── Main ────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  医保智能监管核心规划图 → Feishu (Hermes)")
    print("=" * 60)

    if not os.path.exists(HTML_FILE):
        print(f"❌ HTML file not found: {HTML_FILE}")
        sys.exit(1)

    # Step 1: Render HTML → PNG
    print("\n📸 Rendering HTML to PNG...")
    render_html_to_png(HTML_FILE, OUTPUT_PNG)

    # Step 2: Get token
    print("\n🔑 Getting Feishu access token...")
    token = get_tenant_token(FEISHU_APP_ID, FEISHU_APP_SECRET)

    # Step 3: Upload image
    print("\n📤 Uploading image to Feishu...")
    image_key = upload_image(token, OUTPUT_PNG)

    # Step 4: Send message
    print("\n💬 Sending image message to Hermes channel...")
    send_image_message(token, TARGET_CHAT_ID, image_key)

    print("\n" + "=" * 60)
    print("  ✅ Done! 图片已发送到 Hermes 飞书频道")
    print("=" * 60)


if __name__ == "__main__":
    main()
