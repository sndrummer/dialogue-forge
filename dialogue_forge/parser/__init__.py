"""
Dialogue parser module for .dlg files
"""

from .node import DialogueChoice, DialogueNode
from .parser import DialogueParser

__all__ = ["DialogueParser", "DialogueNode", "DialogueChoice"]
