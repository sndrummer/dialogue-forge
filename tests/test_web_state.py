"""Tests for WebGameState, especially the grant_condition method."""

import pytest
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dialogue_forge.web.app import WebGameState


class TestGrantCondition:
    """Test the grant_condition method that infers state from conditions."""

    def test_grant_boolean_flag(self):
        """Simple variable should be set to True."""
        state = WebGameState()
        state.grant_condition("talked_to_npc")
        assert state.variables["talked_to_npc"] is True

    def test_grant_negated_flag(self):
        """Negated variable should be set to False."""
        state = WebGameState()
        state.variables["betrayed"] = True  # Start as True
        state.grant_condition("!betrayed")
        assert state.variables["betrayed"] is False

    def test_grant_has_item(self):
        """has_item condition should add to inventory."""
        state = WebGameState()
        state.grant_condition("has_item:sword")
        assert "sword" in state.inventory

    def test_grant_companion(self):
        """companion condition should add to companions."""
        state = WebGameState()
        state.grant_condition("companion:peng")
        assert "peng" in state.companions

    def test_grant_greater_equal(self):
        """Greater-or-equal should set to minimum value."""
        state = WebGameState()
        state.grant_condition("gold >= 10")
        assert state.variables["gold"] == 10

    def test_grant_greater_equal_already_satisfied(self):
        """If already satisfied, don't lower the value."""
        state = WebGameState()
        state.variables["gold"] = 50
        state.grant_condition("gold >= 10")
        assert state.variables["gold"] == 50  # Should stay at 50

    def test_grant_greater_than(self):
        """Greater-than should set to value + 1."""
        state = WebGameState()
        state.grant_condition("gold > 10")
        assert state.variables["gold"] == 11

    def test_grant_less_equal(self):
        """Less-or-equal should set to the value."""
        state = WebGameState()
        state.variables["suspicion"] = 100
        state.grant_condition("suspicion <= 5")
        assert state.variables["suspicion"] == 5

    def test_grant_less_than(self):
        """Less-than should set to value - 1."""
        state = WebGameState()
        state.variables["suspicion"] = 100
        state.grant_condition("suspicion < 5")
        assert state.variables["suspicion"] == 4

    def test_grant_equality_int(self):
        """Equality with int should set exact value."""
        state = WebGameState()
        state.grant_condition("level == 5")
        assert state.variables["level"] == 5

    def test_grant_equality_true(self):
        """Equality with true should set boolean."""
        state = WebGameState()
        state.grant_condition("is_hero == true")
        assert state.variables["is_hero"] is True

    def test_grant_equality_false(self):
        """Equality with false should set boolean."""
        state = WebGameState()
        state.grant_condition("is_villain == false")
        assert state.variables["is_villain"] is False

    def test_grant_and_condition(self):
        """AND condition should grant all parts."""
        state = WebGameState()
        state.grant_condition("has_item:key && gold >= 5")
        assert "key" in state.inventory
        assert state.variables["gold"] == 5

    def test_grant_or_condition(self):
        """OR condition should grant first part only."""
        state = WebGameState()
        state.grant_condition("has_item:key || gold >= 100")
        assert "key" in state.inventory
        assert state.variables.get("gold", 0) != 100  # Should NOT have granted second

    def test_grant_with_braces(self):
        """Condition with outer braces should work."""
        state = WebGameState()
        state.grant_condition("{has_item:sword}")
        assert "sword" in state.inventory

    def test_grant_empty_condition(self):
        """Empty condition should do nothing."""
        state = WebGameState()
        state.grant_condition("")
        state.grant_condition(None)
        assert len(state.variables) == 0
        assert len(state.inventory) == 0

    def test_grant_no_spaces(self):
        """Condition without spaces should work."""
        state = WebGameState()
        state.grant_condition("gold>=10")
        assert state.variables["gold"] == 10


class TestExecuteCommandSkipIfExists:
    """Test the skip_if_exists parameter for execute_command."""

    def test_set_new_variable(self):
        """New variable should be set."""
        state = WebGameState()
        state.execute_command("set gold = 10", skip_if_exists=True)
        assert state.variables["gold"] == 10

    def test_skip_existing_variable(self):
        """Existing variable should not be overwritten."""
        state = WebGameState()
        state.variables["gold"] = 50
        state.execute_command("set gold = 10", skip_if_exists=True)
        assert state.variables["gold"] == 50  # Should stay at 50

    def test_overwrite_when_not_skipping(self):
        """Without skip_if_exists, should overwrite."""
        state = WebGameState()
        state.variables["gold"] = 50
        state.execute_command("set gold = 10", skip_if_exists=False)
        assert state.variables["gold"] == 10


class TestEvaluateCondition:
    """Test condition evaluation works correctly."""

    def test_simple_true(self):
        state = WebGameState()
        state.variables["flag"] = True
        assert state.evaluate_condition("flag") is True

    def test_simple_false(self):
        state = WebGameState()
        state.variables["flag"] = False
        assert state.evaluate_condition("flag") is False

    def test_undefined_is_false(self):
        state = WebGameState()
        assert state.evaluate_condition("undefined_var") is False

    def test_has_item_true(self):
        state = WebGameState()
        state.inventory.add("sword")
        assert state.evaluate_condition("has_item:sword") is True

    def test_has_item_false(self):
        state = WebGameState()
        assert state.evaluate_condition("has_item:sword") is False

    def test_companion_true(self):
        state = WebGameState()
        state.companions.add("peng")
        assert state.evaluate_condition("companion:peng") is True

    def test_comparison(self):
        state = WebGameState()
        state.variables["gold"] = 15
        assert state.evaluate_condition("gold >= 10") is True
        assert state.evaluate_condition("gold >= 20") is False
