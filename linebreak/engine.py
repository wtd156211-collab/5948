"""断行引擎：宽度、禁则、动态规划。

DP 状态按单元位置递推：``dp[i]`` 是排完前 ``i`` 个内容单元的最小总代价。
对每个右端 ``i``，左端 ``j`` 从 ``i`` 向左扩展，累计宽度超过行宽 W 即停止；
因此每个状态只检查落在上一行空隙范围内的转移，行宽固定时总时间随文本
长度线性增长。

单元间的边界分四种：

- ``space``：后一单元带前导空格。断行时空格丢弃、不占宽度；不断时保留、
  占 1 个单位宽度。
- ``cjk``：相邻两个单元至少一侧是 CJK 单字单元。
- ``none``：单词/半角单元与非 CJK 单元直接相邻，不可断。
- ``forced``：超长单元强制拆分产生的边界。必断、免禁则；来自真正拆分动作
  的边界罚 1000，只是「不得不从该单元起行」的进入边界不罚。

``space`` 与 ``cjk`` 是普通断点，还要过硬禁则：后一单元首字符不能在行首
禁则表里，前一单元末字符不能在行尾禁则表里。标点连串时每个字符都在表中，
整串自然一起被推到下一行。

最后一行不罚空隙也不罚断行；代价相同时取左端更靠前者（本行更长），保证
结果唯一。禁则在极端窄行下可能无合法断法，此时兜底重排一次、只放宽禁则，
保证任何输入都能排完。
"""

from .kinsoku import load_kinsoku
from .tokenizer import CJK, WORD, tokenize
from .widths import WidthTable

SPLIT_PENALTY = 1000
LINE_PENALTY = 10

SPACE = "space"
CJK_BOUNDARY = "cjk"
NONE = "none"
FORCED = "forced"


def load_width_table(path):
    return WidthTable.from_file(path)


def _normal_break(prev_unit, unit):
    """两个相邻原始单元之间在不考虑强制拆分时是否允许断行。"""
    if unit[3]:  # 前导空格
        return True
    return prev_unit[2] == CJK or unit[2] == CJK


def prepare_units(raw_units, max_width):
    """把原始单元转成 (碎片列表, 强制边界表)。

    碎片是 (文本, 宽度, 种类, 前导空格, 是否允许溢出)。强制边界表把边界位置
    k（碎片 k-1 与碎片 k 之间）映射到该边界的罚分。
    """
    fragments = []
    forced_after = {}

    for raw_index, (text, width, kind, lead) in enumerate(raw_units):
        start_index = len(fragments)

        if width <= max_width or kind != WORD:
            fragments.append((text, width, kind, lead, width > max_width))
        else:
            # 单词内部都是半角字符，每字符宽 1，按个数贪心装。
            pieces = []
            buffer = []
            for char in text:
                if buffer and len(buffer) >= max_width:
                    pieces.append("".join(buffer))
                    buffer = []
                buffer.append(char)
            pieces.append("".join(buffer))
            for piece_index, piece in enumerate(pieces):
                fragments.append(
                    (piece, len(piece), WORD,
                     lead if piece_index == 0 else False, False)
                )

        end_index = len(fragments) - 1

        if width > max_width:
            # 碎片之间：每拆一次罚 1000。
            for boundary in range(start_index + 1, end_index + 1):
                forced_after[boundary] = SPLIT_PENALTY
            # 进入边界：本身不是合法断点时强制起行（不罚），否则留给普通规则。
            if start_index > 0 and raw_index > 0:
                prev_raw = raw_units[raw_index - 1]
                if not _normal_break(prev_raw, raw_units[raw_index]):
                    forced_after.setdefault(start_index, 0)

    return fragments, forced_after


