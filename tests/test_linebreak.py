import itertools
import os
import time
import unittest

from linebreak_engine import load_rules
from linebreak_engine.engine import (
    _split_oversized,
    layout_paragraph,
    layout_text,
    tokenize,
)
from linebreak_engine.widths import parse_width_file

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "samples")


def rules():
    return load_rules(
        os.path.join(SAMPLES, "widths.txt"),
        os.path.join(SAMPLES, "kinsoku.txt"),
    )


class WidthTests(unittest.TestCase):
    def test_sample_ranges(self):
        r = rules()
        for ch, width in [
            ("a", 1), ("9", 1), ("-", 1), ("~", 1),      # U+0020..007E
            (" ", 1),                                      # 空格也有宽度
            ("\U0001F600", 1),                              # 表外按默认 1
            ("　", 2),                                     # U+3000 全角
            ("字", 2), ("あ", 2),                          # 汉字/假名
            ("，", 2),                                     # 全角标点
            ("ﾀ", 1),                                      # 半角片假名
            ("…", 2), ("—", 2),                            # 通用标点按全角
            ("①", 2),                                      # 带圈数字
        ]:
            self.assertEqual(r.widths.width_of(ch), width, ch)

    def test_default_width_parsing(self):
        wt, default = parse_width_file("U+0041 U+005A 2\n默认 3\n")
        self.assertEqual(default, 3)
        self.assertEqual(wt.width_of("A"), 2)
        self.assertEqual(wt.width_of("0"), 3)


class TokenizeTests(unittest.TestCase):
    def test_units_and_spaces(self):
        r = rules()
        units, space = tokenize("字 abc 12-3 x", r.widths)
        texts = [u[0] for u in units]
        self.assertEqual(texts, ["字", "abc", "12-3", "x"])
        self.assertEqual(space, [False, True, True, True])

    def test_hyphenated_word_is_atomic(self):
        r = rules()
        units, _ = tokenize("state-of-the-art", r.widths)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0][1], 16)

    def test_no_space_cjk_word_boundary(self):
        r = rules()
        units, space = tokenize("字abc字", r.widths)
        self.assertEqual([u[0] for u in units], ["字", "abc", "字"])
        self.assertEqual(space, [False, False, False])

    def test_leading_and_double_spaces_drop(self):
        r = rules()
        units, space = tokenize("  字  abc ", r.widths)
        self.assertEqual([u[0] for u in units], ["字", "abc"])
        self.assertEqual(space, [False, True])


class SampleAcceptanceTests(unittest.TestCase):
    def test_golden_samples(self):
        for n, width in [(1, 24), (2, 20), (3, 32)]:
            with self.subTest(n=n):
                with open(os.path.join(SAMPLES, f"text-{n}.txt"),
                          encoding="utf-8") as f:
                    text = f.read()
                with open(os.path.join(SAMPLES, f"text-{n}.expected.txt"),
                          encoding="utf-8") as f:
                    expected = f.read()
                self.assertEqual(layout_text(text, rules(), width), expected)


class KinsokuTests(unittest.TestCase):
    def test_head_forbidden_chain_moves_down_together(self):
        # W=10：贪心会断在「汉字」后，但「，。」连续都不能在行首，
        # 整串必须与汉字同行（恰好放得下）。
        lines = layout_paragraph("汉字，。", rules(), 10)
        self.assertEqual(lines, ["汉字，。"])

    def test_tail_forbidden_opening_bracket(self):
        # W=6：「字」可以单独成行，但「（」不允许留在行尾，
        # 只能把「（文）」整体放到下一行。
        lines = layout_paragraph("字（文）", rules(), 6)
        self.assertEqual(lines, ["字", "（文）"])

    def test_bracket_and_quote_pair(self):
        # 开引号/开书名号不能留在行尾，整对内容被推到下一行。
        lines = layout_paragraph("文字《示例》结束", rules(), 8)
        for line in lines:
            self.assertFalse(line[-1] in "（［｛《「『【〈〖〔“‘")
            self.assertFalse(line[0] in "，。、；：？！）］｝》」』】〉〗”’％‰℃…—")


class ForcedSplitTests(unittest.TestCase):
    def test_long_word_split_greedily(self):
        lines = layout_paragraph("abcdefghij word", rules(), 8)
        # 首段正好填满 8，末段与后续单元仍可同行。
        self.assertEqual(lines[0], "abcdefgh")
        self.assertEqual(lines[1], "ij word")

    def test_long_number_fits_as_whole(self):
        lines = layout_paragraph("x 123456789", rules(), 12)
        # 普通行内数字不拆：整块宽 9，W=12 下与 x 同行。
        self.assertEqual(lines, ["x 123456789"])

    def test_long_word_forced_fee_chunks(self):
        lines = layout_paragraph("123456789012", rules(), 5)
        # 12 宽数字在 W=5 下强制拆成三行，内部按字符贪心。
        self.assertEqual(lines, ["12345", "67890", "12"])

    def test_oversized_fullwidth_char_overflow_line(self):
        # W=1：全角字宽 2，单单元超宽，允许溢出一行且豁免禁则。
        lines = layout_paragraph("字。", rules(), 1)
        self.assertEqual(lines, ["字", "。"])


