#!/usr/bin/env python3
"""全言語のソースから公開APIを抜き出し、言語非依存の論理名へ写す。

このライブラリの差別化要因は「1人の開発者が全言語へ同一の API を提供すること」
にある。人手で5言語を揃え続けるのは必ず破綻するので、機械で突き合わせる。

抽出はソースの静的解析（正規表現）で行う。リフレクションや `cargo public-api`
のような実行時／専用ツールを使わないのは、5言語ぶんのツールチェーンを
CI で揃える手間と、それ自体が壊れたときの原因切り分けの難しさを避けるため
（→ docs/adr/0009-static-api-extraction.md）。

出力する論理名は `docs/spec/00-conventions.md` 3章の命名変換規則に従う。

    型・列挙        PascalCase          NbtCompound
    メンバ          snake_case          read_file
    定数            SCREAMING_SNAKE     TARGET_DATA_VERSION

使い方:
    python3 spec/tools/extract_api.py                 # 言語ごとの一覧を出す
    python3 spec/tools/extract_api.py --json          # JSON で出す
    python3 spec/tools/extract_api.py --language rust # 1言語だけ

仕様: docs/spec/00-conventions.md 3章
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: 出力・比較の言語順。基準実装の C# を先頭に置く。
LANGUAGE_ORDER = ["csharp", "java", "typescript", "python", "rust"]

#: モジュール直下の関数・定数をまとめる仮想の型名。
#:
#: C# と Java には自由関数が無いので静的クラス（`NbtIo` など）に置くが、
#: TypeScript / Python / Rust ではモジュール関数になる。
#: 論理APIとしては同じものなので、ここへ寄せて比較する。
MODULE_LEVEL = "(module)"

#: API 一覧から除く型。実装の都合で公開しているが、利用者向けの API ではない。
INTERNAL_TYPES = {
    # 拡張メソッドの置き場。論理的には元の型のメンバ
    "ChunkCompressionExtensions",
    "ErrorCodeExtensions",
    "TagTypeExtensions",
    # Rust の内部実装
    "Parser",
    "Reader",
    "Writer",
    # Rust の trait 実装（impl Trait for Type の Trait 側を拾ってしまったもの）
    "From",
    "IntoIterator",
}

#: 言語ごとに名前が変わる型を、論理名へ寄せる表。
#:
#: 例外型は C# / Java が `Exception`、TypeScript / Python / Rust が `Error` と
#: 言語の慣習で分かれる。論理的には同じ型なので `SpringNbtError` に統一する。
TYPE_ALIASES = {
    "SpringNbtException": "SpringNbtError",
    "Error": "SpringNbtError",
    # C# / Java の静的クラスは、他言語ではモジュール関数
    "NbtIo": MODULE_LEVEL,
    "Snbt": MODULE_LEVEL,
    "Mutf8": MODULE_LEVEL,
    "SpringNbt": MODULE_LEVEL,
}

#: 言語の予約語を避けるために綴りを変えたメンバを、論理名へ寄せる表。
MEMBER_ALIASES = {
    # Python の with は予約語
    "with_property": "with",
}

#: 言語ごとに存在が変わる型と、その理由。型の一致検査から除く。
#:
#: docs/features.md「言語ごとの差異」に対応する。
EXPECTED_TYPE_GAPS = {
    # Rust では NbtTag 列挙のバリアントなので、独立した型にならない
    "NbtByte": ["rust"],
    "NbtShort": ["rust"],
    "NbtInt": ["rust"],
    "NbtLong": ["rust"],
    "NbtFloat": ["rust"],
    "NbtDouble": ["rust"],
    "NbtByteArray": ["rust"],
    "NbtIntArray": ["rust"],
    "NbtLongArray": ["rust"],
    # TypeScript は NbtTag を型の合併で表すので、基底クラスが無い
    "NbtTag": ["typescript"],
}

#: API 一覧から除くメンバ。言語の作法として要るが、論理APIではない。
INTERNAL_MEMBERS = {
    "equals",
    "hash_code",
    "to_string",
    "dispose",
    "clone",
    "iterator",
    "get_enumerator",
    "get_hash_code",
    "compare_to",
    "next",
    "close",  # 言語ごとに using / try-with-resources / with と作法が違う
    "enter",
    "exit",
    "fmt",
    "default",
    "new",
    "from",
    "into",
    "eq",
    "ne",
    "deref",
    "operator",
    "enumerator",
    "copy_to",
    "is_read_only",
    "count",
    "len",
    "is_empty",
    "index_of",
    "contains",
    "defaults",
    # コレクションの走査・複製は言語ごとに作法が違う
    "copy", "iter", "items", "entries", "keys", "values", "size", "push",
    "add", "append", "remove_at", "insert", "get_enumerator",
}

#: 抽出しないファイル。ライブラリの公開APIではないもの。
EXCLUDED_FILES = {
    # 適合性検証用の CLI。テストの一部であってライブラリの API ではない
    "conformance",
    "Conformance",
    "ChunkReport",
    "RegionReport",
    "NormalizedJson",
}

#: 言語のキーワード。正規表現が制御構文を拾ってしまった場合に落とす。
KEYWORDS = {
    "if", "else", "for", "while", "switch", "case", "return", "throw", "try",
    "catch", "finally", "do", "using", "match", "let", "const", "var", "in",
    "is", "as", "not", "and", "or", "with", "yield", "await", "async", "this",
    "self", "super", "base", "void", "public", "private", "protected", "static",
}


class Api:
    """1 言語ぶんの公開API。

    論理名（言語非依存）から、その言語での実際の名前へ引けるようにしておく。
    `docs/api/` の対応表はこの情報から生成する。
    """

    def __init__(self, language: str) -> None:
        self.language = language
        #: 論理型名 -> その言語での実際の型名
        self.type_names = {}
        #: 論理型名 -> {論理メンバ名: その言語での実際のメンバ名}
        self.members = {}
        #: 論理型名 -> 概要（1行）。基準実装からのみ集める
        self.type_docs = {}
        #: (論理型名, 論理メンバ名) -> 概要（1行）
        self.member_docs = {}

    def add_type(self, name: str, doc: str = "") -> None:
        """公開型を登録する。別名は論理名へ寄せる。"""
        logical = TYPE_ALIASES.get(name, name)

        if logical in INTERNAL_TYPES:
            return

        if logical not in self.members:
            self.members[logical] = {}

        # モジュール扱いの静的クラスは、実名を持たせない
        if logical != MODULE_LEVEL:
            self.type_names[logical] = name

        if len(doc) > 0 and logical not in self.type_docs:
            self.type_docs[logical] = doc

    def add_member(self, type_name: str, member: str, actual: str = "",
                   doc: str = "") -> None:
        """公開メンバを登録する。型が未登録なら先に登録する。"""
        logical = TYPE_ALIASES.get(type_name, type_name)

        if logical in INTERNAL_TYPES:
            return

        member = MEMBER_ALIASES.get(member, member)

        if member in INTERNAL_MEMBERS or len(member) == 0:
            return

        # 制御構文を拾ってしまった場合に落とす。別名で寄せた with は残す
        if member in KEYWORDS and member not in MEMBER_ALIASES.values():
            return

        self.add_type(type_name)

        if len(actual) == 0:
            actual = member

        # 同じ論理名が複数の綴りで現れたら、最初のものを採る
        if member not in self.members[logical]:
            self.members[logical][member] = actual

        if len(doc) > 0 and (logical, member) not in self.member_docs:
            self.member_docs[(logical, member)] = doc

    @property
    def types(self):
        """論理型名 -> 論理メンバ名の集合。型の一致検査で使う。"""
        return {name: set(members.keys()) for name, members in self.members.items()}

    def has(self, type_name: str, member: str = None) -> bool:
        """論理名がこの言語に存在するか。

        メンバの所属する型は言語で変わりうる（モジュール関数か静的クラスか）ので、
        型を指定してもそこに無ければ全体から探す。
        """
        logical = TYPE_ALIASES.get(type_name, type_name)

        if member is None:
            return logical in self.members

        if logical in self.members and member in self.members[logical]:
            return True

        # 所属が言語で変わる場合に備えて、どこかにあれば良しとする
        for members in self.members.values():
            if member in members:
                return True

        return False

    def actual(self, type_name: str, member: str = None) -> str:
        """その言語での実際の名前を返す。無ければ空文字列。"""
        logical = TYPE_ALIASES.get(type_name, type_name)

        if member is None:
            return self.type_names.get(logical, "")

        if logical in self.members and member in self.members[logical]:
            return self.members[logical][member]

        # 所属が変わっている場合は全体から探す
        for members in self.members.values():
            if member in members:
                return members[member]

        return ""

    def merge_setters(self) -> None:
        """`set_foo` と `foo` が両方ある型では、`set_foo` を落とす。

        Java はオプション型に `setFoo()` を生やすが、他言語はプロパティへ
        直接代入する。論理的には同じ「設定子」なので、取得子の行にまとめる
        （docs/spec/00-conventions.md 3章）。

        `set_block` のように対になる取得子が無いものは、独立したメソッドなので残す。
        """
        for members in self.members.values():
            # 対になる取得子があるものだけを設定子とみなす
            setters = [name for name in members
                       if name.startswith("set_") and name[4:] in members]

            for name in setters:
                del members[name]

    def to_json(self):
        """比較・出力用の素の辞書へ変換する。"""
        return {name: sorted(members) for name, members in sorted(self.types.items())}


# ---------------------------------------------------------------------------
# 命名変換（各言語の実際の名前 -> 論理名）
# ---------------------------------------------------------------------------

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def to_snake(name: str) -> str:
    """PascalCase / camelCase を snake_case へ写す。

    数字を含む語（`Mutf8` や `LZ4`）でも語の切れ目を保てるよう、
    小文字または数字のあとの大文字を境界とみなす。
    """
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def normalize_member(name: str) -> str:
    """メンバ名を論理名（snake_case）へ写す。

    接頭辞は落とさない。`get_int` のような「キーを指定して型付きで取り出す」
    取得子は、どの言語でも論理名に `get` を含む
    （docs/spec/00-conventions.md 3章の「取得子」は
    `data_version` のような引数なしのアクセサを指す）。
    """
    return to_snake(name)


def is_constant(name: str) -> bool:
    """SCREAMING_SNAKE_CASE の定数か。"""
    return name.isupper() and "_" in name or (name.isupper() and len(name) > 1)


class DocCollector:
    """直前のドキュメントコメントを溜めておき、宣言行で受け渡す。

    1 行形式（`/// <summary>説明</summary>`）と
    複数行形式（`/// <summary>` / `/// 説明` / `/// </summary>`）の両方を扱う。
    """

    def __init__(self, inline, body, open_tag: str, close_tag: str) -> None:
        self.inline = inline
        self.body = body
        self.open_tag = open_tag
        self.close_tag = close_tag
        self.pending = ""
        self.collecting = False
        self.parts = []

    def feed(self, line: str) -> bool:
        """コメント行なら溜めて True を返す。宣言行なら False。"""
        match = self.body.match(line)

        if match is None:
            return False

        text = match.group(1).strip()
        inline_match = self.inline.search(line)

        # <summary>説明</summary> が 1 行に収まっている場合
        if inline_match is not None:
            self.pending = clean_doc(inline_match.group(1))
            self.collecting = False
            return True

        if text.startswith(self.open_tag):
            self.collecting = True
            self.parts = []
            return True

        if text.startswith(self.close_tag):
            self.collecting = False
            self.pending = clean_doc(" ".join(self.parts))
            return True

        if self.collecting:
            self.parts.append(text)

        return True

    def take(self) -> str:
        """溜めた概要を取り出す。取り出したら空にする。"""
        result = self.pending
        self.pending = ""
        return result


def split_parameters(text: str):
    """`A a, B b` のような引数リストから、引数名だけを取り出す。"""
    names = []

    for part in text.split(","):
        words = part.strip().split()

        # 「型 名前」の形なので最後の語が名前
        if len(words) >= 2:
            names.append(words[-1])

    return names


def with_parens(line: str, name: str) -> str:
    """宣言行を見て、メソッドなら `名前()`、プロパティなら `名前` を返す。"""
    tail = line[line.index(name) + len(name):]

    # 名前の直後が ( ならメソッド
    if tail.lstrip().startswith("("):
        return name + "()"

    return name


def clean_doc(text: str) -> str:
    """ドキュメントコメントを 1 行の説明文へ均す。"""
    # <see cref="A.B"/> は B を残す。単に消すと説明文が意味を失う
    text = re.sub(r'<see\s+cref="(?:[A-Za-z]:)?([^"]*)"\s*/>',
                  lambda match: match.group(1).split(".")[-1], text)
    # 残りのタグ（<c>...</c> など）は囲みだけ落として中身を残す
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("|", "\\|").strip()

    for terminator in ("。", "\n"):
        position = text.find(terminator)

        if position >= 0:
            text = text[:position + len(terminator)]

    return " ".join(text.split())


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------

CSHARP_TYPE = re.compile(
    r"^\s*public\s+(?:sealed\s+|abstract\s+|static\s+|readonly\s+|partial\s+)*"
    r"(?:class|interface|enum|struct|record)\s+([A-Za-z0-9_]+)")

CSHARP_MEMBER = re.compile(
    r"^\s{4}public\s+(?:static\s+|virtual\s+|override\s+|abstract\s+|sealed\s+|"
    r"readonly\s+|const\s+|new\s+|partial\s+)*"
    r"(?:[A-Za-z0-9_<>,\[\]\?\. ]+?)\s+([A-Za-z0-9_]+)\s*[\(\{=;]")

CSHARP_CONSTRUCTOR = re.compile(r"^\s{4}public\s+([A-Z][A-Za-z0-9_]*)\s*\(")

CSHARP_ENUM_VALUE = re.compile(r"^\s{4}([A-Z][A-Za-z0-9_]*)\s*(?:=\s*[^,]+)?,?\s*$")


#: C# の XML ドキュメントコメントから概要を取り出す。
CSHARP_SUMMARY_INLINE = re.compile(r"///\s*<summary>(.*?)</summary>")
CSHARP_SUMMARY_BODY = re.compile(r"^\s*///\s?(.*)$")


def extract_csharp() -> Api:
    """C# のソースから公開APIを抜き出す。

    C# は基準実装なので、ここでだけ概要（`<summary>`）も集める。
    `docs/api/` の説明文はこれを使う。
    """
    api = Api("csharp")
    root = os.path.join(REPO_ROOT, "csharp", "src", "SpringNBTLibrary")

    for path in source_files(root, ".cs"):
        current = None
        in_enum = False
        doc = DocCollector(CSHARP_SUMMARY_INLINE, CSHARP_SUMMARY_BODY, "<summary>", "</summary>")

        # Foo.Bar.cs は partial の続き。型の概要は本体（Foo.cs）から採る
        is_partial_continuation = os.path.basename(path).count(".") > 1

        # ファイルを上から読み、型に入ったらそのメンバを拾う
        for line in read_lines(path):
            if doc.feed(line):
                continue

            type_match = CSHARP_TYPE.match(line)

            if type_match is not None:
                current = type_match.group(1)
                in_enum = " enum " in line
                summary = doc.take()

                if is_partial_continuation:
                    summary = ""

                api.add_type(current, summary)
                continue

            if current is None:
                doc.take()
                continue

            # enum の値は修飾子を持たないので別に拾う
            if in_enum:
                enum_match = CSHARP_ENUM_VALUE.match(line)

                if enum_match is not None:
                    name = enum_match.group(1)
                    api.add_member(current, to_snake(name), name, doc.take())

                continue

            # コンストラクタは型名と同じなので論理名に入れない
            if CSHARP_CONSTRUCTOR.match(line) is not None:
                doc.take()
                continue

            member_match = CSHARP_MEMBER.match(line)

            if member_match is not None:
                name = member_match.group(1)
                api.add_member(current, normalize_member(name), with_parens(line, name),
                               doc.take())
            else:
                doc.take()

    return api


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

JAVA_TYPE = re.compile(
    r"^\s*public\s+(?:final\s+|abstract\s+|static\s+|sealed\s+)*"
    r"(?:class|interface|enum|record)\s+([A-Za-z0-9_]+)")

JAVA_MEMBER = re.compile(
    r"^\s{4}public\s+(?:static\s+|final\s+|abstract\s+|synchronized\s+)*"
    r"(?:[A-Za-z0-9_<>,\[\]\?\. ]+?)\s+([A-Za-z0-9_]+)\s*[\(=;]")

JAVA_CONSTRUCTOR = re.compile(r"^\s{4}public\s+([A-Z][A-Za-z0-9_]*)\s*\(")

JAVA_ENUM_VALUE = re.compile(r"^\s{4}([A-Z][A-Z0-9_]*)\s*(?:\([^)]*\))?\s*[,;]?\s*$")

#: record のコンポーネント。`record RawChunk(A a, B b)` は a() / b() が生える。
JAVA_RECORD = re.compile(r"^public\s+record\s+[A-Za-z0-9_]+\s*\(([^)]*)\)")


def extract_java() -> Api:
    """Java のソースから公開APIを抜き出す。"""
    api = Api("java")
    root = os.path.join(REPO_ROOT, "java", "src", "main", "java")

    for path in source_files(root, ".java"):
        current = None

        for line in read_lines(path):
            type_match = JAVA_TYPE.match(line)

            if type_match is not None:
                current = type_match.group(1)
                api.add_type(current)

                # record は括弧の中のコンポーネントがそのままアクセサになる
                record_match = JAVA_RECORD.match(line)

                if record_match is not None:
                    for component in split_parameters(record_match.group(1)):
                        api.add_member(current, to_snake(component), component + "()")

                continue

            if current is None:
                continue

            if JAVA_CONSTRUCTOR.match(line) is not None:
                continue

            # enum の値は public 修飾子を持たないので別に拾う
            enum_match = JAVA_ENUM_VALUE.match(line)

            if enum_match is not None:
                name = enum_match.group(1)
                api.add_member(current, name.lower(), name)
                continue

            member_match = JAVA_MEMBER.match(line)

            if member_match is not None:
                name = member_match.group(1)
                api.add_member(current, normalize_member(name), with_parens(line, name))

    return api


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------

TS_TYPE = re.compile(
    r"^export\s+(?:abstract\s+)?(?:class|interface|enum)\s+([A-Za-z0-9_]+)")

TS_FUNCTION = re.compile(r"^export\s+function\s+([A-Za-z0-9_]+)")

TS_CONST = re.compile(r"^export\s+const\s+([A-Za-z0-9_]+)")

TS_MEMBER = re.compile(
    r"^  (?:static\s+|readonly\s+)*(?:get\s+|set\s+)?([A-Za-z0-9_]+)\s*[\(:<]")

TS_ENUM_VALUE = re.compile(r"^  ([A-Za-z0-9_]+)\s*=")

TS_INTERFACE_FIELD = re.compile(r"^  ([A-Za-z0-9_]+)\??\s*:")

#: constructor(readonly foo: T, ...) の形で公開されるフィールド。
TS_PARAMETER_PROPERTY = re.compile(r"^    (?:public\s+)?readonly\s+([A-Za-z0-9_]+)\s*:")

#: クラス直下の公開フィールド（`readonly type = TagType.Byte as const;`）。
TS_CLASS_FIELD = re.compile(r"^  (?:public\s+)?readonly\s+([A-Za-z0-9_]+)\s*=")

def extract_typescript() -> Api:
    """TypeScript のソースから公開APIを抜き出す。"""
    api = Api("typescript")
    api.add_type(MODULE_LEVEL)
    root = os.path.join(REPO_ROOT, "typescript", "src")

    for path in source_files(root, ".ts"):
        current = None
        in_enum = False
        in_interface = False
        in_constructor = False

        for line in read_lines(path):
            type_match = TS_TYPE.match(line)

            if type_match is not None:
                current = type_match.group(1)
                in_enum = line.lstrip().startswith("export enum")
                in_interface = line.lstrip().startswith("export interface")
                in_constructor = False
                api.add_type(current)
                continue

            function_match = TS_FUNCTION.match(line)

            if function_match is not None:
                current = None
                name = function_match.group(1)
                api.add_member(MODULE_LEVEL, normalize_member(name), name + "()")
                continue

            const_match = TS_CONST.match(line)

            if const_match is not None:
                current = None
                name = const_match.group(1)
                api.add_member(MODULE_LEVEL, normalize_member(name), name)
                continue

            if current is None:
                continue

            if in_enum:
                enum_match = TS_ENUM_VALUE.match(line)

                if enum_match is not None:
                    name = enum_match.group(1)
                    api.add_member(current, to_snake(name), name)

                continue

            # interface のフィールドはオプション構造体の設定項目にあたる
            if in_interface:
                field_match = TS_INTERFACE_FIELD.match(line)

                if field_match is not None:
                    name = field_match.group(1)
                    api.add_member(current, normalize_member(name), name)

                continue

            # constructor の引数に readonly を付けたものは公開フィールドになる。
            # private constructor でも引数プロパティは公開なので、除外より先に見る
            if line.startswith("  constructor") or line.startswith("  private constructor"):
                # 同じ行で引数リストが閉じているなら、次の行から通常のメンバに戻る
                in_constructor = ")" not in line
                continue

            # private / # 始まりは内部のもの
            if line.startswith("  private") or line.startswith("  #"):
                continue

            if in_constructor:
                parameter_match = TS_PARAMETER_PROPERTY.match(line)

                if parameter_match is not None:
                    name = parameter_match.group(1)
                    api.add_member(current, normalize_member(name), name)

                # 閉じ括弧まで来たら引数リストの終わり
                if line.startswith("  )") or line.rstrip().endswith("{}"):
                    in_constructor = False

                continue

            field_match = TS_CLASS_FIELD.match(line)

            if field_match is not None:
                name = field_match.group(1)
                api.add_member(current, normalize_member(name), name)
                continue

            member_match = TS_MEMBER.match(line)

            if member_match is not None:
                name = member_match.group(1)
                api.add_member(current, normalize_member(name), with_parens(line, name))

    return api


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

PY_CLASS = re.compile(r"^class\s+([A-Za-z0-9_]+)")
PY_METHOD = re.compile(r"^    def\s+([A-Za-z0-9_]+)")
PY_FUNCTION = re.compile(r"^def\s+([A-Za-z0-9_]+)")
PY_ENUM_VALUE = re.compile(r"^    ([A-Z][A-Z0-9_]*)\s*=")
PY_CLASS_FIELD = re.compile(r"^    ([a-z][A-Za-z0-9_]*)\s*[:=]")
PY_MODULE_CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*[:=]")
PY_ATTRIBUTE = re.compile(r"^\s{8,}self\.([a-z][A-Za-z0-9_]*)\s*[:=]")


def extract_python() -> Api:
    """Python のソースから公開APIを抜き出す。"""
    api = Api("python")
    api.add_type(MODULE_LEVEL)
    root = os.path.join(REPO_ROOT, "python", "src", "spring_nbt_library")

    for path in source_files(root, ".py"):
        current = None
        is_property = False

        for line in read_lines(path):
            # @property の次に来る def は呼び出しカッコが要らない
            if line.strip() == "@property":
                is_property = True
                continue
            class_match = PY_CLASS.match(line)

            if class_match is not None:
                current = class_match.group(1)

                # 先頭がアンダースコアなら内部のもの
                if current.startswith("_"):
                    current = None
                else:
                    api.add_type(current)

                continue

            function_match = PY_FUNCTION.match(line)

            if function_match is not None:
                current = None

                if not function_match.group(1).startswith("_"):
                    name = function_match.group(1)
                    api.add_member(MODULE_LEVEL, name, name + "()")

                continue

            const_match = PY_MODULE_CONST.match(line)

            if const_match is not None:
                current = None
                name = const_match.group(1)
                api.add_member(MODULE_LEVEL, name.lower(), name)
                continue

            if current is None:
                continue

            enum_match = PY_ENUM_VALUE.match(line)

            if enum_match is not None:
                api.add_member(current, enum_match.group(1).lower())
                continue

            method_match = PY_METHOD.match(line)

            if method_match is not None and not method_match.group(1).startswith("_"):
                name = method_match.group(1)
                actual = name + "()"

                if is_property:
                    actual = name

                is_property = False
                api.add_member(current, name, actual)
                continue

            is_property = False

            # __init__ で self に代入する属性も公開メンバとして数える
            attribute_match = PY_ATTRIBUTE.match(line)

            if attribute_match is not None:
                api.add_member(current, attribute_match.group(1))
                continue

            # クラス直下で定める値（type = TagType.BYTE など）も公開メンバ
            field_match = PY_CLASS_FIELD.match(line)

            if field_match is not None:
                name = field_match.group(1)

                if not name.startswith("_"):
                    api.add_member(current, name, name)

    return api


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------

RS_TYPE = re.compile(r"^pub\s+(?:struct|enum|trait)\s+([A-Za-z0-9_]+)")
RS_IMPL = re.compile(r"^impl(?:<[^>]*>)?\s+([A-Za-z0-9_]+)")
RS_TRAIT_IMPL = re.compile(r"^impl(?:<[^>]*>)?\s+[A-Za-z0-9_:<>]+\s+for\s+([A-Za-z0-9_]+)")
RS_METHOD = re.compile(r"^    pub\s+fn\s+([A-Za-z0-9_]+)")
RS_FIELD = re.compile(r"^    pub\s+([a-z][A-Za-z0-9_]*)\s*:")
RS_ENUM_VALUE = re.compile(r"^    ([A-Z][A-Za-z0-9_]*)\s*[,\(\{]")
RS_FUNCTION = re.compile(r"^pub\s+fn\s+([A-Za-z0-9_]+)")
RS_CONST = re.compile(r"^pub\s+const\s+([A-Z][A-Z0-9_]*)\s*:")

#: `scalar_accessors!(opt_int, get_int, ...)` のように、マクロで生成するアクセサ。
#: 静的解析ではマクロを展開できないので、呼び出し行から名前だけ拾う。
RS_ACCESSOR_MACRO = re.compile(
    r"^([a-z_]+_accessors)!\(\s*([a-z_0-9]+)\s*,\s*([a-z_0-9]+)\s*,")


def extract_rust() -> Api:
    """Rust のソースから公開APIを抜き出す。"""
    api = Api("rust")
    api.add_type(MODULE_LEVEL)
    root = os.path.join(REPO_ROOT, "rust", "src")

    for path in source_files(root, ".rs"):
        current = None
        in_enum = False

        for line in read_lines(path):
            type_match = RS_TYPE.match(line)

            if type_match is not None:
                current = type_match.group(1)
                in_enum = line.startswith("pub enum")
                api.add_type(current)
                continue

            # trait 実装は言語の作法なので論理APIに数えない
            if RS_TRAIT_IMPL.match(line) is not None:
                current = None
                in_enum = False
                continue

            impl_match = RS_IMPL.match(line)

            if impl_match is not None:
                current = impl_match.group(1)
                in_enum = False
                api.add_type(current)
                continue

            # マクロで生成するアクセサは NbtCompound のメンバとして数える
            macro_match = RS_ACCESSOR_MACRO.match(line)

            if macro_match is not None:
                for name in (macro_match.group(2), macro_match.group(3)):
                    api.add_member("NbtCompound", name, name + "()")

                continue

            function_match = RS_FUNCTION.match(line)

            if function_match is not None:
                name = function_match.group(1)
                api.add_member(MODULE_LEVEL, name, name + "()")
                continue

            const_match = RS_CONST.match(line)

            if const_match is not None:
                name = const_match.group(1)
                api.add_member(MODULE_LEVEL, name.lower(), name)
                continue

            if current is None:
                continue

            if in_enum:
                enum_match = RS_ENUM_VALUE.match(line)

                if enum_match is not None:
                    api.add_member(current, to_snake(enum_match.group(1)))

                continue

            method_match = RS_METHOD.match(line)

            if method_match is not None:
                name = method_match.group(1)
                api.add_member(current, name, name + "()")
                continue

            field_match = RS_FIELD.match(line)

            if field_match is not None:
                name = field_match.group(1)
                api.add_member(current, name, name)

    return api


# ---------------------------------------------------------------------------
# 共通
# ---------------------------------------------------------------------------

def source_files(root: str, suffix: str):
    """ディレクトリ配下のソースを、パス順で列挙する。"""
    found = []

    for dirpath, dirnames, filenames in os.walk(root):
        # ビルド生成物は対象外
        dirnames[:] = [name for name in dirnames
                       if name not in ("bin", "obj", "target", "dist", "node_modules",
                                       "__pycache__", ".venv")]

        for filename in filenames:
            if not filename.endswith(suffix):
                continue

            stem = filename[:-len(suffix)]

            # 検証ツールと内部ヘルパ（_ 始まり）は公開APIではない。
            # ただし __init__.py はパッケージの入口なので対象に含める
            if stem in EXCLUDED_FILES:
                continue

            if stem.startswith("_") and stem != "__init__":
                continue

            found.append(os.path.join(dirpath, filename))

    found.sort()
    return found


def read_lines(path: str):
    """ソースを 1 行ずつ返す。"""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().split("\n")


EXTRACTORS = {
    "csharp": extract_csharp,
    "java": extract_java,
    "typescript": extract_typescript,
    "python": extract_python,
    "rust": extract_rust,
}


def extract_all(languages):
    """指定した言語ぶんの公開APIを抜き出す。"""
    result = {}

    for language in languages:
        api = EXTRACTORS[language]()
        api.merge_setters()
        result[language] = api

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="全言語の公開APIを抜き出す")
    parser.add_argument("--language", action="append", choices=LANGUAGE_ORDER,
                        help="対象言語（既定は全部）")
    parser.add_argument("--json", action="store_true", help="JSON で出す")
    args = parser.parse_args()

    if args.language is None:
        languages = LANGUAGE_ORDER
    else:
        languages = args.language

    extracted = extract_all(languages)

    if args.json:
        print(json.dumps({name: api.to_json() for name, api in extracted.items()},
                         ensure_ascii=False, indent=2))
        return 0

    for language in languages:
        api = extracted[language]
        print("=" * 72)
        print("%s: 型 %d 件" % (language, len(api.types)))
        print("=" * 72)

        for type_name, members in sorted(api.types.items()):
            print("  %-28s %s" % (type_name, " ".join(sorted(members))))

        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
