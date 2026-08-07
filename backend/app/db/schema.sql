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
