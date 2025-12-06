"""
Enhanced validation script for .dlg dialogue files with precise error reporting.

Uses DialogueParser for parsing, then performs additional semantic validation.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from dialogue_forge.parser.parser import Dialogue, DialogueParser


# ANSI color codes for terminal output
class Colors:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"


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
    """Enhanced validator for .dlg files with precise error reporting.

    Uses DialogueParser for initial parsing, then performs semantic validation.
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lines: List[str] = []
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

        # Parsed dialogue (from DialogueParser)
        self.dialogue: Optional[Dialogue] = None

        # Tracking for semantic validation
        self.variables_set: Set[str] = set()
        self.variables_used: Set[str] = set()
        self.items_given: Set[str] = set()
        self.items_checked: Set[str] = set()
        self.companions_added: Set[str] = set()
        self.companions_checked: Set[str] = set()

        # Node tracking
        self.stacked_nodes: Dict[str, List[str]] = {}

    def validate(self) -> bool:
        """Main validation method"""
        if not self.file_path.exists():
            print(f"❌ File not found: {self.file_path}")
            return False

        try:
            # Read file for context in error messages
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.lines = f.readlines()

            # Step 1: Parse file using DialogueParser
            parser = DialogueParser()
            self.dialogue = parser.parse_file(self.file_path)
            parser.validate()

            # Convert parser errors/warnings to our format
            self._convert_parser_issues()

            # Step 2: Perform semantic validation on parsed data
            self._validate_semantic()

            # Step 3: Track stacked nodes and validate flow
            self._detect_stacked_nodes()
            self._validate_flow()

            # Report results
            self._report_results()

            return len(self.errors) == 0

        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return False

    def _convert_parser_issues(self):
        """Convert parser errors/warnings to ValidationError format"""
        for error in self.dialogue.errors:
            # Try to extract line number from error message
            line_match = re.search(r"Line (\d+)", error)
            line_num = int(line_match.group(1)) if line_match else 1
            self._add_error(line_num, 1, error)

        for warning in self.dialogue.warnings:
            line_match = re.search(r"Line (\d+)", warning)
            line_num = int(line_match.group(1)) if line_match else 1
            self._add_warning(line_num, 1, warning)

    def _validate_semantic(self):
        """Perform semantic validation on parsed dialogue"""
        if not self.dialogue:
            return

        # Process initial state commands
        for cmd in self.dialogue.initial_state:
            self._process_command(cmd, 0)

        # Process all nodes
        for node_id, node in self.dialogue.nodes.items():
            # Process commands
            for cmd in node.commands:
                self._process_command(cmd, node.line_number)

            # Process dialogue lines for conditions
            for line in node.lines:
                if line.condition:
                    self._process_condition(line.condition, line.line_number)

            # Process choices
            for choice in node.choices:
                if choice.condition:
                    self._process_condition(choice.condition, choice.line_number)

        # Check for undefined variables
        self._check_undefined_variables()

        # Check for undefined items
        self._check_undefined_items()

        # Check for undefined companions
        self._check_undefined_companions()

    def _process_command(self, command: str, line_num: int):
        """Process a command and track variables/items/companions"""
        parts = command.split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == "set":
            # *set variable = value
            if "=" in command:
                var_name = command[3:].split("=")[0].strip()
                self.variables_set.add(var_name)

        elif cmd in ("add", "sub"):
            # *add variable = value
            if "=" in command:
                var_name = command[len(cmd) :].split("=")[0].strip()
                self.variables_set.add(var_name)

        elif cmd == "give_item":
            if len(parts) >= 2:
                self.items_given.add(parts[1])

        elif cmd == "remove_item":
            if len(parts) >= 2:
                # Removing implies it should exist
                pass

        elif cmd == "add_companion":
            if len(parts) >= 2:
                self.companions_added.add(parts[1])

    def _process_condition(self, condition: str, line_num: int):
        """Process a condition and track variable/item/companion usage"""
        # Track has_item checks
        for match in re.finditer(r"has_item:(\w+)", condition):
            self.items_checked.add(match.group(1))

        # Track companion checks
        for match in re.finditer(r"companion:(\w+)", condition):
            self.companions_checked.add(match.group(1))

        # Extract variables from condition
        # Remove has_item: and companion: patterns first
        cleaned = re.sub(r"has_item:\w+", "", condition)
        cleaned = re.sub(r"companion:\w+", "", cleaned)

        # Find variable names (excluding operators)
        operators = {"true", "false", "and", "or", "not", "has_item", "companion"}
        for match in re.finditer(r"\b([a-zA-Z_]\w*)\b", cleaned):
            var = match.group(1)
            if var not in operators:
                self.variables_used.add(var)

    def _check_undefined_variables(self):
        """Check for variables used but never set"""
        undefined = self.variables_used - self.variables_set

        for var in undefined:
            # Find where it's used
            for line_num, line in enumerate(self.lines, 1):
                if "{" in line and var in line:
                    # Make sure it's not part of has_item: or companion:
                    if not (f"has_item:{var}" in line or f"companion:{var}" in line):
                        # Make sure it's actually in a condition, not just in text
                        if re.search(r"\{[^}]*\b" + re.escape(var) + r"\b[^}]*\}", line):
                            self._add_warning(
                                line_num,
                                line.index(var) + 1,
                                f"Variable '{var}' used but never set",
                            )
                            break

    def _check_undefined_items(self):
        """Check for items checked but never given"""
        undefined = self.items_checked - self.items_given

        for item in undefined:
            for line_num, line in enumerate(self.lines, 1):
                if f"has_item:{item}" in line:
                    col = line.index(f"has_item:{item}") + 10
                    self._add_warning(line_num, col, f"Item '{item}' checked but never given via *give_item")
                    break

    def _check_undefined_companions(self):
        """Check for companions checked but never added"""
        undefined = self.companions_checked - self.companions_added

        for companion in undefined:
            for line_num, line in enumerate(self.lines, 1):
                if f"companion:{companion}" in line:
                    col = line.index(f"companion:{companion}") + 10
                    self._add_warning(
                        line_num,
                        col,
                        f"Companion '{companion}' checked but never added via *add_companion",
                    )
                    break

    def _detect_stacked_nodes(self):
        """Detect stacked node labels (multiple consecutive [node] labels)"""
        if not self.dialogue:
            return

        current_stack = []
        prev_was_node = False

        for line_num, line in enumerate(self.lines, 1):
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]"):
                node_id = stripped[1:-1]
                if node_id not in ("characters", "state") and node_id in self.dialogue.nodes:
                    if prev_was_node:
                        current_stack.append(node_id)
                    else:
                        # Save previous stack if it had multiple nodes
                        if len(current_stack) > 1:
                            for n in current_stack:
                                self.stacked_nodes[n] = current_stack.copy()
                        current_stack = [node_id]
                    prev_was_node = True
                else:
                    prev_was_node = False
            else:
                if stripped and not stripped.startswith("#"):
                    # Save stack if it had multiple nodes
                    if len(current_stack) > 1:
                        for n in current_stack:
                            self.stacked_nodes[n] = current_stack.copy()
                    current_stack = []
                    prev_was_node = False

    def _validate_flow(self):
        """Validate dialogue flow - check for dead ends"""
        if not self.dialogue:
            return

        for node_id, node in self.dialogue.nodes.items():
            # Skip if part of a stacked group that has choices
            if node_id in self.stacked_nodes:
                has_choices = False
                for stacked_id in self.stacked_nodes[node_id]:
                    if stacked_id in self.dialogue.nodes:
                        if self.dialogue.nodes[stacked_id].choices:
                            has_choices = True
                            break
                if has_choices:
                    continue

            # Check if node has no choices (dead end)
            if not node.choices:
                self._add_warning(node.line_number, 1, f"Node '{node_id}' has no choices (dead end)")

    def _add_error(self, line: int, column: int, message: str, suggestion: str = None):
        """Add an error"""
        context = self.lines[line - 1].rstrip() if line <= len(self.lines) else None
        self.errors.append(ValidationError(line, column, "error", message, context, suggestion))

    def _add_warning(self, line: int, column: int, message: str, suggestion: str = None):
        """Add a warning"""
        context = self.lines[line - 1].rstrip() if line <= len(self.lines) else None
        self.warnings.append(ValidationError(line, column, "warning", message, context, suggestion))

    def _report_results(self):
        """Report validation results"""
        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}VALIDATION REPORT: {Colors.CYAN}{self.file_path.name}{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}")

        if not self.errors and not self.warnings:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ VALIDATION PASSED - No issues found!{Colors.RESET}")
            self._print_statistics()
            return

        # Report errors
        if self.errors:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ ERRORS ({len(self.errors)}):{Colors.RESET}")
            print(f"{Colors.RED}{'━' * 60}{Colors.RESET}")
            for i, error in enumerate(sorted(self.errors, key=lambda e: e.line_number), 1):
                self._print_issue(error, "error")
                if i < len(self.errors):
                    print(f"{Colors.RED}{'─' * 60}{Colors.RESET}")

        # Report warnings
        if self.warnings:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  WARNINGS ({len(self.warnings)}):{Colors.RESET}")
            print(f"{Colors.YELLOW}{'━' * 60}{Colors.RESET}")
            for i, warning in enumerate(sorted(self.warnings, key=lambda w: w.line_number), 1):
                self._print_issue(warning, "warning")
                if i < len(self.warnings):
                    print(f"{Colors.YELLOW}{'─' * 60}{Colors.RESET}")

        # Print summary
        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        error_text = f"{Colors.RED}{len(self.errors)} error(s){Colors.RESET}"
        warning_text = f"{Colors.YELLOW}{len(self.warnings)} warning(s){Colors.RESET}"
        print(f"{Colors.BOLD}Summary:{Colors.RESET} {error_text}, {warning_text}")

        if self.errors:
            print(f"{Colors.RED}{Colors.BOLD}❌ VALIDATION FAILED{Colors.RESET}")
        else:
            print(f"{Colors.GREEN}{Colors.BOLD}✅ VALIDATION PASSED WITH WARNINGS{Colors.RESET}")

        self._print_statistics()

    def _print_issue(self, issue: ValidationError, issue_type: str = "error"):
        """Print a single issue with context"""
        color = Colors.RED if issue_type == "error" else Colors.YELLOW

        line_info = f"{color}{Colors.BOLD}Line {issue.line_number}{Colors.RESET}:{issue.column}"
        msg = f"{Colors.BOLD}{issue.message}{Colors.RESET}"
        print(f"\n  {line_info} - {msg}")

        if issue.context:
            line_num_str = f"{color}{issue.line_number:4d}{Colors.RESET}"
            print(f"    {line_num_str} │ {issue.context}")
            pointer = " " * (10 + issue.column - 1) + f"{color}▲{Colors.RESET}"
            print(f"         │{pointer}")

        if issue.suggestion:
            print(f"    {Colors.CYAN}💡 Suggestion:{Colors.RESET} {issue.suggestion}")

    def _print_statistics(self):
        """Print file statistics"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}📊 STATISTICS:{Colors.RESET}")
        print(f"{Colors.BLUE}{'─' * 40}{Colors.RESET}")

        num_nodes = len(self.dialogue.nodes) if self.dialogue else 0
        num_chars = len(self.dialogue.characters) if self.dialogue else 0

        print(f"  • Nodes: {Colors.CYAN}{num_nodes}{Colors.RESET}")
        print(f"  • Characters: {Colors.CYAN}{num_chars}{Colors.RESET}")
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
