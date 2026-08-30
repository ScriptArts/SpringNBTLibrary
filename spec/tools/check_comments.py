#!/usr/bin/env python3
"""コーディング規約のうち、コメントと禁止記法を機械で確かめる。

全言語で同じ書きぶりを保つための道具。人手のレビューでは必ず抜けが出る。

検査するもの:

1. **公開 API の doc コメント** — 型・公開メソッドの直前に、
   その言語の doc 形式のコメントがあるか
   （C# `/// <summary>` / Java・TypeScript `/** */` / Python docstring / Rust `///`）
2. **条件分岐のコメント** — `if` の直前に説明のコメントがあるか
3. **ループのコメント** — `for` / `foreach` / `while` の直前に説明のコメントがあるか
4. **禁止記法** — 三項演算子、オプショナルチェーン、null 合体演算子
5. **コメントの句点** — コメントに `。` を使わない

ガード節（引数検証など、`throw` / `return` だけで終わる短い分岐）は
2 の対象から外す。書いても「不正なら弾く」としか書けず、かえって読みにくいため。

使い方:
    python3 spec/tools/check_comments.py            # 違反があれば終了コード 1
    python3 spec/tools/check_comments.py --summary  # 件数だけ出す
    python3 spec/tools/check_comments.py --language csharp

規約: ユーザーのコーディング規約（コメントは日本語で、意図が明確になるように）
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LANGUAGE_ORDER = ["csharp", "java", "typescript", "python", "rust"]

#: 言語ごとの、検査対象のソースと doc コメントの形。
LANGUAGES = {
    "csharp": {
        "roots": ["csharp/src"],
        "suffix": ".cs",
        "line_comment": "//",
        "doc_prefixes": ["///"],
    },
    "java": {
        "roots": ["java/src/main"],
        "suffix": ".java",
        "line_comment": "//",
        "doc_prefixes": ["*", "/**"],
    },
    "typescript": {
        "roots": ["typescript/src"],
        "suffix": ".ts",
        "line_comment": "//",
        "doc_prefixes": ["*", "/**"],
    },
    "python": {
        "roots": ["python/src"],
        "suffix": ".py",
        "line_comment": "#",
        "doc_prefixes": ['"""'],
    },
    "rust": {
        "roots": ["rust/src"],
        "suffix": ".rs",
        "line_comment": "//",
        "doc_prefixes": ["///", "//!"],
    },
}

# ---------------------------------------------------------------------------
# 禁止記法
# ---------------------------------------------------------------------------

#: 三項演算子。`cond ? a : b`。C# の nullable(`int?`) や
#: TypeScript の省略可能引数(`x?: T`) と紛れないよう、`?` の前後に空白を要求する。
TERNARY = re.compile(r"[^?\s]\s+\?\s+[^?:]+?\s+:\s")

#: オプショナルチェーン。`foo?.bar`
OPTIONAL_CHAIN = re.compile(r"[A-Za-z0-9_\)\]]\?\.")

#: null 合体演算子。`a ?? b` / `a ??= b`
NULL_COALESCE = re.compile(r"\?\?=?")

#: Python の条件式。三項演算子に相当する
PY_CONDITIONAL = re.compile(r"\S\s+if\s+.+\s+else\s+\S")

BANNED = [
    ("三項演算子", TERNARY, ["csharp", "java", "typescript"]),
    ("オプショナルチェーン ?.", OPTIONAL_CHAIN, ["csharp", "typescript"]),
    ("null 合体演算子 ??", NULL_COALESCE, ["csharp", "typescript"]),
    ("条件式（三項演算子に相当）", PY_CONDITIONAL, ["python"]),
]

# ---------------------------------------------------------------------------
# 構文の検出
# ---------------------------------------------------------------------------

#: 条件分岐の始まり。`else if` / `elif` は先頭の if に付いていればよいので除く。
BRANCH = {
    "csharp": re.compile(r"^\s*if\s*\("),
    "java": re.compile(r"^\s*if\s*\("),
    "typescript": re.compile(r"^\s*if\s*\("),
    "python": re.compile(r"^\s*if\s+"),
    "rust": re.compile(r"^\s*if\s+"),
}

