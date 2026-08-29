#!/usr/bin/env python3
"""ドキュメントと実装が食い違っていないかを機械で確かめる。

1人で5言語ぶんの API を人手で揃え続けるのは必ず破綻する。
このツールが CI でそれを守る。

やること:

1. **型の一致** — 全言語の公開型の論理名集合が一致するか。
   言語の性質による差異は `extract_api.EXPECTED_TYPE_GAPS` に理由つきで登録し、
   そこに無い差異が出たら失敗させる
2. **`docs/api/` の再生成** — 対応表は実装から生成する。
   生成結果と現在のファイルが違えば失敗させる（`--write` で書き直せる）
3. **`docs/features.md` の照合** — ✅ が付いている機能に対応する型が
   その言語に実在するか

使い方:
    python3 spec/tools/check_docs_sync.py          # 検査する（CI 用）
    python3 spec/tools/check_docs_sync.py --write  # docs/api/ を書き直す

仕様: docs/spec/00-conventions.md 3章 / docs/adr/0009-static-api-extraction.md
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extract_api import (  # noqa: E402
    EXPECTED_TYPE_GAPS,
    LANGUAGE_ORDER,
    MODULE_LEVEL,
    REPO_ROOT,
    extract_all,
)

#: 表の見出しに使う言語名。
LANGUAGE_LABELS = {
    "csharp": "C#",
    "java": "Java",
    "typescript": "TypeScript",
    "python": "Python",
    "rust": "Rust",
}

#: 生成部分の目印。この間だけを入れ替える。
GENERATED_START = "<!-- generated:start -->"
GENERATED_END = "<!-- generated:end -->"

#: `docs/api/<ファイル>.md` に、どのレイヤの型を載せるか。
#:
#: 型はソースのディレクトリではなく、利用者から見た役割で分ける。
API_PAGES = {
    "nbt": {
        "title": "NBT",
        "types": [
            "TagType", "NbtTag", "NbtByte", "NbtShort", "NbtInt", "NbtLong",
            "NbtFloat", "NbtDouble", "NbtByteArray", "NbtIntArray", "NbtLongArray",
            "NbtString", "NbtList", "NbtCompound",
            "NamedTag", "Compression", "NbtFormat",
            "NbtReadOptions", "NbtWriteOptions",
            MODULE_LEVEL,
        ],
    },
    "anvil": {
        "title": "Anvil",
        "types": [
            "RegionFile", "RegionFolder", "RegionFileMode",
            "ChunkPos", "RegionPos", "ChunkCompression", "RawChunk",
        ],
    },
    "world": {
        "title": "World",
        "types": [
            "MinecraftWorld", "WorldOpenOptions", "LevelData", "Dimension",
            "Chunk", "ChunkSection", "ChunkReadOptions", "ChunkWriteOptions",
            "VersionMismatchAction",
            "BlockState", "PalettedContainer", "BitStorage",
        ],
    },
}

#: `docs/api/` に載せない型。エラーモデルは `docs/guide/06` が本体。
API_EXCLUDED_TYPES = {"SpringNbtError", "ErrorCode"}


class Report:
    """検出した不一致を溜める。"""

    def __init__(self) -> None:
        self.problems = []

    def add(self, message: str) -> None:
        self.problems.append(message)

    def ok(self) -> bool:
        return len(self.problems) == 0


# ---------------------------------------------------------------------------
# 1. 型の一致
# ---------------------------------------------------------------------------

def check_types(apis, report: Report) -> None:
    """全言語で公開型の論理名集合が一致するかを見る。"""
    all_types = set()

    for api in apis.values():
        all_types |= set(api.members.keys())

    # 型ごとに、どの言語に無いかを調べる
    for type_name in sorted(all_types):
        missing = [name for name in LANGUAGE_ORDER if not apis[name].has(type_name)]
        expected = EXPECTED_TYPE_GAPS.get(type_name, [])

        if sorted(missing) == sorted(expected):
            continue

        unexpected = [name for name in missing if name not in expected]

        if len(unexpected) > 0:
            report.add(
                "型 %s が %s に無い。実装漏れなら足す。言語の性質による差なら "
                "extract_api.EXPECTED_TYPE_GAPS へ理由つきで登録する"
                % (type_name, "/".join(unexpected)))

        resolved = [name for name in expected if name not in missing]

        if len(resolved) > 0:
            report.add(
                "型 %s は %s に無い想定だが実在する。"
                "extract_api.EXPECTED_TYPE_GAPS から外す"
                % (type_name, "/".join(resolved)))


# ---------------------------------------------------------------------------
# 2. docs/api/ の生成
# ---------------------------------------------------------------------------

def render_api_page(page_id: str, page, apis) -> str:
    """1 ページぶんの対応表を組み立てる。"""
    lines = []
    lines.append("| 論理名 | " + " | ".join(LANGUAGE_LABELS[name] for name in LANGUAGE_ORDER)
                 + " | 概要 |")
    lines.append("|---|" + "---|" * (len(LANGUAGE_ORDER) + 1))

    csharp = apis["csharp"]

    # 型ごとに、見出し行とメンバ行を並べる
    for type_name in page["types"]:
        if type_name in API_EXCLUDED_TYPES:
            continue

        if type_name == MODULE_LEVEL:
            label = "（モジュール関数）"
            doc = "自由関数。C# / Java には自由関数が無いので静的クラスに置く"
            cells = ["—"] * len(LANGUAGE_ORDER)
        else:
            label = "**%s**" % type_name
            doc = csharp.type_docs.get(type_name, "")
            cells = [type_display(apis[name], type_name) for name in LANGUAGE_ORDER]

        lines.append("| %s | %s | %s |" % (label, " | ".join(cells), doc))

        # メンバは論理名の昇順。言語間で並びがぶれないように
        for member in sorted(collect_members(apis, type_name)):
            member_cells = [member_display(apis[name], type_name, member)
                            for name in LANGUAGE_ORDER]
            member_doc = csharp.member_docs.get((type_name, member), "")
            lines.append("| `%s` | %s | %s |"
                         % (member, " | ".join(member_cells), member_doc))

    return "\n".join(lines)


def collect_members(apis, type_name: str):
    """その型のメンバ論理名を、全言語ぶん集める。"""
    found = set()

    for api in apis.values():
        if type_name in api.members:
            found |= set(api.members[type_name].keys())

    return found


def type_display(api, type_name: str) -> str:
    """その言語での型名。無ければ「—」。"""
    if not api.has(type_name):
        return "—"

    actual = api.actual(type_name)

    if len(actual) == 0:
        return "—"

    return "`%s`" % actual


def member_display(api, type_name: str, member: str) -> str:
    """その言語でのメンバ名。無ければ「—」。"""
    actual = api.actual(type_name, member)

    if len(actual) == 0:
        return "—"

    return "`%s`" % actual


def api_page_path(page_id: str) -> str:
    return os.path.join(REPO_ROOT, "docs", "api", "%s.md" % page_id)


def sync_api_pages(apis, write: bool, report: Report) -> None:
    """docs/api/*.md の生成部分を作り直し、書くか照合するかする。"""
    for page_id, page in API_PAGES.items():
        path = api_page_path(page_id)

        if not os.path.exists(path):
            report.add("docs/api/%s.md が無い。--write で生成する" % page_id)
            continue

        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        if GENERATED_START not in content or GENERATED_END not in content:
            report.add("docs/api/%s.md に %s / %s の目印が無い"
                       % (page_id, GENERATED_START, GENERATED_END))
            continue

        head = content[:content.index(GENERATED_START) + len(GENERATED_START)]
        tail = content[content.index(GENERATED_END):]
        table = render_api_page(page_id, page, apis)
        updated = head + "\n\n" + table + "\n\n" + tail

        if updated == content:
            continue

        # 中身が変わっているなら、書き直すか失敗させる
        if write:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(updated)

            print("更新: docs/api/%s.md" % page_id)
        else:
            report.add("docs/api/%s.md が実装と食い違っている。"
                       "`python3 spec/tools/check_docs_sync.py --write` で直す" % page_id)


def check_api_coverage(apis, report: Report) -> None:
    """docs/api/ のどのページにも載っていない公開型が無いかを見る。"""
    listed = set()

    for page in API_PAGES.values():
        listed |= set(page["types"])

    for type_name in sorted(apis["csharp"].members.keys()):
        if type_name in listed or type_name in API_EXCLUDED_TYPES:
            continue

        report.add("型 %s が docs/api/ のどのページにも載っていない。"
                   "check_docs_sync.API_PAGES に足す" % type_name)


# ---------------------------------------------------------------------------
# 3. docs/features.md の照合
# ---------------------------------------------------------------------------

#: features.md の行と、その機能を代表する型の対応。
#:
#: ✅ が付いている言語にその型が実在するかを確かめる。
#: 表のすべての行を機械検証できるわけではないので、
#: 型の有無で判定できる機能だけを載せる。
FEATURE_TYPES = {
    "SNBT パース": MODULE_LEVEL,
    "リージョンファイル": "RegionFile",
    "`region/` `entities/` `poi/` の横断アクセス": "RegionFolder",
    "`level.dat` の読み込み": "MinecraftWorld",
    "標準3次元 + カスタム次元の解決": "Dimension",
    "チャンクの解釈": "Chunk",
    "`BlockState` の文字列表現": "BlockState",
    "パレット自動拡張とビット幅の再計算": "PalettedContainer",
    "DataVersion 不一致時の警告／エラー切替": "VersionMismatchAction",
}

#: features.md の言語列の並び。表の見出しと同じ順。
FEATURE_COLUMNS = ["csharp", "java", "typescript", "python", "rust"]


def check_features(apis, report: Report) -> None:
    """features.md で ✅ の機能に対応する型が実在するかを見る。"""
    path = os.path.join(REPO_ROOT, "docs", "features.md")

    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().split("\n")

    for line in lines:
        if not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.split("|")[1:-1]]

        # 機能名 + 5言語 + 仕様 + 備考 の形でなければ対象外
        if len(cells) < 6:
            continue

        type_name = None

        # 行の見出しから、対応する型を引く
        for key, value in FEATURE_TYPES.items():
            if cells[0].startswith("| " + key) or cells[0].startswith(key):
                type_name = value
                break

        if type_name is None:
            continue

        for index, language in enumerate(FEATURE_COLUMNS):
            if cells[index + 1] != "✅":
                continue

            if not apis[language].has(type_name):
                report.add("features.md「%s」は %s で ✅ だが、型 %s が無い"
                           % (cells[0], language, type_name))


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="ドキュメントと実装の一致を確かめる")
    parser.add_argument("--write", action="store_true",
                        help="docs/api/ を実装に合わせて書き直す")
    args = parser.parse_args()

    apis = extract_all(LANGUAGE_ORDER)
    report = Report()

    check_types(apis, report)
    check_api_coverage(apis, report)
    sync_api_pages(apis, args.write, report)
    check_features(apis, report)

    print("公開型: %d 件 / 言語: %s"
          % (len(apis["csharp"].members), ", ".join(LANGUAGE_ORDER)))

    if report.ok():
        print("ドキュメントと実装は一致している。")
        return 0

    print()
    print("!!! 不一致 %d 件 !!!" % len(report.problems))

    for problem in report.problems:
        print("  - %s" % problem)

    return 1


if __name__ == "__main__":
    sys.exit(main())
