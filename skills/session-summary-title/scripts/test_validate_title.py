"""Validate assigned Han characters, length, and the standalone CLI contract."""

import subprocess
import sys
import unittest

import validate_title


TITLE = "审查变异注释项目质量缺陷"


class ValidateTitleTest(unittest.TestCase):
    def test_twelve_han_characters_are_valid(self):
        validate_title.validate_title(TITLE)

    def test_wrong_length_and_non_han_characters_are_rejected(self):
        for title in (
            "", TITLE[:-1], TITLE + "测", TITLE[:-1] + "A",
            TITLE[:-1] + "1", TITLE[:-1] + "。", TITLE[:-1] + "😀",
            " " + TITLE, TITLE + "\n", TITLE[:-1] + "\u200d",
        ):
            with self.subTest(title=title):
                with self.assertRaises(ValueError):
                    validate_title.validate_title(title)

    def test_unassigned_codepoint_inside_old_range_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_title.validate_title(chr(0x2F000) * 12)

    def test_assigned_supplementary_ideographs_are_supported(self):
        for character in (chr(0x20000), chr(0x30000), chr(0xF900)):
            with self.subTest(character=character):
                validate_title.validate_title(character * 12)

    def test_radicals_and_iteration_marks_are_not_title_characters(self):
        for character in ("々", "〇", "⼀", "〆"):
            with self.subTest(character=character):
                self.assertFalse(validate_title.is_han(character))

    def test_standalone_cli_exit_and_output(self):
        command = [sys.executable, "-B", validate_title.__file__]
        good = subprocess.run(command + [TITLE], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0)
        self.assertEqual(good.stdout.strip(), "OK")
        bad = subprocess.run(command + [TITLE + "。"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertNotIn("OK", bad.stdout)


if __name__ == "__main__":
    unittest.main()
