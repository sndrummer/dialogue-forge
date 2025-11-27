"""Tests for the DLG parser."""

import pytest
from dialogue_forge.parser import DialogueParser


class TestBasicParsing:
    """Test basic parsing functionality."""

    def test_parse_characters(self):
        """Test parsing character definitions."""
        content = """
[characters]
hero: The Hero
npc: Village Elder

[start]
hero: "Hello!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert 'hero' in dialogue.characters
        assert 'npc' in dialogue.characters
        assert dialogue.characters['hero'] == 'The Hero'
        assert dialogue.characters['npc'] == 'Village Elder'

    def test_parse_single_node(self):
        """Test parsing a single dialogue node."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello world!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert 'start' in dialogue.nodes
        assert len(dialogue.nodes['start'].lines) == 1
        assert dialogue.nodes['start'].lines[0].text == 'Hello world!'

    def test_parse_choices(self):
        """Test parsing dialogue choices."""
        content = """
[characters]
hero: Hero

[start]
hero: "What to do?"
-> option1: "First option"
-> option2: "Second option"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert len(choices) == 3
        assert choices[0].target == 'option1'
        assert choices[0].text == 'First option'
        assert choices[1].target == 'option2'
        assert choices[2].target == 'END'


class TestMultilineParsing:
    """Test multi-line dialogue parsing."""

    def test_multiline_speaker_line(self):
        """Test multi-line speaker dialogue."""
        content = """
[characters]
elder: Village Elder

[start]
elder: "Welcome to our village, traveler.
    We have been expecting you for some
    time now. Please, make yourself at home."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        node = dialogue.nodes['start']
        assert len(node.lines) == 1
        expected_text = (
            "Welcome to our village, traveler. "
            "We have been expecting you for some "
            "time now. Please, make yourself at home."
        )
        assert node.lines[0].text == expected_text
        assert node.lines[0].speaker == 'elder'
        assert len(dialogue.errors) == 0

    def test_multiline_with_condition(self):
        """Test multi-line dialogue with condition at end."""
        content = """
[characters]
elder: Elder

[start]
elder: "I see you have brought the
    sacred artifact. This changes
    everything." {has_item:artifact}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        node = dialogue.nodes['start']
        assert len(node.lines) == 1
        assert 'sacred artifact' in node.lines[0].text
        assert node.lines[0].condition == 'has_item:artifact'

    def test_multiline_choice(self):
        """Test multi-line choice text."""
        content = """
[characters]
npc: NPC

[start]
npc: "Hello!"
-> leave: "I must go now. Thank you for
    your hospitality, but urgent matters
    await me elsewhere."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert len(choices) == 2
        expected_text = (
            "I must go now. Thank you for "
            "your hospitality, but urgent matters "
            "await me elsewhere."
        )
        assert choices[0].text == expected_text
        assert choices[0].target == 'leave'

    def test_multiline_choice_with_condition(self):
        """Test multi-line choice with condition."""
        content = """
[characters]
npc: NPC

[start]
npc: "What will you do?"
-> secret: "I know what you did
    last summer." {knows_secret}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert choices[0].text == "I know what you did last summer."
        assert choices[0].condition == 'knows_secret'

    def test_single_line_still_works(self):
        """Test that single-line dialogue still works correctly."""
        content = """
[characters]
hero: Hero

[start]
hero: "This is a single line."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert dialogue.nodes['start'].lines[0].text == "This is a single line."

    def test_mixed_single_and_multiline(self):
        """Test mixing single-line and multi-line dialogue."""
        content = """
[characters]
hero: Hero
npc: NPC

[start]
hero: "Hello!"
npc: "Welcome, traveler. I have been waiting
    for someone like you to arrive."
hero: "Really?"
npc: "Yes, the prophecy foretold your
    coming many moons ago." {has_prophecy}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        lines = dialogue.nodes['start'].lines
        assert len(lines) == 4
        assert lines[0].text == "Hello!"
        assert "I have been waiting" in lines[1].text
        assert "someone like you" in lines[1].text
        assert lines[2].text == "Really?"
        assert "prophecy foretold" in lines[3].text
        assert lines[3].condition == 'has_prophecy'


class TestConditions:
    """Test condition parsing."""

    def test_simple_condition(self):
        """Test simple condition on choice."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello"
-> secret: "Secret option" {has_key}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert dialogue.nodes['start'].choices[0].condition == 'has_key'

    def test_item_condition(self):
        """Test has_item condition."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello"
-> use: "Use key" {has_item:rusty_key}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert dialogue.nodes['start'].choices[0].condition == 'has_item:rusty_key'

    def test_complex_condition(self):
        """Test complex condition with operators."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello"
-> special: "Special option" {has_key && talked_to_guard}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert dialogue.nodes['start'].choices[0].condition == 'has_key && talked_to_guard'


class TestCommands:
    """Test command parsing."""

    def test_set_command(self):
        """Test *set command parsing."""
        content = """
[characters]
hero: Hero

[start]
*set talked_to_npc = true
hero: "I talked to them."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert 'set talked_to_npc = true' in dialogue.nodes['start'].commands

    def test_give_item_command(self):
        """Test *give_item command parsing."""
        content = """
[characters]
hero: Hero

[start]
*give_item sword
hero: "A sword!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert 'give_item sword' in dialogue.nodes['start'].commands


