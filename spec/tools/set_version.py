#!/usr/bin/env python3
"""パッケージ設定の版を書き換える。

版はリリースのタグ（`v1.2.3`）だけで決める。人が版を書く場所を1つにするため。
リポジトリ内のパッケージ設定は、常に仮の版`0.0.0`のままにしておき、
releaseワークフローがビルドの直前にこのツールでタグの版を書き込む。

使い方:
    python3 spec/tools/set_version.py 1.2.3              # 全パッケージ設定を1.2.3にする（CI用）
    python3 spec/tools/set_version.py --check            # 全部が0.0.0のままか確かめる（lint用）
    python3 spec/tools/set_version.py --changelog-latest # CHANGELOGのいちばん新しい版を出す
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: リポジトリに置いておく仮の版。
PLACEHOLDER = "0.0.0"

#: 版として受け付ける形。`x.y.z`だけを許す。
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

#: CHANGELOGの版ごとの節の見出し。
CHANGELOG_HEADING = re.compile(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", re.MULTILINE)

#: 版が書かれている場所。
#:
#: (ファイル, 版の前までに一致する正規表現, 版の後ろに一致する正規表現)
#: どれも、そのファイルでちょうど1か所に一致しなければならない。
TARGETS = [
    ("csharp/src/SpringNBTLibrary/SpringNBTLibrary.csproj",
     r"<Version>", r"</Version>"),
    ("java/pom.xml",
     r"<artifactId>spring-nbt-library</artifactId>\s*<version>", r"</version>"),
    ("typescript/package.json",
     r'\A\{\s*"name": "spring-nbt-library",\s*"version": "', r'"'),
    ("typescript/package-lock.json",
     r'\A\{\s*"name": "spring-nbt-library",\s*"version": "', r'"'),
    ("typescript/package-lock.json",
     r'"": \{\s*"name": "spring-nbt-library",\s*"version": "', r'"'),
    ("python/pyproject.toml",
     r'\[project\]\s*name = "spring-nbt-library"\s*version = "', r'"'),
    ("rust/Cargo.toml",
     r'\[package\]\s*name = "spring-nbt-library"\s*version = "', r'"'),
    ("rust/Cargo.lock",
     r'name = "spring-nbt-library"\s*version = "', r'"'),
]


def read(path: str) -> str:
    with open(os.path.join(REPO_ROOT, path), "r", encoding="utf-8") as handle:
        return handle.read()


def write(path: str, text: str) -> None:
    with open(os.path.join(REPO_ROOT, path), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def pattern_of(before: str, after: str) -> re.Pattern:
    """版の部分だけを取り出せる正規表現を組み立てる。"""
    return re.compile("(" + before + ")([^\"<]*)(" + after + ")")


def current_versions():
    """各場所に書かれている版を、(ファイル, 版)の一覧で返す。"""
    found = []

    # 場所ごとに、ちょうど1か所に一致することを確かめながら版を拾う
    for path, before, after in TARGETS:
        matches = pattern_of(before, after).findall(read(path))

        if len(matches) != 1:
            raise SystemExit("%s で版の場所が %d か所に一致した（1か所のはず）" % (path, len(matches)))

        found.append((path, matches[0][1]))

    return found


def set_version(version: str) -> None:
    """全部の場所の版を書き換える。"""
    # 場所ごとに、版の部分だけを差し替える
    for path, before, after in TARGETS:
        text = read(path)
        replaced, count = pattern_of(before, after).subn(
            lambda match: match.group(1) + version + match.group(3), text)

        if count != 1:
            raise SystemExit("%s で版の場所が %d か所に一致した（1か所のはず）" % (path, count))

        write(path, replaced)
        print("%s: %s" % (path, version))


def check_placeholder() -> int:
    """全部の場所が仮の版のままか確かめる。違えば終了コード1。"""
    wrong = []

    # 仮の版になっていない場所を集める
    for path, version in current_versions():
        if version != PLACEHOLDER:
            wrong.append((path, version))

    if len(wrong) == 0:
        print("パッケージ設定の版はすべて %s のまま。" % PLACEHOLDER)
        return 0

    # 版はタグで決めるので、リポジトリに具体的な版を書いてはいけない
    for path, version in wrong:
        print("%s の版が %s になっている。%s に戻す（版はリリースのタグで決まる）" % (path, version, PLACEHOLDER))

    return 1


def changelog_latest() -> str:
    """CHANGELOGに書かれている、いちばん新しい版を返す。"""
    match = CHANGELOG_HEADING.search(read("CHANGELOG.md"))

    if match is None:
        raise SystemExit("CHANGELOG.md に `## [x.y.z]` の節が無い")

    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="パッケージ設定の版を書き換える")
    parser.add_argument("version", nargs="?", help="書き込む版（x.y.z。先頭のvは付けても付けなくてもよい）")
    parser.add_argument("--check", action="store_true", help="全部が仮の版0.0.0のままか確かめる")
    parser.add_argument("--changelog-latest", action="store_true",
                        help="CHANGELOGのいちばん新しい版を出す")
    args = parser.parse_args()

    if args.check:
        return check_placeholder()

    if args.changelog_latest:
        print(changelog_latest())
        return 0

    if args.version is None:
        parser.error("版を指定するか、--check / --changelog-latest を付けること")

    version = args.version

    # タグ名をそのまま渡せるよう、先頭のvは外す
    if version.startswith("v"):
        version = version[1:]

    if VERSION.match(version) is None:
        parser.error("版は x.y.z の形で指定すること: %s" % args.version)

    set_version(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
