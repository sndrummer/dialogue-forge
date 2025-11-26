"""
Dialogue node classes
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class DialogueChoice:
    """Represents a player choice in dialogue"""
    text: str
    conditions: List[str] = field(default_factory=list)
    consequences: List['DialogueNode'] = field(default_factory=list)
    jump_to: Optional[str] = None
    actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'text': self.text,
            'conditions': self.conditions,
            'consequences': [c.to_dict() for c in self.consequences],
            'jump_to': self.jump_to,
            'actions': self.actions
        }


@dataclass
class DialogueNode:
    """Represents a node in the dialogue tree"""
    speaker: str
    text: str
    line_number: int = 0
    node_id: Optional[str] = None
    choices: List[DialogueChoice] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    jump_to: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'speaker': self.speaker,
            'text': self.text,
            'line_number': self.line_number,
            'node_id': self.node_id,
            'choices': [c.to_dict() for c in self.choices],
            'conditions': self.conditions,
            'actions': self.actions,
            'jump_to': self.jump_to,
            'metadata': self.metadata
        }

    def is_branch(self) -> bool:
        """Check if this node has choices (is a branching point)"""
        return len(self.choices) > 0

    def is_terminal(self) -> bool:
        """Check if this node is terminal (no choices and no jump)"""
        return len(self.choices) == 0 and self.jump_to is None