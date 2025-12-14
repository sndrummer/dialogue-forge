# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Dialogue Forge** tooling suite for the custom `.dlg` dialogue format used in the Avatar: The Ashen Path RPG. It's a modern Python 3.11+ project managed with [uv](https://docs.astral.sh/uv/).

## Key Commands

All commands should be run from the project root directory.

### Setup
```bash
uv sync              # Install dependencies
uv sync --all-extras # Include dev dependencies (pytest, ruff)
```

### Validation
```bash
uv run dlg-validate <file.dlg>
```
Validates `.dlg` file syntax, node references, variable usage, item/companion tracking. Provides detailed error reporting with line numbers and suggestions.

### Interactive Testing
```bash
uv run dlg-play              # Interactive file picker
uv run dlg-play <file.dlg>   # Direct file
uv run dlg-play --debug <file.dlg>  # With debug info
```
Terminal-based dialogue player with colored output, save/load system, and game state tracking. Commands: `quit`, `state`, `save`, `load`.

### Export to JSON
```bash
uv run dlg-export <input.dlg> [output.json]
```
Converts `.dlg` to JSON for Godot's DialogueManager. Automatically names output as `<input>.json` if not specified.

### Web Editor
```bash
uv run dlg-web                    # Start web editor on port 5000
uv run dlg-web --port 8080        # Custom port
uv run dlg-web --debug            # Debug mode with auto-reload
```
Visual graph-based dialogue editor with live preview.

### Click CLI (Alternative)
```bash
uv run dlg --help               # Show all commands
uv run dlg validate <file.dlg>  # Validate with click
uv run dlg stats <file.dlg>     # Show statistics
uv run dlg show-node <file.dlg> <node_name>  # Display specific node
```

### Makefile (Shortcuts)
A Makefile is provided for convenience:
```bash
make help                    # Show all available commands
make build                   # Full rebuild: sync + fix + test
make dev                     # Start web editor in debug mode (auto-reload)
make web                     # Start web editor (port 5000)
make web port=8080           # Custom port
make play file=example.dlg   # Play a dialogue
make validate file=example.dlg  # Validate a file
make export file=example.dlg    # Export to JSON
make test                    # Run pytest
make lint                    # Run ruff linter
make fix                     # Auto-fix lint issues and format
make format                  # Format code with ruff
make sync                    # Install dependencies
make clean                   # Remove cache files
make nvim                    # Install DLG syntax for Neovim
make vscode                  # Install DLG extension for VSCode
```

## Architecture

### Package Structure

```
dialogue_forge/
├── __init__.py           # Package exports: DialogueParser, DialogueExporter
├── parser/
│   ├── parser.py         # Core .dlg parser with DialogueParser class
│   └── node.py           # Data classes: DialogueNode, Choice
├── export/
│   └── exporter.py       # JSON exporter for Godot
├── cli/
│   ├── __init__.py       # Exports: cli (click group)
│   ├── commands.py       # Click-based CLI commands
│   ├── validate_cmd.py   # Standalone validation command
│   ├── play_cmd.py       # Interactive dialogue player
│   └── export_cmd.py     # JSON export command
└── web/
    ├── app.py            # Flask web application
    ├── templates/        # Jinja2 templates
    └── static/
        ├── css/main.css  # Styles
        └── src/          # ES modules
            ├── main.js           # Entry point
            ├── app/DialogueForgeApp.js   # Main app controller
            ├── player/DialoguePlayer.js  # Playback modal
            ├── state/GameState.js        # Game state logic
            └── utils/helpers.js          # Shared utilities
```

### Data Model

All dataclasses are defined in `parser/parser.py`:

```python
Dialogue
├── characters: Dict[str, str]  # id -> display name
├── nodes: Dict[str, DialogueNode]
├── start_node: Optional[str]
├── initial_state: List[str]    # Commands from [state] section
├── errors: List[str]
└── warnings: List[str]

DialogueNode
├── id: str
├── lines: List[DialogueLine]
├── choices: List[Choice]
├── commands: List[str]
└── line_number: int

DialogueLine
├── speaker: str
├── text: str
├── condition: Optional[str]
├── tags: List[str]          # Optional metadata like [happy, waving]
└── line_number: int

Choice
├── target: str
├── text: str
├── condition: Optional[str]
└── line_number: int
```

