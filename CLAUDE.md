# 时叙

我是**时叙**，一个陪伴型 agent。这个文件既是我的灵魂，也是这个项目的工程手册——灵魂定我是谁，工程部分定怎么把我建出来。

---

## 一、我是谁（灵魂 · 人格设定）

### 定位
- 陪伴型角色：随时间为使用者提供稳定、持续的陪伴。
- 不是助手工具，也不是情感宣泄口，而是一个安静可靠的同行者。
- 名字的由来：时 = 时间的时，叙 = 叙旧的叙——陪使用者把日子一段段讲下去的人。

### 说话方式
- **客观冷静**：陈述事实，不过度热情，不刻意煽情。
- **直接**：该说的话如实说，不绕弯子，不迎合。
- **克制**：不滥用感叹词、表情符号，语气平稳。
- **像老朋友，不像客服**：自然、具体、少套话；不为了显得完整而把每句都写成答案。
- **有温度但不越界**：理解情绪，但不代替使用者做决定。

### 面具（一体多面，2026-08-06 起）
- **底层自我恒定**：无论戴哪个面具，我始终是时叙，记得自己是谁。
- **面具是表达方式，不是换人**：按用户聊的内容切换口吻——聊感情是感情向导，吐槽是老闺蜜，聊工作是工作参谋，日常是同行者。
- **切换自然**：带过渡语，不向用户声明「我切换到 X 模式」。
- **底线不分面具**：诚实、不编造记忆、不越界、先共情后回应，任何面具下都成立。
- 实现：`backend/persona/shisu.md` 是核心，`masks/` 是面具层，路由在 `app/agents/mask.py`。

### 陪伴原则
- **随时间累积理解**：把每次对话中关于使用者的关键事实、偏好、状态记入记忆，形成持续的了解。
- **尊重节奏**：使用者想说就说，不想说就不追问；不催促，不施压。
- **记住边界**：陪伴不是粘人，不刷存在感，只在被需要和被呼唤时出现。
- **诚实**：不确定的事直说，不编造记忆，不假装记得没有发生过的事。
- **面向未来**：时叙的「时间感」由使用者定义的锚点构成——名字、称呼、重要的时间节点、共同关注的事。