class TestStackedNodes:
    """Test stacked node labels."""

    def test_stacked_nodes(self):
        """Test multiple node labels pointing to same content."""
        content = """
[characters]
npc: NPC

[option_a]
[option_b]
[option_c]
npc: "Interesting choice..."
-> continue
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        # All three nodes should exist
        assert 'option_a' in dialogue.nodes
        assert 'option_b' in dialogue.nodes
        assert 'option_c' in dialogue.nodes

        # They should all have the same content
        assert dialogue.nodes['option_a'].lines[0].text == "Interesting choice..."
        assert dialogue.nodes['option_b'].lines[0].text == "Interesting choice..."
        assert dialogue.nodes['option_c'].lines[0].text == "Interesting choice..."


class TestValidation:
    """Test validation functionality."""

    def test_validate_undefined_target(self):
        """Test that undefined choice targets are flagged as errors."""
        content = """
[characters]
hero: Hero

[start]
hero: "Hello"
-> nonexistent: "Go to undefined node"
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))
        parser.validate()

        assert len(dialogue.errors) > 0
        assert any('nonexistent' in err for err in dialogue.errors)

    def test_validate_undefined_speaker_warning(self):
        """Test that undefined speakers generate warnings."""
        content = """
[characters]
hero: Hero

[start]
unknown_speaker: "Hello"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))
        parser.validate()

        assert any('unknown_speaker' in warn for warn in dialogue.warnings)


class TestConditionalGOTOs:
    """Test conditional GOTO parsing (-> target {condition})."""

    def test_simple_conditional_goto(self):
        """Test parsing a simple conditional GOTO."""
        content = """
[characters]
hero: Hero

[start]
hero: "What happens?"
-> branch_a {has_key}
-> branch_b

[branch_a]
hero: "Took branch A"
-> END

[branch_b]
hero: "Took branch B"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert len(choices) == 2
        # First choice: conditional GOTO
        assert choices[0].target == 'branch_a'
        assert choices[0].text == ''
        assert choices[0].condition == 'has_key'
        # Second choice: unconditional GOTO
        assert choices[1].target == 'branch_b'
        assert choices[1].text == ''
        assert choices[1].condition is None

    def test_multiple_conditional_gotos(self):
        """Test multiple conditional GOTOs (like if/elif/else)."""
        content = """
[characters]
hero: Hero

[start]
hero: "Branching logic..."
-> peng_path {peng_saved}
-> alternate_path {!peng_saved && has_key}
-> default_path

[peng_path]
hero: "Peng is here!"
-> END

[alternate_path]
hero: "Alternate route."
-> END

[default_path]
hero: "Default."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert len(choices) == 3
        assert choices[0].target == 'peng_path'
        assert choices[0].condition == 'peng_saved'
        assert choices[1].target == 'alternate_path'
        assert choices[1].condition == '!peng_saved && has_key'
        assert choices[2].target == 'default_path'
        assert choices[2].condition is None

    def test_mixed_gotos_and_choices(self):
        """Test mixing conditional GOTOs with player choices."""
        content = """
[characters]
hero: Hero

[start]
hero: "Choose wisely..."
-> auto_branch {secret_unlocked}
-> option_a: "Option A"
-> option_b: "Option B" {has_permission}
-> END

[auto_branch]
hero: "Secret path!"
-> END

[option_a]
hero: "You chose A"
-> END

[option_b]
hero: "You chose B"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert len(choices) == 4
        # GOTO with condition
        assert choices[0].target == 'auto_branch'
        assert choices[0].text == ''
        assert choices[0].condition == 'secret_unlocked'
        # Player choice without condition
        assert choices[1].target == 'option_a'
        assert choices[1].text == 'Option A'
        assert choices[1].condition is None
        # Player choice with condition
        assert choices[2].target == 'option_b'
        assert choices[2].text == 'Option B'
        assert choices[2].condition == 'has_permission'
        # Simple END
        assert choices[3].target == 'END'
        assert choices[3].text == ''

    def test_conditional_goto_with_complex_condition(self):
        """Test conditional GOTO with complex boolean condition."""
        content = """
[characters]
hero: Hero

[start]
hero: "Complex check..."
-> success {has_item:key && reputation > 10 || is_vip}
-> failure

[success]
hero: "Success!"
-> END

[failure]
hero: "Failed."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert choices[0].target == 'success'
        assert choices[0].condition == 'has_item:key && reputation > 10 || is_vip'

    def test_conditional_goto_negation(self):
        """Test conditional GOTO with negation."""
        content = """
[characters]
hero: Hero

[start]
hero: "Check..."
-> path_a {!enemy_defeated}
-> path_b {enemy_defeated}

[path_a]
hero: "A"
-> END

[path_b]
hero: "B"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        choices = dialogue.nodes['start'].choices
        assert choices[0].condition == '!enemy_defeated'
        assert choices[1].condition == 'enemy_defeated'


class TestStateSection:
    """Test [state] section parsing."""

    def test_parse_state_section(self):
        """Test parsing state initialization commands."""
        content = """
[characters]
hero: Hero

[state]
*set has_key = false
*set reputation = 0
*give_item torch

[start]
hero: "Ready to go!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert 'set has_key = false' in dialogue.initial_state
        assert 'set reputation = 0' in dialogue.initial_state
        assert 'give_item torch' in dialogue.initial_state