class OptimalBreakTests(unittest.TestCase):
    """用独立的暴力枚举验证 DP 取到全局最优与唯一并列裁决。"""

    @staticmethod
    def _brute_force(text, r, width):
        rules_ = r
        units, space_before = tokenize(text, r.widths)
        chunks, space, forced, penalty, no_kinsoku, fragment = (
            _split_oversized(units, space_before, width)
        )
        n = len(chunks)
        candidate_edges = [e for e in range(1, n) if not forced[e]]

        def render(breaks):
            out, start = [], 0
            for b in breaks + [n]:
                parts = [chunks[start][0]]
                for e in range(start + 1, b):
                    if space[e]:
                        parts.append(" ")
                    parts.append(chunks[e][0])
                out.append("".join(parts))
                start = b
            return out

        best = None
        for chosen in range(len(candidate_edges) + 1):
            for subset in itertools.combinations(candidate_edges, chosen):
                breaks = sorted(
                    [e for e in range(1, n) if forced[e]] + list(subset)
                )
                bounds = [0] + breaks + [n]
                ok = True
                total = 0
                for li in range(len(bounds) - 1):
                    i, k = bounds[li], bounds[li + 1]
                    w = 0
                    for e in range(i, k):
                        w += chunks[e][1]
                        if e > i and space[e]:
                            w += 1
                    overflow = k == i + 1 and fragment[i]
                    if w > width and not overflow:
                        ok = False
                        break
                    if i > 0 and not no_kinsoku[i]:
                        if (chunks[i - 1][0][-1] in r.no_line_end
                                or chunks[i][0][0] in r.no_line_start):
                            ok = False
                            break
                    if k < n and not no_kinsoku[k]:
                        if (chunks[k - 1][0][-1] in r.no_line_end
                                or chunks[k][0][0] in r.no_line_start):
                            ok = False
                            break
                    if k < n:
                        total += (width - w) ** 2 + 10
                    if i > 0:
                        total += penalty[i]
                if not ok:
                    continue
                # 取代价最小；同代价时断点序列（含终点）字典序更大者胜：
                # 即第一行尽量长，再依次让后面的行尽量长。
                seq = tuple(bounds[1:])
                if best is None or total < best[0][0] or (
                    total == best[0][0] and seq > best[0][1]
                ):
                    best = ((total, seq), breaks)
        assert best is not None
        return render(best[1])

    # 规模保持在暴力枚举可接受的范围内（单元数 <= 约 18）。
    CASES = [
        ("汉字标点，开括号（这样）也不行。", 12),
        ("abc def ghi jkl mn", 6),
        ("中英 mixed 混排 text 中文 tail", 14),
        ("一二三四，五六七八、九十", 10),
        ("a bb ccc dddd eeeee", 5),
        ("书名号《甲乙》引号「丁戊」测试", 12),
        ("one two three four five", 9),
        ("甲乙丙丁戊己庚辛壬癸", 7),
        ("x state-of-the-art y", 10),
        ("数字 12345 与 67 混排 890", 12),
    ]

    def test_matches_brute_force(self):
        r = rules()
        tie_cases = 0
        for text, width in self.CASES:
            expected = self._brute_force(text, r, width)
            got = layout_paragraph(text, r, width)
            self.assertEqual(got, expected, (text, width))

    def test_tie_prefers_longer_current_line(self):
        # 枚举随机小输入：在所有最优排法中，引擎必须选择首行最长的那种。
        from linebreak_engine.engine import _optimal_breaks
        import random
        rng = random.Random(20260923)
        vocab = ["甲", "乙", "丙", "丁", "，", "。", "ab", "cd", "ef", "gh"]
        tie_seen = 0
        for _ in range(300):
            tokens = [rng.choice(vocab) for _ in range(rng.randint(4, 9))]
            text = " ".join(tokens)
            width = rng.choice([6, 8, 10, 12])
            units, space_before = tokenize(text, rules().widths)
            chunks, space, forced, penalty, no_kinsoku, fragment = (
                _split_oversized(units, space_before, width)
            )
            n = len(chunks)
            candidate_edges = [e for e in range(1, n) if not forced[e]]

            def evaluate(breaks):
                bounds = [0] + sorted(breaks) + [n]
                total = 0
                for li in range(len(bounds) - 1):
                    i, k = bounds[li], bounds[li + 1]
                    w = sum(
                        chunks[e][1] + (1 if e > i and space[e] else 0)
                        for e in range(i, k)
                    )
                    if w > width and not (k == i + 1 and fragment[i]):
                        return None
                    # 行顶 b=i 查上一行尾 chunks[i-1]；行底 b=k 查本行尾 chunks[k-1]
                    if i > 0 and not no_kinsoku[i]:
                        if (chunks[i - 1][0][-1] in rules().no_line_end
                                or chunks[i][0][0] in rules().no_line_start):
                            return None
                    if k < n and not no_kinsoku[k]:
                        if (chunks[k - 1][0][-1] in rules().no_line_end
                                or chunks[k][0][0] in rules().no_line_start):
                            return None
                    if i > 0:
                        total += penalty[i]
                    if k < n:
                        total += (width - w) ** 2 + 10
                return total

            best_cost = None
            first_ends = set()
            forced_edges = {e for e in range(1, n) if forced[e]}
            for count in range(len(candidate_edges) + 1):
                for subset in itertools.combinations(candidate_edges, count):
                    breaks = forced_edges | set(subset)
                    cost = evaluate(breaks)
                    if cost is None:
                        continue
                    first_end = min(breaks) if breaks else n
                    if best_cost is None or cost < best_cost:
                        best_cost = cost
                        first_ends = {first_end}
                    elif cost == best_cost:
                        first_ends.add(first_end)
            if best_cost is None:
                continue
            engine_ranges = _optimal_breaks(
                chunks, space, forced, penalty, no_kinsoku, fragment,
                width, rules(),
            )
            if len(first_ends) > 1:
                tie_seen += 1
            self.assertEqual(engine_ranges[0][1], max(first_ends), text)
        self.assertGreater(tie_seen, 0, "随机构造里应至少出现一次代价并列")

    def test_random_full_sequence_against_brute_force(self):
        import random
        rng = random.Random(424242)
        vocab = ["甲", "乙", "，", "。", "ab", "cd", "《", "》", "（", "）"]
        checked = 0
        for _ in range(80):
            tokens = [rng.choice(vocab) for _ in range(rng.randint(5, 14))]
            text = " ".join(tokens)
            width = rng.choice([6, 8, 10, 12])
            try:
                got = layout_paragraph(text, rules(), width)
            except RuntimeError:
                continue  # 禁则导致无解的输入不在本测试范围
            expected = self._brute_force(text, rules(), width)
            self.assertEqual(got, expected, (text, width))
            checked += 1
        self.assertGreater(checked, 40)


