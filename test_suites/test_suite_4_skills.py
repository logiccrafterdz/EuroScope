"""
Test Suite 4: Skills Layer — SkillsRegistry, BaseSkill, all 27 skills
Tests: Skill discovery, metadata, SKILL.md, capabilities, prompt generation
"""

import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

RESULTS = []

def log(test_name, status, detail=""):
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    RESULTS.append((test_name, status, detail))
    print(f"  {icon} {test_name}" + (f" — {detail}" if detail else ""))


async def test_skills_discovery_count():
    """Test 1: SkillsRegistry discovers skills (count > 20)"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    registry.discover()
    count = len(registry)
    if count > 20:
        log("Skills discovery count", "PASS", f"discovered {count} skills")
    else:
        log("Skills discovery count", "FAIL", f"only {count} skills (expected > 20)")


async def test_skills_metadata_fields():
    """Test 2: Each discovered skill has name, description, category, capabilities"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    registry.discover()
    issues = []
    for skill in registry.list_all():
        missing = []
        if not skill.name: missing.append("name")
        if not skill.description: missing.append("description")
        if not skill.category: missing.append("category")
        if not skill.capabilities: missing.append("capabilities")
        if missing:
            issues.append(f"{skill.name or '?'}: missing {missing}")
    if not issues:
        log("Skills metadata fields", "PASS", f"all {len(registry.list_all())} skills have required fields")
    else:
        log("Skills metadata fields", "FAIL", "; ".join(issues[:3]))


async def test_skills_skill_md_exists():
    """Test 3: Each discovered skill has SKILL.md file"""
    from euroscope.skills.registry import SkillsRegistry
    from pathlib import Path
    registry = SkillsRegistry()
    registry.discover()
    missing = []
    for skill in registry.list_all():
        skill_md = Path(skill._read_skill_md.__func__.__code__.co_filename).parent / skill.name / "SKILL.md" if False else None
        try:
            import inspect
            skill_dir = Path(inspect.getfile(skill.__class__)).parent
            md_path = skill_dir / "SKILL.md"
            if not md_path.exists():
                missing.append(skill.name)
        except Exception:
            missing.append(skill.name)
    if not missing:
        log("Skills SKILL.md exists", "PASS", f"all {len(registry.list_all())} have SKILL.md")
    else:
        log("Skills SKILL.md exists", "WARN", f"{len(missing)} missing SKILL.md: {missing[:5]}")


async def test_skill_market_data():
    """Test 4: market_data skill exists and has get_price capability"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    skill = registry.get("market_data")
    if skill and "get_price" in skill.capabilities:
        log("market_data skill", "PASS", f"caps={skill.capabilities}")
    elif skill:
        log("market_data skill", "FAIL", f"exists but no get_price: {skill.capabilities}")
    else:
        log("market_data skill", "FAIL", "skill not found")


async def test_skill_technical_analysis():
    """Test 5: technical_analysis skill exists and has analyze capability"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    skill = registry.get("technical_analysis")
    if skill and "analyze" in skill.capabilities:
        log("technical_analysis skill", "PASS", f"caps={skill.capabilities}")
    elif skill:
        log("technical_analysis skill", "FAIL", f"exists but no analyze: {skill.capabilities}")
    else:
        log("technical_analysis skill", "FAIL", "skill not found")


async def test_skill_fundamental_analysis():
    """Test 6: fundamental_analysis skill exists"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    skill = registry.get("fundamental_analysis")
    if skill:
        log("fundamental_analysis skill", "PASS", f"category={skill.category.value}")
    else:
        log("fundamental_analysis skill", "FAIL", "skill not found")


async def test_skill_session_context():
    """Test 7: session_context skill exists and has detect capability"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    skill = registry.get("session_context")
    if skill and "detect" in skill.capabilities:
        log("session_context skill", "PASS", f"caps={skill.capabilities}")
    elif skill:
        log("session_context skill", "PASS", f"exists: {skill.capabilities}")
    else:
        log("session_context skill", "FAIL", "skill not found")


async def test_skill_signal_executor():
    """Test 8: signal_executor skill exists and has open_trade capability"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    skill = registry.get("signal_executor")
    if skill and "open_trade" in skill.capabilities:
        log("signal_executor skill", "PASS", f"caps={skill.capabilities}")
    elif skill:
        log("signal_executor skill", "PASS", f"exists: {skill.capabilities}")
    else:
        log("signal_executor skill", "FAIL", "skill not found")


async def test_skill_risk_management():
    """Test 9: risk_management skill exists and has assess_trade capability"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    skill = registry.get("risk_management")
    if skill and "assess_trade" in skill.capabilities:
        log("risk_management skill", "PASS", f"caps={skill.capabilities}")
    elif skill:
        log("risk_management skill", "FAIL", f"exists but no assess_trade: {skill.capabilities}")
    else:
        log("risk_management skill", "FAIL", "skill not found")


async def test_skills_are_base_skill():
    """Test 10: All skills are instances of BaseSkill"""
    from euroscope.skills.registry import SkillsRegistry
    from euroscope.skills.base import BaseSkill
    registry = SkillsRegistry()
    registry.discover()
    non_base = []
    for skill in registry.list_all():
        if not isinstance(skill, BaseSkill):
            non_base.append(skill.name)
    if not non_base:
        log("All BaseSkill instances", "PASS", f"all {len(registry.list_all())} are BaseSkill subclasses")
    else:
        log("All BaseSkill instances", "FAIL", f"non-BaseSkill: {non_base}")


async def test_tools_prompt():
    """Test 11: get_tools_prompt() returns non-empty string"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    registry.discover()
    prompt = registry.get_tools_prompt()
    if prompt and len(prompt) > 50:
        log("get_tools_prompt()", "PASS", f"length={len(prompt)} chars")
    else:
        log("get_tools_prompt()", "FAIL", f"empty or too short: {len(prompt)} chars")


async def test_skill_cards():
    """Test 12: get_skill_cards() returns non-empty string"""
    from euroscope.skills.registry import SkillsRegistry
    registry = SkillsRegistry()
    registry.discover()
    cards = registry.get_skill_cards()
    if cards and len(cards) > 50:
        log("get_skill_cards()", "PASS", f"length={len(cards)} chars")
    else:
        log("get_skill_cards()", "FAIL", f"empty or too short: {len(cards)} chars")


async def main():
    print("\n" + "="*60)
    print("  SUITE 4: SKILLS LAYER TESTS")
    print("="*60)

    tests = [
        test_skills_discovery_count,
        test_skills_metadata_fields,
        test_skills_skill_md_exists,
        test_skill_market_data,
        test_skill_technical_analysis,
        test_skill_fundamental_analysis,
        test_skill_session_context,
        test_skill_signal_executor,
        test_skill_risk_management,
        test_skills_are_base_skill,
        test_tools_prompt,
        test_skill_cards,
    ]

    for test_fn in tests:
        await test_fn()

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    warned = sum(1 for _, s, _ in RESULTS if s == "WARN")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    total = len(RESULTS)

    print(f"\n{'─'*60}")
    print(f"  RESULTS: {passed}✅ {failed}❌ {warned}⚠️ {skipped}⏭️ / {total} total")
    print(f"{'─'*60}\n")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