#: ループの始まり。
LOOP = {
    "csharp": re.compile(r"^\s*(for|foreach|while|do)\b\s*[\(\{]"),
    "java": re.compile(r"^\s*(for|while|do)\b\s*[\(\{]"),
    "typescript": re.compile(r"^\s*(for|while|do)\b\s*[\(\{]"),
    "python": re.compile(r"^\s*(for|while)\s+"),
    "rust": re.compile(r"^\s*(for\s+|while\s+|loop\s*\{)"),
}

#: 公開メソッド・関数の宣言。doc コメントを要求する。
PUBLIC_MEMBER = {
    "csharp": re.compile(
        r"^\s{4}public\s+(?!class|interface|enum|struct|record)"
        r"(?:static\s+|virtual\s+|override\s+|abstract\s+|sealed\s+|readonly\s+|const\s+|new\s+)*"
        r"[A-Za-z0-9_<>,\[\]\?\. ]+\s+[A-Za-z0-9_]+\s*[\(\{=>]"),
    "java": re.compile(
        r"^\s{4}public\s+(?!class|interface|enum|record)"
        r"(?:static\s+|final\s+|abstract\s+|synchronized\s+)*"
        r"[A-Za-z0-9_<>,\[\]\?\. ]+\s+[A-Za-z0-9_]+\s*\("),
    # 宣言は `{` で終わる。`foo(...);` のような呼び出しと区別する
    "typescript": re.compile(
        r"^  (?!private|#|constructor|if|for|while|switch|return|throw|else|do|try|catch)"
        r"(?:static\s+|get\s+|set\s+)?[A-Za-z0-9_]+\s*[\(<].*\{\s*$"),
    "python": re.compile(r"^    def\s+(?!_)[A-Za-z0-9_]+"),
    "rust": re.compile(r"^    pub\s+fn\s+[A-Za-z0-9_]+"),
}

#: 公開型の宣言。
PUBLIC_TYPE = {
    "csharp": re.compile(r"^\s*public\s+(?:sealed\s+|abstract\s+|static\s+|readonly\s+|partial\s+)*(?:class|interface|enum|struct|record)\s"),
    "java": re.compile(r"^\s*public\s+(?:final\s+|abstract\s+|static\s+|sealed\s+)*(?:class|interface|enum|record)\s"),
    "typescript": re.compile(r"^export\s+(?:abstract\s+)?(?:class|interface|enum)\s"),
    "python": re.compile(r"^class\s+(?!_)"),
    "rust": re.compile(r"^pub\s+(?:struct|enum|trait)\s"),
}

#: 本文を載せたまま閉じていない doc コメントの開始行。
#: 複数行の doc コメントは本文の無い `/**` で始める決まりなので、
#: この形は整形が壊れた跡とみなす。
BROKEN_DOC = re.compile(r"^\s*/\*\*\s*\S")

#: ガード節とみなす本体。これだけで終わる分岐にはコメントを求めない。
GUARD_BODY = re.compile(
    r"^\s*(throw|return|continue|break|raise)\b|^\s*\{?\s*$")


class Finding:
    """1 件の指摘。"""

    def __init__(self, language: str, path: str, line: int, kind: str, text: str) -> None:
        self.language = language
        self.path = path
        self.line = line
        self.kind = kind
        self.text = text

    def __str__(self) -> str:
        return "%s:%d [%s] %s" % (self.path, self.line, self.kind, self.text.strip()[:70])


def is_comment(line: str, language: str) -> bool:
    """その行がコメント（doc 形式を含む）か。"""
    stripped = line.strip()
    spec = LANGUAGES[language]

    if len(stripped) == 0:
        return False

    if stripped.startswith(spec["line_comment"]):
        return True

    # doc コメントの途中の行（Java / TypeScript の ` * ...`）も含める
    for prefix in spec["doc_prefixes"]:
        if stripped.startswith(prefix):
            return True

    return stripped.startswith("*/") or stripped.startswith("/*")


def has_doc_before(lines, index: int, language: str) -> bool:
    """宣言行の直前に doc 形式のコメントがあるか。

    属性やアノテーション（`[Fact]` / `@Override` など）は読み飛ばす。
    """
    spec = LANGUAGES[language]
    position = index - 1

    # 修飾のための行を遡って飛ばす
    while position >= 0:
        stripped = lines[position].strip()

        if len(stripped) == 0:
            return False

        if stripped.startswith("[") or stripped.startswith("@") or stripped.startswith("#["):
            position -= 1
            continue

        break

    if position < 0:
        return False

    stripped = lines[position].strip()

    for prefix in spec["doc_prefixes"]:
        if stripped.startswith(prefix):
            return True

    # Java / TypeScript は doc コメントの終わりが `*/`
    return stripped == "*/"


