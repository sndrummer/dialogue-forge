"""
Dialogue parser module for .dlg files
"""

from .node import DialogueChoice, DialogueNode
from .parser import (
    Choice,
    Dialogue,
    DialogueLine,
    DialogueNode as ParsedDialogueNode,
    DialogueParser,
    EntryGroup,
    EntryRoute,
    Trigger,
)

__all__ = [
    "DialogueParser",
    "DialogueNode",
    "DialogueChoice",
    # New parser dataclasses
    "Dialogue",
    "ParsedDialogueNode",
    "DialogueLine",
    "Choice",
    "EntryGroup",
    "EntryRoute",
    "Trigger",
]
