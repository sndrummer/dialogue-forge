"""
Core parser for .dlg dialogue files (DLG Format v1.0)
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class Trigger:
    """Represents a trigger that starts dialogue at this node"""

    trigger_type: str  # "talk" or "event"
    target: str  # NPC id for talk, event name for event
    condition: Optional[str] = None
    line_number: int = 0


# Legacy dataclasses - kept for backwards compatibility during transition
@dataclass
class EntryRoute:
    """Represents a conditional entry route within an entry group"""

    condition: Optional[str]  # None means default (always matches)
    target: str
    line_number: int = 0


@dataclass
class EntryGroup:
    """Represents a named entry group with routes and exits"""

    name: str
    routes: List[EntryRoute] = field(default_factory=list)
    exits: List[str] = field(default_factory=list)  # Node names that end this conversation
    line_number: int = 0


@dataclass
class Choice:
    """Represents a dialogue choice"""

    target: str
    text: str
    condition: Optional[str] = None
    line_number: int = 0


@dataclass
class DialogueLine:
    """Represents a single dialogue line with optional condition and tags"""

    speaker: str
    text: str
    condition: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class DialogueNode:
    """Represents a dialogue node"""

    id: str
    lines: List[DialogueLine] = field(default_factory=list)
    choices: List[Choice] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    triggers: List[Trigger] = field(default_factory=list)  # @talk: and @event: triggers
    is_end: bool = False  # True if node has @end marker
    line_number: int = 0


@dataclass
class Dialogue:
    """Represents a complete dialogue file"""

    characters: Dict[str, str] = field(default_factory=dict)  # id -> display name
    nodes: Dict[str, DialogueNode] = field(default_factory=dict)
    entries: Dict[str, EntryGroup] = field(default_factory=dict)  # name -> entry group
    start_node: Optional[str] = None
    initial_state: List[str] = field(default_factory=list)  # Commands to execute before dialogue starts
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class DialogueParser:
    """Parser for .dlg dialogue files (DLG Format v1.0)"""

    # Valid condition operators and patterns
    CONDITION_OPERATORS = {"&&", "||", "!", ">", "<", ">=", "<=", "==", "!="}
    CONDITION_KEYWORDS = {"true", "false", "and", "or", "not"}
    SPECIAL_CHECKS = re.compile(r"(has_item|companion):(\w+)")

    def __init__(self):
        self.dialogue: Dialogue = Dialogue()
        self.current_line_number: int = 0
        # Track known items and companions for editor convenience
        self.known_items: Set[str] = set()
        self.known_companions: Set[str] = set()

    def _track_items_and_companions(self, text: str):
        """Extract and track items/companions from commands or conditions"""
        # Track from commands: *give_item X, *remove_item X, *add_companion X, *remove_companion X
        if text.startswith("give_item ") or text.startswith("remove_item "):
            parts = text.split()
            if len(parts) >= 2:
                self.known_items.add(parts[1])
        elif text.startswith("add_companion ") or text.startswith("remove_companion "):
            parts = text.split()
            if len(parts) >= 2:
                self.known_companions.add(parts[1])

        # Track from conditions: has_item:X, companion:X
        for match in re.finditer(r"has_item:(\w+)", text):
            self.known_items.add(match.group(1))
        for match in re.finditer(r"companion:(\w+)", text):
            self.known_companions.add(match.group(1))

    def _extract_tags(self, text: str) -> Tuple[str, List[str]]:
        """
        Extract tags from text. Tags appear in square brackets after the quoted text.
        Format: "dialogue text" [tag1, tag2]

        Returns:
            Tuple of (remaining_text, tags_list)
        """
        tags = []

        # Look for [tags] pattern after the last quote (if quotes exist)
        if "[" not in text:
            return text, tags

        # Find the tag brackets - they should be after the closing quote
        if '"' in text:
            last_quote = text.rindex('"')
            bracket_start = text.find("[", last_quote)
            if bracket_start == -1:
                return text, tags
        else:
            bracket_start = text.find("[")

        bracket_end = text.find("]", bracket_start)
        if bracket_end == -1:
            return text, tags

        # Extract the tags string
        tags_str = text[bracket_start + 1 : bracket_end].strip()
        remaining_text = text[:bracket_start].strip() + text[bracket_end + 1 :].strip()

        # Parse comma-separated tags
        if tags_str:
            tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]

        return remaining_text.strip(), tags

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
        if condition.count("{") != condition.count("}"):
            warnings.append(f"Line {line_number}: Unbalanced braces in condition '{condition}'")

        # Check for balanced parentheses
        if condition.count("(") != condition.count(")"):
            warnings.append(f"Line {line_number}: Unbalanced parentheses in condition '{condition}'")

        # Check for common syntax errors
        # Empty operators
        if "&&" in condition and re.search(r"&&\s*&&", condition):
            warnings.append(f"Line {line_number}: Double && operator in condition")
        if "||" in condition and re.search(r"\|\|\s*\|\|", condition):
            warnings.append(f"Line {line_number}: Double || operator in condition")

        # Check for has_item/companion without colon (common mistake)
        if re.search(r"\bhas_item\s+\w+", condition):
            warnings.append(f"Line {line_number}: 'has_item' should use colon syntax: has_item:item_name")
        if re.search(r"\bcompanion\s+\w+", condition):
            warnings.append(f"Line {line_number}: 'companion' should use colon syntax: companion:name")

        # Check for invalid comparison operators
        if re.search(r"[^!<>=]=[^=]", condition):
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
            "set": {"min_parts": 4, "requires_equals": True, "syntax": "*set variable = value"},
            "add": {"min_parts": 4, "requires_equals": True, "syntax": "*add variable = amount"},
            "sub": {"min_parts": 4, "requires_equals": True, "syntax": "*sub variable = amount"},
            "give_item": {
                "min_parts": 2,
                "requires_equals": False,
                "syntax": "*give_item item_name",
            },
            "remove_item": {
                "min_parts": 2,
                "requires_equals": False,
                "syntax": "*remove_item item_name",
            },
            "add_companion": {
                "min_parts": 2,
                "requires_equals": False,
                "syntax": "*add_companion companion_name",
            },
            "remove_companion": {
                "min_parts": 2,
                "requires_equals": False,
                "syntax": "*remove_companion companion_name",
            },
            "start_combat": {
                "min_parts": 2,
                "requires_equals": False,
                "syntax": "*start_combat combat_id",
            },
            "start_conversation": {
                "min_parts": 2,
                "requires_equals": False,
                "syntax": "*start_conversation npc_id",
            },
        }

        if cmd in KNOWN_COMMANDS:
            spec = KNOWN_COMMANDS[cmd]

            # Check minimum parts
            if len(parts) < spec["min_parts"]:
                warnings.append(f"Line {line_number}: Command '{cmd}' missing arguments. Expected: {spec['syntax']}")

            # Check for equals sign if required
            if spec["requires_equals"] and "=" not in command:
                warnings.append(
                    f"Line {line_number}: Command '{cmd}' requires '=' operator. Expected: {spec['syntax']}"
                )

            # For add/sub, verify the value is numeric
            if cmd in ("add", "sub") and len(parts) >= 4:
                try:
                    int(parts[3])
                except ValueError:
                    warnings.append(f"Line {line_number}: Command '{cmd}' requires numeric value, got '{parts[3]}'")
        else:
            # Unknown command - check for common typos
            TYPO_SUGGESTIONS = {
                "sett": "set",
                "ad": "add",
                "addd": "add",
                "subb": "sub",
                "give": "give_item",
                "remove": "remove_item",
                "addcompanion": "add_companion",
                "removecompanion": "remove_companion",
                "give_companion": "add_companion",
                "giveitem": "give_item",
                "removeitem": "remove_item",
                "startcombat": "start_combat",
            }

            if cmd in TYPO_SUGGESTIONS:
                warnings.append(f"Line {line_number}: Unknown command '{cmd}', did you mean '{TYPO_SUGGESTIONS[cmd]}'?")
            else:
                # Check string similarity for other typos
                for known_cmd in KNOWN_COMMANDS:
                    if self._string_similarity(cmd, known_cmd) > 0.7:
                        warnings.append(f"Line {line_number}: Unknown command '{cmd}', did you mean '{known_cmd}'?")
                        break

        return warnings

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity ratio"""
        if not s1 or not s2:
            return 0.0
        matches = sum(1 for c1, c2 in zip(s1.lower(), s2.lower()) if c1 == c2)
        return matches / max(len(s1), len(s2))

    def _read_multiline_quoted_text(
        self, lines: List[str], start_index: int, initial_text: str
    ) -> Tuple[str, List[str], Optional[str], int]:
        """
        Read multi-line quoted text when a quote is opened but not closed on the same line.

        Returns:
            Tuple of (text, tags, condition, next_line_index)
        """
        text_parts = [initial_text]
        i = start_index

        while i < len(lines):
            line = lines[i].rstrip()
            stripped = line.strip()

            # Skip empty lines and comments within multi-line text
            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            # Check if this line closes the quote
            if '"' in stripped:
                # Find the closing quote
                quote_pos = stripped.find('"')
                before_quote = stripped[:quote_pos].strip()
                after_quote = stripped[quote_pos + 1 :].strip()

                # Add the text before the closing quote
                if before_quote:
                    text_parts.append(before_quote)

                # Extract tags and condition from after_quote
                # Format: [tag1, tag2] {condition}
                tags = []
                condition = None

                # First extract tags [...]
                if "[" in after_quote:
                    bracket_start = after_quote.find("[")
                    bracket_end = after_quote.find("]", bracket_start)
                    if bracket_end > bracket_start:
                        tags_str = after_quote[bracket_start + 1 : bracket_end].strip()
                        if tags_str:
                            tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                        after_quote = after_quote[:bracket_start].strip() + " " + after_quote[bracket_end + 1 :].strip()
                        after_quote = after_quote.strip()

                # Then extract condition {...}
                if after_quote.startswith("{") and after_quote.endswith("}"):
                    condition = after_quote[1:-1].strip()
                elif "{" in after_quote:
                    cond_start = after_quote.find("{")
                    cond_end = after_quote.rfind("}")
                    if cond_end > cond_start:
                        condition = after_quote[cond_start + 1 : cond_end].strip()

                # Join all parts with a single space
                final_text = " ".join(text_parts)
                return final_text, tags, condition, i + 1
            else:
                # No closing quote - this is a continuation line
                text_parts.append(stripped)
                i += 1

        # Reached end of file without closing quote - return what we have
        final_text = " ".join(text_parts)
        return final_text, [], None, i

    def parse_file(self, file_path: Path) -> Dialogue:
        """Parse a .dlg file and return dialogue structure"""
        if not file_path.exists():
            raise FileNotFoundError(f"Dialogue file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
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
            if not line or line.strip().startswith("#"):
                i += 1
                continue

            # Parse character definitions
            if line.strip() == "[characters]":
                i = self._parse_characters(lines, i + 1)
                continue

            # Parse state initialization section
            if line.strip() == "[state]":
                i = self._parse_state(lines, i + 1)
                continue

            # Parse entry group section [entry:name]
            entry_match = re.match(r"\[entry:(\w+)\]", line.strip())
            if entry_match:
                entry_name = entry_match.group(1)
                i = self._parse_entry_group(lines, i + 1, entry_name, i + 1)
                continue

            # Parse dialogue node(s) - can have multiple stacked labels
            if line.strip().startswith("[") and line.strip().endswith("]"):
                node_ids = [line.strip()[1:-1]]
                # Check for additional stacked node labels
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("[") and lines[j].strip().endswith("]"):
                    node_ids.append(lines[j].strip()[1:-1])
                    j += 1
                i = self._parse_node(lines, j, node_ids)
                continue

            i += 1

        # Set start node if not explicitly defined
        if not self.dialogue.start_node and self.dialogue.nodes:
            # First node becomes start if no [start] node exists
            if "start" in self.dialogue.nodes:
                self.dialogue.start_node = "start"
            else:
                self.dialogue.start_node = next(iter(self.dialogue.nodes.keys()))

        return self.dialogue

    def _parse_characters(self, lines: List[str], start_index: int) -> int:
        """Parse character definitions"""
        i = start_index

        while i < len(lines):
            line = lines[i].strip()

            # Stop at next section or empty line followed by non-character line
            if line.startswith("[") and line.endswith("]"):
                break

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                i += 1
                continue

            # Parse character definition (id: Display Name)
            if ":" in line:
                char_id, display_name = line.split(":", 1)
                self.dialogue.characters[char_id.strip()] = display_name.strip()

            i += 1

        return i

    def _parse_state(self, lines: List[str], start_index: int) -> int:
        """Parse state initialization commands"""
        i = start_index

        while i < len(lines):
            line = lines[i].strip()

            # Stop at next section
            if line.startswith("[") and line.endswith("]"):
                break

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                i += 1
                continue

            # Parse commands (lines starting with *)
            if line.startswith("*"):
                cmd_text = line[1:].strip()
                self.dialogue.initial_state.append(cmd_text)
                self._track_items_and_companions(cmd_text)
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

    def _parse_entry_group(
        self, lines: List[str], start_index: int, entry_name: str, definition_line: int
    ) -> int:
        """Parse an entry group section [entry:name]

        Entry groups define conditional entry points and exit nodes for a conversation.

        Syntax:
            [entry:officer]
            # Entry routes - condition -> target (first match wins)
            equipment_equipped -> equip_items
            talked_before && !has_sword -> reminder
            -> start

            # Exit markers - conversation ends at these nodes
            <- equip_items
            <- ship_deck
        """
        entry_group = EntryGroup(name=entry_name, line_number=definition_line)
        i = start_index

        while i < len(lines):
            line = lines[i].strip()

            # Stop at next section (any [...] header)
            if line.startswith("[") and line.endswith("]"):
                break

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                i += 1
                continue

            # Parse exit marker: <- node_name
            if line.startswith("<-"):
                exit_target = line[2:].strip()
                if exit_target:
                    entry_group.exits.append(exit_target)
                else:
                    self.dialogue.warnings.append(
                        f"Line {i + 1}: Empty exit marker '<-' in [entry:{entry_name}]"
                    )
                i += 1
                continue

            # Parse entry route: condition -> target OR -> target (default)
            if "->" in line:
                arrow_pos = line.index("->")
                condition_part = line[:arrow_pos].strip()
                target = line[arrow_pos + 2 :].strip()

                if not target:
                    self.dialogue.warnings.append(
                        f"Line {i + 1}: Empty target in entry route in [entry:{entry_name}]"
                    )
                    i += 1
                    continue

                # Empty condition means default route
                condition = condition_part if condition_part else None

                # Validate condition syntax if present
                if condition:
                    condition_warnings = self.validate_condition_syntax(condition, i + 1)
                    self.dialogue.warnings.extend(condition_warnings)
                    self._track_items_and_companions(condition)

                route = EntryRoute(condition=condition, target=target, line_number=i + 1)
                entry_group.routes.append(route)
                i += 1
                continue

            # Unexpected content
            self.dialogue.warnings.append(
                f"Line {i + 1}: Unexpected content in [entry:{entry_name}]: '{line}'. "
                f"Expected 'condition -> target', '-> target', or '<- exit_node'."
            )
            i += 1

        # Validate entry group has at least one route
        if not entry_group.routes:
            self.dialogue.warnings.append(
                f"[entry:{entry_name}] has no entry routes defined"
            )

        # Check for duplicate entry group names
        if entry_name in self.dialogue.entries:
            self.dialogue.warnings.append(
                f"Line {definition_line}: Duplicate entry group name '{entry_name}'"
            )

        self.dialogue.entries[entry_name] = entry_group
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
            if line.strip().startswith("[") and line.strip().endswith("]"):
                break

            # Skip empty lines and comments
            if not line or line.strip().startswith("#"):
                i += 1
                continue

            stripped = line.strip()

            # Parse trigger (@talk:, @event:) or end marker (@end)
            if stripped.startswith("@"):
                if stripped == "@end":
                    primary_node.is_end = True
                    i += 1
                    continue
                elif stripped.startswith("@talk:") or stripped.startswith("@event:"):
                    trigger = self._parse_trigger(stripped, i + 1)
                    if trigger:
                        primary_node.triggers.append(trigger)
                        self._track_items_and_companions(trigger.condition or "")
                    i += 1
                    continue
                else:
                    self.dialogue.warnings.append(
                        f"Line {i + 1}: Unknown trigger type: {stripped}. Expected @talk:, @event:, or @end"
                    )
                    i += 1
                    continue

            # Parse command/effect
            if stripped.startswith("*"):
                cmd_text = stripped[1:].strip()
                primary_node.commands.append(cmd_text)
                self._track_items_and_companions(cmd_text)
                # Validate command syntax at parse time
                cmd_warnings = self.validate_command_syntax(cmd_text, i + 1)
                self.dialogue.warnings.extend(cmd_warnings)
                i += 1
                continue

            # Parse choice
            if stripped.startswith("->"):
                i = self._parse_choice(lines, i, primary_node)
                continue

            # Parse speaker line
            if ":" in stripped and not stripped.startswith("{"):
                speaker, rest = stripped.split(":", 1)
                rest = rest.strip()

                # Check for multi-line quoted text (quote opened but not closed)
                if rest.startswith('"') and rest.count('"') == 1:
                    # Multi-line: quote opened but not closed on this line
                    initial_text = rest[1:].strip()  # Remove opening quote
                    text, tags, condition, next_i = self._read_multiline_quoted_text(lines, i + 1, initial_text)

                    # Validate condition syntax if present
                    if condition:
                        condition_warnings = self.validate_condition_syntax(condition, i + 1)
                        self.dialogue.warnings.extend(condition_warnings)

                    dialogue_line = DialogueLine(
                        speaker=speaker.strip(),
                        text=text,
                        condition=condition,
                        tags=tags,
                        line_number=i + 1,
                    )
                    primary_node.lines.append(dialogue_line)
                    i = next_i
                    continue

                # Single-line: extract tags and condition if present
                # Format: "text" [tag1, tag2] {condition}
                condition = None
                tags = []
                text = rest

                # First extract tags [...]
                text, tags = self._extract_tags(text)

                # Then extract condition {...}
                if "{" in text:
                    # Check if the { appears after the last quote (if quotes exist)
                    if '"' in text:
                        if text.rindex("{") > text.rindex('"'):
                            cond_start = text.rindex("{")
                            condition = text[cond_start:].strip()
                            text = text[:cond_start].strip()
                            # Remove the curly braces
                            if condition.startswith("{") and condition.endswith("}"):
                                condition = condition[1:-1].strip()
                    else:
                        # No quotes, so check if { is at the end
                        cond_start = text.rindex("{")
                        condition = text[cond_start:].strip()
                        text = text[:cond_start].strip()
                        # Remove the curly braces
                        if condition.startswith("{") and condition.endswith("}"):
                            condition = condition[1:-1].strip()

                # Remove quotes from text
                if text.startswith('"') and text.endswith('"'):
                    text = text[1:-1]

                # Validate condition syntax if present
                if condition:
                    condition_warnings = self.validate_condition_syntax(condition, i + 1)
                    self.dialogue.warnings.extend(condition_warnings)

                dialogue_line = DialogueLine(
                    speaker=speaker.strip(),
                    text=text,
                    condition=condition,
                    tags=tags,
                    line_number=i + 1,
                )
                primary_node.lines.append(dialogue_line)
                i += 1
                continue

            i += 1

        # Create shallow copies for stacked nodes (prevents mutation hazards)
        # Each alias gets its own DialogueNode instance with shared content references
        for node_id in node_ids[1:]:
            alias_node = DialogueNode(
                id=node_id,
                lines=primary_node.lines,  # Share the list reference (read-only expected)
                choices=primary_node.choices,  # Share the list reference (read-only expected)
                commands=primary_node.commands,  # Share the list reference (read-only expected)
                triggers=primary_node.triggers,  # Share triggers
                is_end=primary_node.is_end,  # Share is_end
                line_number=primary_node.line_number,
            )
            self.dialogue.nodes[node_id] = alias_node

        return i

    def _parse_trigger(self, line: str, line_number: int) -> Optional[Trigger]:
        """Parse a trigger line (@talk: or @event:)

        Format:
            @talk:officer
            @talk:officer {condition}
            @event:enter_temple
            @event:pickup_item {has_item:key}
        """
        # Determine trigger type
        if line.startswith("@talk:"):
            trigger_type = "talk"
            rest = line[6:].strip()
        elif line.startswith("@event:"):
            trigger_type = "event"
            rest = line[7:].strip()
        else:
            return None

        # Extract target and optional condition
        condition = None
        target = rest

        if "{" in rest:
            brace_start = rest.index("{")
            target = rest[:brace_start].strip()
            condition = rest[brace_start:].strip()
            # Remove curly braces
            if condition.startswith("{") and condition.endswith("}"):
                condition = condition[1:-1].strip()

            # Validate condition syntax
            if condition:
                condition_warnings = self.validate_condition_syntax(condition, line_number)
                self.dialogue.warnings.extend(condition_warnings)

        if not target:
            self.dialogue.errors.append(
                f"Line {line_number}: Trigger missing target: {line}"
            )
            return None

        return Trigger(
            trigger_type=trigger_type,
            target=target,
            condition=condition,
            line_number=line_number,
        )

    def _parse_choice(self, lines: List[str], start_index: int, node: DialogueNode) -> int:
        """Parse a choice line, returns the next line index to process"""
        line = lines[start_index].strip()
        next_index = start_index + 1

        # Remove -> prefix
        choice_text = line[2:].strip()

        # Determine if this is a player choice (has colon before any condition)
        # or a GOTO (no colon, or colon only inside condition)
        # -> target: "text" = choice (colon before { or no {)
        # -> target {condition} = conditional GOTO (colon only inside {})
        has_colon = ":" in choice_text
        has_condition = "{" in choice_text

        # Check if colon comes before the condition brace
        colon_before_condition = False
        if has_colon and has_condition:
            colon_pos = choice_text.index(":")
            brace_pos = choice_text.index("{")
            colon_before_condition = colon_pos < brace_pos
        elif has_colon and not has_condition:
            colon_before_condition = True

        # Parse target and text
        if colon_before_condition:
            target, rest = choice_text.split(":", 1)
            target = target.strip()
            rest = rest.strip()

            # Check for multi-line quoted text (quote opened but not closed)
            if rest.startswith('"') and rest.count('"') == 1:
                # Multi-line: quote opened but not closed on this line
                initial_text = rest[1:].strip()  # Remove opening quote
                text, _tags, condition, next_index = self._read_multiline_quoted_text(
                    lines, start_index + 1, initial_text
                )
                # Note: tags are ignored for choices (only used on dialogue lines)

                # Validate condition syntax if present
                if condition:
                    condition_warnings = self.validate_condition_syntax(condition, start_index + 1)
                    self.dialogue.warnings.extend(condition_warnings)
                    self._track_items_and_companions(condition)

                choice = Choice(target=target, text=text, condition=condition, line_number=start_index + 1)
                node.choices.append(choice)
                return next_index

            # Single-line: check for condition
            condition = None
            text = rest

            # Look for condition at the end (after the quoted text)
            if "{" in rest:
                # Check if the { appears after the last quote (if quotes exist)
                if '"' in rest:
                    if rest.rindex("{") > rest.rindex('"'):
                        cond_start = rest.rindex("{")
                        text = rest[:cond_start].strip()
                        condition = rest[cond_start:].strip()
                        # Remove the curly braces
                        if condition.startswith("{") and condition.endswith("}"):
                            condition = condition[1:-1].strip()
                else:
                    # No quotes, so check if { is at the end
                    cond_start = rest.rindex("{")
                    text = rest[:cond_start].strip()
                    condition = rest[cond_start:].strip()
                    # Remove the curly braces
                    if condition.startswith("{") and condition.endswith("}"):
                        condition = condition[1:-1].strip()

            # Remove quotes from text
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]

            # Validate condition syntax if present
            if condition:
                condition_warnings = self.validate_condition_syntax(condition, start_index + 1)
                self.dialogue.warnings.extend(condition_warnings)
                self._track_items_and_companions(condition)

            choice = Choice(target=target, text=text, condition=condition, line_number=start_index + 1)
        else:
            # No colon - could be simple GOTO or conditional GOTO
            # -> target OR -> target {condition}
            if "{" in choice_text:
                # Conditional GOTO: -> target {condition}
                cond_start = choice_text.index("{")
                target = choice_text[:cond_start].strip()
                condition = choice_text[cond_start:].strip()
                # Remove the curly braces
                if condition.startswith("{") and condition.endswith("}"):
                    condition = condition[1:-1].strip()

                # Validate condition syntax
                if condition:
                    condition_warnings = self.validate_condition_syntax(condition, start_index + 1)
                    self.dialogue.warnings.extend(condition_warnings)
                    self._track_items_and_companions(condition)

                choice = Choice(
                    target=target,
                    text="",  # No text for conditional GOTO
                    condition=condition,
                    line_number=start_index + 1,
                )
            else:
                # Simple GOTO without condition (like -> END or -> next_node)
                choice = Choice(target=choice_text, text="", condition=None, line_number=start_index + 1)

        node.choices.append(choice)
        return next_index

    def validate(self) -> bool:
        """Validate the parsed dialogue"""
        valid = True

        # Check for undefined nodes in choices
        for node_id, node in self.dialogue.nodes.items():
            for choice in node.choices:
                if choice.target != "END" and choice.target not in self.dialogue.nodes:
                    self.dialogue.errors.append(
                        f"Line {choice.line_number}: Undefined target node '{choice.target}' in node '{node_id}'"
                    )
                    valid = False

        # Check for undefined speakers
        for node_id, node in self.dialogue.nodes.items():
            for line in node.lines:
                if line.speaker not in self.dialogue.characters:
                    self.dialogue.warnings.append(
                        f"Node '{node_id}': Speaker '{line.speaker}' not defined in [characters] section"
                    )

        # Validate entry groups
        for entry_name, entry_group in self.dialogue.entries.items():
            # Check entry route targets exist
            for route in entry_group.routes:
                if route.target not in self.dialogue.nodes:
                    self.dialogue.errors.append(
                        f"Line {route.line_number}: Entry route target '{route.target}' "
                        f"in [entry:{entry_name}] does not exist"
                    )
                    valid = False

            # Check exit nodes exist
            for exit_node in entry_group.exits:
                if exit_node not in self.dialogue.nodes:
                    self.dialogue.warnings.append(
                        f"[entry:{entry_name}]: Exit node '{exit_node}' does not exist"
                    )

            # Warn if entry group has no default route (no unconditional route)
            has_default = any(route.condition is None for route in entry_group.routes)
            if not has_default:
                self.dialogue.warnings.append(
                    f"[entry:{entry_name}] has no default entry route (-> target). "
                    f"Conversation may not start if no conditions match."
                )

        # Check for unreachable nodes (now considering entry points too)
        reachable = self._find_reachable_nodes()
        for node_id in self.dialogue.nodes:
            if node_id not in reachable and node_id != self.dialogue.start_node:
                self.dialogue.warnings.append(f"Node '{node_id}' is unreachable from start")

        # Check that there's at least one path to END
        if not self._has_path_to_end():
            self.dialogue.warnings.append("No path leads to END - conversation may not be able to terminate")

        return valid and len(self.dialogue.errors) == 0

    def _find_reachable_nodes(self) -> Set[str]:
        """Find all nodes reachable from start node and entry group targets"""
        visited = set()
        to_visit = []

        # Add start node as a starting point
        if self.dialogue.start_node:
            to_visit.append(self.dialogue.start_node)

        # Add all entry group targets as starting points (legacy support)
        for entry_group in self.dialogue.entries.values():
            for route in entry_group.routes:
                if route.target not in to_visit:
                    to_visit.append(route.target)

        # Add all nodes with triggers as starting points (new syntax)
        for node_id, node in self.dialogue.nodes.items():
            if node.triggers and node_id not in to_visit:
                to_visit.append(node_id)

        while to_visit:
            current = to_visit.pop(0)
            if current in visited or current == "END":
                continue

            visited.add(current)

            if current in self.dialogue.nodes:
                node = self.dialogue.nodes[current]
                for choice in node.choices:
                    if choice.target != "END" and choice.target not in visited:
                        to_visit.append(choice.target)

        return visited

    def _has_path_to_end(self) -> bool:
        """Check if there's at least one path that leads to END"""
        for node in self.dialogue.nodes.values():
            for choice in node.choices:
                if choice.target == "END":
                    return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the parsed dialogue"""
        total_lines = sum(len(node.lines) for node in self.dialogue.nodes.values())
        total_choices = sum(len(node.choices) for node in self.dialogue.nodes.values())
        total_commands = sum(len(node.commands) for node in self.dialogue.nodes.values())
        total_entry_routes = sum(len(e.routes) for e in self.dialogue.entries.values())
        total_exits = sum(len(e.exits) for e in self.dialogue.entries.values())

        # Count new trigger system
        total_triggers = sum(len(node.triggers) for node in self.dialogue.nodes.values())
        total_end_nodes = sum(1 for node in self.dialogue.nodes.values() if node.is_end)

        return {
            "characters": len(self.dialogue.characters),
            "nodes": len(self.dialogue.nodes),
            "entry_groups": len(self.dialogue.entries),
            "entry_routes": total_entry_routes,
            "exit_nodes": total_exits,
            "triggers": total_triggers,
            "end_nodes": total_end_nodes,
            "dialogue_lines": total_lines,
            "choices": total_choices,
            "commands": total_commands,
            "initial_state_commands": len(self.dialogue.initial_state),
            "errors": len(self.dialogue.errors),
            "warnings": len(self.dialogue.warnings),
            "known_items": sorted(list(self.known_items)),
            "known_companions": sorted(list(self.known_companions)),
        }
