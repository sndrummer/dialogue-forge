"""
Flask web application for Dialogue Forge - Visual Dialogue Editor
"""

import random
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import Flask, jsonify, render_template, request

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dialogue_forge.parser.parser import DialogueParser


class WebGameState:
    """
    Simplified game state for web pathfinding.
    Mirrors the CLI GameState but focused on state computation.
    """

    def __init__(self):
        self.variables: Dict[str, Any] = {}
        self.inventory: Set[str] = set()
        self.companions: Set[str] = set()

    def copy(self) -> "WebGameState":
        """Create a deep copy of the state"""
        new_state = WebGameState()
        new_state.variables = dict(self.variables)
        new_state.inventory = set(self.inventory)
        new_state.companions = set(self.companions)
        return new_state

    def to_dict(self) -> dict:
        """Convert state to JSON-serializable dict"""
        return {
            "variables": dict(self.variables),
            "inventory": list(self.inventory),
            "companions": list(self.companions),
        }

    def evaluate_condition(self, condition: str) -> bool:
        """Evaluate a condition string"""
        if not condition:
            return True

        # Replace DLG syntax with Python syntax
        condition = condition.replace("!", "not ")
        condition = condition.replace("&&", " and ")
        condition = condition.replace("||", " or ")

        # Replace special checks
        condition = re.sub(r"has_item:(\w+)", lambda m: f"'{m.group(1)}' in inventory", condition)
        condition = re.sub(r"companion:(\w+)", lambda m: f"'{m.group(1)}' in companions", condition)

        # Create evaluation context
        context = {
            "inventory": self.inventory,
            "companions": self.companions,
            **{k: v for k, v in self.variables.items()},
        }

        # For undefined variables in 'not' checks, default to False
        if "not " in condition:
            not_vars = re.findall(r"not\s+(\w+)", condition)
            for var in not_vars:
                if var not in context and var not in ["inventory", "companions"]:
                    context[var] = False

        try:
            return eval(condition, {"__builtins__": {}}, context)
        except Exception:
            return False

    def execute_command(self, command: str):
        """Execute a game command"""
        parts = command.split()
        if not parts:
            return

        cmd = parts[0]

        if cmd == "set" and len(parts) >= 4:
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
            var_name = parts[1]
            try:
                amount = int(parts[3])
                current = self.variables.get(var_name, 0)
                self.variables[var_name] = current + amount
            except ValueError:
                pass

        elif cmd == "sub" and len(parts) >= 4:
            var_name = parts[1]
            try:
                amount = int(parts[3])
                current = self.variables.get(var_name, 0)
                self.variables[var_name] = current - amount
            except ValueError:
                pass

        elif cmd == "give_item" and len(parts) >= 2:
            self.inventory.add(parts[1])

        elif cmd == "remove_item" and len(parts) >= 2:
            self.inventory.discard(parts[1])

        elif cmd == "add_companion" and len(parts) >= 2:
            self.companions.add(parts[1])

        elif cmd == "remove_companion" and len(parts) >= 2:
            self.companions.discard(parts[1])


def find_valid_path_to_node(dialogue, target_node: str) -> Tuple[Optional[List[str]], Optional[WebGameState]]:
    """
    Find a valid path from start to target_node using BFS.
    Returns (path, final_state) or (None, None) if unreachable.

    The algorithm simulates game state as it traverses, only following
    choices whose conditions are satisfied.
    """
    # Create initial state and execute [state] section commands
    initial_state = WebGameState()
    for cmd in dialogue.initial_state:
        initial_state.execute_command(cmd)

    if target_node == dialogue.start_node:
        # Already at start, return path with initial state
        state = initial_state.copy()
        # Execute start node commands
        if target_node in dialogue.nodes:
            for cmd in dialogue.nodes[target_node].commands:
                state.execute_command(cmd)
        return [target_node], state

    if target_node not in dialogue.nodes and target_node != "END":
        return None, None

    # BFS: queue contains (current_node, path, state)
    # Execute commands at start node
    if dialogue.start_node in dialogue.nodes:
        for cmd in dialogue.nodes[dialogue.start_node].commands:
            initial_state.execute_command(cmd)

    queue = deque([(dialogue.start_node, [dialogue.start_node], initial_state)])
    visited = {(dialogue.start_node, frozenset(), frozenset(), frozenset(initial_state.variables.items()))}

    while queue:
        current_node, path, state = queue.popleft()

        if current_node == target_node:
            return path, state

        if current_node not in dialogue.nodes:
            continue

        node = dialogue.nodes[current_node]

        # Try each choice
        for choice in node.choices:
            # Check if condition is satisfied
            if not state.evaluate_condition(choice.condition):
                continue

            next_node = choice.target

            if next_node == "END":
                if target_node == "END":
                    return path + ["END"], state
                continue

            if next_node not in dialogue.nodes:
                continue

            # Create new state and execute commands at next node
            new_state = state.copy()
            for cmd in dialogue.nodes[next_node].commands:
                new_state.execute_command(cmd)

            # Create state signature for visited check
            state_sig = (
                next_node,
                frozenset(new_state.inventory),
                frozenset(new_state.companions),
                frozenset(new_state.variables.items()),
            )

            if state_sig not in visited:
                visited.add(state_sig)
                queue.append((next_node, path + [next_node], new_state))

    # No path found - target might be unreachable
    # Return path to target anyway with empty state (for testing purposes)
    return None, None


