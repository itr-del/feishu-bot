# 🤖 feishu-bot

> 飞书 Claude 智能机器人 — 通过 WebSocket 长连接接收飞书消息，调用 Claude API 回复。

## ✨ 特性

- 📡 **飞书长连接**：WebSocket 接收事件，无需公网 IP
- 🤖 **Claude 对话**：调用 Anthropic Claude API 回复消息
- 🔄 **多轮对话**：记住 chat_id 上下文
- 🛡️ **限流保护**：单用户 3秒/条 防刷
- 📎 **消息类型**：文本 / 图片 / 文件均支持

## 📁 项目结构

```
feishu-bot/
├── main.py              # 入口：启动 WebSocket 监听
├── claude_client.py     # Claude API 客户端
├── feishu_client.py     # 飞书 SDK 封装
├── send_html_diagram.py # 发送 HTML 图表工具
├── config.py            # 配置加载
└── .env                 # 环境变量（gitignore）
```

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/itr-del/feishu-bot.git
cd feishu-bot

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入：
#   FEISHU_APP_ID=cli_xxx
#   FEISHU_APP_SECRET=xxx
#   CLAUDE_API_KEY=sk-ant-xxx

# 4. 启动
python3 main.py
```

## ⚙️ 环境变量

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` | 飞书应用 AppID |
| `FEISHU_APP_SECRET` | 飞书应用 AppSecret |
| `CLAUDE_API_KEY` | Anthropic Claude API Key |
| `CLAUDE_MODEL` | 模型名（默认 claude-sonnet-4） |
| `BOT_NAME` | 机器人名（被 @ 时触发） |

## 🔧 飞书侧配置

1. 飞书开放平台 → 创建应用 → 机器人
2. 权限管理 → 开通 `im:message` / `im:message.group_at_msg`
3. 事件订阅 → `im.message.receive_v1`（**用长连接，无需公网回调**）
4. 创建版本并发布上线

## 📜 License

MIT

## 🙏 致谢

飞书开放平台、Anthropic Claude。