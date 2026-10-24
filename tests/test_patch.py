"""Tests for the standard-library patch applier.

Round-trip tests generate unified diffs with difflib from seeded random edits
and check that applying them reproduces the edited file exactly. Fixed patches
cover git's output format, line endings, and rejected changes.
"""

import difflib
import os
import random
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from builderer.details.patch import apply_patch, parse_patch


# A unified diff of old -> new, with git's no-newline markers
def _diff(old: str, new: str, context: int) -> str:
    out = []
    for line in difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile="a/f.txt",
        tofile="b/f.txt",
        n=context,
    ):
        out.append(line)
        if not line.endswith("\n"):
            out.append("\n\\ No newline at end of file\n")
    return "".join(out)


def _random_lines(rng: random.Random, count: int, prefix: str) -> list:
    return [f"{prefix} {rng.randrange(8)}" for _ in range(count)]


def _join(lines: list, eol: str, final_eol: bool) -> str:
    return eol.join(lines) + (eol if lines and final_eol else "")


class TestPatch(unittest.TestCase):
    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.root = Path(self._scratch.name) / "tree"
        self.root.mkdir()
        self.patch_file = Path(self._scratch.name) / "change.patch"

    def tearDown(self):
        self._scratch.cleanup()

    def _write(self, rel: str, text: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())

    def _read(self, rel: str) -> str:
        return (self.root / rel).read_bytes().decode()

    def _apply(self, patch: str):
        self.patch_file.write_bytes(patch.encode())
        apply_patch(self.root, self.patch_file)

    def test_random_edits_round_trip(self):
        rng = random.Random(1234)
        for iteration in range(2000):
            eol = rng.choice(["\n", "\r\n"])
            lines = _random_lines(rng, rng.randrange(12), "line")
            old = _join(lines, eol, final_eol=rng.randrange(4) != 0)
            for _ in range(rng.randrange(1, 4)):
                index = rng.randrange(len(lines) + 1)
                if rng.randrange(3) == 0 or not lines:
                    lines[index:index] = _random_lines(rng, 1, "new")
                elif rng.randrange(2) == 0:
                    del lines[min(index, len(lines) - 1)]
                else:
                    lines[min(index, len(lines) - 1)] = f"changed {iteration}"
            new = _join(lines, eol, final_eol=rng.randrange(4) != 0)
            if old == new:
                continue
            with self.subTest(iteration=iteration, old=old, new=new):
                self._write("f.txt", old)
                self._apply(_diff(old, new, context=rng.choice([0, 1, 3])))
                self.assertEqual(self._read("f.txt"), new)

    def test_git_format_patch(self):
        self._write("src/a.c", "int a;\nint b;\nint c;\n")
        self._write("old.txt", "bye\n")
        self._apply(dedent("""\
            From 1234 Mon Sep 17 00:00:00 2001
            From: Someone <someone@example.com>
            Subject: [PATCH] several changes

            --- a dashed line in the commit message
            ---
             src/a.c | 2 +-

            diff --git a/src/a.c b/src/a.c
            index 1111111..2222222 100644
            --- a/src/a.c
            +++ b/src/a.c
            @@ -1,3 +1,3 @@
             int a;
            -int b;
            +long b;
             int c;
            diff --git a/new.sh b/new.sh
            new file mode 100755
            index 0000000..3333333
            --- /dev/null
            +++ b/new.sh
            @@ -0,0 +1 @@
            +echo hi
            diff --git a/old.txt b/old.txt
            deleted file mode 100644
            index 4444444..0000000
            --- a/old.txt
            +++ /dev/null
            @@ -1 +0,0 @@
            -bye
            --\x20
            2.43.0
            """))
        self.assertEqual(self._read("src/a.c"), "int a;\nlong b;\nint c;\n")
        self.assertEqual(self._read("new.sh"), "echo hi\n")
        self.assertFalse((self.root / "old.txt").exists())
        if os.name == "posix":
            self.assertTrue(os.stat(self.root / "new.sh").st_mode & 0o100)

    def test_quoted_path_and_timestamps(self):
        self._write("dir with space/é.txt", "x\n")
        self._write("f.txt", "x\n")
        self._apply(dedent("""\
            --- "a/dir with space/\\303\\251.txt"
            +++ "b/dir with space/\\303\\251.txt"
            @@ -1 +1 @@
            -x
            +y
            --- a/f.txt\t2024-01-01 00:00:00.000000000 +0000
            +++ b/f.txt\t2024-01-02 00:00:00.000000000 +0000
            @@ -1 +1 @@
            -x
            +y
            """))
        self.assertEqual(self._read("dir with space/é.txt"), "y\n")
        self.assertEqual(self._read("f.txt"), "y\n")

    def test_hunks_apply_at_offset(self):
        self._write("f.txt", "pad\n" + "".join(f"{i}\n" for i in range(20)))
        self._apply(dedent("""\
            --- a/f.txt
            +++ b/f.txt
            @@ -1,2 +1,2 @@
             0
            -1
            +one
            @@ -15,2 +15,2 @@
             14
            -15
            +fifteen
            """))
        lines = self._read("f.txt").splitlines()
        self.assertEqual((lines[2], lines[16]), ("one", "fifteen"))

    def test_blank_context_line_without_space(self):
        self._write("f.txt", "a\n\nb\n")
        self._apply(dedent("""\
            --- a/f.txt
            +++ b/f.txt
            @@ -1,3 +1,3 @@
             a

            -b
            +B
            """))
        self.assertEqual(self._read("f.txt"), "a\n\nB\n")

    # A lone "\r" is line content, and added lines take the file's line endings
    # whatever the patch's line endings are.
    def test_line_endings_follow_the_file(self):
        patch = dedent("""\
            --- a/f.txt
            +++ b/f.txt
            @@ -1,3 +1,3 @@
             a\rb
            -c
            +C
             d
            """)
        for file_eol, patch_eol in [("\r\n", "\n"), ("\n", "\r\n")]:
            with self.subTest(file_eol=repr(file_eol), patch_eol=repr(patch_eol)):
                self._write("f.txt", file_eol.join(["a\rb", "c", "d", ""]))
                self._apply(patch.replace("\n", patch_eol))
                self.assertEqual(
                    self._read("f.txt"), file_eol.join(["a\rb", "C", "d", ""])
                )

    def test_failed_patch_leaves_tree_untouched(self):
        self._write("a.txt", "a\n")
        self._write("b.txt", "b\n")
        with self.assertRaisesRegex(ValueError, r"b\.txt @@ .*does not match"):
            self._apply(dedent("""\
                --- a/a.txt
                +++ b/a.txt
                @@ -1 +1 @@
                -a
                +A
                --- a/b.txt
                +++ b/b.txt
                @@ -1 +1 @@
                -not b
                +B
                """))
        self.assertEqual(self._read("a.txt"), "a\n")

    def test_unsupported_patches_are_rejected(self):
        cases = {
            "similarity index": """\
                diff --git a/x b/y
                similarity index 100%
                rename from x
                rename to y
                """,
            "old mode": """\
                diff --git a/x b/x
                old mode 100644
                new mode 100755
                """,
            "unsupported binary": """\
                diff --git a/x.png b/x.png
                Binary files a/x.png and b/x.png differ
                """,
            "without edits": """\
                diff --git a/e b/e
                new file mode 100644
                index 0000000..e69de29
                """,
            "unsupported rename": """\
                --- a/x
                +++ b/y
                @@ -1 +1 @@
                -a
                +b
                """,
            "no a/ or b/ prefix": """\
                --- x
                +++ x
                @@ -1 +1 @@
                -a
                +b
                """,
            "truncated": """\
                --- a/f
                +++ b/f
                @@ -1,2 +1,2 @@
                -a
                +b
                """,
            "more lines than its header": """\
                --- a/f
                +++ b/f
                @@ -1 +1 @@
                -a
                -b
                +c
                """,
            "no file changes": "hello\n",
        }
        for message, patch in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    parse_patch(dedent(patch).encode())

    def test_invalid_changes_are_rejected(self):
        self._write("exists.txt", "a\nb\n")
        cases = {
            "outside the patched tree": """\
                --- /dev/null
                +++ b/../escape.txt
                @@ -0,0 +1 @@
                +x
                """,
            "already exists": """\
                --- /dev/null
                +++ b/exists.txt
                @@ -0,0 +1 @@
                +x
                """,
            "does not exist": """\
                --- a/missing.txt
                +++ b/missing.txt
                @@ -1 +1 @@
                -a
                +b
                """,
            "not empty": """\
                --- a/exists.txt
                +++ /dev/null
                @@ -1 +0,0 @@
                -a
                """,
        }
        for message, patch in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self._apply(dedent(patch))