class LineBreaker:
    """给定宽度表、禁则表和行宽的断行器。"""

    def __init__(self, width_table, no_line_start=frozenset(),
                 no_line_end=frozenset(), max_width=80):
        if max_width < 1:
            raise ValueError("max_width 必须为正整数")
        self.width_table = width_table
        self.no_line_start = frozenset(no_line_start)
        self.no_line_end = frozenset(no_line_end)
        self.max_width = max_width

    def layout(self, paragraph):
        """排一个段落（不含换行），返回行文本列表。"""
        raw_units = tokenize(paragraph, self.width_table)
        fragments, forced_after = prepare_units(raw_units, self.max_width)
        count = len(fragments)
        if count == 0:
            return []

        parents = self._solve(fragments, forced_after, True)
        if parents[count] < 0:
            parents = self._solve(fragments, forced_after, False)
        return self._render(fragments, parents, count)

    def _solve(self, units, forced_after, enforce_kinsoku):
        count = len(units)
        infinity = float("inf")
        dp = [infinity] * (count + 1)
        parent = [-1] * (count + 1)
        dp[0] = 0

        for end in range(1, count + 1):
            width = 0
            start = end
            while start > 0:
                start -= 1
                width += units[start][1]
                if start + 1 < end and units[start + 1][3]:
                    # 行内边界上的空格保留，占 1 个单位；行首空格渲染时丢弃。
                    width += 1

                single_overflow = (
                    end - start == 1 and units[start][4]
                )
                if width > self.max_width and not single_overflow:
                    break

                if start == 0:
                    boundary = None
                elif start in forced_after:
                    boundary = FORCED
                elif units[start][3]:
                    boundary = SPACE
                elif units[start - 1][2] == CJK or units[start][2] == CJK:
                    boundary = CJK_BOUNDARY
                else:
                    boundary = NONE

                if boundary == NONE:
                    continue

                if start > 0 and dp[start] == infinity:
                    if boundary == FORCED:
                        break
                    continue

                if (boundary in (SPACE, CJK_BOUNDARY)
                        and enforce_kinsoku
                        and not self._kinsoku_ok(units, start)):
                    continue

                gap = max(0, self.max_width - width)
                if end == count:
                    line_cost = 0
                else:
                    line_cost = gap * gap + LINE_PENALTY
                if boundary == FORCED:
                    line_cost += forced_after[start]

                candidate = dp[start] + line_cost if start > 0 else line_cost
                if (candidate < dp[end]
                        or (candidate == dp[end]
                            and parent[end] != -1
                            and start < parent[end])):
                    dp[end] = candidate
                    parent[end] = start

                if boundary == FORCED or width > self.max_width:
                    break

        return parent

    def _kinsoku_ok(self, units, start):
        return (units[start][0][0] not in self.no_line_start
                and units[start - 1][0][-1] not in self.no_line_end)

    @staticmethod
    def _render(units, parent, count):
        lines = []
        end = count
        while end > 0:
            start = parent[end]
            if start < 0:
                raise RuntimeError("无法为段落找到合法断行")
            pieces = []
            for index in range(start, end):
                if units[index][3] and index != start:
                    pieces.append(" ")
                pieces.append(units[index][0])
            lines.append("".join(pieces))
            end = start
        lines.reverse()
        return lines


def layout_paragraph(paragraph, max_width, width_table,
                     no_line_start=frozenset(), no_line_end=frozenset()):
    breaker = LineBreaker(width_table, no_line_start, no_line_end, max_width)
    return breaker.layout(paragraph)


def layout_text(text, max_width, width_table,
                no_line_start=frozenset(), no_line_end=frozenset()):
    """排多段文本。

    空行分段；段内换行按 Markdown 惯例折叠成空格；段间保留一个空行。
    返回的字符串行与行之间用 LF 分隔、文件末尾留一个 LF；空文本返回空串。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text:
        return ""
    paragraphs = []
    for block in text.split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if lines:
            paragraphs.append(" ".join(lines))
    breaker = LineBreaker(width_table, no_line_start, no_line_end, max_width)
    blocks = ["\n".join(breaker.layout(paragraph)) for paragraph in paragraphs]
    return "\n\n".join(blocks) + "\n"
