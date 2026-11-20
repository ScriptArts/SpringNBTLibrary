#!/usr/bin/env python3
"""パッケージに入れるREADMEの相対リンクを、そのタグを指す絶対URLへ直す。

npm / PyPI / NuGetのパッケージのページは、READMEだけを表示する。
リポジトリ内への相対リンクはそこから辿れないので、組み立てる直前に書き換える。
リポジトリのREADMEは相対リンクのまま残す（GitHubと手元ではそのほうが読みやすい）。

ファイルをその場で書き換える。releaseワークフローの中で使う前提で、
書き換えたファイルはコミットしない。

使い方:
    python3 spec/tools/readme_links.py 3.0.1 README.md python/README.md typescript/README.md
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: リポジトリ内への相対リンク。外部のURLと、同じページ内の見出しへのリンクは除く。
RELATIVE_LINK = re.compile(r"\]\((?!https?://|mailto:|#)([^)]+)\)")

#: 相対リンクの解決先。
REPOSITORY_URL = "https://github.com/ScriptArts/SpringNBTLibrary"


def absolute_url(target: str, readme_dir: str, version: str) -> str:
    """READMEのあるディレクトリから見た相対パスを、そのタグを指す絶対URLにする。"""
    path = target
    fragment = ""

    # 見出しへの飛び先は、パスを直したあとに付け直す
    if "#" in target:
        path, fragment = target.split("#", 1)
        fragment = "#" + fragment

    resolved = posixpath.normpath(posixpath.join(readme_dir, path))

    # リポジトリ直下のREADMEから見た「.」はリポジトリのトップを指す
    if resolved == ".":
        return "%s/tree/v%s%s" % (REPOSITORY_URL, version, fragment)

    return "%s/blob/v%s/%s%s" % (REPOSITORY_URL, version, resolved, fragment)


def rewrite(text: str, readme_dir: str, version: str) -> str:
    """本文の中の相対リンクをすべて絶対URLへ直す。"""
    return RELATIVE_LINK.sub(
        lambda match: "](" + absolute_url(match.group(1), readme_dir, version) + ")", text)


def main() -> int:
    parser = argparse.ArgumentParser(description="READMEの相対リンクを絶対URLへ直す")
    parser.add_argument("version", help="版番号（例: 3.0.1）")
    parser.add_argument("readmes", nargs="+", help="書き換えるREADME（リポジトリ直下からのパス）")
    args = parser.parse_args()

    # 指定されたREADMEを1つずつ書き換える
    for readme in args.readmes:
        path = os.path.join(REPO_ROOT, readme)
        readme_dir = posixpath.dirname(readme.replace(os.sep, "/"))

        with open(path, encoding="utf-8") as handle:
            text = handle.read()

        with open(path, "w", encoding="utf-8") as handle:
            handle.write(rewrite(text, readme_dir, args.version))

        print("%sのリンクを絶対URLへ直した" % readme)

    return 0


if __name__ == "__main__":
    sys.exit(main())
