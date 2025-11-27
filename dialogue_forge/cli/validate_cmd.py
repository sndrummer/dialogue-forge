"""
Enhanced validation script for .dlg dialogue files with precise error reporting
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from collections import defaultdict


# ANSI color codes for terminal output
class Colors:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'


@dataclass
class ValidationError:
    """Represents a validation error with location info"""
    line_number: int
    column: int
    severity: str  # 'error' or 'warning'
    message: str
    context: Optional[str] = None
    suggestion: Optional[str] = None


class DialogueValidator:
    """Enhanced validator for .dlg files with precise error reporting"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lines: List[str] = []
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        self.nodes: Dict[str, int] = {}  # node_id -> line_number
        self.characters: Dict[str, int] = {}  # char_id -> line_number
        self.referenced_nodes: Set[str] = set()
        self.variables_set: Set[str] = set()
        self.variables_used: Set[str] = set()
        self.items_given: Set[str] = set()  # Track items from *give_item
        self.items_checked: Set[str] = set()  # Track items from has_item: checks
        self.companions_added: Set[str] = set()  # Track companions from *add_companion
        self.companions_checked: Set[str] = set()  # Track companions from companion: checks
        self.stacked_nodes: Dict[str, List[str]] = {}  # Track which nodes are stacked together

    def validate(self) -> bool:
        """Main validation method"""
        if not self.file_path.exists():
            print(f"❌ File not found: {self.file_path}")
            return False

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.lines = f.readlines()

            # Perform validation passes
            self._validate_structure()
            self._validate_references()
            self._validate_conditions()
            self._validate_commands()
            self._validate_flow()

            # Report results
            self._report_results()

            return len(self.errors) == 0

        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return False

    def _validate_structure(self):
        """Validate basic structure and syntax"""
        in_characters_section = False
        in_state_section = False
        in_node = False
        current_node = None
        current_stacked_nodes = []  # Track consecutive node labels
        node_line = 0
        bracket_stack = []
        self._in_multiline_string = False  # Track multi-line dialogue strings

        for line_num, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            # Handle multi-line string continuation
            if self._in_multiline_string:
                # Check if this line closes the string
                if '"' in stripped:
                    self._in_multiline_string = False
                continue

            # Check for characters section
            if stripped == '[characters]':
                if in_node:
                    self._add_error(line_num, 1, "Characters section cannot be inside a node")
                in_characters_section = True
                in_state_section = False
                in_node = False
                current_stacked_nodes = []
                continue

            # Check for state section - track variables set here
            if stripped == '[state]':
                in_characters_section = False
                in_state_section = True
                in_node = False
                current_stacked_nodes = []
                continue

            # Handle state section content
            if in_state_section:
                if stripped.startswith('[') and stripped.endswith(']'):
                    in_state_section = False
                    # Fall through to process this as a node
                elif stripped.startswith('*'):
                    # Track variables/items/companions set in state section
                    self._validate_command_syntax(line_num, stripped)
                    continue
                else:
                    continue

            # Check for node definitions
            if stripped.startswith('[') and stripped.endswith(']'):
                node_id = stripped[1:-1]

                if not node_id:
                    self._add_error(line_num, 1, "Empty node name")
                elif node_id in self.nodes:
                    self._add_warning(line_num, 1, f"Duplicate node '{node_id}' (first defined at line {self.nodes[node_id]})")
                else:
                    self.nodes[node_id] = line_num

                # Check if next line is also a node (stacked nodes)
                if line_num < len(self.lines):
                    next_line = self.lines[line_num].strip() if line_num < len(self.lines) else ""
                    if next_line.startswith('[') and next_line.endswith(']'):
                        # This is part of a stack
                        current_stacked_nodes.append(node_id)
                    else:
                        # End of stack or single node
                        if current_stacked_nodes:
                            current_stacked_nodes.append(node_id)
                            # Store all stacked nodes pointing to each other
                            for n in current_stacked_nodes:
                                self.stacked_nodes[n] = current_stacked_nodes.copy()
                            current_stacked_nodes = []
                        in_node = True
                        current_node = node_id
                        node_line = line_num

                in_characters_section = False
                continue

            # Validate characters section
            if in_characters_section:
                if ':' not in stripped:
                    self._add_error(line_num, 1, "Character definition must be in format 'id: Display Name'")
                else:
                    char_id = stripped.split(':')[0].strip()
                    if char_id in self.characters:
                        self._add_warning(line_num, 1, f"Duplicate character '{char_id}' (first defined at line {self.characters[char_id]})")
                    else:
                        self.characters[char_id] = line_num

            # Validate node content
            if in_node:
                # Check for speaker lines
                if ':' in stripped and not stripped.startswith('->') and not stripped.startswith('*'):
                    speaker = stripped.split(':')[0].strip()

                    # Validate dialogue text has quotes
                    dialogue_part = stripped[stripped.index(':') + 1:].strip()

                    # Check for multi-line string (starts with quote but doesn't end with one)
                    if dialogue_part.startswith('"') and dialogue_part.count('"') == 1:
                        # This is the start of a multi-line string - valid, skip further validation
                        self._in_multiline_string = True
                        # Check if speaker is defined
                        if speaker not in self.characters:
                            self._add_warning(line_num, 1, f"Speaker '{speaker}' not defined in [characters] section")
                        continue

                    # Check if this has a condition at the end
                    has_condition = False
                    if dialogue_part and '{' in dialogue_part:
                        # Check if it ends with a condition like "text" {condition}
                        match = re.match(r'^".*"\s*\{[^}]+\}$', dialogue_part)
                        if match:
                            has_condition = True

                    # Only validate quote enclosure if it's not a conditional dialogue
                    if dialogue_part and not has_condition:
                        if not (dialogue_part.startswith('"') and dialogue_part.endswith('"')):
                            self._add_error(line_num, len(stripped.split(':')[0]) + 2,
                                           "Dialogue text must be enclosed in quotes",
                                           suggestion=f'{speaker}: "{dialogue_part}"')

                    # Check if speaker is defined
                    if speaker not in self.characters:
                        self._add_warning(line_num, 1, f"Speaker '{speaker}' not defined in [characters] section")

                # Check for choices
                elif stripped.startswith('->'):
                    self._validate_choice(line_num, stripped)

                # Check for commands
                elif stripped.startswith('*'):
                    self._validate_command_syntax(line_num, stripped)

    def _validate_choice(self, line_num: int, line: str):
        """Validate choice syntax"""
        # Extract target node
        match = re.match(r'->\s*(\w+)\s*:?\s*(.*)', line)
        if not match:
            self._add_error(line_num, 1, "Invalid choice syntax",
                           suggestion="-> target_node: \"Choice text\" {optional_condition}")
            return

        target = match.group(1)
        rest = match.group(2).strip()

        if target != 'END':
            self.referenced_nodes.add(target)

        # Check for choice text
        if rest and rest.startswith(':'):
            rest = rest[1:].strip()

        if rest:
            # Check if this is ONLY a condition (allowed for flag-only transitions)
            if rest.startswith('{') and rest.endswith('}'):
                # This is a condition-only choice, which is valid
                condition = rest[1:-1]
                self._validate_condition_syntax(line_num, condition, line.index('{') + 1)
                return

            # Check for proper quotes or brackets
            if not ((rest.startswith('"') or rest.startswith('[') or rest.startswith('{'))):
                # Suggest both options for non-condition text
                suggestion = f'-> {target}: "{rest}" OR -> {target}: "[{rest}]"'
                self._add_error(line_num, line.index(rest) + 1,
                              "Choice text must be in quotes (spoken) or brackets (action)",
                              suggestion=suggestion)

            # Check for matching quotes/brackets
            if rest.startswith('"'):
                # Find the closing quote
                quote_count = rest.count('"')
                if quote_count < 2:
                    # This is the start of a multi-line string - valid
                    self._in_multiline_string = True
                    return

            elif rest.startswith('['):
                # Find the closing bracket
                if not re.search(r'\[.*?\]', rest):
                    self._add_error(line_num, line.index(rest) + 1, "Unclosed bracket in action text")

            # Check for condition after text
            if '{' in rest and not rest.startswith('{'):
                condition_match = re.search(r'\{([^}]*)\}', rest)
                if not condition_match:
                    self._add_error(line_num, rest.index('{') + 1, "Unclosed condition bracket")
                else:
                    self._validate_condition_syntax(line_num, condition_match.group(1), rest.index('{') + 1)

    def _validate_command_syntax(self, line_num: int, line: str):
        """Validate command syntax"""
        # Remove the asterisk
        command = line[1:].strip()

        # Common command patterns
        if command.startswith('set'):
            if '=' not in command:
                self._add_error(line_num, 2, "Set command requires '=' operator",
                              suggestion="*set variable_name = value")
            else:
                var_name = command[3:].split('=')[0].strip()
                self.variables_set.add(var_name)

        elif command.startswith('add_companion') or command.startswith('remove_companion'):
            # These are special companion commands, not variable adds
            parts = command.split()
            if len(parts) < 2:
                self._add_error(line_num, 2, f"Command requires companion name",
                              suggestion=f"*{parts[0]} companion_name")
            else:
                # Track the companion
                companion_name = parts[1]
                if command.startswith('add_companion'):
                    self.companions_added.add(companion_name)

        elif command.startswith('add') or command.startswith('sub'):
            if '=' not in command:
                self._add_error(line_num, 2, f"{command[:3].capitalize()} command requires '=' operator",
                              suggestion=f"*{command[:3]} variable_name = value")

        elif command.startswith('give_item') or command.startswith('remove_item'):
            parts = command.split()
            if len(parts) < 2:
                self._add_error(line_num, 2, f"Command requires item name",
                              suggestion=f"*{parts[0]} item_name")
            else:
                # Track the item
                item_name = parts[1]
                if command.startswith('give_item'):
                    self.items_given.add(item_name)

    def _validate_condition_syntax(self, line_num: int, condition: str, column: int):
        """Validate condition syntax"""
        if not condition.strip():
            self._add_error(line_num, column, "Empty condition")
            return

        # Check for has_item: checks
        has_item_matches = re.findall(r'has_item:(\w+)', condition)
        for item in has_item_matches:
            self.items_checked.add(item)

        # Check for companion: checks
        companion_matches = re.findall(r'companion:(\w+)', condition)
        for companion in companion_matches:
            self.companions_checked.add(companion)

        # Remove has_item: and companion: patterns before extracting variables
        cleaned_condition = re.sub(r'has_item:\w+', '', condition)
        cleaned_condition = re.sub(r'companion:\w+', '', cleaned_condition)

        # Extract variables from condition
        var_pattern = re.findall(r'\b[a-zA-Z_]\w*\b', cleaned_condition)

        # Filter out operators
        operators = {'true', 'false', 'and', 'or', 'not', 'has_item', 'companion'}
        variables = [v for v in var_pattern if v not in operators]

        for var in variables:
            self.variables_used.add(var)

    def _validate_references(self):
        """Validate node references"""
        # Check for undefined node references
        for ref_node in self.referenced_nodes:
            if ref_node not in self.nodes and ref_node != 'END':
                # Find where it's referenced
                for line_num, line in enumerate(self.lines, 1):
                    if f'-> {ref_node}' in line:
                        self._add_error(line_num, line.index(ref_node) + 1,
                                       f"Reference to undefined node '{ref_node}'")

        # Check for unreachable nodes
        start_node = 'start' if 'start' in self.nodes else (list(self.nodes.keys())[0] if self.nodes else None)
        if start_node:
            reachable = self._find_reachable_nodes(start_node)
            unreachable = set(self.nodes.keys()) - reachable - {start_node}

            for node in unreachable:
                self._add_warning(self.nodes[node], 1, f"Node '{node}' may be unreachable")

    def _find_reachable_nodes(self, start: str) -> Set[str]:
        """Find all nodes reachable from start"""
        reachable = set()
        to_visit = [start]

        while to_visit:
            current = to_visit.pop(0)
            if current in reachable or current == 'END':
                continue

            reachable.add(current)

            # Find choices from this node
            in_node = False
            for line in self.lines:
                stripped = line.strip()
                if stripped == f'[{current}]':
                    in_node = True
                elif stripped.startswith('[') and stripped.endswith(']'):
                    in_node = False
                elif in_node and stripped.startswith('->'):
                    match = re.match(r'->\s*(\w+)', stripped)
                    if match:
                        target = match.group(1)
                        if target != 'END' and target not in reachable:
                            to_visit.append(target)

        return reachable

    def _validate_conditions(self):
        """Validate conditions and variables"""
        # Check for variables used but never set
        undefined_vars = self.variables_used - self.variables_set

        if undefined_vars:
            for var in undefined_vars:
                # Find where it's used
                for line_num, line in enumerate(self.lines, 1):
                    if '{' in line and var in line:
                        # Make sure this isn't part of has_item: or companion:
                        if not (f'has_item:{var}' in line or f'companion:{var}' in line):
                            self._add_warning(line_num, line.index(var) + 1,
                                            f"Variable '{var}' used but never set")

        # Check for items checked but never given
        undefined_items = self.items_checked - self.items_given
        if undefined_items:
            for item in undefined_items:
                # Find where it's checked
                for line_num, line in enumerate(self.lines, 1):
                    if f'has_item:{item}' in line:
                        self._add_warning(line_num, line.index(f'has_item:{item}') + 10,
                                        f"Item '{item}' checked but never given via *give_item")

        # Check for companions checked but never added
        undefined_companions = self.companions_checked - self.companions_added
        if undefined_companions:
            for companion in undefined_companions:
                # Find where it's checked
                for line_num, line in enumerate(self.lines, 1):
                    if f'companion:{companion}' in line:
                        self._add_warning(line_num, line.index(f'companion:{companion}') + 10,
                                        f"Companion '{companion}' checked but never added via *add_companion")

    def _validate_commands(self):
        """Validate commands"""
        # Track command usage
        command_count = defaultdict(int)

        for line_num, line in enumerate(self.lines, 1):
            stripped = line.strip()
            if stripped.startswith('*'):
                cmd = stripped[1:].strip().split()[0] if stripped[1:].strip() else ""
                command_count[cmd] += 1

                # Check for common typos
                common_commands = ['set', 'add', 'sub', 'give_item', 'remove_item', 'add_companion', 'start_combat', 'start_conversation']
                if cmd and cmd not in common_commands:
                    # Find closest match
                    for correct in common_commands:
                        if self._string_similarity(cmd, correct) > 0.7:
                            self._add_warning(line_num, 2, f"Unknown command '{cmd}', did you mean '{correct}'?")
                            break

    def _validate_flow(self):
        """Validate dialogue flow"""
        # Check for nodes with no exit
        for node_id, line_num in self.nodes.items():
            # Skip if this node is part of a stacked group
            if node_id in self.stacked_nodes:
                # Check if ANY of the stacked nodes has content
                has_content = False
                for stacked_node in self.stacked_nodes[node_id]:
                    if self._node_has_choices(stacked_node):
                        has_content = True
                        break
                if has_content:
                    continue  # Skip this node, it's part of a valid stack

            # Check individual node
            if not self._node_has_choices(node_id) and node_id != 'END':
                self._add_warning(line_num, 1, f"Node '{node_id}' has no choices (dead end)")

    def _node_has_choices(self, node_id: str) -> bool:
        """Check if a node has any choices"""
        if node_id not in self.nodes:
            return False

        line_num = self.nodes[node_id]
        in_node = False

        for i, line in enumerate(self.lines[line_num-1:], line_num):
            stripped = line.strip()

            if stripped == f'[{node_id}]':
                in_node = True
            elif stripped.startswith('[') and stripped.endswith(']'):
                # Check if this is another stacked node
                other_node = stripped[1:-1]
                if node_id in self.stacked_nodes and other_node in self.stacked_nodes[node_id]:
                    continue  # Still in the same stacked group
                else:
                    break  # Different node, stop checking
            elif in_node and stripped.startswith('->'):
                return True

        return False

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity (simple ratio)"""
        if not s1 or not s2:
            return 0.0
        matches = sum(1 for c1, c2 in zip(s1, s2) if c1 == c2)
        return matches / max(len(s1), len(s2))

    def _add_error(self, line: int, column: int, message: str, suggestion: str = None):
        """Add an error"""
        context = self.lines[line-1].rstrip() if line <= len(self.lines) else None
        self.errors.append(ValidationError(line, column, 'error', message, context, suggestion))

    def _add_warning(self, line: int, column: int, message: str, suggestion: str = None):
        """Add a warning"""
        context = self.lines[line-1].rstrip() if line <= len(self.lines) else None
        self.warnings.append(ValidationError(line, column, 'warning', message, context, suggestion))

    def _report_results(self):
        """Report validation results"""
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}VALIDATION REPORT: {Colors.CYAN}{self.file_path.name}{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")

        if not self.errors and not self.warnings:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ VALIDATION PASSED - No issues found!{Colors.RESET}")
            self._print_statistics()
            return

        # Report errors
        if self.errors:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ ERRORS ({len(self.errors)}):{Colors.RESET}")
            print(f"{Colors.RED}{'━' * 60}{Colors.RESET}")
            for i, error in enumerate(sorted(self.errors, key=lambda e: e.line_number), 1):
                self._print_issue(error, 'error')
                if i < len(self.errors):  # Add separator between errors
                    print(f"{Colors.RED}{'─' * 60}{Colors.RESET}")

        # Report warnings
        if self.warnings:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  WARNINGS ({len(self.warnings)}):{Colors.RESET}")
            print(f"{Colors.YELLOW}{'━' * 60}{Colors.RESET}")
            for i, warning in enumerate(sorted(self.warnings, key=lambda w: w.line_number), 1):
                self._print_issue(warning, 'warning')
                if i < len(self.warnings):  # Add separator between warnings
                    print(f"{Colors.YELLOW}{'─' * 60}{Colors.RESET}")

        # Print summary
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        error_text = f"{Colors.RED}{len(self.errors)} error(s){Colors.RESET}"
        warning_text = f"{Colors.YELLOW}{len(self.warnings)} warning(s){Colors.RESET}"
        print(f"{Colors.BOLD}Summary:{Colors.RESET} {error_text}, {warning_text}")

        if self.errors:
            print(f"{Colors.RED}{Colors.BOLD}❌ VALIDATION FAILED{Colors.RESET}")
        else:
            print(f"{Colors.GREEN}{Colors.BOLD}✅ VALIDATION PASSED WITH WARNINGS{Colors.RESET}")

        self._print_statistics()

    def _print_issue(self, issue: ValidationError, issue_type: str = 'error'):
        """Print a single issue with context"""
        # Choose color based on issue type
        color = Colors.RED if issue_type == 'error' else Colors.YELLOW

        # Print location and message with colored line number
        print(f"\n  {color}{Colors.BOLD}Line {issue.line_number}{Colors.RESET}:{issue.column} - {Colors.BOLD}{issue.message}{Colors.RESET}")

        # Print context with error pointer
        if issue.context:
            # Format line number with color
            line_num_str = f"{color}{issue.line_number:4d}{Colors.RESET}"
            print(f"    {line_num_str} │ {issue.context}")
            # Print pointer
            pointer = " " * (10 + issue.column - 1) + f"{color}▲{Colors.RESET}"
            print(f"         │{pointer}")

        # Print suggestion if available
        if issue.suggestion:
            print(f"    {Colors.CYAN}💡 Suggestion:{Colors.RESET} {issue.suggestion}")

    def _print_statistics(self):
        """Print file statistics"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}📊 STATISTICS:{Colors.RESET}")
        print(f"{Colors.BLUE}{'─' * 40}{Colors.RESET}")
        print(f"  • Nodes: {Colors.CYAN}{len(self.nodes)}{Colors.RESET}")
        print(f"  • Characters: {Colors.CYAN}{len(self.characters)}{Colors.RESET}")
        print(f"  • Variables set: {Colors.CYAN}{len(self.variables_set)}{Colors.RESET}")
        print(f"  • Variables used: {Colors.CYAN}{len(self.variables_used)}{Colors.RESET}")
        print(f"  • Items given: {Colors.CYAN}{len(self.items_given)}{Colors.RESET}")
        print(f"  • Items checked: {Colors.CYAN}{len(self.items_checked)}{Colors.RESET}")
        print(f"  • Companions added: {Colors.CYAN}{len(self.companions_added)}{Colors.RESET}")
        print(f"  • Total lines: {Colors.CYAN}{len(self.lines)}{Colors.RESET}")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: dlg-validate <dialogue_file.dlg>")
        print("\nExample:")
        print("  dlg-validate ../../resources/dialogue/prologue/fire_nation_prologue.dlg")
        sys.exit(1)
    else:
        file_path = Path(sys.argv[1])

    validator = DialogueValidator(file_path)
    success = validator.validate()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
