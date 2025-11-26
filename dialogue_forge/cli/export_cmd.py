"""
Export .dlg dialogue files to JSON for use in Godot
"""

import sys
import json
from pathlib import Path

from dialogue_forge.parser.parser import DialogueParser


def export_to_json(dlg_path: Path, output_path: Path = None):
    """Export a .dlg file to JSON format"""

    # Parse the dialogue file
    parser = DialogueParser()
    dialogue = parser.parse_file(dlg_path)

    if not parser.validate():
        print(f"⚠️  Warning: Dialogue has validation issues:")
        for error in dialogue.errors:
            print(f"  • {error}")

    # Prepare output path
    if output_path is None:
        output_path = dlg_path.with_suffix('.json')

    # Convert to JSON-serializable format
    json_data = {
        "characters": dialogue.characters,
        "start_node": dialogue.start_node,
        "initial_state": dialogue.initial_state,
        "nodes": {}
    }

    # Convert each node
    for node_id, node in dialogue.nodes.items():
        json_data["nodes"][node_id] = {
            "lines": node.lines,
            "commands": node.commands,
            "choices": [
                {
                    "target": choice.target,
                    "text": choice.text,
                    "condition": choice.condition
                }
                for choice in node.choices
            ]
        }

    # Write JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Exported to: {output_path}")
    print(f"   • {len(dialogue.nodes)} nodes")
    print(f"   • {len(dialogue.characters)} characters")
    if dialogue.initial_state:
        print(f"   • {len(dialogue.initial_state)} initial state commands")

    return output_path


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: dlg-export <dialogue_file.dlg> [output.json]")
        print("\nExample:")
        print("  dlg-export ../../resources/dialogue/prologue/fire_nation_prologue.dlg")
        sys.exit(1)

    dlg_path = Path(sys.argv[1])

    if not dlg_path.exists():
        print(f"❌ File not found: {dlg_path}")
        sys.exit(1)

    output_path = None
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])

    try:
        export_to_json(dlg_path, output_path)
    except Exception as e:
        print(f"❌ Export failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
