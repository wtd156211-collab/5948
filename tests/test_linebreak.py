# -*- coding: utf-8 -*-
"""断行引擎单元测试。

覆盖：宽度表解析与查表、禁则解析、单元切分、样例验收（全局最优代价）、
禁则连串、连字符词原子性、超长强制拆分、极端窄行降级、多段输出格式、
同代价决策的唯一性与可复现性。
"""

import os
import random
import unittest

from linebreak.engine import LineBreaker, layout_paragraph, layout_text
from linebreak.kinsoku import parse_kinsoku
from linebreak.tokenizer import CHAR, CJK, WORD, tokenize
from linebreak.widths import WidthTable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")


def sample_path(name):
    return os.path.join(SAMPLES, name)


class WidthTableTests(unittest.TestCase):
    def setUp(self):
        self.table = WidthTable.from_file(sample_path("widths.txt"))

    def test_halfwidth_ascii(self):
        self.assertEqual(self.table.width_of("a"), 1)
        self.assertEqual(self.table.width_of("9"), 1)
        self.assertEqual(self.table.width_of("-"), 1)
        self.assertEqual(self.table.width_of(" "), 1)

    def test_fullwidth_cjk(self):
        self.assertEqual(self.table.width_of("我"), 2)
        self.assertEqual(self.table.width_of("，"), 2)
        self.assertEqual(self.table.width_of("ひ"), 2)
        self.assertEqual(self.table.width_of("—"), 2)

    def test_halfwidth_katakana_is_one(self):
        self.assertEqual(self.table.width_of("ﾊ"), 1)

    def test_default_for_unlisted(self):
        self.assertEqual(WidthTable([]).width_of("a"), 1)
        table = WidthTable([], default=1)
        self.assertEqual(table.width_of("\uE000"), 1)

    def test_from_string_with_comments_and_default(self):
        table = WidthTable.from_string(
            "# 注释\n\nU+0041 U+005A 2\n默认 1\n"
        )
        self.assertEqual(table.width_of("A"), 2)
        self.assertEqual(table.width_of("a"), 1)


class KinsokuTests(unittest.TestCase):
    def test_parse_sections(self):
        no_start, no_end = parse_kinsoku(
            "# 行首禁则：x\n， 。\n\n# 行尾禁则：y\n（ 「\n"
        )
        self.assertEqual(no_start, frozenset({"，", "。"}))
        self.assertEqual(no_end, frozenset({"（", "「"}))


class TokenizerTests(unittest.TestCase):
    def setUp(self):
        self.table = WidthTable.from_file(sample_path("widths.txt"))

    def test_words_and_numbers_are_atomic(self):
        units = tokenize("abc-9 x", self.table)
        self.assertEqual([u[0] for u in units], ["abc-9", "x"])
        self.assertEqual(units[0][2], WORD)

    def test_cjk_and_punctuation_one_char_each(self):
        units = tokenize("我，", self.table)
        self.assertEqual([u[0] for u in units], ["我", "，"])
        self.assertTrue(all(u[2] == CJK for u in units))

    def test_leading_space_attached_to_next_unit(self):
        units = tokenize("我 abc", self.table)
        self.assertEqual([u[0] for u in units], ["我", "abc"])
        self.assertFalse(units[0][3])
        self.assertTrue(units[1][3])

    def test_leading_space_marked_but_render_drops_it(self):
        units = tokenize(" abc", self.table)
        self.assertEqual(len(units), 1)
        self.assertTrue(units[0][3])
        from linebreak.engine import layout_paragraph
        self.assertEqual(
            layout_paragraph(" abc  def", 80, self.table),
            ["abc def"],
        )

    def test_halfwidth_katakana_is_cjk_kind(self):
        units = tokenize("ﾊ", self.table)
        self.assertEqual(units[0][1], 1)
        self.assertEqual(units[0][2], CJK)

    def test_halfwidth_punctuation_is_char_kind(self):
        units = tokenize(",", self.table)
        self.assertEqual(units[0][2], CHAR)


class EngineFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.widths = WidthTable.from_file(sample_path("widths.txt"))
        cls.no_start, cls.no_end = load_kinsoku_file()

    def breaker(self, width):
        return LineBreaker(self.widths, self.no_start, self.no_end, width)

    def layout(self, text, width):
        return self.breaker(width).layout(text)


def load_kinsoku_file():
    from linebreak.kinsoku import load_kinsoku
    return load_kinsoku(sample_path("kinsoku.txt"))


class SampleAcceptanceTests(EngineFixture):
    """samples 下的三段文本与期望结果，逐字节一致即验收通过。"""

    CASES = [("text-1", 24), ("text-2", 20), ("text-3", 32)]

    def test_samples(self):
        for name, width in self.CASES:
            with self.subTest(sample=name):
                text = read_text(f"{name}.txt")
                expected = read_text(f"{name}.expected.txt")
                result = layout_text(
                    text, width, self.widths, self.no_start, self.no_end
                )
                self.assertEqual(result, expected)


def read_text(name):
    with open(sample_path(name), encoding="utf-8") as fh:
        return fh.read()


