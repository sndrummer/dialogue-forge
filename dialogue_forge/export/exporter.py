"""
Export dialogue to various formats
"""

import csv
import json
from pathlib import Path
from typing import List, Dict, Any

from ..parser.node import DialogueNode


class DialogueExporter:
    """Export dialogue nodes to various formats"""

    def export_to_csv(self, nodes: List[DialogueNode], output_path: Path):
        """Export to Pixel Crushers Dialogue System CSV format"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'ID', 'Actor', 'Conversant', 'Title', 'Dialogue Text',
                'Menu Text', 'Sequence', 'Conditions', 'Script',
                'Is Root', 'Is Group', 'Node Color', 'Delay',
                'Falsehood Safe', 'Priority', 'Entry Tag'
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            # Write dialogue entries
            for i, node in enumerate(nodes):
                # Main dialogue entry
                entry = {
                    'ID': i + 1,
                    'Actor': node.speaker,
                    'Conversant': 'Player' if node.speaker != 'Player' else 'NPC',
                    'Title': f"Node_{i+1}",
                    'Dialogue Text': node.text,
                    'Menu Text': '',
                    'Sequence': '',
                    'Conditions': '; '.join(node.conditions) if node.conditions else '',
                    'Script': '; '.join(node.actions) if node.actions else '',
                    'Is Root': 'True' if i == 0 else 'False',
                    'Is Group': 'False',
                    'Node Color': 'White',
                    'Delay': '-1',
                    'Falsehood Safe': 'False',
                    'Priority': 'Normal',
                    'Entry Tag': f"Tag_{i+1}"
                }
                writer.writerow(entry)

                # Write choices as separate entries
                for j, choice in enumerate(node.choices):
                    choice_entry = {
                        'ID': f"{i+1}.{j+1}",
                        'Actor': 'Player',
                        'Conversant': node.speaker,
                        'Title': f"Choice_{i+1}_{j+1}",
                        'Dialogue Text': choice.text,
                        'Menu Text': choice.text,
                        'Sequence': '',
                        'Conditions': '; '.join(choice.conditions) if choice.conditions else '',
                        'Script': '; '.join(choice.actions) if choice.actions else '',
                        'Is Root': 'False',
                        'Is Group': 'False',
                        'Node Color': 'Blue',
                        'Delay': '-1',
                        'Falsehood Safe': 'False',
                        'Priority': 'Normal',
                        'Entry Tag': f"Choice_{i+1}_{j+1}"
                    }
                    writer.writerow(choice_entry)

    def export_to_json(self, nodes: List[DialogueNode], output_path: Path):
        """Export to JSON format"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'dialogue': [node.to_dict() for node in nodes],
            'metadata': {
                'version': '1.0',
                'node_count': len(nodes),
                'branch_count': sum(1 for node in nodes if node.is_branch()),
                'terminal_count': sum(1 for node in nodes if node.is_terminal())
            }
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def export_to_xml(self, nodes: List[DialogueNode], output_path: Path):
        """Export to XML format (for other game engines)"""
        # This would be implemented if XML export is needed
        pass

    def export_to_ink(self, nodes: List[DialogueNode], output_path: Path):
        """Export to Ink format (for Inkle's narrative scripting)"""
        # This would be implemented if Ink export is needed
        pass