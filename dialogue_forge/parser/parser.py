"""
Core parser for .dlg dialogue files (DLG Format v1.0)
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class Choice:
    """Represents a dialogue choice"""
    target: str
    text: str
    condition: Optional[str] = None
    line_number: int = 0


@dataclass
class DialogueNode:
    """Represents a dialogue node"""
    id: str
    lines: List[Tuple[str, str]] = field(default_factory=list)  # (speaker, text) pairs
    choices: List[Choice] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class Dialogue:
    """Represents a complete dialogue file"""
    characters: Dict[str, str] = field(default_factory=dict)  # id -> display name
    nodes: Dict[str, DialogueNode] = field(default_factory=dict)
    start_node: Optional[str] = None
    initial_state: List[str] = field(default_factory=list)  # Commands to execute before dialogue starts
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class DialogueParser:
    """Parser for .dlg dialogue files (DLG Format v1.0)"""

    # Valid condition operators and patterns
    CONDITION_OPERATORS = {'&&', '||', '!', '>', '<', '>=', '<=', '==', '!='}
    CONDITION_KEYWORDS = {'true', 'false', 'and', 'or', 'not'}
    SPECIAL_CHECKS = re.compile(r'(has_item|companion):(\w+)')

    def __init__(self):
        self.dialogue: Dialogue = Dialogue()
        self.current_line_number: int = 0

    def validate_condition_syntax(self, condition: str, line_number: int) -> List[str]:
        """
        Validate condition syntax and return list of warnings/errors.
        Does NOT execute the condition, only checks syntax.
        """
        warnings = []
        if not condition or not condition.strip():
            return warnings

        condition = condition.strip()

        # Check for balanced braces (should already be stripped, but verify)
        if condition.count('{') != condition.count('}'):
            warnings.append(f"Line {line_number}: Unbalanced braces in condition '{condition}'")

        # Check for balanced parentheses
        if condition.count('(') != condition.count(')'):
            warnings.append(f"Line {line_number}: Unbalanced parentheses in condition '{condition}'")

        # Check for common syntax errors
        # Empty operators
        if '&&' in condition and re.search(r'&&\s*&&', condition):
            warnings.append(f"Line {line_number}: Double && operator in condition")
        if '||' in condition and re.search(r'\|\|\s*\|\|', condition):
            warnings.append(f"Line {line_number}: Double || operator in condition")

        # Check for has_item/companion without colon (common mistake)
        if re.search(r'\bhas_item\s+\w+', condition):
            warnings.append(f"Line {line_number}: 'has_item' should use colon syntax: has_item:item_name")
        if re.search(r'\bcompanion\s+\w+', condition):
            warnings.append(f"Line {line_number}: 'companion' should use colon syntax: companion:name")

        # Check for invalid comparison operators
        if re.search(r'[^!<>=]=[^=]', condition):
            # Single = that's not part of ==, !=, <=, >=
            warnings.append(f"Line {line_number}: Use '==' for comparison, not '=' in condition")

        return warnings

    def validate_command_syntax(self, command: str, line_number: int) -> List[str]:
        """
        Validate command syntax and return list of warnings/errors.
        Catches typos and syntax errors at parse time.
        """
        warnings = []
        if not command or not command.strip():
            return warnings

        command = command.strip()
        parts = command.split()
        if not parts:
            return warnings

        cmd = parts[0].lower()

        # Known commands and their expected syntax
        KNOWN_COMMANDS = {
            'set': {'min_parts': 4, 'requires_equals': True, 'syntax': '*set variable = value'},
            'add': {'min_parts': 4, 'requires_equals': True, 'syntax': '*add variable = amount'},
            'sub': {'min_parts': 4, 'requires_equals': True, 'syntax': '*sub variable = amount'},
            'give_item': {'min_parts': 2, 'requires_equals': False, 'syntax': '*give_item item_name'},
            'remove_item': {'min_parts': 2, 'requires_equals': False, 'syntax': '*remove_item item_name'},
            'add_companion': {'min_parts': 2, 'requires_equals': False, 'syntax': '*add_companion companion_name'},
            'remove_companion': {'min_parts': 2, 'requires_equals': False, 'syntax': '*remove_companion companion_name'},
            'start_combat': {'min_parts': 2, 'requires_equals': False, 'syntax': '*start_combat combat_id'},
            'start_conversation': {'min_parts': 2, 'requires_equals': False, 'syntax': '*start_conversation npc_id'},
        }

        if cmd in KNOWN_COMMANDS:
            spec = KNOWN_COMMANDS[cmd]

            # Check minimum parts
            if len(parts) < spec['min_parts']:
                warnings.append(
                    f"Line {line_number}: Command '{cmd}' missing arguments. Expected: {spec['syntax']}"
                )

            # Check for equals sign if required
            if spec['requires_equals'] and '=' not in command:
                warnings.append(
                    f"Line {line_number}: Command '{cmd}' requires '=' operator. Expected: {spec['syntax']}"
                )

            # For add/sub, verify the value is numeric
            if cmd in ('add', 'sub') and len(parts) >= 4:
                try:
                    int(parts[3])
                except ValueError:
                    warnings.append(
                        f"Line {line_number}: Command '{cmd}' requires numeric value, got '{parts[3]}'"
                    )
        else:
            # Unknown command - check for common typos
            TYPO_SUGGESTIONS = {
                'sett': 'set', 'ad': 'add', 'addd': 'add', 'subb': 'sub',
                'give': 'give_item', 'remove': 'remove_item',
                'addcompanion': 'add_companion', 'removecompanion': 'remove_companion',
                'give_companion': 'add_companion', 'giveitem': 'give_item',
                'removeitem': 'remove_item', 'startcombat': 'start_combat',
            }

            if cmd in TYPO_SUGGESTIONS:
                warnings.append(
                    f"Line {line_number}: Unknown command '{cmd}', did you mean '{TYPO_SUGGESTIONS[cmd]}'?"
                )
            else:
                # Check string similarity for other typos
                for known_cmd in KNOWN_COMMANDS:
                    if self._string_similarity(cmd, known_cmd) > 0.7:
                        warnings.append(
                            f"Line {line_number}: Unknown command '{cmd}', did you mean '{known_cmd}'?"
                        )
                        break

        return warnings

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity ratio"""
        if not s1 or not s2:
            return 0.0
        matches = sum(1 for c1, c2 in zip(s1.lower(), s2.lower()) if c1 == c2)
        return matches / max(len(s1), len(s2))

    def parse_file(self, file_path: Path) -> Dialogue:
        """Parse a .dlg file and return dialogue structure"""
        if not file_path.exists():
            raise FileNotFoundError(f"Dialogue file not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        return self.parse_lines(lines)

    def parse_lines(self, lines: List[str]) -> Dialogue:
        """Parse lines of dialogue text"""
        self.dialogue = Dialogue()
        self.current_line_number = 0

        i = 0
        while i < len(lines):
            self.current_line_number = i + 1
            line = lines[i].rstrip()

            # Skip empty lines and comments
            if not line or line.strip().startswith('#'):
                i += 1
                continue

            # Parse character definitions
            if line.strip() == '[characters]':
                i = self._parse_characters(lines, i + 1)
                continue

            # Parse state initialization section
            if line.strip() == '[state]':
                i = self._parse_state(lines, i + 1)
                continue

            # Parse dialogue node(s) - can have multiple stacked labels
            if line.strip().startswith('[') and line.strip().endswith(']'):
                node_ids = [line.strip()[1:-1]]
                # Check for additional stacked node labels
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith('[') and lines[j].strip().endswith(']'):
                    node_ids.append(lines[j].strip()[1:-1])
                    j += 1
                i = self._parse_node(lines, j, node_ids)
                continue

            i += 1

        # Set start node if not explicitly defined
        if not self.dialogue.start_node and self.dialogue.nodes:
            # First node becomes start if no [start] node exists
            if 'start' in self.dialogue.nodes:
                self.dialogue.start_node = 'start'
            else:
                self.dialogue.start_node = next(iter(self.dialogue.nodes.keys()))

        return self.dialogue

    def _parse_characters(self, lines: List[str], start_index: int) -> int:
        """Parse character definitions"""
        i = start_index

        while i < len(lines):
            line = lines[i].strip()

            # Stop at next section or empty line followed by non-character line
            if line.startswith('[') and line.endswith(']'):
                break

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                i += 1
                continue

            # Parse character definition (id: Display Name)
            if ':' in line:
                char_id, display_name = line.split(':', 1)
                self.dialogue.characters[char_id.strip()] = display_name.strip()

            i += 1

        return i

    def _parse_state(self, lines: List[str], start_index: int) -> int:
        """Parse state initialization commands"""
        i = start_index

        while i < len(lines):
            line = lines[i].strip()

            # Stop at next section
            if line.startswith('[') and line.endswith(']'):
                break

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                i += 1
                continue

            # Parse commands (lines starting with *)
            if line.startswith('*'):
                cmd_text = line[1:].strip()
                self.dialogue.initial_state.append(cmd_text)
                # Validate command syntax at parse time
                cmd_warnings = self.validate_command_syntax(cmd_text, i + 1)
                self.dialogue.warnings.extend(cmd_warnings)
            else:
                # Non-command line in state section is a warning
                self.dialogue.warnings.append(
                    f"Line {i + 1}: Unexpected content in [state] section: '{line}'. Expected *command."
                )

            i += 1

        return i

    def _parse_node(self, lines: List[str], start_index: int, node_ids: List[str]) -> int:
        """Parse a dialogue node (can have multiple IDs for stacked labels)"""
        # Create the primary node with the first ID
        primary_node = DialogueNode(id=node_ids[0], line_number=start_index)
        self.dialogue.nodes[node_ids[0]] = primary_node

        i = start_index

        while i < len(lines):
            line = lines[i].rstrip()

            # Stop at next node
            if line.strip().startswith('[') and line.strip().endswith(']'):
                break

            # Skip empty lines and comments
            if not line or line.strip().startswith('#'):
                i += 1
                continue

            stripped = line.strip()

            # Parse command/effect
            if stripped.startswith('*'):
                cmd_text = stripped[1:].strip()
                primary_node.commands.append(cmd_text)
                # Validate command syntax at parse time
                cmd_warnings = self.validate_command_syntax(cmd_text, i + 1)
                self.dialogue.warnings.extend(cmd_warnings)
                i += 1
                continue

            # Parse choice
            if stripped.startswith('->'):
                i = self._parse_choice(lines, i, primary_node)
                continue

            # Parse speaker line
            if ':' in stripped and not stripped.startswith('{'):
                speaker, text = stripped.split(':', 1)
                # Remove quotes if present
                text = text.strip()
                if text.startswith('"') and text.endswith('"'):
                    text = text[1:-1]
                primary_node.lines.append((speaker.strip(), text))
                i += 1
                continue

            i += 1

        # Create shallow copies for stacked nodes (prevents mutation hazards)
        # Each alias gets its own DialogueNode instance with shared content references
        for node_id in node_ids[1:]:
            alias_node = DialogueNode(
                id=node_id,
                lines=primary_node.lines,      # Share the list reference (read-only expected)
                choices=primary_node.choices,  # Share the list reference (read-only expected)
                commands=primary_node.commands,  # Share the list reference (read-only expected)
                line_number=primary_node.line_number
            )
            self.dialogue.nodes[node_id] = alias_node

        return i

    def _parse_choice(self, lines: List[str], start_index: int, node: DialogueNode) -> int:
        """Parse a choice line"""
        line = lines[start_index].strip()

        # Remove -> prefix
        choice_text = line[2:].strip()

        # Parse target and text
        if ':' in choice_text:
            target, rest = choice_text.split(':', 1)
            target = target.strip()
            rest = rest.strip()

            # Check for condition
            condition = None
            text = rest

            # Look for condition at the end (after the quoted text)
            if '{' in rest:
                # Check if the { appears after the last quote (if quotes exist)
                if '"' in rest:
                    if rest.rindex('{') > rest.rindex('"'):
                        cond_start = rest.rindex('{')
                        text = rest[:cond_start].strip()
                        condition = rest[cond_start:].strip()
                        # Remove the curly braces
                        if condition.startswith('{') and condition.endswith('}'):
                            condition = condition[1:-1].strip()
                else:
                    # No quotes, so check if { is at the end
                    cond_start = rest.rindex('{')
                    text = rest[:cond_start].strip()
                    condition = rest[cond_start:].strip()
                    # Remove the curly braces
                    if condition.startswith('{') and condition.endswith('}'):
                        condition = condition[1:-1].strip()

            # Remove quotes from text
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]

            # Validate condition syntax if present
            if condition:
                condition_warnings = self.validate_condition_syntax(condition, start_index + 1)
                self.dialogue.warnings.extend(condition_warnings)

            choice = Choice(
                target=target,
                text=text,
                condition=condition,
                line_number=start_index + 1
            )
        else:
            # Simple target without text (like -> END)
            choice = Choice(
                target=choice_text,
                text="",
                condition=None,
                line_number=start_index + 1
            )

        node.choices.append(choice)
        return start_index + 1

    def validate(self) -> bool:
        """Validate the parsed dialogue"""
        valid = True

        # Check for undefined nodes in choices
        for node_id, node in self.dialogue.nodes.items():
            for choice in node.choices:
                if choice.target != 'END' and choice.target not in self.dialogue.nodes:
                    self.dialogue.errors.append(
                        f"Line {choice.line_number}: Undefined target node '{choice.target}' in node '{node_id}'"
                    )
                    valid = False

        # Check for undefined speakers
        for node_id, node in self.dialogue.nodes.items():
            for speaker, text in node.lines:
                if speaker not in self.dialogue.characters:
                    self.dialogue.warnings.append(
                        f"Node '{node_id}': Speaker '{speaker}' not defined in [characters] section"
                    )

        # Check for unreachable nodes
        reachable = self._find_reachable_nodes()
        for node_id in self.dialogue.nodes:
            if node_id not in reachable and node_id != self.dialogue.start_node:
                self.dialogue.warnings.append(
                    f"Node '{node_id}' is unreachable from start"
                )

        # Check that there's at least one path to END
        if not self._has_path_to_end():
            self.dialogue.warnings.append(
                "No path leads to END - conversation may not be able to terminate"
            )

        return valid and len(self.dialogue.errors) == 0

    def _find_reachable_nodes(self) -> Set[str]:
        """Find all nodes reachable from the start node"""
        if not self.dialogue.start_node:
            return set()

        visited = set()
        to_visit = [self.dialogue.start_node]

        while to_visit:
            current = to_visit.pop(0)
            if current in visited or current == 'END':
                continue

            visited.add(current)

            if current in self.dialogue.nodes:
                node = self.dialogue.nodes[current]
                for choice in node.choices:
                    if choice.target != 'END' and choice.target not in visited:
                        to_visit.append(choice.target)

        return visited

    def _has_path_to_end(self) -> bool:
        """Check if there's at least one path that leads to END"""
        for node in self.dialogue.nodes.values():
            for choice in node.choices:
                if choice.target == 'END':
                    return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the parsed dialogue"""
        total_lines = sum(len(node.lines) for node in self.dialogue.nodes.values())
        total_choices = sum(len(node.choices) for node in self.dialogue.nodes.values())
        total_commands = sum(len(node.commands) for node in self.dialogue.nodes.values())

        return {
            'characters': len(self.dialogue.characters),
            'nodes': len(self.dialogue.nodes),
            'dialogue_lines': total_lines,
            'choices': total_choices,
            'commands': total_commands,
            'initial_state_commands': len(self.dialogue.initial_state),
            'errors': len(self.dialogue.errors),
            'warnings': len(self.dialogue.warnings)
        }