def has_python_docstring(lines, index: int) -> bool:
    """Python の宣言の次行以降に docstring があるか。

    引数リストが複数行に渡ることがあるので、宣言が閉じる行まで読み飛ばす。
    """
    position = index

    # 宣言が `:` で終わるまで進める（複数行のシグネチャに対応）
    while position < len(lines) and not lines[position].rstrip().endswith(":"):
        position += 1

        # 際限なく探さない
        if position > index + 10:
            return False

    position += 1

    while position < len(lines):
        stripped = lines[position].strip()

        if len(stripped) == 0:
            position += 1
            continue

        return stripped.startswith('"""') or stripped.startswith("'''")

    return False


def has_comment_before(lines, index: int, language: str) -> bool:
    """その行の直前にコメントがあるか。空行は挟んでよい。"""
    position = index - 1

    while position >= 0:
        stripped = lines[position].strip()

        if len(stripped) == 0:
            position -= 1
            continue

        # Python は docstring がその前の説明にあたる
        if language == "python" and '"""' in stripped:
            return True

        return is_comment(lines[position], language)

    return False


def has_comment_inside(lines, index: int, language: str) -> bool:
    """ブロックの中の先頭にコメントがあるか。

    `if (...) {` の次の行から書き始める書き方も、
    「この分岐で何をするか」を説明しているので認める。
    """
    position = index + 1

    # 開き波括弧だけの行は飛ばす
    while position < len(lines) and position <= index + 3:
        stripped = lines[position].strip()

        if len(stripped) == 0 or stripped == "{":
            position += 1
            continue

        return is_comment(lines[position], language)

    return False


def has_explanation(lines, index: int, language: str) -> bool:
    """直前かブロック内の先頭に、説明のコメントがあるか。"""
    if has_comment_before(lines, index, language):
        return True

    return has_comment_inside(lines, index, language)


def is_nested_loop(lines, index: int, language: str) -> bool:
    """直前の行もループの開始か。

    多重ループは 1 つの処理単位なので、いちばん外側に目的が書いてあれば足りる。
    内側にも同じ説明を重ねると、かえって読みにくくなる。
    """
    position = index - 1

    while position >= 0:
        stripped = lines[position].strip()

        if len(stripped) == 0:
            position -= 1
            continue

        return LOOP[language].match(lines[position]) is not None

    return False


def is_guard(lines, index: int, language: str) -> bool:
    """引数検証などのガード節か。本体が 1 文で、抜けるだけのもの。"""
    # 同じ行に本体がある場合（`if (x) return;`）
    tail = lines[index].split(")", 1)

    if len(tail) > 1 and GUARD_BODY.match(tail[1]):
        if len(tail[1].strip()) > 0:
            return True

    # 次の 1〜2 行が抜けるだけなら、ガード節とみなす
    for offset in (1, 2):
        if index + offset >= len(lines):
            break

        stripped = lines[index + offset].strip()

        if len(stripped) == 0 or stripped == "{":
            continue

        return GUARD_BODY.match(lines[index + offset]) is not None

    return False


def is_inherited(lines, index: int) -> bool:
    """継承元の doc を引き継ぐ宣言か。

    `@Override` や `<inheritdoc/>` が付いていれば、同じ説明を重ねて書く必要はない。
    """
    position = index - 1

    while position >= 0:
        stripped = lines[position].strip()

        if len(stripped) == 0:
            return False

        if stripped.startswith("@Override") or "inheritdoc" in stripped:
            return True

        if stripped.startswith("[") or stripped.startswith("@") or stripped.startswith("#["):
            position -= 1
            continue

        return False

    return False


def source_files(language: str):
    """検査対象のソースを列挙する。"""
    spec = LANGUAGES[language]
    found = []

    for root in spec["roots"]:
        base = os.path.join(REPO_ROOT, root)

        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [name for name in dirnames
                           if name not in ("bin", "obj", "target", "dist",
                                           "node_modules", "__pycache__", ".venv")]

            for filename in filenames:
                if filename.endswith(spec["suffix"]):
                    found.append(os.path.join(dirpath, filename))

    found.sort()
    return found