def find_random_path_to_node(dialogue, target_node: str) -> Tuple[Optional[List[str]], Optional[WebGameState]]:
    """
    Find a random valid path from start to target_node using randomized DFS.
    Returns (path, final_state) or (None, None) if unreachable.

    Unlike BFS, this shuffles choices at each node to explore a random path.
    Equal probability for each valid choice at every branch point.
    """
    initial_state = WebGameState()
    for cmd in dialogue.initial_state:
        initial_state.execute_command(cmd)

    if target_node == dialogue.start_node:
        state = initial_state.copy()
        if target_node in dialogue.nodes:
            for cmd in dialogue.nodes[target_node].commands:
                state.execute_command(cmd)
        return [target_node], state

    if target_node not in dialogue.nodes and target_node != "END":
        return None, None

    # Execute commands at start node
    if dialogue.start_node in dialogue.nodes:
        for cmd in dialogue.nodes[dialogue.start_node].commands:
            initial_state.execute_command(cmd)

    # Randomized DFS using a stack
    stack = [(dialogue.start_node, [dialogue.start_node], initial_state)]
    visited = {(dialogue.start_node, frozenset(), frozenset(), frozenset(initial_state.variables.items()))}

    while stack:
        current_node, path, state = stack.pop()

        if current_node == target_node:
            return path, state

        if current_node not in dialogue.nodes:
            continue

        node = dialogue.nodes[current_node]

        # Get valid choices and shuffle them for randomness
        valid_choices = []
        for choice in node.choices:
            if state.evaluate_condition(choice.condition):
                valid_choices.append(choice)

        random.shuffle(valid_choices)

        for choice in valid_choices:
            next_node = choice.target

            if next_node == "END":
                if target_node == "END":
                    return path + ["END"], state
                continue

            if next_node not in dialogue.nodes:
                continue

            new_state = state.copy()
            for cmd in dialogue.nodes[next_node].commands:
                new_state.execute_command(cmd)

            state_sig = (
                next_node,
                frozenset(new_state.inventory),
                frozenset(new_state.companions),
                frozenset(new_state.variables.items()),
            )

            if state_sig not in visited:
                visited.add(state_sig)
                stack.append((next_node, path + [next_node], new_state))

    return None, None