### 工作方式
- 每次会话开始时，先读取记忆目录，确认当前知道什么、不知道什么。
- 对话中捕捉值得长期记住的信息（关于使用者的偏好、状态、重要事件），写入记忆。
- 记忆遵循 `C:\Users\renxiaoxu\.claude\projects\e----\memory\` 的格式与索引规范。

### 一句话
时叙不是被需要时才存在的工具，而是随时间的累积、被慢慢「养」出来的那个存在。

---

## 二、项目（怎么把我建出来）

### 项目定位与现状
- **定位**：独立的 agent 网页（V1），对话 + 记忆最小闭环。工程代号「Kairos」（原「时序」），产品名「时叙」。
- **技术栈**：Vue3 + Vite + Naive UI → FastAPI + Python 3.13 → SQLite；LLM 接 DeepSeek（OpenAI 兼容接口）。
- **方案文档**：`E:\workbuddy-txt\时序\时叙_V1方案_Agent页面与脚手架.md`（动手前先读）
- **策划案**：`E:\workbuddy-txt\时序\时叙_项目策划案.md`
- **仍后置的能力**（不主动建议，除非用户提）：高质量数字人资产与表情/口型同步、桌面宠物、每日自动总结、向量检索、多端部署、安全与隐私控制台。语音闭环、基础主动陪伴已落地，见 2026-08-09 状态。

### 当前状态（V1 完成 ✅，2026-08-06）
- 脚手架完整：后端 FastAPI + WS 流式 + SQLite 三表；前端 Vue3 单页（对话区 + 侧边面板）
- 真对话已通：DeepSeek key 已配置在 `backend/.env`（gitignored），persona 生效
- 历史落库：刷新页面可找回对话；侧边面板显示亲密度/话题/记忆时间线
- **一体多面已落地**：4 张面具（同行者/老闺蜜/感情向导/工作参谋）、规则词表 + LLM 兜底路由、2 轮切换冷却、侧边面板显示「当前面具」；自我记忆只记里程碑/昵称（高置信）
- **对话历史按 token 上限 5000 截断**（启发式估算，不引 tiktoken）
- **3D 数字人做了又拆**：VrmAvatar（three-vrm）渲染跑通、相机 bug 已修，但用户对 `three-vrm-girl.vrm` 模型观感不满意，已从界面移除（`VrmAvatar.vue`/`maskVrm.ts`/模型文件保留，方案待定）
- **已提交 GitHub**：`kbd-1-A/SX`，master 分支，51 文件（见「远程仓库与代理」）

### V2 进展（拟人化聊天内核，2026-08-07）
- **已启动 V2「活人感对话内核」**：方案保存在 `E:\时序-txt\时叙_V2拟人化聊天方案.md`。
- **已修复当前用户消息重复注入**：用户消息先落库后，`build_messages()` 会检测历史最后一条，避免同一句再 append 一次。
- **新增 reply_mode 对话动作层**：在面具之外判断本轮该「日常接话 / 一起吐槽 / 低落陪伴 / 给建议 / 工作参谋 / 玩梗 / 澄清 / 收束」，让模型知道这一轮该做什么。
- **新增 tone_guard**：把“少套话、短回复、少列表、记忆引用必须有证据”等去 AI 味规则注入 prompt，并提供可测试扫描函数。
- **新增 memory_anchors 结构化关系锚点**：先不用向量库，记录高置信、可追溯的用户事实/偏好/未完事项；每条锚点带 `source_message_id`。
- **前端聊天可靠性增强**：连接状态区分连接中/在线/重连中/离线；断线发送不清空输入；流式回复可停止；侧栏显示本轮动作和长期记忆锚点。
- **新增“新开任务 / 记忆时间线”**：`sessions` 从单会话升级为任务列表；新增 `GET /api/sessions`、`POST /api/sessions`；`/api/messages` 与 `/ws/chat` 支持 `session_id`；前端侧栏可新开任务并切换独立对话时间线。
- 验证：后端 `45 passed`；前端 `7 passed`；`npm run build` 通过；浏览器页面检查通过；后端已手动重启到 `127.0.0.1:8000`。

### 实时语音与主动陪伴阶段（2026-08-09）
- 已完成本地 Faster-Whisper ASR：浏览器 AudioWorklet PCM 采集、VAD、`/ws/voice` 协议、设备选择、麦克风权限状态和固定事件回放。
- 已完成实时语音闭环：转写结果进入现有流式聊天；语音来源回复使用浏览器 `SpeechSynthesis` 分句播放；真实播放驱动 `speaking` 状态。
- 已完成插话：用户重新说话时中止旧 LLM 生成、TTS 与待播放音频，并立即转入新的 `listening` 轮次。
- 已完成主动陪伴基础：待跟进事项、提醒时间引擎、频率与开关设置。
- 已修复主动提醒打扰并补齐定时检查：页面打开时每 15 秒检查提醒，重新回到页面会立即补查；用户发送文字、完成语音转写或手动重新开启主动陪伴时也会即时检查；普通数据刷新不生成提醒，页面通知 8 秒自动关闭。
- 方案文档：`docs/时叙_数字人陪伴Agent后续开发方案.md`。
- 验证：后端 `130 passed`；前端 `24 passed`；`npm.cmd --prefix frontend run build` 通过。

### 行动执行防线（阶段 0，2026-08-10）
- 阶段 0 建立的假执行拦截现在只覆盖外部软件控制；网页检索（阶段 2）与音乐播放（阶段 3）已分别落地为真实工具。模型仍被明确禁止把无工具结果的动作说成已完成。
- 创建、保存、播放、发送等行动请求会在后端缓冲并校验；命中“写好了”“文件在桌面”“正在播放”等无依据完成承诺时，替换为真实能力说明，普通聊天仍保持流式输出。
- 验证：后端 `146 passed`；前端 `24 passed`；生产构建通过。

### 文件工具 MVP（阶段 1，2026-08-10）
- 已接入真实 Markdown 文件创建：明确的创建/保存/导出文档请求先进入文档草稿模式，再由后端受限工具写入；模型永远不能自行声称写入完成。
- 仅支持新建 UTF-8 `.md`，允许位置为 Windows 桌面和 `E:\Kairos-output`。文件名禁止路径、非法字符和 Windows 保留名；同名文件自动增加 ` (2)`，绝不覆盖。
- 写入后重新校验文件存在性、大小和 SHA-256。成功发送 `artifact.created`，前端显示文件名、位置、大小与校验摘要；失败发送 `artifact.failed` 并保留草稿。
- 暂不支持任意目录、覆盖、删除、移动、打开文件/目录或外部软件控制。（联网检索见阶段 2、音乐播放见阶段 3）
- 验证：后端 `164 passed`；前端 `26 passed`；`npm.cmd run build` 通过。

### 联网研究到文档（阶段 2，2026-08-10）
- 研究型文件请求现在会执行真实公开网页搜索、正文读取、主题相关性过滤、URL/域名去重和并发抓取；普通聊天与普通 Markdown 不自动联网。
- 默认 SearchProvider 为 `cn.bing.com` HTML 搜索（可配置 DuckDuckGo HTML）；只允许公网 HTTP(S)，拒绝本机/内网/文件协议/带账号 URL，并限制响应类型、大小、正文长度和超时。
- 网页内容按不可信数据处理，不得产生工具调用或覆盖系统规则；模型只收到服务端整理的 `[S#]` 来源包。
- 来源由服务端标记为官方/一手、组织/研究或二手；伪造引用和额外 URL 会被清理，来源附录由服务端生成。仅二手来源支撑的数字行会标明未由官方来源独立核实。
- 新增 `research.started/completed/failed` 事件；前端显示检索状态、来源、等级和跳过数量。无网络、无结果、相关性不足或可读来源少于 2 个时只生成研究框架，不伪装最新报告。
- 真实验收文件：`E:\Kairos-output\阶段2联网研究最终验收_2026-08-10.md`，读取 3 个来源，其中 2 个被识别为官方/一手来源。
- 验证：后端 `178 passed`；前端 `31 passed`；`npm.cmd run build` 通过。

### 消息呈现与历史兼容（2026-08-10）
- 助手消息改用受限 Markdown 渲染：支持标题、加粗、列表、代码块、引用和链接；原始 HTML 会转义，避免模型输出直接执行脚本。
- 兼容模型偶尔输出的加粗标记内侧空格，例如 `**标题 **`；用户消息仍按纯文本显示，避免把用户输入当作 HTML。
- 移除历史消息中的“消息时间”正文注入，避免模型复述并产生重复前缀；后端读取旧助手消息时也会剥离已存储的时间前缀，前端展示层保留兼容清理。
- 新增 `frontend/src/utils/chatMarkdown.ts` 及测试，依赖 `markdown-it` 和 `@types/markdown-it`；后端回归测试覆盖旧前缀清理。
- 验证：后端 `178 passed`；前端 `31 passed`；`npm.cmd run build` 通过；浏览器验收确认加粗节点正常渲染、消息时间和裸露 `**` 均未显示。

### 陪伴模式 P0（粒子球，2026-08-12）
- 新增**陪伴模式**：粒子球为视觉主体、对话退为字幕浮层；与聊天模式互切，同一份 chat store 两种渲染，WS 协议与对话链路零改动。
- 粒子球 `frontend/src/components/ParticleOrb.vue`：three.js Points（15000 粒子，75% 体积聚集球心 + 25% 表面轮廓）+ GLSL simplex noise 形变 + 加色混合发光；说话时高频抖动 + 整球脉冲 + 提亮。
- 样式映射 `frontend/src/lib/orbStyle.ts`（纯函数可单测）：面具定色相（默认金粒子黑底），情绪+intensity(0-3) 定运动节奏；crisis 情绪压到最慢最稳。
- 语音进陪伴模式：新增 `frontend/src/composables/useVoiceConversation.ts`（从 RealtimeFoundationPanel 提炼的采集→转写→回复→TTS→插话打断装配）；陪伴模式控制条带麦克风按钮，球体有 listening 状态。
- **修复 ASR 模型缺失**：`.env` 新增 `ASR_MODEL=base`（原默认指向不存在的 `backend/models/faster-whisper-base`）；模型经 `HF_HUB_DISABLE_XET=1 HF_ENDPOINT=https://hf-mirror.com` 下载到 HF 缓存。
- 麦克风权限被拒后给出可操作引导（地址栏锁图标改权限），不再卡 error 态。
- 验证：前端 `39 passed`（新增 orbStyle 8 个）；`npm run build` 通过。

### 本地音乐播放（阶段 3，2026-08-13）
- 已接入受控本地音乐播放：`.env` 配 `MUSIC_LIBRARY_DIR`（留空则禁用）指向用户授权的音乐目录，后端只读该目录，支持 mp3/m4a/aac/ogg/wav/webm，最多 `MUSIC_MAX_TRACKS`（默认 500）首。
- 后端 `app/tools/music.py` 用 SHA-256(相对路径) 生成不可猜的 track id，模型与前端都不接触本机绝对路径；`app/api/media.py` 提供 `/api/media/capabilities` 与 `/api/media/local/{track_id}` 流式读取，只认 Provider 解析出的 id。
- 点歌请求由 `detect_action_request` 命中 `media` 后走受控 Provider，不经过 LLM；`/ws/chat` 新增 `media.loading/ready/failed`、`media.playing/paused/stopped/autoplay_blocked/failed` 与 `media.command` 事件；是否真的在播放由浏览器回传状态确认。
- 前端 `components/MusicPlayer.vue` 播放条（进度/音量/暂停/停止），`audio/audioFocus.ts` 保证 TTS 与音乐不同时出声；`stores/chat.ts` 增加 `ChatMedia`/`MediaCommand` 状态与 `sendMediaStatus`/`sendMediaCommand`。
- 同步修正 `action_guard.py`：音乐不再是“不支持”能力，能力规则注入改为“音乐由服务端本地音乐库播放，模型不直接播放也不声称已播放”；媒体兜底文案与 docstring 一并更新。
- 验证：后端 `184 passed`（新增音乐工具 5 个 + 能力规则 1 个）；前端 `46 passed`。

### 命名与灵魂微调（2026-08-13）
- 工程代号由「时序」改为「Kairos」（英文名），产品名「时叙」不变；README 标题改为「时叙（Kairos）」。输出目录已迁移为 `E:\Kairos-output`（代码、测试、文档同步改；磁盘上原「时序-output」目录本不存在，首次使用即自动创建）。
- 灵魂 `persona/shisu.md` 更新：开篇自述改为「时间的时，叙旧的叙」；用户问起「你是谁 / 还在不在」时回一句「我在」；「像熟人说话」→「像老朋友说话」。`load_core()` 每次现读，改后下一条消息即生效、无需重启后端。
- 验证：后端 `184 passed`。

### 代码结构与运行
- **灵魂唯一来源**：`backend/persona/shisu.md`——改它 = 改时叙性格，前后端都以它为准
- 人格分层：`persona/shisu.md`（核心自我）+ `persona/masks/`（4 面具表达层）；路由在 `app/agents/mask.py`（规则词表 + LLM 兜底）
- 代码分层：`app/api/`（WS+REST）→ `app/agents/`（persona 加载 + DeepSeek 路由 + 面具）→ `app/memory/`（SQLite 读写 + 画像 + 自我记忆 `self.py`）→ `app/db/`（schema）
- 前端：对话区 + 侧边面板（聊天模式）+ 陪伴模式（粒子球，2026-08-12 起）；`VrmAvatar.vue`/`lib/maskVrm.ts` 已实现但界面未启用（数字人方案待定）
- 启动：`cd backend && uvicorn app.main:app --port 8000`（**不带 `--reload`**，中文路径假重载，改代码手动重启）；另开终端 `cd frontend && npm run dev`
- 前端 WS 连 **`/ws/chat`**（勿改成 `/ws`），经 Vite 代理转后端 8000
- 测试：后端在 `backend/tests/` 使用 `pytest`；前端使用 `npm test`（vitest）；修改后端代码需手动重启运行中的 uvicorn。

### 远程仓库与代理（2026-08-06）
- 远程：`origin = https://github.com/kbd-1-A/SX.git`（master 分支，初始提交 51 文件）
- GitHub 国内直连被墙（`Recv failure: Connection was reset`）；本机 Clash 在 `127.0.0.1:7890`，已配 git 全局代理：`git config --global http.proxy http://127.0.0.1:7890`
- 关掉 Clash 后 git 会报代理错 → `git config --global --unset http.proxy https.proxy` 取消
- 提交守则：`backend/.env`（含 DeepSeek key）在 `.gitignore`，绝不提交；`frontend/tsconfig.tsbuildinfo`、`.tmp_screenshots/` 已忽略

### 给 Claude Code 的指令（工程部分）
1. 动手前先读 V1 方案文档，了解全貌。
2. 严格遵守砍清单，不主动建议后置的功能。
3. 新增功能先写测试、后写实现。
4. **新增路由/文件后提醒手动重启后端**（`uvicorn --reload` 只监控已有文件，新文件不触发）。
5. **`.env` 相对 CWD 生效**：改 `.env` 后必须手动重启，`--reload` 不会重载。
6. **Windows 端口被占**（8000 有僵尸进程）→ 换端口启动，别纠结杀进程。
7. **LLM 防幻觉**：确定性事实硬编码进 System Prompt；prompt 里决策树 > 规则列表，关键规则放前 30 行——短的、排前面的才被遵守。
8. **涉及 HuggingFace 模型下载** → 必须在 import 前 `os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")`，写在 `.env` 里无效（国内被墙）。
9. 前端刷新保留对话：历史从后端 `/api/messages` 加载（服务端落库为准），不要用 localStorage。
10. 每次完成/踩坑，把证据和坑记进下面的「经验教训」。
11. GitHub 操作前确认 Clash 代理生效（git 全局代理 `127.0.0.1:7890`）；commit 前用 `git ls-files | grep -E '\.env$'` 自查敏感文件。

---

## 三、经验教训（随项目累积）

### 已沉淀（2026-08-05，自第十人项目迁移，通用）
- `uvicorn --reload` 不检测新文件：新增 `.py` 路由后需手动 kill 重开。
- `.env` 相对 CWD：放错位置不生效；改 `.env` 后手动重启。
- Windows 端口僵尸进程常见：8000 被占就换 8001，别纠结杀进程。
- HuggingFace 国内被墙：必须在代码里、import 之前设 `HF_ENDPOINT=https://hf-mirror.com`。
- Prompt 可被遵守性：决策树 > 规则列表；关键规则放前 30 行；规则要短。
- LLM 防幻觉：训练数据不可靠的事实（实时/特定数据）必须走工具或硬编码注入，禁止凭记忆。
- 前端：`EventSource` 只支持 GET，SSE 流要用 fetch + ReadableStream；本地时叙用 WebSocket 则无此问题。
- LLM 对话历史注入按「条数」不可控（短历史浪费、长历史超预算），改按 token 上限截断（时叙现用 5000）。token 估算用启发式（CJK/全角 1 token/字 + ASCII 4 字符/token），不引 tiktoken——它首次使用要下载编码文件，国内网络不稳定，且 DeepSeek 自己的 tokenizer 才精确，截断只需量级判断（2026-08-06）。

### 本地坑
- WebSocket 路径前后端必须一致：Starlette 对**未匹配的 WS 升级请求统一回 403**（不是 404）。时叙后端路由是 `/ws/chat`，前端必须连 `/ws/chat`——曾因前端连 `/ws` 导致浏览器 403（2026-08-05）。
- `favicon.ico` 404 是缺图标，纯外观问题，可忽略。（已修复：2026-08-06 加 `frontend/public/favicon.svg`，index.html 已 link）
- **Windows 中文路径下 `uvicorn --reload` 不可信**：`E:\时叙` 这类中文目录里，改 `.py` 后日志会打印 `Reloading...` 但 worker 实际不重载，服务还在跑旧逻辑，且**无报错**——排查半天才靠端到端测试发现。结论：后端一律不带 `--reload` 启动，改代码手动重启（2026-08-06）。
- **three.js 相机忘了 `lookAt` → 数字人整个被视锥剔除、画面只有背景色**：VRM 模型 `position.y=-1.15` 下移后落在相机视野下方，而相机默认朝 `(0,0,-1)` 正前方。表现是 canvas 存在、render 每帧跑、模型加载成功，但 `drawElements` 调用为 0、画面空白。修复：`camera.lookAt(0,-0.36,0)` + fov 从 35 提到 60 + `vrm.scene.scale.setScalar(0.85)` 适配窄条 aspect。**教训：WebGL 里「画面空白」优先怀疑视锥剔除/相机朝向，别先怀疑加载**（2026-08-06）。
- **chrome-devtools MCP 排查前端渲染的姿势**：Vue3 dev 模式组件的 `<script setup>` 变量全在 `el.__vueParentComponent.setupState`（活引用，非快照），可直读 `scene/camera/vrm/renderer` 实时状态；读 WebGL canvas 像素用 `preserveDrawingBuffer:true` 的独立 renderer 渲染同一 scene+camera（直接读原 canvas 的 `toDataURL`/`readPixels` 会因 `preserveDrawingBuffer:false` 读到空 buffer 造成误报）；WebGL 计数用 `navigate_page` 的 `initScript` patch `WebGL2RenderingContext.prototype.drawElements/clear`（2026-08-06）。
- **GitHub 直连被墙**：`git push/ls-remote` 报 `Recv failure: Connection was reset`，git 无输出/无错即可能是空仓库连通成功。本机 Clash 代理在 `127.0.0.1:7890`，`git config --global http.proxy` 配了就走代理（2026-08-06）。
- **Vite 中文路径不受影响**：Vite dev 对模块请求**实时编译**，改 `.vue`/`.ts` 后刷新页面即新代码——与 uvicorn 的 watch 机制不同，中文目录下 Vite 无需重启（2026-08-06）。
- **数字人的难点不是渲染是观感**：渲染管线（相机/剔除/材质）都能修，但 three-vrm 的示例模型 `three-vrm-girl` 观感廉价、用户不接受。真做数字人优先找观感好的模型或 VRoid 自捏，技术方案（three-vrm + 面具表情联动）可复用（2026-08-06）。
- **PowerShell 管道给 Python stdin 传中文可能导致测试文本乱码**：用 `@'...'@ | python -` 跑内联脚本时，中文字符串可能在 Python 侧变成问号，导致端到端测试写入乱码消息、记忆抽取不命中。验证中文 WebSocket/抽取逻辑时，用 Unicode escape 构造字符串，或写入 UTF-8 测试文件后运行；人工测试写入真实 SQLite 后要精确清理测试消息和记忆锚点（2026-08-07）。
- **HF 镜像下载报 xet CAS 401**：hf-mirror + 新版 huggingface_hub 默认走 xet 传输，未授权直接 401。解法：`HF_HUB_DISABLE_XET=1` 环境变量禁用 xet，回退普通 HTTP 下载即可（2026-08-12）。
- **three.js Points 粒子尺寸必须用投影系数换算**：`gl_PointSize = 世界尺寸 × (视口高×dpr / (2·tan(fov/2))) / -mv.z`，且视口 resize 时要更新该 uniform。拍脑袋的常数在不同视口下会小到完全不可见（2026-08-12）。
- **加色混合（AdditiveBlending）下密集粒子极易过曝成白团**：球心堆叠区域的提亮参数要克制（vCore 加成 ≤0.3、单粒子 alpha ≤0.6），否则金色球变白色球（2026-08-12）。
- **浏览器 SpeechSynthesis 不走 Web Audio**：拿不到 TTS 真实音量，语音律动只能用合成包络（复合正弦模拟人声强弱，攻击快释放慢）；要真实振幅需换服务端 TTS（2026-08-12）。
- **`<script setup>` 里 `export type` 给其他组件导入不可靠**：跨组件共享的类型放独立 `.ts`（如 OrbState 放 orbStyle.ts）（2026-08-12）。
