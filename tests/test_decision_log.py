import pytest
from unittest.mock import AsyncMock, MagicMock
from euroscope.brain.decision_log import DecisionLog
from euroscope.brain.reflector import Reflector
from euroscope.brain.llm_router import LLMRouter
from euroscope.skills.base import SkillContext


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    # Mock storage to act like in-memory dict
    db = {"decision_log": []}
    
    async def load_json(key):
        return db.get(key, [])
        
    async def save_json(key, data):
        db[key] = data
        
    storage.load_json = AsyncMock(side_effect=load_json)
    storage.save_json = AsyncMock(side_effect=save_json)
    return storage


@pytest.fixture
def mock_reflector():
    reflector = MagicMock(spec=Reflector)
    reflector.reflect = AsyncMock(return_value="This is a test reflection.")
    return reflector


@pytest.fixture
def decision_log(mock_storage, mock_reflector):
    return DecisionLog(storage=mock_storage, reflector=mock_reflector)


@pytest.fixture
def sample_context():
    ctx = SkillContext()
    ctx.metadata = {"regime": "ranging"}
    return ctx


@pytest.mark.asyncio
async def test_store_decision(decision_log, mock_storage, sample_context):
    decision = {
        "final_direction": "BUY",
        "confidence": 75.0,
        "reasoning": "Test reasoning"
    }
    debate = {
        "bull_case": {"key_arguments": ["A", "B"]},
        "bear_case": {"counter_arguments": ["C", "D"]}
    }
    
    decision_id = await decision_log.store_decision(sample_context, decision, debate)
    
    assert decision_id is not None
    assert mock_storage.save_json.call_count == 1
    
    # Verify what was saved
    saved_data = await mock_storage.load_json("decision_log")
    assert len(saved_data) == 1
    assert saved_data[0]["id"] == decision_id
    assert saved_data[0]["status"] == "pending"
    assert saved_data[0]["direction"] == "BUY"


@pytest.mark.asyncio
async def test_resolve_with_outcome(decision_log, mock_storage, sample_context):
    # Setup a pending decision
    decision = {"final_direction": "SELL", "reasoning": "Test"}
    decision_id = await decision_log.store_decision(sample_context, decision)
    
    # Resolve it
    reflection = await decision_log.resolve_with_outcome(decision_id, pnl_pips=20.5, is_win=True)
    
    assert reflection == "This is a test reflection."
    
    # Verify update in storage
    saved_data = await mock_storage.load_json("decision_log")
    assert saved_data[0]["status"] == "resolved"
    assert saved_data[0]["pnl_pips"] == 20.5
    assert saved_data[0]["is_win"] is True
    assert saved_data[0]["reflection"] == reflection


@pytest.mark.asyncio
async def test_get_past_context(decision_log, sample_context):
    # Store and resolve 2 decisions
    d1 = await decision_log.store_decision(sample_context, {"final_direction": "BUY"})
    await decision_log.resolve_with_outcome(d1, 10.0, True)
    
    d2 = await decision_log.store_decision(sample_context, {"final_direction": "SELL"})
    await decision_log.resolve_with_outcome(d2, -5.0, False)
    
    context_str = await decision_log.get_past_context(n_recent=5)
    
    assert "Lessons from Recent Trades" in context_str
    assert "Trade (BUY) -> WIN (10.0 pips):" in context_str
    assert "Trade (SELL) -> LOSS (-5.0 pips):" in context_str
    assert "This is a test reflection." in context_str


@pytest.mark.asyncio
async def test_reflector_unit():
    mock_llm = MagicMock(spec=LLMRouter)
    mock_llm.chat = AsyncMock(return_value="LLM Reflection Output.")
    
    reflector = Reflector(mock_llm)
    
    result = await reflector.reflect("Test decision", 50.0, True)
    assert result == "LLM Reflection Output."
    assert mock_llm.chat.call_count == 1
    
    # Verify prompt contains win/loss
    call_args = mock_llm.chat.call_args[0][0]
    user_prompt = call_args[1]["content"]
    assert "PROFITABLE (+50.0 pips)" in user_prompt
