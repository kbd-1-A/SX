-- V1 最小表结构

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id),
    role TEXT NOT NULL,               -- user / assistant
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 用户画像（单行，V1 只读展示，自动演化后置）
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY DEFAULT 1,
    intimacy INTEGER DEFAULT 0,       -- 亲密度 0-100
    interests TEXT DEFAULT '{}',      -- JSON {关键词: 权重}
    self_memory TEXT DEFAULT '{}',    -- JSON {milestones/nicknames/relationship_phase/...}
    behavior_profile TEXT DEFAULT '{}', -- JSON：性格倾向、表达习惯、证据与置信度
    companion_settings TEXT DEFAULT '{}', -- JSON：主动陪伴频率等用户控制项
    emotion_state TEXT DEFAULT '{}',      -- JSON：时叙当前情绪状态（持续，进记忆）
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- V2 关系锚点：高置信、可追溯的长期记忆
CREATE TABLE IF NOT EXISTS memory_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                -- user_fact / preference / episode / open_loop / relationship_note
    content TEXT NOT NULL,
    source_message_id INTEGER REFERENCES messages(id),
    confidence REAL DEFAULT 0.9,
    tags TEXT DEFAULT '[]',
    status TEXT DEFAULT 'active',       -- pending / active / stale / archived
    expires_at TIMESTAMP,
    confirmed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_anchors_status
ON memory_anchors(status, updated_at);

-- 主动陪伴：需要被后续关心的事项
CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    due_at TIMESTAMP,
    importance INTEGER NOT NULL DEFAULT 1, -- 1 普通 / 2 重要 / 3 高优先级
    status TEXT NOT NULL DEFAULT 'open',  -- open / done / archived
    source_message_id INTEGER REFERENCES messages(id),
    last_cared_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_follow_ups_open_due
ON follow_ups(status, due_at, importance);

-- 时叙已生成的主动关心点；delivery_key 保证同一提醒不会反复打扰
CREATE TABLE IF NOT EXISTS companion_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                -- greeting / evening_review / due_5m / due_3m / due_1m / due_now / overdue / open_loop
    content TEXT NOT NULL,
    follow_up_id INTEGER REFERENCES follow_ups(id),
    importance INTEGER NOT NULL DEFAULT 1,
    delivery_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_companion_events_created
ON companion_events(created_at DESC);

-- 消息级反馈：对 assistant 回复的赞/踩 sidecar（自主学习，乐观并发）
CREATE TABLE IF NOT EXISTS message_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL UNIQUE REFERENCES messages(id),
    rating TEXT NOT NULL,                -- positive / negative
    note TEXT DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_message_feedback_updated
ON message_feedback(updated_at DESC);

-- 目标事件溯源：follow_ups 生命周期只追加日志
CREATE TABLE IF NOT EXISTS goal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    follow_up_id INTEGER NOT NULL REFERENCES follow_ups(id),
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,            -- created/edited/paused/resumed/blocked/unblocked/completed/reopened/archived
    payload TEXT NOT NULL DEFAULT '{}',  -- JSON 快照
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(follow_up_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_goal_events_follow_up
ON goal_events(follow_up_id, seq);

-- P1 观察层：每轮对话元数据（纯确定性，零 LLM）
CREATE TABLE IF NOT EXISTS turn_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id),
    user_message_id INTEGER REFERENCES messages(id),
    assistant_message_id INTEGER REFERENCES messages(id),
    mask TEXT DEFAULT '',
    reply_mode TEXT DEFAULT '',
    emotion TEXT DEFAULT '',
    user_chars INTEGER DEFAULT 0,
    reply_chars INTEGER DEFAULT 0,
    reply_seconds REAL DEFAULT 0,
    hour_of_day INTEGER,                -- 本地时间小时 0-23
    weekday INTEGER,                    -- 本地时间星期 0=周一
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_turn_observations_created
ON turn_observations(created_at);

-- P2 隐式反馈：系统从行为痕迹推断的信号（append-only）
CREATE TABLE IF NOT EXISTS implicit_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    assistant_message_id INTEGER,       -- 完成的回复可引用；中断的回复为 NULL
    signal TEXT NOT NULL,               -- continued_after / interrupted_long
    polarity TEXT NOT NULL,             -- positive / negative
    content TEXT DEFAULT '',
    applied INTEGER NOT NULL DEFAULT 0, -- 是否已被行为学习消费
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_implicit_feedback_unapplied
ON implicit_feedback(applied, signal);

-- 持续情绪事件历史（append-only，可追溯）：会记仇/记喜的依据
CREATE TABLE IF NOT EXISTS emotion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emotion TEXT NOT NULL,                -- 温柔/生气/嗔怪...（见 emotion_map.yaml）
    intensity REAL NOT NULL,              -- 0.0-1.0
    cause TEXT DEFAULT '',                -- 起因
    source_message_id INTEGER REFERENCES messages(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_emotion_log_created
ON emotion_log(created_at DESC);