def find_exploratory_path_to_node(dialogue, target_node: str) -> Tuple[Optional[List[str]], Optional[WebGameState]]:
    """
    Find a path that prefers longer/less common routes to target_node.
    Returns (path, final_state) or (None, None) if unreachable.

    Uses randomized DFS with bias toward:
    - Nodes with more content (lines + choices)
    - Longer paths (depth-first naturally explores deeper)
    - Random selection among equally-weighted choices
    """
    initial_state = WebGameState()
    for cmd in dialogue.initial_state:
        initial_state.execute_command(cmd)

    if target_node == dialogue.start_node:
        state = initial_state.copy()
        if target_node in dialogue.nodes:
            for cmd in dialogue.nodes[target_node].commands:
                state.execute_command(cmd)
        return [target_node], state

    if target_node not in dialogue.nodes and target_node != "END":
        return None, None

    if dialogue.start_node in dialogue.nodes:
        for cmd in dialogue.nodes[dialogue.start_node].commands:
            initial_state.execute_command(cmd)

    # Track all valid paths found, then return the longest
    all_paths = []
    stack = [(dialogue.start_node, [dialogue.start_node], initial_state)]
    visited = {(dialogue.start_node, frozenset(), frozenset(), frozenset(initial_state.variables.items()))}

    # Limit iterations to prevent infinite loops in large graphs
    max_iterations = 10000
    iterations = 0

    while stack and iterations < max_iterations:
        iterations += 1
        current_node, path, state = stack.pop()

        if current_node == target_node:
            all_paths.append((path, state))
            # Continue searching for more paths (up to a limit)
            if len(all_paths) >= 20:
                break
            continue

        if current_node not in dialogue.nodes:
            continue

        node = dialogue.nodes[current_node]

        # Score and sort choices to prefer "interesting" paths
        scored_choices = []
        for choice in node.choices:
            if not state.evaluate_condition(choice.condition):
                continue

            next_node = choice.target
            score = 0

            if next_node == "END":
                if target_node == "END":
                    all_paths.append((path + ["END"], state))
                continue

            if next_node in dialogue.nodes:
                next_node_data = dialogue.nodes[next_node]
                # Prefer nodes with more content
                score += len(next_node_data.lines) * 2
                score += len(next_node_data.choices)
                score += len(next_node_data.commands)
                # Add randomness to break ties and vary paths
                score += random.random() * 3

            scored_choices.append((score, choice))

        # Sort by score (lower first since we pop from end of stack)
        scored_choices.sort(key=lambda x: x[0])

        for _, choice in scored_choices:
            next_node = choice.target

            if next_node == "END" or next_node not in dialogue.nodes:
                continue

            new_state = state.copy()
            for cmd in dialogue.nodes[next_node].commands:
                new_state.execute_command(cmd)

            state_sig = (
                next_node,
                frozenset(new_state.inventory),
                frozenset(new_state.companions),
                frozenset(new_state.variables.items()),
            )

            if state_sig not in visited:
                visited.add(state_sig)
                stack.append((next_node, path + [next_node], new_state))

    if not all_paths:
        return None, None

    # Return a random path from the longer ones (top 50% by length)
    all_paths.sort(key=lambda x: len(x[0]), reverse=True)
    top_half = all_paths[: max(1, len(all_paths) // 2)]
    chosen = random.choice(top_half)
    return chosen


def create_app(dialogues_root=None):
    """Create and configure the Flask application"""
    app = Flask(__name__)

    # Default to repo_root/resources/dialogue if not specified
    if dialogues_root is None:
        # From dialogue_forge/web/app.py -> go up 3 levels to repo root
        dialogues_root = Path(__file__).parent.parent.parent / "resources" / "dialogue"
    else:
        dialogues_root = Path(dialogues_root)

    app.config["DIALOGUES_ROOT"] = dialogues_root

    @app.route("/")
    def index():
        """Main page with dialogue graph visualization"""
        return render_template("index.html")

    @app.route("/api/dialogues")
    def list_dialogues():
        """List all dialogue files"""
        dialogue_dir = app.config["DIALOGUES_ROOT"]
        files = []

        if dialogue_dir.exists():
            for dlg_file in dialogue_dir.rglob("*.dlg"):
                rel_path = dlg_file.relative_to(dialogue_dir)
                files.append(
                    {
                        "path": str(dlg_file),
                        "relative_path": str(rel_path),
                        "name": dlg_file.stem,
                        "category": rel_path.parent.name if str(rel_path.parent) != "." else "root",
                    }
                )

        return jsonify({"files": files})

    @app.route("/api/file/<path:filename>")
    def get_file(filename):
        """Get content of a dialogue file"""
        dialogue_dir = app.config["DIALOGUES_ROOT"]
        file_path = dialogue_dir / filename

        if not file_path.exists() or not file_path.is_relative_to(dialogue_dir):
            return jsonify({"error": "File not found"}), 404

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            return jsonify({"content": content, "path": str(file_path), "name": file_path.stem})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/parse", methods=["POST"])
    def parse_dialogue():
        """Parse dialogue content and return graph data"""
        data = request.json
        content = data.get("content", "")

        parser = DialogueParser()

        try:
            lines = content.split("\n")
            dialogue = parser.parse_lines(lines)
            is_valid = parser.validate()

            # Convert to graph data format for Cytoscape
            nodes = []
            edges = []

            # Add character info
            characters_info = dialogue.characters

            # Track if we need an END node
            has_end_target = False

            # Create nodes for each dialogue node
            for node_id, node in dialogue.nodes.items():
                # Count dialogue lines and commands for node size
                node_data = {
                    "id": node_id,
                    "label": node_id,
                    "lines_count": len(node.lines),
                    "choices_count": len(node.choices),
                    "commands_count": len(node.commands),
                    "is_start": node_id == dialogue.start_node,
                    "lines": [
                        {
                            "speaker": line.speaker,
                            "text": line.text,
                            "condition": line.condition,
                            "tags": line.tags,
                        }
                        for line in node.lines
                    ],
                    "commands": node.commands,
                }

                nodes.append({"data": node_data})

                # Create edges for each choice
                for choice in node.choices:
                    # Track if any choice targets END
                    if choice.target == "END":
                        has_end_target = True

                    edge_data = {
                        "id": f"{node_id}->{choice.target}",
                        "source": node_id,
                        "target": choice.target,
                        "label": choice.text[:30] + "..." if len(choice.text) > 30 else choice.text,
                        "condition": choice.condition,
                        "full_text": choice.text,
                    }
                    edges.append({"data": edge_data})

            # Add END node if any edges target it
            if has_end_target:
                nodes.append(
                    {
                        "data": {
                            "id": "END",
                            "label": "END",
                            "lines_count": 0,
                            "choices_count": 0,
                            "commands_count": 0,
                            "is_start": False,
                            "lines": [],
                            "commands": [],
                        }
                    }
                )

            return jsonify(
                {
                    "valid": is_valid,
                    "errors": dialogue.errors,
                    "warnings": dialogue.warnings,
                    "characters": characters_info,
                    "start_node": dialogue.start_node,
                    "initial_state": dialogue.initial_state,
                    "graph": {"nodes": nodes, "edges": edges},
                    "stats": parser.get_stats(),
                }
            )
        except Exception as e:
            import traceback

            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route("/api/save", methods=["POST"])
    def save_file():
        """Save content to a dialogue file"""
        data = request.json
        relative_path = data.get("path", "")
        content = data.get("content", "")

        if not relative_path:
            return jsonify({"error": "No file path specified"}), 400

        dialogue_dir = app.config["DIALOGUES_ROOT"]
        file_path = dialogue_dir / relative_path

        # Security check: ensure path is within dialogues directory
        try:
            file_path = file_path.resolve()
            dialogue_dir = dialogue_dir.resolve()
            if not file_path.is_relative_to(dialogue_dir):
                return jsonify({"error": "Invalid file path"}), 403
        except Exception:
            return jsonify({"error": "Invalid file path"}), 400

        # Only allow .dlg files
        if not str(file_path).endswith(".dlg"):
            return jsonify({"error": "Can only save .dlg files"}), 400

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return jsonify({"success": True, "message": f"Saved to {relative_path}"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/export", methods=["POST"])
    def export_dialogue():
        """Export dialogue to JSON format"""
        data = request.json
        content = data.get("content", "")

        parser = DialogueParser()

        try:
            lines = content.split("\n")
            dialogue = parser.parse_lines(lines)

            # Convert to JSON format (same as export_json.py)
            json_data = {
                "characters": dialogue.characters,
                "start_node": dialogue.start_node,
                "initial_state": dialogue.initial_state,
                "nodes": {},
            }

            for node_id, node in dialogue.nodes.items():
                json_data["nodes"][node_id] = {
                    "lines": [
                        {
                            "speaker": line.speaker,
                            "text": line.text,
                            "condition": line.condition,
                            "tags": line.tags,
                        }
                        for line in node.lines
                    ],
                    "commands": node.commands,
                    "choices": [
                        {
                            "target": choice.target,
                            "text": choice.text,
                            "condition": choice.condition,
                        }
                        for choice in node.choices
                    ],
                }

            return jsonify({"success": True, "json": json_data})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/compute-path", methods=["POST"])
    def compute_path():
        """
        Compute a valid path from start to a target node, along with the
        accumulated game state at that point. Used for "Play from here" feature.

        Accepts optional 'mode' parameter:
        - 'shortest' (default): BFS to find shortest valid path
        - 'random': Randomized DFS with equal probability at each choice
        - 'explore': Biased toward longer/more interesting paths
        """
        data = request.json
        content = data.get("content", "")
        target_node = data.get("target_node", "")
        mode = data.get("mode", "shortest")

        if not target_node:
            return jsonify({"error": "No target node specified"}), 400

        parser = DialogueParser()

        try:
            lines = content.split("\n")
            dialogue = parser.parse_lines(lines)

            # Select pathfinding algorithm based on mode
            if mode == "random":
                path, state = find_random_path_to_node(dialogue, target_node)
            elif mode == "explore":
                path, state = find_exploratory_path_to_node(dialogue, target_node)
            else:  # 'shortest' or default
                path, state = find_valid_path_to_node(dialogue, target_node)

            if path is None:
                # No valid path found - start with empty state
                return jsonify(
                    {
                        "success": True,
                        "path": None,
                        "state": WebGameState().to_dict(),
                        "warning": f"No valid path found to '{target_node}'. Starting with empty state.",
                    }
                )

            return jsonify(
                {
                    "success": True,
                    "path": path,
                    "path_length": len(path),
                    "mode": mode,
                    "state": state.to_dict(),
                }
            )

        except Exception as e:
            import traceback

            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route("/api/replay-path", methods=["POST"])
    def replay_path():
        """
        Replay an exact path through the dialogue, reconstructing the game state
        at the final node. Used for "Resume from history" feature.

        Unlike compute-path which finds a path, this takes a known path and
        simulates walking through it to reconstruct the exact state.
        """
        data = request.json
        content = data.get("content", "")
        path = data.get("path", [])

        if not path:
            return jsonify({"error": "No path specified"}), 400

        parser = DialogueParser()

        try:
            lines = content.split("\n")
            dialogue = parser.parse_lines(lines)

            # Initialize state and execute [state] section commands
            state = WebGameState()
            for cmd in dialogue.initial_state:
                state.execute_command(cmd)

            # Walk through the path, executing commands at each node
            for i, node_id in enumerate(path):
                if node_id not in dialogue.nodes:
                    # Skip unknown nodes (might be END or similar)
                    continue

                node = dialogue.nodes[node_id]

                # Execute commands at this node
                for cmd in node.commands:
                    state.execute_command(cmd)

                # If there's a next node in the path, find which choice leads there
                # and see if it has any state-affecting side effects
                if i < len(path) - 1:
                    next_node_id = path[i + 1]
                    for choice in node.choices:
                        if choice.target == next_node_id:
                            # Found the choice that was taken
                            # (Choice conditions don't affect state, just gate access)
                            break

            return jsonify({"success": True, "path": path, "path_length": len(path), "state": state.to_dict()})

        except Exception as e:
            import traceback

            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route("/api/new-file", methods=["POST"])
    def create_new_file():
        """Create a new dialogue file with template content"""
        data = request.json
        filename = data.get("filename", "")

        if not filename:
            return jsonify({"error": "No filename specified"}), 400

        # Ensure .dlg extension
        if not filename.endswith(".dlg"):
            filename += ".dlg"

        dialogue_dir = app.config["DIALOGUES_ROOT"]
        file_path = dialogue_dir / filename

        # Security check: ensure path is within dialogues directory
        try:
            file_path = file_path.resolve()
            dialogue_dir_resolved = dialogue_dir.resolve()
            if not file_path.is_relative_to(dialogue_dir_resolved):
                return jsonify({"error": "Invalid file path"}), 403
        except Exception:
            return jsonify({"error": "Invalid file path"}), 400

        # Check if file already exists
        if file_path.exists():
            return jsonify({"error": f"File already exists: {filename}"}), 409

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Template content for new dialogue
        template = """# New Dialogue File
# Created with Dialogue Forge

[characters]
hero: Player
npc: Character Name

[state]
# Initialize game state for this scene
# *set talked_before = false
# *set reputation = 0

[start]
npc: "Hello there!"
-> greet: "Hi!"
-> END: "Goodbye."

[greet]
npc: "Nice to meet you!"
-> END
"""

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(template)

            return jsonify(
                {
                    "success": True,
                    "path": str(file_path.relative_to(dialogue_dir_resolved)),
                    "message": f"Created {filename}",
                }
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def main():
    """Run the development server"""
    import argparse

    parser = argparse.ArgumentParser(description="Dialogue Forge Web Editor")
    parser.add_argument("--dialogues", "-d", help="Path to dialogues directory", default=None)
    parser.add_argument("--port", "-p", help="Port to run on", type=int, default=5000)
    parser.add_argument("--debug", help="Run in debug mode", action="store_true")

    args = parser.parse_args()

    app = create_app(dialogues_root=args.dialogues)

    print(f"\n{'=' * 60}")
    print("🎭 Dialogue Forge Web Editor")
    print(f"{'=' * 60}")
    print(f"\n📂 Dialogues directory: {app.config['DIALOGUES_ROOT']}")
    print(f"🌐 Server running at: http://localhost:{args.port}")
    print("\nPress Ctrl+C to stop\n")

    app.run(host="0.0.0.0", port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
