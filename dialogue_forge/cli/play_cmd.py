"""
Interactive Dialogue Player - Walk through dialogues and make choices in real-time!
"""

import re
import sys
from pathlib import Path
from typing import Dict, Optional, Set

from dialogue_forge.parser.parser import DialogueParser


# ANSI color codes for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    # Text colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


class GameState:
    """Tracks game state including variables, inventory, etc."""

    def __init__(self):
        self.variables: Dict[str, any] = {}
        self.inventory: Set[str] = set()
        self.companions: Set[str] = set()
        self.visited_nodes: Set[str] = set()

    def evaluate_condition(self, condition: str, verbose: bool = False) -> bool:
        """
        Evaluate a condition string.

        Args:
            condition: The condition string to evaluate
            verbose: If True, print debug info for condition evaluation

        Returns:
            True if condition passes, False otherwise
        """
        if not condition:
            return True

        original_condition = condition

        # Replace DLG syntax with Python syntax
        condition = condition.replace("!", "not ")  # Convert ! to not
        condition = condition.replace("&&", " and ")  # Convert && to and
        condition = condition.replace("||", " or ")  # Convert || to or

        # Replace special checks
        condition = re.sub(r"has_item:(\w+)", lambda m: f"'{m.group(1)}' in inventory", condition)
        condition = re.sub(r"companion:(\w+)", lambda m: f"'{m.group(1)}' in companions", condition)

        # Create evaluation context
        context = {
            "inventory": self.inventory,
            "companions": self.companions,
            **{k: v for k, v in self.variables.items()},  # Existing variables
        }

        # Extract ALL variable names from condition and default undefined ones
        # This prevents NameError for undefined variables
        reserved_words = {
            "inventory",
            "companions",
            "in",
            "and",
            "or",
            "not",
            "True",
            "False",
            "true",
            "false",
        }
        potential_vars = re.findall(r"\b([a-zA-Z_]\w*)\b", condition)

        for var in potential_vars:
            if var not in context and var not in reserved_words:
                # Default undefined variables to False (for boolean) or 0 (for numeric comparisons)
                # Using False since it's falsy and works in numeric contexts as 0
                context[var] = False
                if verbose or "--debug" in sys.argv:
                    msg = f"[Undefined variable '{var}' defaulting to False]"
                    print(f"  {Colors.DIM}{msg}{Colors.RESET}")

        try:
            # Safely evaluate the condition
            result = eval(condition, {"__builtins__": {}}, context)

            if verbose or "--debug" in sys.argv:
                print(f"  {Colors.DIM}[Condition: {original_condition} -> {result}]{Colors.RESET}")

            return result
        except Exception as e:
            # If we can't evaluate, show error and return False (hide the option)
            if verbose or "--debug" in sys.argv:
                print(f"  {Colors.YELLOW}[Condition error: {original_condition} -> {e}]{Colors.RESET}")
            else:
                # Always warn about condition errors - these are bugs that should be fixed
                msg = f"⚠ Condition error in '{original_condition}': {e}"
                print(f"  {Colors.YELLOW}{msg}{Colors.RESET}")
            return False  # Hide options with broken conditions

    def execute_command(self, command: str):
        """Execute a game command"""
        parts = command.split()
        if not parts:
            return

        cmd = parts[0]

        if cmd == "set" and len(parts) >= 4:
            # *set variable = value
            var_name = parts[1]
            value = " ".join(parts[3:])
            if value.lower() == "true":
                self.variables[var_name] = True
            elif value.lower() == "false":
                self.variables[var_name] = False
            else:
                try:
                    self.variables[var_name] = int(value)
                except ValueError:
                    self.variables[var_name] = value

        elif cmd == "add" and len(parts) >= 4:
            # *add variable = amount
            var_name = parts[1]
            try:
                amount = int(parts[3])
                current = self.variables.get(var_name, 0)
                self.variables[var_name] = current + amount

                # Display visual feedback for harmony/discord/xp changes
                new_total = self.variables[var_name]
                if var_name == "harmony":
                    label = f"{Colors.BRIGHT_CYAN}☯️  +{amount} Harmony{Colors.RESET}"
                    print(f"\n  {label} {Colors.DIM}(Total: {new_total}){Colors.RESET}")
                elif var_name == "discord":
                    label = f"{Colors.BRIGHT_RED}💀 +{amount} Discord{Colors.RESET}"
                    print(f"\n  {label} {Colors.DIM}(Total: {new_total}){Colors.RESET}")
                elif var_name == "xp":
                    label = f"{Colors.BRIGHT_YELLOW}⭐ +{amount} XP{Colors.RESET}"
                    print(f"\n  {label} {Colors.DIM}(Total: {new_total}){Colors.RESET}")
            except ValueError:
                pass

        elif cmd == "sub" and len(parts) >= 4:
            # *sub variable = amount
            var_name = parts[1]
            try:
                amount = int(parts[3])
                current = self.variables.get(var_name, 0)
                self.variables[var_name] = current - amount

                # Display visual feedback for harmony/discord/xp changes
                new_total = self.variables[var_name]
                if var_name == "harmony":
                    label = f"{Colors.BRIGHT_CYAN}☯️  -{amount} Harmony{Colors.RESET}"
                    print(f"\n  {label} {Colors.DIM}(Total: {new_total}){Colors.RESET}")
                elif var_name == "discord":
                    label = f"{Colors.BRIGHT_RED}💀 -{amount} Discord{Colors.RESET}"
                    print(f"\n  {label} {Colors.DIM}(Total: {new_total}){Colors.RESET}")
                elif var_name == "xp":
                    label = f"{Colors.BRIGHT_YELLOW}⭐ -{amount} XP{Colors.RESET}"
                    print(f"\n  {label} {Colors.DIM}(Total: {new_total}){Colors.RESET}")
            except ValueError:
                pass

        elif cmd == "give_item" and len(parts) >= 2:
            # *give_item item_name
            item = parts[1]
            self.inventory.add(item)

        elif cmd == "remove_item" and len(parts) >= 2:
            # *remove_item item_name
            item = parts[1]
            self.inventory.discard(item)

        elif cmd == "add_companion" and len(parts) >= 2:
            # *add_companion companion_name
            companion = parts[1]
            self.companions.add(companion)

        elif cmd == "remove_companion" and len(parts) >= 2:
            # *remove_companion companion_name
            companion = parts[1]
            self.companions.discard(companion)