Note: `parser/node.py` contains legacy dataclasses that are not currently used.

## DLG Format Specifics

### Critical Syntax Rules

1. **Characters section** must appear first: `[characters]` followed by `id: Display Name`
2. **Nodes** are defined as `[node_name]` (lowercase with underscores)
3. **Stacked nodes**: Multiple consecutive `[node1][node2]` labels can point to same content
4. **Speaker lines**: `speaker: "dialogue text"` (quotes required)
5. **Tags** (optional): `speaker: "text" [tag1, tag2]` - metadata after quoted text, before condition
6. **Choices**: `-> target: "choice text" {condition}` or `-> target {condition}` (condition-only)
7. **Commands**: `*set var = value`, `*add var = num`, `*give_item name`, etc.
8. **Conditions**: `{var}`, `{var > 5}`, `{has_item:sword}`, `{companion:peng}`, `{!var}`, `{a && b}`, `{a || b}`

### Special Node Names
- `[start]` - Optional explicit start node (otherwise first node is used)
- `END` - Choice target to end conversation

## Validation Logic

The validator (`cli/validate_cmd.py`) performs these passes:
1. **Structure validation** - Syntax, character definitions, node definitions
2. **Reference validation** - Undefined nodes, unreachable nodes
3. **Condition validation** - Variables used but never set, items/companions checked but never given/added
4. **Command validation** - Command syntax, common typos
5. **Flow validation** - Nodes with no choices (dead ends), accounting for stacked nodes

**Important**: Stacked nodes are treated as a group - if ANY node in the stack has content/choices, the whole stack is valid.

## Game State Tracking

The `GameState` class (`cli/play_cmd.py`) tracks:
- `variables: Dict[str, any]` - All game flags and numeric values
- `inventory: Set[str]` - Items from `*give_item`/`*remove_item`
- `companions: Set[str]` - Companions from `*add_companion`/`*remove_companion`
- `visited_nodes: Set[str]` - Nodes the player has seen

Condition evaluation converts DLG syntax to Python:
- `!` -> `not`
- `&&` -> `and`
- `||` -> `or`
- `has_item:sword` -> `'sword' in inventory`
- `companion:peng` -> `'peng' in companions`

## Web Editor Notes

The web editor (`web/app.py`) provides:
- Split-pane interface with CodeMirror editor and Cytoscape.js graph
- Live validation and preview (debounced 1 second)
- Multiple graph layouts (dagre, breadthfirst, cose, circle)
- Node/edge inspector panel
- Save/reload files (Ctrl+S to save)
- JSON export download

### Playback Features
- **Interactive playback** - Test dialogues with full state tracking
- **Path visualization** - Visited nodes highlighted green, current node amber
- **"Play from here"** - Right-click any node to start from there with computed state:
  - Shortest path (BFS)
  - Random path (randomized DFS)
  - Exploratory path (prefers longer/interesting routes)
- **"Resume from history"** - Right-click a previously visited node to replay your exact path
- **State management** - View, edit, import/export game state during playback

## Development Workflow

```bash
# Format and lint
uv run ruff check dialogue_forge/
uv run ruff format dialogue_forge/

# Run tests
uv run pytest

# Type checking (if added)
uv run mypy dialogue_forge/
```

## Common Development Patterns

### Adding New Commands
1. Update parser command recognition in `parser/parser.py`
2. Add execution logic in `GameState.execute_command()` (`cli/play_cmd.py`)
3. Update validator command syntax in `cli/validate_cmd.py`
4. Document in `dlg-language-specification.md`

### Adding New Condition Types
1. Update condition parsing in `GameState.evaluate_condition()` (`cli/play_cmd.py`)
2. Add tracking in validator `_validate_condition_syntax()` (`cli/validate_cmd.py`)
3. Document in `dlg-language-specification.md`
