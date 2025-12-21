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


class TestTags:
    """Test tags parsing (optional metadata on dialogue lines)."""

    def test_single_tag(self):
        """Test parsing a single tag on a dialogue line."""
        content = """
[characters]
peng: Peng

[start]
peng: "I found you!" [happy]
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        line = dialogue.nodes['start'].lines[0]
        assert line.text == "I found you!"
        assert line.tags == ['happy']
        assert line.condition is None

    def test_multiple_tags(self):
        """Test parsing multiple comma-separated tags."""
        content = """
[characters]
peng: Peng

[start]
peng: "It was so hard..." [sad, tired, relieved]
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        line = dialogue.nodes['start'].lines[0]
        assert line.text == "It was so hard..."
        assert line.tags == ['sad', 'tired', 'relieved']

    def test_tags_with_condition(self):
        """Test tags combined with conditions."""
        content = """
[characters]
peng: Peng

[start]
peng: "Thank you for saving me!" [grateful, tearful] {saved_peng}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        line = dialogue.nodes['start'].lines[0]
        assert line.text == "Thank you for saving me!"
        assert line.tags == ['grateful', 'tearful']
        assert line.condition == 'saved_peng'

    def test_no_tags(self):
        """Test that lines without tags have empty tags list."""
        content = """
[characters]
hero: Hero

[start]
hero: "Just a normal line."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        line = dialogue.nodes['start'].lines[0]
        assert line.text == "Just a normal line."
        assert line.tags == []

    def test_multiline_with_tags(self):
        """Test multi-line dialogue with tags at the end."""
        content = """
[characters]
elder: Elder

[start]
elder: "Welcome to our village.
    We have been waiting for you
    for a long time." [warm, welcoming]
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        line = dialogue.nodes['start'].lines[0]
        assert "Welcome to our village" in line.text
        assert "for a long time" in line.text
        assert line.tags == ['warm', 'welcoming']

    def test_multiline_with_tags_and_condition(self):
        """Test multi-line dialogue with both tags and condition."""
        content = """
[characters]
elder: Elder

[start]
elder: "I see you have the artifact.
    This changes everything." [surprised, serious] {has_item:artifact}
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        line = dialogue.nodes['start'].lines[0]
        assert "artifact" in line.text
        assert line.tags == ['surprised', 'serious']
        assert line.condition == 'has_item:artifact'

    def test_mixed_lines_with_and_without_tags(self):
        """Test mixing lines with and without tags."""
        content = """
[characters]
hero: Hero
peng: Peng

[start]
hero: "Hello there!"
peng: "Oh, it's you!" [surprised]
hero: "Yes, I came to help." [determined]
peng: "That's wonderful."
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        lines = dialogue.nodes['start'].lines
        assert len(lines) == 4
        assert lines[0].tags == []
        assert lines[1].tags == ['surprised']
        assert lines[2].tags == ['determined']
        assert lines[3].tags == []


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


class TestEntryGroups:
    """Test entry group parsing for conversation entry points."""

    def test_parse_basic_entry_group(self):
        """Test parsing a basic entry group with routes and exits."""
        content = """
[characters]
officer: Officer

[entry:officer]
equipment_equipped -> equip_items
-> start
<- equip_items

[start]
officer: "Hello!"
-> equip_items: "Get gear"

[equip_items]
officer: "Equipped!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert 'officer' in dialogue.entries
        entry = dialogue.entries['officer']

        # Check routes
        assert len(entry.routes) == 2
        assert entry.routes[0].condition == 'equipment_equipped'
        assert entry.routes[0].target == 'equip_items'
        assert entry.routes[1].condition is None  # Default route
        assert entry.routes[1].target == 'start'

        # Check exits
        assert len(entry.exits) == 1
        assert 'equip_items' in entry.exits

    def test_multiple_entry_groups(self):
        """Test parsing multiple entry groups in same file."""
        content = """
[characters]
officer: Officer
recruit: Recruit

[entry:officer]
-> start
<- ship_deck

[entry:recruit]
asked_about_comet -> talk_2
-> talk_1
<- exploration

[start]
officer: "Hello!"
-> ship_deck

[ship_deck]
officer: "We're here!"
-> END

[talk_1]
recruit: "Hey!"
-> exploration

[talk_2]
recruit: "The comet!"
-> exploration

[exploration]
recruit: "Good luck!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        assert 'officer' in dialogue.entries
        assert 'recruit' in dialogue.entries

        officer_entry = dialogue.entries['officer']
        assert len(officer_entry.routes) == 1
        assert len(officer_entry.exits) == 1
        assert 'ship_deck' in officer_entry.exits

        recruit_entry = dialogue.entries['recruit']
        assert len(recruit_entry.routes) == 2
        assert recruit_entry.routes[0].condition == 'asked_about_comet'
        assert 'exploration' in recruit_entry.exits

    def test_complex_entry_conditions(self):
        """Test entry groups with complex conditions."""
        content = """