class DialoguePlayer:
    """Interactive dialogue player"""

    def __init__(self, dialogue_path: Path, verbose: bool = False):
        self.parser = DialogueParser()
        self.dialogue = self.parser.parse_file(dialogue_path)
        self.state = GameState()
        self.current_node: Optional[str] = None
        self.verbose = verbose or "--verbose" in sys.argv or "-v" in sys.argv

        # Get terminal width for formatting
        try:
            import shutil

            self.term_width = shutil.get_terminal_size().columns
        except OSError:
            self.term_width = 80  # Default fallback

        # Show parse-time warnings
        if self.dialogue.warnings:
            print(f"{Colors.YELLOW}⚠️  Parse warnings:{Colors.RESET}")
            for warning in self.dialogue.warnings:
                print(f"  {Colors.YELLOW}• {warning}{Colors.RESET}")
            print()

        # Validate the dialogue
        if not self.parser.validate():
            print(f"{Colors.YELLOW}⚠️  Warning: Dialogue has validation issues:{Colors.RESET}")
            for error in self.dialogue.errors:
                print(f"  {Colors.YELLOW}• {error}{Colors.RESET}")
            print()

    def format_dialogue_box(self, text: str, speaker: str, color: str, max_width: int = 60) -> str:
        """Format dialogue text in a nice box"""
        import textwrap

        # Calculate actual max width based on terminal size
        padding = 4  # 2 chars on each side for box borders
        actual_max = min(max_width, self.term_width - padding - 4)  # Extra space for margins

        # Wrap text
        lines = []
        for paragraph in text.split("\n"):
            if paragraph:
                lines.extend(textwrap.wrap(paragraph, width=actual_max))
            else:
                lines.append("")

        # Find the longest line for box width
        box_width = max(len(line) for line in lines) if lines else 20
        box_width = max(box_width, len(speaker) + 2)  # Ensure speaker name fits

        # Build the box
        result = []
        result.append(f"\n  {color}╭─ {speaker} {'─' * (box_width - len(speaker) - 1)}╮{Colors.RESET}")
        for line in lines:
            padded_line = line.ljust(box_width)
            result.append(f"  {color}│{Colors.RESET} {padded_line} {color}│{Colors.RESET}")
        result.append(f"  {color}╰{'─' * (box_width + 2)}╯{Colors.RESET}")

        return "\n".join(result)

    def play(self):
        """Start playing the dialogue"""
        print(f"\n{Colors.BRIGHT_CYAN}{'=' * 70}{Colors.RESET}")
        print(f"{Colors.BRIGHT_YELLOW}{Colors.BOLD}🎭 INTERACTIVE DIALOGUE PLAYER{Colors.RESET}")
        if self.verbose:
            print(f"{Colors.BRIGHT_MAGENTA}  [VERBOSE MODE - showing condition evaluations]{Colors.RESET}")
        print(f"{Colors.BRIGHT_CYAN}{'=' * 70}{Colors.RESET}")
        print(f"\n{Colors.BRIGHT_WHITE}Controls:{Colors.RESET}")
        print(f"  {Colors.CYAN}•{Colors.RESET} Enter the number to select a choice")
        quit_cmd = f"{Colors.YELLOW}'quit'{Colors.RESET}"
        exit_cmd = f"{Colors.YELLOW}'exit'{Colors.RESET}"
        print(f"  {Colors.CYAN}•{Colors.RESET} Type {quit_cmd} or {exit_cmd} to stop")
        print(f"  {Colors.CYAN}•{Colors.RESET} Type {Colors.YELLOW}'state'{Colors.RESET} to see current game state")
        print(f"  {Colors.CYAN}•{Colors.RESET} Type {Colors.YELLOW}'save'{Colors.RESET} to save current position")
        print(f"  {Colors.CYAN}•{Colors.RESET} Type {Colors.YELLOW}'load'{Colors.RESET} to load saved position")
        print(f"\n{Colors.BRIGHT_CYAN}{'=' * 70}{Colors.RESET}\n")

        # Execute initial state commands if any
        if self.dialogue.initial_state:
            if self.verbose:
                print(f"{Colors.BRIGHT_MAGENTA}Executing [state] section commands...{Colors.RESET}")
            for cmd in self.dialogue.initial_state:
                self.state.execute_command(cmd)
            if self.verbose:
                print(f"{Colors.BRIGHT_MAGENTA}Initial state set up complete.{Colors.RESET}\n")

        # Start from the start node
        self.current_node = self.dialogue.start_node

        while self.current_node and self.current_node != "END":
            self.play_node(self.current_node)

            # Check if we've reached a dead end
            if self.current_node in self.dialogue.nodes:
                node = self.dialogue.nodes[self.current_node]
                if not node.choices:
                    print(f"\n{Colors.BRIGHT_CYAN}{'=' * 70}{Colors.RESET}")
                    print(f"{Colors.BRIGHT_YELLOW}📍 You've reached the end of this path.{Colors.RESET}")
                    print(f"{Colors.BRIGHT_CYAN}{'=' * 70}{Colors.RESET}")
                    break

        if self.current_node == "END":
            print(f"\n{Colors.BRIGHT_CYAN}{'=' * 70}{Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}{Colors.BOLD}🎬 THE END{Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}{'=' * 70}{Colors.RESET}")

        self.show_final_state()

    def play_node(self, node_id: str):
        """Play a single node"""
        if node_id not in self.dialogue.nodes:
            print(f"{Colors.RED}❌ Error: Node '{node_id}' not found!{Colors.RESET}")
            self.current_node = None
            return

        node = self.dialogue.nodes[node_id]
        self.state.visited_nodes.add(node_id)

        # Show node header if in debug mode
        if "--debug" in sys.argv:
            print(f"\n{Colors.DIM}[{node_id}]{Colors.RESET}")

        # Execute commands at the start of the node
        for command in node.commands:
            self.state.execute_command(command)
            if "--debug" in sys.argv:
                print(f"  {Colors.DIM}*{command}{Colors.RESET}")

        # Display dialogue lines (filter by condition)
        for line in node.lines:
            # Only show lines whose conditions are met (or have no condition)
            if not self.state.evaluate_condition(line.condition, verbose=self.verbose):
                continue

            speaker = line.speaker
            text = line.text
            speaker_name = self.dialogue.characters.get(speaker, speaker)

            # Format based on speaker type
            if speaker == "narrator":
                # Wrap narrator text properly to avoid mid-word breaks
                import textwrap

                max_width = min(70, self.term_width - 6)  # Account for emoji and indent

                # Process each paragraph separately but display as continuous text
                paragraphs = text.split("\n")
                for para in paragraphs:
                    if para:
                        wrapped = textwrap.fill(para, width=max_width, break_long_words=False)
                        print(f"\n{Colors.ITALIC}{Colors.BRIGHT_BLACK}📖 {wrapped}{Colors.RESET}")
            elif speaker == "hero" or speaker == "[PlayerName]":
                # Player dialogue in green box
                print(self.format_dialogue_box(text, "You", Colors.BRIGHT_GREEN))
            else:
                # NPC dialogue in cyan box
                print(self.format_dialogue_box(text, speaker_name, Colors.BRIGHT_CYAN))

        # Separate GOTOs (no text) from player choices (with text)
        # GOTOs are automatic transitions, choices are presented to the player
        gotos = []
        player_choices = []
        for choice in node.choices:
            if choice.text:
                # This is a player choice - only include if condition passes
                if self.state.evaluate_condition(choice.condition, verbose=self.verbose):
                    player_choices.append(choice)
            else:
                # This is a GOTO (automatic transition)
                gotos.append(choice)

        # First, check GOTOs - find first one with true condition (or no condition)
        for goto in gotos:
            if self.state.evaluate_condition(goto.condition, verbose=self.verbose):
                # Auto-transition to this target
                if self.verbose:
                    cond_str = f" (condition: {goto.condition})" if goto.condition else ""
                    print(f"{Colors.DIM}[Auto-transition → {goto.target}{cond_str}]{Colors.RESET}")
                self.current_node = goto.target
                return

        # No GOTOs matched, check if we have player choices
        if not player_choices:
            # No choices available, this is a dead end
            self.current_node = None
            return

        # Display player choices
        print(f"\n{Colors.DIM}{'─' * 50}{Colors.RESET}")
        for i, choice in enumerate(player_choices, 1):
            cond_indicator = f" {Colors.BRIGHT_YELLOW}✓{Colors.RESET}" if choice.condition else ""
            prefix = f"  {Colors.BRIGHT_YELLOW}[{i}]{Colors.RESET}"
            text = f"{Colors.YELLOW}{choice.text}{Colors.RESET}"
            print(f"{prefix} {text}{cond_indicator}")

        # Get player input
        while True:
            try:
                user_input = input(f"\n{Colors.BRIGHT_MAGENTA}>{Colors.RESET} ").strip().lower()

                if user_input in ["quit", "exit", "q"]:
                    print("\n👋 Thanks for playing!")
                    self.current_node = None
                    return

                elif user_input == "state":
                    self.show_state()
                    continue

                elif user_input == "save":
                    self.save_game()
                    continue

                elif user_input == "load":
                    self.load_game()
                    return

                # Try to parse as choice number
                choice_num = int(user_input)
                if 1 <= choice_num <= len(player_choices):
                    selected = player_choices[choice_num - 1]

                    # Show player's choice in a dialogue box
                    if selected.text:
                        print(self.format_dialogue_box(selected.text, "You", Colors.BRIGHT_GREEN))

                    # Move to target node
                    self.current_node = selected.target
                    return
                else:
                    msg = "❌ Invalid choice. Please enter a number from the list."
                    print(f"{Colors.RED}{msg}{Colors.RESET}")

            except ValueError:
                print(f"{Colors.RED}❌ Please enter a valid number or command.{Colors.RESET}")
            except KeyboardInterrupt:
                print(f"\n\n{Colors.BRIGHT_YELLOW}👋 Thanks for playing!{Colors.RESET}")
                self.current_node = None
                return

    def show_state(self):
        """Display current game state"""
        print(f"\n{Colors.BRIGHT_BLUE}{'=' * 50}{Colors.RESET}")
        print(f"{Colors.BRIGHT_BLUE}📊 CURRENT GAME STATE{Colors.RESET}")
        print(f"{Colors.BRIGHT_BLUE}{'=' * 50}{Colors.RESET}")

        # Show key stats prominently
        xp = self.state.variables.get("xp", 0)
        harmony = self.state.variables.get("harmony", 0)
        discord = self.state.variables.get("discord", 0)

        print("\n⚔️  Character Stats:")
        print(f"  {Colors.BRIGHT_YELLOW}⭐ Experience:{Colors.RESET} {xp}")
        print(f"  {Colors.BRIGHT_CYAN}☯️  Harmony:{Colors.RESET} {harmony}")
        print(f"  {Colors.BRIGHT_RED}💀 Discord:{Colors.RESET} {discord}")

        print("\n🎒 Inventory:")
        if self.state.inventory:
            for item in sorted(self.state.inventory):
                print(f"  • {item}")
        else:
            print("  (empty)")

        print("\n👥 Companions:")
        if self.state.companions:
            for companion in sorted(self.state.companions):
                print(f"  • {companion}")
        else:
            print("  (none)")

        print("\n📈 Other Variables:")
        other_vars = {k: v for k, v in self.state.variables.items() if k not in ["xp", "harmony", "discord"]}
        if other_vars:
            for var, value in sorted(other_vars.items()):
                print(f"  • {var}: {value}")
        else:
            print("  (none)")

        print("\n📍 Current Node: " + (self.current_node or "None"))
        print(f"📝 Nodes Visited: {len(self.state.visited_nodes)}")

        print("=" * 50)

    def show_final_state(self):
        """Show final game state summary"""
        print(f"\n{Colors.BRIGHT_MAGENTA}{'=' * 70}{Colors.RESET}")
        print(f"{Colors.BRIGHT_MAGENTA}{Colors.BOLD}📊 FINAL STATS{Colors.RESET}")
        print(f"{Colors.BRIGHT_MAGENTA}{'=' * 70}{Colors.RESET}")

        print(f"\n📝 Nodes Visited: {len(self.state.visited_nodes)}/{len(self.dialogue.nodes)}")

        # Show XP earned
        xp = self.state.variables.get("xp", 0)
        if xp > 0:
            print(f"\n{Colors.BRIGHT_YELLOW}⭐ Total Experience Earned: {xp}{Colors.RESET}")

        # Calculate alignment if present
        harmony = self.state.variables.get("harmony", 0)
        discord = self.state.variables.get("discord", 0)
        if harmony or discord:
            print("\n⚖️  Alignment:")
            print(f"  {Colors.BRIGHT_CYAN}• Harmony: {harmony}{Colors.RESET}")
            print(f"  {Colors.BRIGHT_RED}• Discord: {discord}{Colors.RESET}")
            if harmony > discord:
                print(f"  → {Colors.BRIGHT_CYAN}You leaned toward harmony and peace{Colors.RESET}")
            elif discord > harmony:
                print(f"  → {Colors.BRIGHT_RED}You leaned toward discord and chaos{Colors.RESET}")
            else:
                print("  → You maintained perfect balance")

        # Show final inventory
        if self.state.inventory:
            print(f"\n🎒 Final Inventory: {', '.join(sorted(self.state.inventory))}")

        # Show companions
        if self.state.companions:
            print(f"\n👥 Final Party: {', '.join(sorted(self.state.companions))}")

        print("=" * 70)

    def save_game(self):
        """Save current game state"""
        import json
        import os
        from datetime import datetime

        # Create saves directory relative to package location
        saves_dir = Path(__file__).parent.parent.parent / "saves"
        os.makedirs(saves_dir, exist_ok=True)

        # Get save name from user
        print(f"\n{Colors.BRIGHT_CYAN}Enter save name (or press Enter for timestamp):{Colors.RESET}")
        save_name = input(f"{Colors.BRIGHT_MAGENTA}>{Colors.RESET} ").strip()

        if not save_name:
            save_name = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Sanitize filename
        save_name = "".join(c for c in save_name if c.isalnum() or c in (" ", "-", "_")).rstrip()
        save_file = saves_dir / f"{save_name}.json"

        save_data = {
            "node": self.current_node,
            "timestamp": datetime.now().isoformat(),
            "state": {
                "variables": dict(self.state.variables),
                "inventory": list(self.state.inventory),
                "companions": list(self.state.companions),
                "visited": list(self.state.visited_nodes),
            },
        }

        with open(save_file, "w") as f:
            json.dump(save_data, f, indent=2)

        print(f"{Colors.BRIGHT_GREEN}💾 Game saved as '{save_name}'!{Colors.RESET}")

    def load_game(self):
        """Load saved game state"""
        import json
        import os
        from datetime import datetime

        try:
            # List available saves relative to package location
            saves_dir = Path(__file__).parent.parent.parent / "saves"
            if not saves_dir.exists():
                print(f"{Colors.RED}❌ No saves directory found!{Colors.RESET}")
                return

            saves = [f for f in os.listdir(saves_dir) if f.endswith(".json")]
            if not saves:
                print(f"{Colors.RED}❌ No save files found!{Colors.RESET}")
                return

            # Display saves
            print(f"\n{Colors.BRIGHT_CYAN}{'=' * 50}{Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}💾 AVAILABLE SAVES{Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}{'=' * 50}{Colors.RESET}")

            save_info = []
            for i, save_file in enumerate(saves, 1):
                try:
                    with open(f"{saves_dir}/{save_file}", "r") as f:
                        data = json.load(f)
                        timestamp = data.get("timestamp", "Unknown time")
                        node = data.get("node", "Unknown location")

                        # Parse timestamp
                        if timestamp != "Unknown time":
                            dt = datetime.fromisoformat(timestamp)
                            timestamp = dt.strftime("%Y-%m-%d %H:%M")

                        save_name = save_file[:-5]  # Remove .json
                        save_info.append((save_file, save_name, timestamp, node))

                        prefix = f"  {Colors.BRIGHT_YELLOW}[{i}]{Colors.RESET}"
                        name = f"{Colors.YELLOW}{save_name}{Colors.RESET}"
                        print(f"{prefix} {name}")
                        print(f"      {Colors.DIM}📅 {timestamp} | 📍 {node}{Colors.RESET}")
                except (json.JSONDecodeError, KeyError, OSError):
                    continue

            if not save_info:
                print(f"{Colors.RED}❌ No valid save files found!{Colors.RESET}")
                return

            # Get choice
            print(f"\n{Colors.BRIGHT_CYAN}Select save to load (or 'cancel'):{Colors.RESET}")
            choice = input(f"{Colors.BRIGHT_MAGENTA}>{Colors.RESET} ").strip().lower()

            if choice == "cancel":
                return

            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(save_info):
                    save_file = save_info[choice_num - 1][0]

                    with open(f"{saves_dir}/{save_file}", "r") as f:
                        save_data = json.load(f)

                    self.current_node = save_data["node"]
                    self.state.variables = save_data["state"]["variables"]
                    self.state.inventory = set(save_data["state"]["inventory"])
                    self.state.companions = set(save_data["state"]["companions"])
                    self.state.visited_nodes = set(save_data["state"]["visited"])

                    loaded_name = save_info[choice_num - 1][1]
                    print(f"{Colors.BRIGHT_GREEN}💾 Game loaded from '{loaded_name}'!{Colors.RESET}")
                else:
                    print(f"{Colors.RED}❌ Invalid choice!{Colors.RESET}")
            except ValueError:
                print(f"{Colors.RED}❌ Please enter a valid number!{Colors.RESET}")

        except Exception as e:
            print(f"{Colors.RED}❌ Error loading save: {e}{Colors.RESET}")
            if "--debug" in sys.argv:
                import traceback

                traceback.print_exc()


