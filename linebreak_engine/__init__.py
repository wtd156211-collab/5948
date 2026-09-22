"""只做断行这一件事的排版引擎。"""

from .rules import Rules, load_rules
from .engine import layout_paragraph, layout_text

__all__ = ["Rules", "load_rules", "layout_paragraph", "layout_text"]