[characters]
npc: NPC

[entry:npc]
has_sword && reputation > 10 -> armed_greeting
!talked_before || is_angry -> hostile_greeting
has_item:key -> key_greeting
-> default_greeting
<- key_greeting

[default_greeting]
npc: "Hello."
-> END

[armed_greeting]
npc: "Nice weapon!"
-> END

[hostile_greeting]
npc: "What do you want?"
-> END

[key_greeting]
npc: "You have the key!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        entry = dialogue.entries['npc']
        assert len(entry.routes) == 4

        assert entry.routes[0].condition == 'has_sword && reputation > 10'
        assert entry.routes[0].target == 'armed_greeting'

        assert entry.routes[1].condition == '!talked_before || is_angry'
        assert entry.routes[1].target == 'hostile_greeting'

        assert entry.routes[2].condition == 'has_item:key'
        assert entry.routes[2].target == 'key_greeting'

        assert entry.routes[3].condition is None
        assert entry.routes[3].target == 'default_greeting'

    def test_multiple_exits(self):
        """Test entry groups with multiple exit nodes."""
        content = """
[characters]
npc: NPC

[entry:npc]
-> start
<- exit_a
<- exit_b
<- exit_c

[start]
npc: "Hello!"
-> exit_a: "Option A"
-> exit_b: "Option B"
-> exit_c: "Option C"

[exit_a]
npc: "Bye A!"
-> END

[exit_b]
npc: "Bye B!"
-> END

[exit_c]
npc: "Bye C!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        entry = dialogue.entries['npc']
        assert len(entry.exits) == 3
        assert 'exit_a' in entry.exits
        assert 'exit_b' in entry.exits
        assert 'exit_c' in entry.exits

    def test_entry_group_validation_invalid_target(self):
        """Test that invalid entry targets are caught."""
        content = """
[characters]
npc: NPC

[entry:npc]
-> nonexistent_node
<- also_nonexistent

[start]
npc: "Hello!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))
        valid = parser.validate()

        assert not valid
        assert any('nonexistent_node' in err for err in dialogue.errors)
        # Exits generate warnings, not errors
        assert any('also_nonexistent' in warn for warn in dialogue.warnings)

    def test_entry_group_no_default_warning(self):
        """Test warning when entry group has no default route."""
        content = """
[characters]
npc: NPC

[entry:npc]
has_key -> key_route

[start]
npc: "Hello!"
-> END

[key_route]
npc: "You have the key!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))
        parser.validate()

        assert any('no default entry route' in warn for warn in dialogue.warnings)

    def test_entry_group_stats(self):
        """Test that entry groups are included in stats."""
        content = """
[characters]
npc: NPC

[entry:npc]
condition1 -> route1
condition2 -> route2
-> default
<- exit1
<- exit2

[route1]
npc: "Route 1"
-> END

[route2]
npc: "Route 2"
-> END

[default]
npc: "Default"
-> END

[exit1]
npc: "Exit 1"
-> END

[exit2]
npc: "Exit 2"
-> END
"""
        parser = DialogueParser()
        parser.parse_lines(content.strip().split('\n'))

        stats = parser.get_stats()
        assert stats['entry_groups'] == 1
        assert stats['entry_routes'] == 3
        assert stats['exit_nodes'] == 2

    def test_entry_targets_make_nodes_reachable(self):
        """Test that nodes reachable from entry routes are not marked unreachable."""
        content = """
[characters]
npc: NPC

[entry:npc]
has_key -> secret_route
-> start

[start]
npc: "Hello!"
-> END

[secret_route]
npc: "You found the secret!"
-> hidden_node

[hidden_node]
npc: "Very hidden!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))
        parser.validate()

        # secret_route and hidden_node should NOT be marked unreachable
        # because they're reachable from the entry group
        unreachable_warnings = [w for w in dialogue.warnings if 'unreachable' in w.lower()]
        assert not any('secret_route' in w for w in unreachable_warnings)
        assert not any('hidden_node' in w for w in unreachable_warnings)

    def test_parse_entry_with_comments(self):
        """Test that comments in entry groups are handled."""
        content = """
[characters]
npc: NPC

[entry:npc]
# This is a comment about the entry routing
has_key -> key_route
# Default route below
-> start

# Exit markers
<- key_route

[start]
npc: "Hello!"
-> END

[key_route]
npc: "Key!"
-> END
"""
        parser = DialogueParser()
        dialogue = parser.parse_lines(content.strip().split('\n'))

        entry = dialogue.entries['npc']
        assert len(entry.routes) == 2
        assert entry.routes[0].condition == 'has_key'
        assert entry.routes[1].condition is None
