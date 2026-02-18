import pytest
import json
from euroscope.data.storage import Storage
from euroscope.skills.trade_journal.skill import TradeJournalSkill
from euroscope.skills.base import SkillContext

@pytest.fixture
def storage():
    # Use memory for fast testing
    return Storage(":memory:")

@pytest.fixture
def skill(storage):
    s = TradeJournalSkill()
    s.storage = storage
    return s

@pytest.mark.asyncio
async def test_learning_loop_end_to_end(skill, storage):
    # 1. Log a trade with specific context
    context = SkillContext()
    context.metadata["causal_chain"] = {
        "trigger": "macro_event",
        "liquidity_aligned": False,
        "data_quality": "minimal"
    }
    
    log_result = skill.execute(
        context, 
        "log_trade", 
        direction="BUY", 
        entry_price=1.0850,
        strategy="test_strat",
        regime="ranging"
    )
    assert log_result.success
    trade_id = log_result.data["trade_id"]
    
    # 2. Close the trade with a loss
    close_result = skill.execute(
        context,
        "close_trade",
        trade_id=trade_id,
        exit_price=1.0800,
        pnl_pips=-50.0,
        is_win=False
    )
    assert close_result.success
    
    # 3. Verify that a learning insight was created
    insights = storage.get_recent_learning_insights()
    assert len(insights) >= 1
    insight = insights[0]
    assert insight["trade_id"] == str(trade_id)
    assert "incomplete_fundamental_data" in insight["factors"]
    assert "Avoid high-risk setups when data health is below 80%." in insight["recommendations"]

@pytest.mark.asyncio
async def test_adaptive_tuner_with_insights(skill, storage):
    # 1. Inject some failures into the database
    for i in range(3):
        storage.save_learning_insight(
            trade_id=f"T{i}",
            accuracy=0.0,
            factors=["regime_misidentification"],
            recommendations=["Increase sensitivity"]
        )
    
    # 2. Run AdaptiveTuner
    from euroscope.learning.adaptive_tuner import AdaptiveTuner
    tuner = AdaptiveTuner(storage=storage)
    
    # We need at least 5 trades for the tuner to be 'ready'
    # Let's mock the trade journal stats
    storage._conn.execute("""
        INSERT INTO trade_journal (timestamp, direction, entry_price, status, is_win, pnl_pips)
        VALUES ('2024-01-01', 'BUY', 1.0, 'closed', 0, -10.0)
    """)
    for i in range(5):
        storage._conn.execute(f"""
            INSERT INTO trade_journal (timestamp, direction, entry_price, status, is_win, pnl_pips)
            VALUES ('2024-01-01', 'BUY', 1.0, 'closed', 0, -10.0)
        """)
    storage._conn.commit()

    report = tuner.analyze()
    assert report["ready"] is True
    
    # Check if qualitative recommendation is present
    recs = [r["param"] for r in report["recommendations"]]
    assert "regime_sensitivity" in recs
