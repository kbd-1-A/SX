# 时叙 · 陪伴型 Agent

一个独立的陪伴 Agent 网页。不是聊天机器人，是被慢慢「养」出来的存在——记住你说过的、感受过的，随时间累积理解。

## 当前状态（V1 骨架）

- ✅ 后端 FastAPI + WebSocket 流式对话 + SQLite 存储 + persona 灵魂
- ✅ 前端 Vue3 单页（对话区 + 侧边面板：亲密度 / 话题 / 记忆时间线）
- ✅ 对话历史落库，刷新页面可找回
- ⬜ DeepSeek API key（需你自己填）
- ⬜ 后置：语音、形象、词典情感引擎、每日自动总结、向量检索、多端

## 目录结构

```
时叙/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口
│   │   ├── config.py        # .env 加载（绝对路径，不受 CWD 影响）
│   │   ├── api/             # chat.py（WS）、memory.py（REST）
│   │   ├── agents/          # persona 加载 + 对话路由（DeepSeek 流式）
│   │   ├── memory/          # SQLite 读写 + 画像
│   │   └── db/              # 建表（schema.sql）
│   ├── persona/shisu.md     # 时叙灵魂（system prompt 唯一来源）
│   ├── data/shishu.db       # SQLite 数据文件（自动生成，已 gitignore）
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/ChatView.vue
│   │   ├── components/      # ChatWindow / SidePanel
│   │   └── stores/chat.ts   # WebSocket 状态
│   └── package.json
├── CLAUDE.md                # 灵魂 + 工程手册
└── README.md
```

## 怎么跑起来

### 1. 配置 DeepSeek key

```bash
cd backend
cp .env.example .env
# 编辑 .env，填 DEEPSEEK_API_KEY（https://platform.deepseek.com 获取）
```

### 2. 启动后端（端口 8000）

```bash
cd backend
source venv/Scripts/activate        # 已建好 venv；也可直接用 venv/Scripts/python.exe
uvicorn app.main:app --reload --port 8000
```

验证：`curl http://127.0.0.1:8000/api/health` → `{"status":"ok","database":"connected"}`

### 3. 启动前端（端口 5173）

```bash
cd frontend
npm run dev
```

浏览器打开 `http://localhost:5173` 即可对话。

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 页面上"离线" | 后端没起 / 端口不对 | 确认后端在 8000；改了端口要同步改 `frontend/vite.config.ts` |
| 回复"未配置 DEEPSEEK_API_KEY" | `.env` 没建或没填 | `cp .env.example .env` 后填写，改完手动重启后端 |
| 8000 端口被占但不响应 | Windows 僵尸进程 | 换 8001 端口启动（记得改 vite 代理），或 `netstat -ano | grep 8000` 找 PID 杀掉 |
| 新增 `.py` 文件不生效 | `--reload` 不检测新文件 | 手动重启后端 |
| 改了 `.env` 不生效 | `.env` 改动不触发 reload | 手动重启后端 |

## V1 边界

第一版只做「能说话、记得住、看得到它在长」的骨架。语音/形象/桌面宠物、词典情感引擎、每日自动总结、向量检索、多端全部后置，但代码结构预留了扩展位（agents/、memory/ 各自独立）。

## 文档

- 策划案：`E:\workbuddy-txt\时序\时叙_项目策划案.md`
- V1 方案：`E:\workbuddy-txt\时序\时叙_V1方案_Agent页面与脚手架.md`
