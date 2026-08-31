#!/usr/bin/env python3
"""リリース本文を組み立てる。

CHANGELOG.md からその版の節を抜き出し、毎回同じ案内文（`.github/release-common.md`）
と合わせて 1 つの本文にする。

パッチノートの実体を CHANGELOG.md 側に置くのは、
同じ内容を 2 か所へ書かせないため。
CHANGELOG に節が無ければ失敗させるので、書き忘れたままリリースできない。

使い方:
    python3 spec/tools/release_notes.py 1.1.0
    python3 spec/tools/release_notes.py 1.1.0 --output notes.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: 版ごとの節の見出し。`## [1.1.0]` の形。
SECTION = re.compile(r"^## \[([^\]]+)\]\s*$")

#: 節の終わりとみなす見出し。版以外の `## 〜` でも区切る。
HEADING = re.compile(r"^## ")

#: リポジトリ内への相対リンク。リリースのページからは辿れないので絶対URLへ直す。
RELATIVE_LINK = re.compile(r"\]\((?!https?://|#)([^)]+)\)")

#: 相対リンクの解決先。
REPOSITORY_URL = "https://github.com/ScriptArts/SpringNBTLibrary"


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def extract_section(changelog: str, version: str):
    """CHANGELOG から指定した版の節の中身を取り出す。無ければ None。"""
    lines = changelog.split("\n")
    start = None

    # 見出しを上から探し、見つかったら次の見出しまでを本文とする
    for index, line in enumerate(lines):
        if start is not None and HEADING.match(line) is not None:
            return "\n".join(lines[start:index]).strip("\n")

        match = SECTION.match(line)

        if match is not None and match.group(1) == version:
            start = index + 1

    if start is None:
        return None

    return "\n".join(lines[start:]).strip("\n")


def build(version: str) -> str:
    """その版のリリース本文を組み立てる。"""
    changelog = read_text(os.path.join(REPO_ROOT, "CHANGELOG.md"))
    body = extract_section(changelog, version)

    if body is None:
        raise SystemExit(
            "CHANGELOG.md に「## [%s]」の節が無い。\n"
            "リリースする前に、その版の変更点を書くこと。" % version)

    common = read_text(os.path.join(REPO_ROOT, ".github", "release-common.md"))
    text = "## 変更点\n\n%s\n\n---\n\n%s" % (body.strip(), common.strip()) + "\n"
    return absolute_links(text, version)


def absolute_links(text: str, version: str) -> str:
    """リポジトリ内への相対リンクを、そのタグを指す絶対URLへ直す。

    リリースのページは相対リンクの起点が違うので、そのままでは辿れない。
    """
    prefix = "%s/blob/v%s/" % (REPOSITORY_URL, version)
    return RELATIVE_LINK.sub(lambda m: "](" + prefix + m.group(1) + ")", text)


def main() -> int:
    parser = argparse.ArgumentParser(description="リリース本文を組み立てる")
    parser.add_argument("version", help="版番号（例: 1.1.0）")
    parser.add_argument("--output", help="書き出し先。省略すると標準出力")
    args = parser.parse_args()

    text = build(args.version)

    # 出力先が指定されていればファイルへ書く
    if args.output is None:
        sys.stdout.write(text)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)

        print("リリース本文を %s へ書き出した（%d 行）"
              % (args.output, len(text.split("\n"))))

    return 0


if __name__ == "__main__":
    sys.exit(main())
