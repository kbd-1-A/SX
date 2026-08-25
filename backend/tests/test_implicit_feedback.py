"""P2 隐式反馈测试：续聊/中断信号 + 学习消费。"""

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import app.db.init as init_mod
    from app.memory import behavior as behavior_mod
    from app.memory import observations as obs_mod
    from app.memory import store as store_mod

    db = tmp_path / "test.db"
    monkeypatch.setattr(obs_mod, "DB_PATH", db)
    monkeypatch.setattr(behavior_mod, "DB_PATH", db)
    monkeypatch.setattr(store_mod, "DB_PATH", db)
    monkeypatch.setattr(init_mod, "DB_PATH", db)
    init_mod.init_db()
    return db


def test_continuation_signal_requires_recent_assistant(tmp_db):
    from app.memory.observations import record_continuation_signal
    from app.memory.store import add_message, create_session

    session_id = create_session()
    # 没有 assistant 消息 → 无信号
    assert record_continuation_signal(session_id) is None

    add_message(session_id, "assistant", "刚说完的回复")
    assert record_continuation_signal(session_id) is not None

    # 用户紧接着发消息：仍能找到上一条 assistant 回复
    add_message(session_id, "user", "继续聊聊")
    assert record_continuation_signal(session_id) is not None


def test_interrupt_signal_only_for_long(tmp_db):
    from app.memory.observations import record_interrupt_signal

    assert record_interrupt_signal(1, "好的，我知道了") is None
    long_partial = "这段回复比较长" * 30
    assert record_interrupt_signal(1, long_partial) is not None


def test_apply_implicit_learning_consumes_interrupts(tmp_db):
    from app.memory import behavior as behavior_mod
    from app.memory.observations import (
        apply_implicit_learning,
        record_interrupt_signal,
    )

    long_with_cliche = "我理解你的感受。" + "这段回复写得特别长，希望这能帮助到你。" * 20
    record_interrupt_signal(1, long_with_cliche)

    applied = apply_implicit_learning()
    assert applied == 1

    styles = behavior_mod.get_behavior_profile()["styles"]
    assert styles["short_reply"]["observations"] == 1
    assert styles["less_cliche"]["observations"] == 1
    # 幂等：已消费的信号不会重复计数
    assert apply_implicit_learning() == 0
    assert (
        behavior_mod.get_behavior_profile()["styles"]["short_reply"]["observations"] == 1
    )
