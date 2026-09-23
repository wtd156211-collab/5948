"""中英混排断行引擎。

只做断行：按宽度表计算码位宽度，把文本切成不可再分的单元，
再用以断点位置为状态的动态规划求全局最小代价的断法。
"""

from .engine import (
    LineBreaker,
    WidthTable,
    load_kinsoku,
    load_width_table,
    layout_paragraph,
    layout_text,
)

__all__ = [
    "LineBreaker",
    "WidthTable",
    "load_kinsoku",
    "load_width_table",
    "layout_paragraph",
    "layout_text",
]