class GlobalOptimalityTests(EngineFixture):
    def test_not_greedy(self):
        # W=6：贪心会在第 6 个单位后断（后面的标点触发禁则再回退），
        # 全局最优给出 2/3/2 的均衡断法。
        self.assertEqual(
            self.layout("你好，。世界", 6),
            ["你", "好，。", "世界"],
        )

    def test_take_longer_line_on_equal_cost(self):
        # 8 个全角单位、W=12：4/4（空隙 4 罚 26）与 6/2（空隙 4 罚 26）
        # 代价相同；规则要求本行更长，即断在第 6 个单位之后。
        self.assertEqual(
            self.layout("中中中中中中中中", 12),
            ["中中中中中中", "中中"],
        )

    def test_cost_prefers_even_over_packed(self):
        # W=10 时 4/4/3 与 5/5/1 的代价对比：后者最后一行虽短但无代价，
        # 前两行 0+0；4/4/3 是 4+4。最优应把两行填满。
        lines = self.layout("中中中中中中中中中中中", 10)
        self.assertEqual(lines, ["中中中中中", "中中中中中", "中"])


class KinsokuTests(EngineFixture):
    def test_closing_punctuation_chain_kept_together(self):
        lines = self.layout("你好，。世界", 6)
        # 任何一行都不能以行首禁则字符开头
        for line in lines:
            self.assertNotIn(line[0], self.no_start)
        self.assertEqual(lines, ["你", "好，。", "世界"])

    def test_infeasible_kinsoku_falls_back_without_crashing(self):
        # W=2 时 6 个字无论怎么断都会把行首禁则字符顶到行首，
        # 属于降级路径：放宽禁则也要把文本排完。
        lines = self.layout("，。，。，。", 2)
        self.assertEqual("".join(lines), "，。，。，。")

    def test_opening_bracket_not_left_at_line_end(self):
        lines = self.layout("（开括号在中间）测试一下", 8)
        for line in lines:
            self.assertNotIn(line[-1], self.no_end)
        self.assertEqual(lines, ["（开括号", "在中间）", "测试一下"])

    def test_last_line_not_penalized(self):
        # 最后一行再短也不罚空隙，不应为了填满末行而改变前面的断法。
        lines = self.layout("价格是100元", 8)
        self.assertEqual(lines, ["价格是", "100元"])


class AtomicWordTests(EngineFixture):
    def test_hyphenated_word_not_split_when_fits(self):
        self.assertEqual(
            self.layout("a state-of-the-art b", 40),
            ["a state-of-the-art b"],
        )

    def test_hyphenated_word_forced_split_when_too_long(self):
        lines = self.layout("state-of-the-art", 10)
        self.assertEqual(lines, ["state-of-t", "he-art"])
        for line in lines:
            self.assertLessEqual(len(line), 10)

    def test_long_word_between_cjk(self):
        lines = self.layout("超abcdefghij长", 4)
        self.assertEqual(lines, ["超", "abcd", "efgh", "ij长"])

    def test_long_word_fragments_incur_split_penalty(self):
        # 同一长词在更宽行下能放下时绝不拆。
        self.assertEqual(self.layout("abcdefghij", 20), ["abcdefghij"])


class DegradationTests(EngineFixture):
    def test_fullwidth_overflow_when_width_one(self):
        lines = self.layout("中", 1)
        self.assertEqual(lines, ["中"])

    def test_width_one_mixed(self):
        lines = self.layout("中ab", 1)
        self.assertEqual(lines, ["中", "a", "b"])

    def test_width_one_long_word(self):
        lines = self.layout("abcde", 1)
        self.assertEqual(lines, list("abcde"))


class OutputFormatTests(EngineFixture):
    def test_single_paragraph_ends_with_one_lf(self):
        result = layout_text("你好世界", 10, self.widths,
                             self.no_start, self.no_end)
        self.assertTrue(result.endswith("\n"))
        self.assertFalse(result.endswith("\n\n"))

    def test_paragraphs_separated_by_blank_line(self):
        result = layout_text("第一段测试。\n\n第二段测试。", 10,
                             self.widths, self.no_start, self.no_end)
        self.assertEqual(result, "第一段测\n试。\n\n第二段测\n试。\n")

    def test_inner_newline_collapsed_to_space(self):
        result = layout_text("第一段\n换行", 80, self.widths,
                             self.no_start, self.no_end)
        self.assertEqual(result, "第一段 换行\n")

    def test_empty_input(self):
        self.assertEqual(layout_text("", 10, self.widths), "")
        self.assertEqual(layout_text("\n\n\n", 10, self.widths), "")

    def test_no_trailing_spaces(self):
        result = layout_text("请把 state 渲染", 20, self.widths,
                             self.no_start, self.no_end)
        for line in result.splitlines():
            self.assertFalse(line.endswith(" "))
            self.assertFalse(line.startswith(" "))


class DeterminismTests(EngineFixture):
    SAMPLE_POOL = (
        "我们把这个排版工具的断行引擎重写了一遍标点不能跑到行首，"
        "state-of-the-art Markdown parser 100 元（示例）「引号」。 "
    )

    def _random_text(self, seed):
        random.seed(seed)
        return "".join(random.choice(self.SAMPLE_POOL) for _ in range(5000))

    def test_repeated_runs_identical(self):
        text = self._random_text(7)
        first = layout_paragraph(text, 32, self.widths,
                                 self.no_start, self.no_end)
        second = layout_paragraph(text, 32, self.widths,
                                  self.no_start, self.no_end)
        self.assertEqual(first, second)

    def test_width_does_not_change_result_for_other_widths(self):
        # 同一引擎对象重复使用，结果不依赖内部状态或遍历顺序。
        breaker = self.breaker(30)
        text = self._random_text(9)
        self.assertEqual(breaker.layout(text), breaker.layout(text))


class ApiTests(unittest.TestCase):
    def test_invalid_width(self):
        table = WidthTable.from_file(sample_path("widths.txt"))
        with self.assertRaises(ValueError):
            LineBreaker(table, max_width=0)


if __name__ == "__main__":
    unittest.main()
