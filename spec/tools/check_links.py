#!/usr/bin/env python3
"""ドキュメント内のリンク切れを調べる。

`docs/` は5系統に分かれていて相互に行き来する作りなので、
ファイルを増やしたり動かしたりするとリンクが静かに死ぬ。
読み手がそこで止まってしまうため、CI で検出する。

調べるもの:

1. 相対リンクの指す先のファイルが実在するか
2. `#見出し` の指す見出しがそのファイルに実在するか

外部リンク（http/https）は対象外。ネットワークに依存すると
CI がその日の外部サイトの都合で落ちるようになるため。

使い方:
    python3 spec/tools/check_links.py

仕様: docs/adr/0009-static-api-extraction.md
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: `[表示](リンク先)` の形。画像も同じ形なので一緒に拾う。
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

#: Markdown の見出し。
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")

#: コードブロックの区切り。この中のリンクは例示なので対象外。
FENCE = re.compile(r"^\s*```")

#: リンク先として許すが、実在を確かめないもの。
SKIPPED_PREFIXES = ("http://", "https://", "mailto:", "#")


def slugify(text: str) -> str:
    """見出しを GitHub のアンカー名へ写す。

    GitHub は見出しを小文字にし、記号を落とし、空白をハイフンに変える。
    日本語はそのまま残る。
    """
    # インラインのコード・強調・リンクの装飾を落とす
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

    result = []

    # 英数字・ハイフン・アンダースコアと、日本語などの文字を残す
    for character in text.lower():
        if character.isalnum() or character in "-_":
            result.append(character)
        elif character in " \t":
            result.append("-")
        elif unicodedata.category(character).startswith("L"):
            result.append(character)

    return "".join(result)


def collect_headings(path: str):
    """ファイル内の見出しのアンカー名を集める。"""
    anchors = set()
    in_fence = False

    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            # コードブロックの中の # はコメントなので見出しではない
            if FENCE.match(line):
                in_fence = not in_fence
                continue

            if in_fence:
                continue

            match = HEADING.match(line.rstrip("\n"))

            if match is not None:
                anchors.add(slugify(match.group(2)))

    return anchors


def markdown_files():
    """検査対象の Markdown を列挙する。"""
    found = []

    # docs/ 配下は全部、言語ディレクトリは README だけを見る
    for language in ("csharp", "java", "typescript", "python", "rust"):
        candidate = os.path.join(REPO_ROOT, language, "README.md")

        if os.path.exists(candidate):
            found.append(candidate)

    base = os.path.join(REPO_ROOT, "docs")

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [name for name in dirnames
                       if name not in (".git", "node_modules", "target", "bin",
                                       "obj", "dist", "__pycache__", ".venv")]

        for filename in filenames:
            if filename.endswith(".md"):
                found.append(os.path.join(dirpath, filename))

    # リポジトリ直下の README なども対象にする（1 階層だけ）
    for filename in os.listdir(REPO_ROOT):
        if filename.endswith(".md"):
            found.append(os.path.join(REPO_ROOT, filename))

    return sorted(set(found))


def main() -> int:
    problems = []
    anchors_cache = {}

    for path in markdown_files():
        relative = os.path.relpath(path, REPO_ROOT)
        in_fence = False

        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().split("\n")

        # 行ごとに見て、コードブロックの中は飛ばす
        for number, line in enumerate(lines, start=1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue

            if in_fence:
                continue

            for target in LINK.findall(line):
                if target.startswith(SKIPPED_PREFIXES):
                    continue

                if "#" in target:
                    file_part, anchor = target.split("#", 1)
                else:
                    file_part, anchor = target, ""

                if len(file_part) == 0:
                    resolved = path
                else:
                    resolved = os.path.normpath(
                        os.path.join(os.path.dirname(path), file_part))

                if not os.path.exists(resolved):
                    problems.append("%s:%d 参照先が無い: %s" % (relative, number, target))
                    continue

                if len(anchor) == 0 or not resolved.endswith(".md"):
                    continue

                if resolved not in anchors_cache:
                    anchors_cache[resolved] = collect_headings(resolved)

                if anchor not in anchors_cache[resolved]:
                    problems.append("%s:%d 見出しが無い: %s" % (relative, number, target))

    print("Markdown %d 件を検査した。" % len(markdown_files()))

    if len(problems) == 0:
        print("リンク切れなし。")
        return 0

    print()
    print("!!! リンク切れ %d 件 !!!" % len(problems))

    for problem in problems:
        print("  - %s" % problem)

    return 1


if __name__ == "__main__":
    sys.exit(main())
