"""排版规则：宽度表 + 行首/行尾禁则字符集，以及规则文件的加载。"""

from dataclasses import dataclass

from .widths import WidthTable, parse_width_file


@dataclass(frozen=True)
class Rules:
    widths: WidthTable
    no_line_start: frozenset
    no_line_end: frozenset


def _parse_kinsoku_file(text):
    """解析禁则文件。

    以注释里出现的「行首禁则」「行尾禁则」分段，注释行之后到下一段
    注释之间的字符（去掉空白）即为该段禁则字符。
    """
    sections = {"start": set(), "end": set()}
    current = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            if "行首禁则" in stripped:
                current = "start"
            elif "行尾禁则" in stripped:
                current = "end"
            continue
        if current is not None:
            for ch in stripped.split():
                sections[current].add(ch)
    return frozenset(sections["start"]), frozenset(sections["end"])


def load_rules(width_path, kinsoku_path, encoding="utf-8"):
    with open(width_path, "r", encoding=encoding) as f:
        widths, _ = parse_width_file(f.read())
    with open(kinsoku_path, "r", encoding=encoding) as f:
        no_start, no_end = _parse_kinsoku_file(f.read())
    return Rules(widths=widths, no_line_start=no_start, no_line_end=no_end)
