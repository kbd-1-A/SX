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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
