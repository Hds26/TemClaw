<div align="center">

# 🤖 Agent Template

**可插拔 AI 智能体框架，开箱即用的 Web UI**

接入任意 LLM 服务商，拖入 Skill 插件，几分钟构建你自己的 AI Agent。

[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ 特性一览

- **12+ LLM 服务商** — OpenAI、Anthropic Claude、Moonshot/Kimi、DeepSeek、通义千问、智谱 GLM、零一万物、Groq、Together AI、Ollama 及任意 OpenAI 兼容接口
- **ReAct Agent 循环** — 自主多步推理 + 工具调用（最多 8 轮迭代，自动检测重复调用并终止）
- **可插拔 Skill** — 放入 `.py` 文件或通过 Web UI 上传即可扩展能力，无需改动框架代码
- **流式输出** — 基于 SSE 的实时流式响应，逐字显示 + 工具调用过程可视化（含图片等富内容直出）
- **对话持久化** — 聊天记录存入 SQLite，侧边栏浏览/重命名/删除历史会话
- **Provider 管理** — 在设置页增删改查 LLM 服务商配置，支持一键**连接测试**
- **Skill 管理** — 在设置页启用/禁用/上传/删除技能插件
- **暗色主题 UI** — 基于 Tailwind CSS 的现代化响应式界面

---

## 🏗️ 系统架构

```
                            ┌─────────────────────────────────────────┐
                            │              用户浏览器                   │
                            └──────────────────┬──────────────────────┘
                                               │
                                       http://localhost:3000
                                               │
                ┌──────────────────────────────┴──────────────────────────────┐
                │                      Next.js 前端                           │
                │                                                             │
                │   ┌─────────┐   ┌──────────────┐   ┌───────────────────┐   │
                │   │ 会话侧栏 │   │   对话主区域   │   │   设置页面        │   │
                │   │         │   │              │   │                   │   │
                │   │ • 新建   │   │ • 消息列表    │   │ • Provider 管理   │   │
                │   │ • 历史   │   │ • 工具调用卡片 │   │ • Skill 管理     │   │
                │   │ • 重命名 │   │ • 流式渲染    │   │ • 连接测试       │   │
                │   │ • 删除   │   │ • System     │   │ • 上传 Skill     │   │
                │   │         │   │   Prompt     │   │                   │   │
                │   └─────────┘   └──────────────┘   └───────────────────┘   │
                └──────────────────────────┬──────────────────────────────────┘
                                           │
                              REST API + SSE Stream
                                           │
                ┌──────────────────────────┴──────────────────────────────────┐
                │                     FastAPI 后端 (:8000)                     │
                │                                                             │
                │   ┌─────────────────────────────────────────────────────┐   │
                │   │                   API 路由层                         │   │
                │   │                                                     │   │
                │   │  /api/chat    /api/providers   /api/conversations   │   │
                │   │               /api/skills                           │   │
                │   └────────────────────┬────────────────────────────────┘   │
                │                        │                                    │
                │          ┌─────────────┴─────────────┐                     │
                │          ▼                           ▼                      │
                │   ┌─────────────┐           ┌──────────────┐               │
                │   │ ReAct Agent │           │  Skill 加载器 │               │
                │   │    循环     │◄─────────►│  (自动发现)   │               │
                │   └──────┬──────┘           └──────┬───────┘               │
                │          │                         │                        │
                │     ┌────┴────┐          ┌─────────┴─────────┐             │
                │     ▼         ▼          ▼         ▼         ▼             │
                │  ┌──────┐ ┌──────┐  ┌──────────────────────────────────┐   │
                │  │OpenAI│ │Claude│  │ 计算器 / 搜索 / 读网页 / 生图 /   │   │
                │  │ SDK  │ │ SDK  │  │ Python 沙箱 / 日期时间 等内置技能 │   │
                │  └──────┘ └──────┘  └──────────────────────────────────┘   │
                │     LLM 客户端               内置 Skills                    │
                │     工厂                     + 用户自定义                    │
                │                                                             │
                │   ┌─────────────────────────────────────────────────────┐   │
                │   │                SQLite 数据库                         │   │
                │   │                                                     │   │
                │   │  providers │ skills_config │ conversations │ messages│   │
                │   └─────────────────────────────────────────────────────┘   │
                └─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

| 工具 | 版本 |
|------|------|
| Python | 3.8+ |
| Node.js | 18+ |
| pip / npm | 最新版 |

### 1. 克隆仓库

```bash
git clone https://github.com/<your-username>/agent-template.git
cd agent-template
```

### 2. 安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd ../frontend
npm install
```

### 3. 启动服务

打开 **两个终端**：

```bash
# 终端 1 — 后端
cd backend
uvicorn main:app --reload --port 8000
```

```bash
# 终端 2 — 前端
cd frontend
npm run dev
```

### 4. 打开浏览器

访问 **[http://localhost:3000](http://localhost:3000)**

### 5. 添加 Provider

点击左侧边栏底部 **Settings** → **Add Provider** → 填写 API Key → **Save**，即可开始对话。

---

## 🔌 支持的服务商

| 服务商 | 类型 | Base URL | 代表模型 |
|--------|------|----------|----------|
| OpenAI | `openai` | `https://api.openai.com/v1` | `gpt-4o`、`gpt-4o-mini` |
| Anthropic | `anthropic` | （SDK 内置） | `claude-3-5-sonnet-20241022` |
| Moonshot (Kimi) | `moonshot` | `https://api.moonshot.cn/v1` | `kimi-k2.5` |
| DeepSeek | `deepseek` | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 通义千问 (Qwen) | `qwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` |
| 智谱 AI (GLM) | `zhipu` | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |
| 零一万物 (Yi) | `yi` | `https://api.lingyiwanwu.com/v1` | `yi-large` |
| 百川智能 | `baichuan` | `https://api.baichuan-ai.com/v1` | `Baichuan4` |
| MiniMax (海螺) | `minimax` | `https://api.minimax.chat/v1` | `MiniMax-Text-01` |
| Groq | `groq` | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| Together AI | `together` | `https://api.together.xyz/v1` | `Llama-3.3-70B-Instruct-Turbo` |
| Ollama（本地） | `ollama` | `http://localhost:11434/v1` | `llama3.2` |
| 自定义 | `openai_compat` | 任意 OpenAI 兼容地址 | 自行填写 |

> **使用代理/中转站？** 将 Base URL 改为代理地址，模型名与代理实际支持的保持一致。添加后可在设置页点击 **Test** 按钮验证连接。

---

## 🛠️ 内置技能

| 技能 | 功能 | 依赖 |
|------|------|------|
| `calculator` | 安全计算数学表达式（`sqrt`、`sin`、`log`、`pi` 等） | 无 |
| `web_search` | DuckDuckGo 搜索，支持 `search`（网页）和 `news`（新闻）模式 | 需要网络 |
| `url_reader` | 抓取指定 URL 并提取正文（与 `web_search` 配合：先搜后读） | 需要网络 |
| `image_generate` | 按文本描述生成或检索图片，下载到本地并通过 Markdown 展示 | 可选：`IMAGE_API_KEY`（见环境变量）；否则走 DuckDuckGo / 公开接口 |
| `python_execute` | 在受限子进程中执行 Python 片段，返回 stdout/stderr | 无（建议用标准库；部分环境包名见技能内检测列表） |
| `datetime_info` | 获取当前日期、时间、星期、时区 | 无 |

---

## 🧩 添加自定义技能

### 方式一：通过 Web UI 上传

进入 **Settings** → 点击 **Upload Skill** → 选择 `.py` 文件 → 自动验证并注册，立即可用。

### 方式二：放入目录

在 `backend/skills/` 下新建 `.py` 文件，重启后端自动发现。

### Skill 模板

```python
from skills.base import Skill

class MySkill(Skill):
    name = "my_skill"                         # 唯一标识（建议 snake_case）
    description = "描述技能做什么，帮助 LLM 决定何时调用。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要处理的输入"
            }
        },
        "required": ["query"],
    }

    def execute(self, query: str) -> str:
        return f"处理结果：{query}"
```

### 编写规范

- `name` 必须全局唯一
- `execute()` 的参数名必须与 `parameters.properties` 的键名一致
- `execute()` 必须返回 **字符串**
- `description` 写得越清楚，LLM 调用越准确

---

## 📁 项目结构

```
agent-template/
├── backend/
│   ├── main.py                 # FastAPI 入口 + 生命周期 + /static/images 静态资源
│   ├── requirements.txt
│   ├── api/
│   │   ├── chat.py             # POST /api/chat（SSE 流式 + 消息持久化）
│   │   ├── conversations.py    # CRUD /api/conversations
│   │   ├── providers.py        # CRUD /api/providers + 连接测试
│   │   └── skills.py           # /api/skills（列表、上传、开关、删除）
│   ├── core/
│   │   ├── agent.py            # ReAct Agent 循环（多步工具调用）
│   │   ├── llm.py              # LLM 客户端工厂（OpenAI / Anthropic）
│   │   └── skill_loader.py     # 自动发现、DB 同步、文件验证
│   ├── skills/
│   │   ├── base.py             # Skill 抽象基类
│   │   ├── calculator.py       # 内置：数学计算器
│   │   ├── datetime_info.py    # 内置：日期时间查询
│   │   ├── web_search.py       # 内置：DuckDuckGo 搜索
│   │   ├── url_reader.py       # 内置：网页正文抓取
│   │   ├── image_generate.py   # 内置：图片生成/检索（静态文件见 static/images）
│   │   └── python_sandbox.py   # 内置：Python 代码执行（工具名 python_execute）
│   ├── static/
│   │   └── images/             # 生图技能保存的图片（/static/images 挂载）
│   ├── db/
│   │   └── storage.py          # 异步 SQLite 封装（4 张表）
│   └── data/
│       └── agent.db            # SQLite 数据库（首次运行自动创建）
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx            # 对话主页（侧边栏 + 对话区）
│   │   └── settings/page.tsx   # Provider + Skill 管理
│   ├── components/
│   │   ├── ChatMessage.tsx     # 消息气泡（Markdown + 工具调用卡片）
│   │   └── SkillBadge.tsx      # 技能标签（含 Tooltip）
│   └── lib/
│       └── api.ts              # 类型化 API 客户端 + SSE 流
│
├── docs/
│   ├── 用户使用手册.md
│   └── 项目架构与调用流程.md
│
├── .env.example                # 环境变量模板
├── .gitignore
└── LICENSE
```

---

## ⚙️ 环境变量

将 `.env.example` 复制到 `backend/.env`：

```bash
cp .env.example backend/.env
```

**后端：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_PATH` | `data/agent.db` | SQLite 数据库路径 |
| `DEFAULT_PROVIDER_NAME` | — | 首次启动时自动创建的 Provider 名称 |
| `DEFAULT_PROVIDER_TYPE` | `openai` | 自动创建的 Provider 类型 |
| `DEFAULT_PROVIDER_API_KEY` | — | 自动创建的 Provider API Key |
| `DEFAULT_PROVIDER_BASE_URL` | — | 自动创建的 Provider 接口地址 |
| `DEFAULT_PROVIDER_MODEL` | `gpt-4o-mini` | 自动创建的 Provider 默认模型 |

> 仅当数据库中 **没有任何 Provider** 时才会执行自动创建。

**生图技能（`image_generate`，可选）：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IMAGE_API_KEY` | — | 若设置，优先走 SiliconFlow 等 OpenAI 兼容生图 API |
| `IMAGE_API_BASE` | `https://api.siliconflow.cn/v1` | 生图 API Base URL |
| `BACKEND_URL` | `http://127.0.0.1:8000` | 返回给前端的图片访问基址（需与后端实际地址一致） |

**前端** (`frontend/.env.local`)：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 后端 API 地址 |

---

## 📡 API 接口

后端启动后可访问交互式文档：**[http://localhost:8000/docs](http://localhost:8000/docs)**

健康检查：`GET /api/health` → `{"status":"ok"}`。

### 对话

```
POST /api/chat
```

```json
{
  "provider_id": 1,
  "messages": [{ "role": "user", "content": "2 的 10 次方是多少？" }],
  "system_prompt": "You are a helpful assistant.",
  "conversation_id": null
}
```

返回 `text/event-stream`：

```
data: {"type": "tool_start", "name": "calculator", "args": {"expression": "2**10"}}
data: {"type": "tool_end",   "name": "calculator", "result": "1024"}
data: {"type": "token",      "content": "2 的 10 次方是 **1024**。"}
data: {"type": "done"}
```

### Provider 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/providers` | 获取列表（API Key 已脱敏） |
| `POST` | `/api/providers` | 新建 |
| `PATCH` | `/api/providers/{id}` | 更新 |
| `DELETE` | `/api/providers/{id}` | 删除 |
| `POST` | `/api/providers/{id}/test` | 连接测试 |

### Skill 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/skills` | 获取列表（含启用状态） |
| `POST` | `/api/skills/upload` | 上传 `.py` 文件 |
| `PATCH` | `/api/skills/{name}` | 启用 / 禁用 |
| `DELETE` | `/api/skills/{name}` | 删除（仅用户上传的） |

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/conversations` | 获取列表（按最近更新排序） |
| `POST` | `/api/conversations` | 新建 |
| `GET` | `/api/conversations/{id}` | 获取详情（含消息列表） |
| `PATCH` | `/api/conversations/{id}` | 重命名 |
| `DELETE` | `/api/conversations/{id}` | 删除（级联删除消息） |

---

## 🗄️ 数据库

SQLite，包含 4 张表（首次启动自动创建）：

| 表名 | 用途 |
|------|------|
| `providers` | LLM 服务商配置（名称、类型、API Key、模型等） |
| `skills_config` | 技能启用/禁用状态及来源追踪 |
| `conversations` | 会话元数据（标题、时间戳） |
| `messages` | 会话消息记录 |

---

## 🤝 参与贡献

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/awesome-skill`)
3. 提交修改 (`git commit -m '添加 awesome-skill'`)
4. 推送分支 (`git push origin feature/awesome-skill`)
5. 提交 Pull Request

---

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。
