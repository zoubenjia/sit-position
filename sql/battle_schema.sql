-- 俯卧撑对战表
CREATE TABLE pushup_battles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    creator_id UUID REFERENCES auth.users(id) NOT NULL,
    opponent_id UUID REFERENCES auth.users(id) NOT NULL,
    status TEXT NOT NULL DEFAULT 'invite'
        CHECK (status IN ('invite', 'accepted', 'countdown', 'active', 'finished', 'expired', 'cancelled')),
    mode TEXT NOT NULL DEFAULT 'async'
        CHECK (mode IN ('async', 'realtime')),
    time_limit_seconds INT NOT NULL DEFAULT 120,
    quality_weight REAL NOT NULL DEFAULT 0.3,

    -- 创建者成绩
    creator_reps INT DEFAULT 0,
    creator_good_reps INT DEFAULT 0,
    creator_form_errors JSONB DEFAULT '{}'::jsonb,
    creator_score REAL DEFAULT 0,
    creator_duration_seconds INT DEFAULT 0,
    creator_finished_at TIMESTAMPTZ,

    -- 对手成绩
    opponent_reps INT DEFAULT 0,
    opponent_good_reps INT DEFAULT 0,
    opponent_form_errors JSONB DEFAULT '{}'::jsonb,
    opponent_score REAL DEFAULT 0,
    opponent_duration_seconds INT DEFAULT 0,
    opponent_finished_at TIMESTAMPTZ,

    -- 结果
    winner_id UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ DEFAULT (now() + INTERVAL '24 hours')
);

-- RLS：参与者可读写自己的对战
ALTER TABLE pushup_battles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "参与者可读自己的对战" ON pushup_battles
    FOR SELECT USING (auth.uid() IN (creator_id, opponent_id));

CREATE POLICY "参与者可更新自己的对战" ON pushup_battles
    FOR UPDATE USING (auth.uid() IN (creator_id, opponent_id));

CREATE POLICY "认证用户可创建对战" ON pushup_battles
    FOR INSERT WITH CHECK (auth.uid() = creator_id);

-- 索引
CREATE INDEX idx_battles_creator ON pushup_battles(creator_id);
CREATE INDEX idx_battles_opponent ON pushup_battles(opponent_id);
CREATE INDEX idx_battles_status ON pushup_battles(status);


-- 实时对战进度表（Phase 2 用）
CREATE TABLE battle_live_updates (
    id BIGSERIAL PRIMARY KEY,
    battle_id UUID REFERENCES pushup_battles(id) NOT NULL,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    rep_number INT NOT NULL,
    form_quality TEXT NOT NULL DEFAULT 'good',
    form_errors TEXT[] DEFAULT '{}',
    elapsed_seconds REAL NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 启用 REPLICA IDENTITY FULL 供 Supabase Realtime 订阅
ALTER TABLE battle_live_updates REPLICA IDENTITY FULL;

-- RLS
ALTER TABLE battle_live_updates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "对战参与者可读进度" ON battle_live_updates
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM pushup_battles
            WHERE pushup_battles.id = battle_live_updates.battle_id
            AND auth.uid() IN (pushup_battles.creator_id, pushup_battles.opponent_id)
        )
    );

CREATE POLICY "本人可写进度" ON battle_live_updates
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE INDEX idx_live_updates_battle ON battle_live_updates(battle_id, user_id);


-- users 表新增字段（社交登录）
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT DEFAULT 'device';