def check_language(language: str):
    """1 言語分を検査して、指摘の一覧を返す。"""
    findings = []

    for path in source_files(language):
        relative = os.path.relpath(path, REPO_ROOT)

        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().split("\n")

        in_block_comment = False
        in_docstring = False

        for index, line in enumerate(lines):
            number = index + 1
            stripped = line.strip()

            # Python の docstring も句点を使わない
            if language == "python" and in_docstring and "。" in line:
                findings.append(Finding(language, relative, number,
                                        "コメントに句点がある", line))

            if language == "python":
                # 三重引用符の数が奇数なら、docstring の出入りが切り替わる
                if stripped.count('"""') % 2 == 1:
                    in_docstring = not in_docstring

            # 閉じ忘れた doc コメントは、この行だけで判別できる
            if BROKEN_DOC.match(line) and not stripped.endswith("*/"):
                findings.append(Finding(language, relative, number,
                                        "doc コメントの整形が壊れている", line))

            # ブロックコメントの中は検査しない
            if stripped.startswith("/*"):
                in_block_comment = "*/" not in stripped
                continue

            if in_block_comment:
                in_block_comment = "*/" not in stripped
                continue

            if is_comment(line, language):
                # コメントに句点は使わない。文が続くなら行を分ける
                if "。" in line:
                    findings.append(Finding(language, relative, number,
                                            "コメントに句点がある", line))

                continue

            # 1. 禁止記法
            for label, pattern, languages in BANNED:
                if language in languages and pattern.search(line):
                    findings.append(Finding(language, relative, number, "禁止記法: " + label, line))

            # 2. 公開型の doc コメント
            if PUBLIC_TYPE[language].match(line):
                if language == "python":
                    documented = has_python_docstring(lines, index)
                else:
                    documented = has_doc_before(lines, index, language)

                if not documented:
                    findings.append(Finding(language, relative, number, "型に doc コメントが無い", line))

                continue

            # 3. 公開メソッドの doc コメント
            if PUBLIC_MEMBER[language].match(line):
                # 継承元の doc を引き継ぐものは、重ねて書かなくてよい
                if is_inherited(lines, index):
                    continue

                if language == "python":
                    documented = has_python_docstring(lines, index)
                else:
                    documented = has_doc_before(lines, index, language)

                if not documented:
                    findings.append(Finding(language, relative, number, "メソッドに doc コメントが無い", line))

                continue

            # 4. 条件分岐のコメント（ガード節と定型句は除く）
            if BRANCH[language].match(line):
                # スクリプトの入口を示す定型句。説明することがない
                if stripped.startswith("if __name__ =="):
                    continue

                if not is_guard(lines, index, language) and not has_explanation(lines, index, language):
                    findings.append(Finding(language, relative, number, "if にコメントが無い", line))

                continue

            # 5. ループのコメント
            if LOOP[language].match(line):
                # 多重ループの内側は、外側に付けた説明が 効いている
                if is_nested_loop(lines, index, language):
                    continue

                if not has_explanation(lines, index, language):
                    findings.append(Finding(language, relative, number, "ループにコメントが無い", line))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="コメントと禁止記法の規約適合を確かめる")
    parser.add_argument("--language", action="append", choices=LANGUAGE_ORDER,
                        help="対象言語（既定は全部）")
    parser.add_argument("--summary", action="store_true", help="件数だけ出す")
    parser.add_argument("--kind", help="この種別の指摘だけ出す（部分一致）")
    args = parser.parse_args()

    if args.language is None:
        languages = LANGUAGE_ORDER
    else:
        languages = args.language

    total = []

    for language in languages:
        findings = check_language(language)

        if args.kind is not None:
            findings = [item for item in findings if args.kind in item.kind]

        total.extend(findings)

        # 種別ごとの内訳を出す
        counts = {}

        for item in findings:
            counts[item.kind] = counts.get(item.kind, 0) + 1

        print("=" * 72)
        print("%s: %d 件" % (language, len(findings)))
        print("=" * 72)

        for kind in sorted(counts):
            print("  %-34s %d" % (kind, counts[kind]))

        if not args.summary:
            for item in findings:
                print("    %s" % item)

        print()

    print("合計 %d 件" % len(total))

    if len(total) == 0:
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
