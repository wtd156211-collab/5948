"""断行引擎本体。

流程：段落 -> 单元切分 -> 超长单元强制拆分 -> 按代价函数做全局最优
动态规划 -> 逐行拼回文本。

DP 自后向前递推：g[i] 是后缀 [i, n) 的最小代价，当前行取 [i, k)。
代价相同时取更大的 k（当前行更长）；该局部偏好沿递推复合成
全局唯一解，整个过程没有随机、也不依赖哈希遍历顺序。
"""

_SEPARATORS = frozenset(" \t\n\r\f\v")


def tokenize(text, widths):
    """把一段文本切成单元。

    宽 2 的码位每个单独成一个 CJK 单元；连续的宽 1 非分隔符码位
    组成一个英文/数字单元（连字符词因此天然不可拆）。分隔符不进
    单元，只记录相邻单元之间是否夹有空格。

    返回 (units, space_before)：unit = (text, width, cjk)，
    space_before[i] 表示单元 i 与前一单元之间是否有分隔符。
    """
    units = []
    space_before = []
    run = []
    run_width = 0
    pending_space = False

    def flush_run():
        nonlocal run, run_width, pending_space
        if run:
            had_prior = bool(units)
            units.append(("".join(run), run_width, False))
            space_before.append(pending_space if had_prior else False)
            pending_space = False
            run = []
            run_width = 0

    for ch in text:
        if ch in _SEPARATORS:
            flush_run()
            pending_space = True
            continue
        width = widths.width_of(ch)
        if width == 2:
            had_prior = bool(units)
            flush_run()
            units.append((ch, 2, True))
            space_before.append(pending_space if had_prior else False)
            pending_space = False
        else:
            run.append(ch)
            run_width += width
    flush_run()
    return units, space_before


def _split_oversized(units, space_before, max_width):
    """把宽度超过 max_width 的单元按「能放多少放多少」强制拆开。

    超长单元内的字符都是宽 1（宽 2 单元只有一个字符，不会内拆），
    逐字符贪心累积即可。

    返回 chunks 与每条块间边界（下标 e，1 <= e < n）的属性：
      space[e]      该边界原文是否是空格（成行则保留、断行则丢弃）；
      forced[e]     是否强制断行（拆出的片段各自成行）；
      penalty[e]    强制拆行的罚分（内拆 1000，起始断行 0）；
      no_kinsoku[e] 该边界是否豁免禁则（降级路径）。
    另有 fragment[i] 标记块 i 是强制拆出来的片段。
    """
    chunks = []
    space = [False]
    forced = [False]
    penalty = [0]
    no_kinsoku = [False]
    fragment = []
    prev_unit_oversized = False

    for idx, (text, width, cjk) in enumerate(units):
        had_space = space_before[idx] if idx >= 1 else False
        if width <= max_width:
            chunks.append((text, width, cjk))
            fragment.append(False)
            if idx >= 1:
                space.append(had_space)
                forced.append(False)
                penalty.append(0)
                no_kinsoku.append(prev_unit_oversized)
            prev_unit_oversized = False
            continue

        pieces = []
        buf = []
        buf_width = 0
        for ch in text:
            if buf and buf_width + 1 > max_width:
                pieces.append("".join(buf))
                buf = []
                buf_width = 0
            buf.append(ch)
            buf_width += 1
        if buf:
            pieces.append("".join(buf))

        for p_idx, piece in enumerate(pieces):
            if chunks:
                if p_idx == 0:
                    # 首段从行首开始：强制断行，不记拆行罚分。
                    space.append(had_space)
                    forced.append(True)
                    penalty.append(0)
                    no_kinsoku.append(True)
                else:
                    # 单元内部的一刀：强制断行 + 1000 分，豁免禁则。
                    space.append(False)
                    forced.append(True)
                    penalty.append(1000)
                    no_kinsoku.append(True)
            chunks.append((piece, len(piece), cjk))
            fragment.append(True)
        prev_unit_oversized = True

    return chunks, space, forced, penalty, no_kinsoku, fragment


def _violates_kinsoku(prev_chunk, next_chunk, rules):
    last_char = prev_chunk[0][-1]
    first_char = next_chunk[0][0]
    return last_char in rules.no_line_end or first_char in rules.no_line_start


def _optimal_breaks(chunks, space, forced, penalty, no_kinsoku, fragment,
                    max_width, rules):
    """后缀 DP，返回每个行首 i 选择的行尾 choice[i]。"""
    n = len(chunks)
    widths = [c[1] for c in chunks]

    inf = float("inf")
    best_cost = [inf] * (n + 1)
    choice = [0] * (n + 1)
    best_cost[n] = 0

    for i in range(n - 1, -1, -1):
        line_width = 0
        best = None  # (cost, -k)
        for k in range(i + 1, n + 1):
            e = k - 1
            if e > i and forced[e]:
                break  # 强制断点在本行内部，[i, k) 不合法
            line_width += widths[e] + (1 if e > i and space[e] else 0)

            overflow_ok = k == i + 1 and fragment[e]
            if line_width > max_width and not overflow_ok:
                break  # 再往后只会更宽

            start_ok = (
                i == 0
                or no_kinsoku[i]
                or not _violates_kinsoku(chunks[i - 1], chunks[i], rules)
            )
            if not start_ok:
                break  # 行首禁则与 k 无关，整段扫描作废
            if k < n and not no_kinsoku[k]:
                if _violates_kinsoku(chunks[k - 1], chunks[k], rules):
                    if forced[k]:
                        break
                    continue  # 该断点违反行首/行尾禁则，再往后试

            split_fee = penalty[i] if i > 0 else 0
            if k == n:
                cost = split_fee
            else:
                gap = max_width - line_width
                cost = (
                    split_fee
                    + 10
                    + gap * gap
                    + best_cost[k]
                )
            key = (cost, -k)  # 同代价取更大的 k：当前行更长
            if best is None or key < best:
                best = key
                choice[i] = k

            if k < n and forced[k]:
                break  # 强制断行：本行必须在 k 处结束

        best_cost[i] = best[0] if best is not None else inf

    lines = []
    i = 0
    while i < n:
        k = choice[i]
        if k == 0:
            raise RuntimeError("no legal line break found")
        lines.append((i, k))
        i = k
    return lines


def _render(chunks, space, start, end):
    parts = [chunks[start][0]]
    for e in range(start + 1, end):
        if space[e]:
            parts.append(" ")
        parts.append(chunks[e][0])
    return "".join(parts)


def layout_paragraph(text, rules, max_width):
    """排一段文本，返回排好的行（字符串列表）。"""
    units, space_before = tokenize(text, rules.widths)
    if not units:
        return []
    chunks, space, forced, penalty, no_kinsoku, fragment = _split_oversized(
        units, space_before, max_width
    )
    ranges_ = _optimal_breaks(
        chunks, space, forced, penalty, no_kinsoku, fragment,
        max_width, rules,
    )
    return [_render(chunks, space, i, k) for i, k in ranges_]


def _split_paragraphs(text):
    paragraphs = []
    current = []
    for line in text.split("\n"):
        if line.strip() == "":
            if current:
                paragraphs.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def layout_text(text, rules, max_width):
    """排整篇文本：段间保留一个空行，行尾不留空格，末尾留一个 LF。"""
    paragraphs = _split_paragraphs(text)
    rendered = [
        "\n".join(layout_paragraph(p, rules, max_width)) for p in paragraphs
    ]
    rendered = [r for r in rendered if r]
    if not rendered:
        return ""
    return "\n\n".join(rendered) + "\n"