def select_dialogue_file():
    """Interactive dialogue file selection"""
    # Look for dialogues in the resources folder relative to repo root
    repo_root = Path(__file__).parent.parent.parent
    dialogues_dir = repo_root / "resources" / "dialogue"

    if not dialogues_dir.exists():
        print(f"{Colors.RED}❌ No dialogues directory found at {dialogues_dir}!{Colors.RESET}")
        return None

    # Find all .dlg files, excluding test folder
    dlg_files = []
    for path in dialogues_dir.rglob("*.dlg"):
        # Skip files in test folder
        if "test" not in path.parts:
            # Store relative path from dialogues folder
            rel_path = path.relative_to(dialogues_dir)
            dlg_files.append((path, rel_path))

    if not dlg_files:
        print(f"{Colors.RED}❌ No dialogue files found!{Colors.RESET}")
        return None

    # Sort by directory then filename
    dlg_files.sort(key=lambda x: (x[1].parent, x[1].name))

    # Display file list
    print(f"\n{Colors.BRIGHT_CYAN}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BRIGHT_CYAN}📚 AVAILABLE DIALOGUES{Colors.RESET}")
    print(f"{Colors.BRIGHT_CYAN}{'=' * 60}{Colors.RESET}\n")

    current_section = None
    for i, (full_path, rel_path) in enumerate(dlg_files, 1):
        # Group by directory
        section = rel_path.parent
        if section != current_section:
            current_section = section
            section_name = str(section) if str(section) != "." else "root"
            print(f"\n{Colors.BRIGHT_YELLOW}📁 {section_name}/{Colors.RESET}")

        # Display file
        file_name = rel_path.name
        # Remove .dlg extension for cleaner display
        display_name = file_name[:-4]
        print(f"  {Colors.YELLOW}[{i:2d}]{Colors.RESET} {display_name}")

    # Get user choice
    print(f"\n{Colors.BRIGHT_CYAN}Select dialogue number (or 'q' to quit):{Colors.RESET}")

    while True:
        try:
            choice = input(f"{Colors.BRIGHT_MAGENTA}>{Colors.RESET} ").strip().lower()

            if choice == "q" or choice == "quit":
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(dlg_files):
                return dlg_files[choice_num - 1][0]
            else:
                print(f"{Colors.RED}❌ Please enter a number between 1 and {len(dlg_files)}{Colors.RESET}")
        except ValueError:
            print(f"{Colors.RED}❌ Please enter a valid number or 'q' to quit{Colors.RESET}")
        except KeyboardInterrupt:
            print("\n")
            return None


def main():
    """Main entry point"""
    dialogue_path = None

    # Check if file was provided as argument
    if len(sys.argv) >= 2 and not sys.argv[1].startswith("--"):
        dialogue_path = Path(sys.argv[1])
    else:
        # Interactive mode - let user select a file
        dialogue_path = select_dialogue_file()

        if dialogue_path is None:
            print(f"{Colors.BRIGHT_YELLOW}👋 Goodbye!{Colors.RESET}")
            sys.exit(0)

    if not dialogue_path.exists():
        print(f"❌ File not found: {dialogue_path}")
        sys.exit(1)

    if not dialogue_path.suffix == ".dlg":
        print("⚠️  Warning: File doesn't have .dlg extension")

    try:
        player = DialoguePlayer(dialogue_path)
        player.play()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if "--debug" in sys.argv:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
