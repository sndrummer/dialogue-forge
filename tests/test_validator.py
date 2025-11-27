"""Tests for the DLG validator."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

from dialogue_forge.cli.validate_cmd import DialogueValidator


def create_temp_dlg(content: str) -> Path:
    """Create a temporary .dlg file with the given content."""
    with NamedTemporaryFile(mode='w', suffix='.dlg', delete=False, encoding='utf-8') as f:
        f.write(content)
        return Path(f.name)


class TestValidatorBasic:
    """Test basic validator functionality."""

    def test_valid_simple_dialogue(self):
        """Test validation of a simple valid dialogue."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            assert validator.validate() is True
            assert len(validator.errors) == 0
        finally:
            path.unlink()

    def test_missing_file(self):
        """Test validation of non-existent file."""
        validator = DialogueValidator(Path("/nonexistent/file.dlg"))
        assert validator.validate() is False

    def test_undefined_node_reference(self):
        """Test detection of undefined node references."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello!"
-> nonexistent: "Go somewhere"
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Parser should catch undefined node
            assert len(validator.errors) > 0
        finally:
            path.unlink()


class TestValidatorMultiline:
    """Test validator with multi-line strings."""

    def test_multiline_dialogue_valid(self):
        """Test that multi-line dialogue passes validation."""
        content = """
[characters]
elder: Elder

[start]
elder: "Welcome to our village, traveler.
    We have been expecting you for some
    time now. Please, make yourself at home."
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            assert validator.validate() is True
            assert len(validator.errors) == 0
        finally:
            path.unlink()

    def test_multiline_with_condition(self):
        """Test multi-line dialogue with condition."""
        content = """
[characters]
elder: Elder

[state]
*set has_key = true

[start]
elder: "I see you have the
    ancient key." {has_key}
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            assert validator.validate() is True
            assert len(validator.errors) == 0
        finally:
            path.unlink()

    def test_multiline_choice(self):
        """Test multi-line choice text."""
        content = """
[characters]
npc: NPC

[start]
npc: "Hello!"
-> leave: "I must go now. Thank you for
    your hospitality."
-> END

[leave]
npc: "Goodbye!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            assert validator.validate() is True
            assert len(validator.errors) == 0
        finally:
            path.unlink()


class TestValidatorSemantics:
    """Test semantic validation."""

    def test_undefined_variable_warning(self):
        """Test warning for variable used but never set."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello!"
-> secret: "Secret option" {undefined_var}
-> END

[secret]
hero: "Found it!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should have warning about undefined variable
            var_warnings = [w for w in validator.warnings if 'undefined_var' in w.message]
            assert len(var_warnings) > 0
        finally:
            path.unlink()

    def test_defined_variable_no_warning(self):
        """Test no warning when variable is properly set."""
        content = """
[characters]
hero: Hero

[state]
*set my_var = true

[start]
hero: "Hello!"
-> secret: "Secret option" {my_var}
-> END

[secret]
hero: "Found it!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should have no warnings about my_var
            var_warnings = [w for w in validator.warnings if 'my_var' in w.message]
            assert len(var_warnings) == 0
        finally:
            path.unlink()

    def test_undefined_item_warning(self):
        """Test warning for item checked but never given."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello!"
-> use_key: "Use the key" {has_item:magic_key}
-> END

[use_key]
hero: "Used it!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should have warning about undefined item
            item_warnings = [w for w in validator.warnings if 'magic_key' in w.message]
            assert len(item_warnings) > 0
        finally:
            path.unlink()

    def test_defined_item_no_warning(self):
        """Test no warning when item is given before checked."""
        content = """
[characters]
hero: Hero

[state]
*give_item magic_key

[start]
hero: "Hello!"
-> use_key: "Use the key" {has_item:magic_key}
-> END

[use_key]
hero: "Used it!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should have no warnings about magic_key
            item_warnings = [w for w in validator.warnings if 'magic_key' in w.message]
            assert len(item_warnings) == 0
        finally:
            path.unlink()

    def test_undefined_companion_warning(self):
        """Test warning for companion checked but never added."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello!"
-> ask_peng: "Ask Peng" {companion:peng}
-> END

[ask_peng]
hero: "Peng says hi!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should have warning about undefined companion
            comp_warnings = [w for w in validator.warnings if 'peng' in w.message]
            assert len(comp_warnings) > 0
        finally:
            path.unlink()


class TestValidatorFlow:
    """Test flow validation."""

    def test_dead_end_warning(self):
        """Test warning for node with no choices."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello!"
-> middle

[middle]
hero: "This is a dead end with no choices."
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should have warning about dead end
            dead_end_warnings = [w for w in validator.warnings if 'dead end' in w.message.lower()]
            assert len(dead_end_warnings) > 0
        finally:
            path.unlink()

    def test_stacked_nodes_valid(self):
        """Test that stacked nodes with choices don't trigger dead end warnings."""
        content = """
[characters]
npc: NPC

[option_a]
[option_b]
[option_c]
npc: "You all chose the same thing!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Stacked nodes should not trigger dead end warnings
            dead_end_warnings = [w for w in validator.warnings if 'dead end' in w.message.lower()]
            assert len(dead_end_warnings) == 0
        finally:
            path.unlink()


class TestValidatorStateSection:
    """Test [state] section handling."""

    def test_state_section_variables_tracked(self):
        """Test that variables from [state] section are tracked as set."""
        content = """
[characters]
hero: Hero

[state]
*set has_key = true
*set reputation = 10

[start]
hero: "Hello!"
-> secret: "Secret" {has_key}
-> reputation_check: "Check rep" {reputation > 5}
-> END

[secret]
hero: "Found it!"
-> END

[reputation_check]
hero: "Good rep!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should track variables from state section
            assert 'has_key' in validator.variables_set
            assert 'reputation' in validator.variables_set
            # No warnings about undefined variables
            var_warnings = [w for w in validator.warnings
                          if 'has_key' in w.message or 'reputation' in w.message]
            assert len(var_warnings) == 0
        finally:
            path.unlink()

    def test_state_section_items_tracked(self):
        """Test that items from [state] section are tracked."""
        content = """
[characters]
hero: Hero

[state]
*give_item sword
*give_item shield

[start]
hero: "Hello!"
-> use_sword: "Use sword" {has_item:sword}
-> END

[use_sword]
hero: "Slash!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should track items from state section
            assert 'sword' in validator.items_given
            assert 'shield' in validator.items_given
        finally:
            path.unlink()

    def test_state_section_companions_tracked(self):
        """Test that companions from [state] section are tracked."""
        content = """
[characters]
hero: Hero

[state]
*add_companion peng

[start]
hero: "Hello!"
-> ask_peng: "Ask Peng" {companion:peng}
-> END

[ask_peng]
hero: "Peng says hi!"
-> END
"""
        path = create_temp_dlg(content)
        try:
            validator = DialogueValidator(path)
            validator.validate()
            # Should track companions from state section
            assert 'peng' in validator.companions_added
            # No warnings about undefined companion
            comp_warnings = [w for w in validator.warnings if 'peng' in w.message]
            assert len(comp_warnings) == 0
        finally:
            path.unlink()