class FormatTests(unittest.TestCase):
    def test_trailing_lf_and_no_trailing_spaces(self):
        out = layout_text("字 abc 字 ", rules(), 40)
        self.assertTrue(out.endswith("\n"))
        self.assertFalse(out.endswith("\n\n"))
        for line in out.splitlines():
            self.assertFalse(line.endswith(" "))
            self.assertFalse(line.startswith(" "))

    def test_paragraph_break_is_one_blank_line(self):
        out = layout_text("第一段文字。\n\n第二段文字。", rules(), 40)
        self.assertEqual(out, "第一段文字。\n\n第二段文字。\n")

    def test_multiple_blank_lines_collapse(self):
        out = layout_text("甲\n\n\n\n\n乙", rules(), 40)
        self.assertEqual(out, "甲\n\n乙\n")

    def test_empty_input(self):
        self.assertEqual(layout_text("", rules(), 40), "")
        self.assertEqual(layout_text("   \n  \n", rules(), 40), "")
        self.assertEqual(layout_paragraph("", rules(), 40), [])


class DeterminismTests(unittest.TestCase):
    def test_repeat_runs_identical(self):
        text = open(os.path.join(SAMPLES, "text-3.txt"),
                    encoding="utf-8").read()
        a = layout_text(text, rules(), 32)
        for _ in range(5):
            self.assertEqual(layout_text(text, rules(), 32), a)


class PerformanceTests(unittest.TestCase):
    def test_book_length_in_seconds(self):
        rng_bits = 0
        paragraph = (
            "这是一段用来压测的中英混排文本，包含 English words 与数字 12345，"
            "还有标点、括号（例如这样）和书名号《示例》，state-of-the-art "
            "之类的连字符词也不能断开。"
        )
        text = "\n\n".join([paragraph] * 1200)
        self.assertGreater(len(text), 100000)
        start = time.perf_counter()
        out = layout_text(text, rules(), 60)
        elapsed = time.perf_counter() - start
        self.assertTrue(out.endswith("\n"))
        self.assertLess(elapsed, 5.0, f"全书排版耗时 {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
