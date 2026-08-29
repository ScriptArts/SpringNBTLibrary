#!/usr/bin/env python3
"""全言語の適合性検証を走らせる。

仕様: docs/spec/90-conformance.md

やること:
    1. 各言語の検証ツールを起動できるようにビルドする
    2. 全テストベクタについて、各言語で decode / encode / snbt を実行する
    3. decode の結果を expect/ の正規化JSON と突き合わせる
    4. encode の結果を展開後の入力バイト列と突き合わせる（ラウンドトリップ）
    5. 言語どうしの出力を相互に diff する

使い方:
    python3 spec/tools/run_conformance.py                # 全言語を検証
    python3 spec/tools/run_conformance.py --only csharp  # 言語を絞る
    python3 spec/tools/run_conformance.py --generate-expect
        基準実装 (C#) の出力から expect/ を作り直す
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTDATA = os.path.join(REPO_ROOT, "spec", "testdata")
MANIFEST = os.path.join(TESTDATA, "manifest.json")

# 基準実装。expect/ の生成元になる（docs/adr/0002-idiomatic-naming.md）
REFERENCE_LANGUAGE = "csharp"

LANGUAGE_ORDER = ["csharp", "java", "typescript", "python", "rust"]


class Runner:
    """1 言語ぶんの検証ツールを起動する。"""

    def __init__(self, name, build_command, invoke_command):
        self.name = name
        self.build_command = build_command
        self.invoke_command = invoke_command

    def build(self):
        """検証ツールをビルドする。失敗したらその言語は「未使用」として扱う。"""
        if self.build_command is None:
            return True

        result = subprocess.run(
            self.build_command, cwd=REPO_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        if result.returncode != 0:
            sys.stderr.write("[%s] ビルドに失敗した:\n%s\n"
                             % (self.name, result.stdout.decode("utf-8", "replace")))
            return False

        return True

    def run(self, args):
        """検証ツールを起動し、(終了コード, 標準エラー) を返す。"""
        environment = dict(os.environ)

        # Python 版はインストールせずソースツリーから直接動かせるようにする
        if self.name == "python":
            environment["PYTHONPATH"] = os.path.join(REPO_ROOT, "python", "src")

        result = subprocess.run(
            self.invoke_command + args, cwd=REPO_ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode, result.stderr.decode("utf-8", "replace")


def build_runners():
    """利用できる検証ツールの一覧を作る。まだ実装されていない言語は自動的に外れる。"""
    runners = []

    csharp_dll = os.path.join(
        REPO_ROOT, "csharp", "tests", "SpringNBTLibrary.Conformance",
        "bin", "Release", "net8.0", "springnbt-conformance.dll")
    if os.path.isdir(os.path.join(REPO_ROOT, "csharp", "tests", "SpringNBTLibrary.Conformance")):
        runners.append(Runner(
            "csharp",
            ["dotnet", "build", "-c", "Release",
             "csharp/tests/SpringNBTLibrary.Conformance/SpringNBTLibrary.Conformance.csproj"],
            ["dotnet", csharp_dll]))

    java_main = "io.github.scriptarts.springnbt.conformance.Conformance"
    java_source = os.path.join(
        REPO_ROOT, "java", "src", "test", "java", "io", "github", "scriptarts",
        "springnbt", "conformance", "Conformance.java")
    if os.path.isfile(java_source):
        runners.append(Runner(
            "java",
            ["mvn", "-B", "-q", "-f", "java/pom.xml", "test-compile"],
            ["java", "-cp", "java/target/classes:java/target/test-classes", java_main]))

    python_module = os.path.join(
        REPO_ROOT, "python", "src", "spring_nbt_library", "conformance.py")
    if os.path.isfile(python_module):
        runners.append(Runner(
            "python",
            None,
            [sys.executable, "-m", "spring_nbt_library.conformance"]))

    typescript_source = os.path.join(
        REPO_ROOT, "typescript", "src", "conformance.ts")
    if os.path.isfile(typescript_source):
        runners.append(Runner(
            "typescript",
            ["npm", "--prefix", "typescript", "run", "--silent", "build"],
            ["node", os.path.join(REPO_ROOT, "typescript", "dist", "src", "conformance.js")]))

    rust_example = os.path.join(REPO_ROOT, "rust", "examples", "conformance.rs")
    if os.path.isfile(rust_example):
        runners.append(Runner(
            "rust",
            ["cargo", "build", "--release", "--manifest-path", "rust/Cargo.toml",
             "--example", "conformance"],
            [os.path.join(REPO_ROOT, "rust", "target", "release", "examples", "conformance")]))

    # 実装順ではなく決まった順に並べて、出力を読みやすくする
    runners.sort(key=lambda runner: LANGUAGE_ORDER.index(runner.name))
    return runners


def decompress(data, method):
    """マニフェストの compression に従って展開する。"""
    if method == "gzip":
        return gzip.decompress(data)

    if method == "zlib":
        return zlib.decompress(data)

    return data


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def read_text(path):
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8")


class Report:
    """検証結果を集計する。"""

    def __init__(self):
        self.passed = 0
        self.failures = []

    def ok(self):
        self.passed += 1

    def fail(self, message):
        self.failures.append(message)

    def summary(self):
        if len(self.failures) == 0:
            return "成功: %d 件すべて一致" % self.passed

        lines = ["失敗: %d 件 (成功 %d 件)" % (len(self.failures), self.passed)]
        for failure in self.failures:
            lines.append("  - " + failure)
        return "\n".join(lines)


def run_vector(runner, vector, workdir, report, outputs):
    """1 言語 × 1 ベクタを検証する。ベクタの種別で扱いを分ける。"""
    if vector.get("kind") == "anvil":
        run_anvil_vector(runner, vector, workdir, report, outputs)
        return

    if vector.get("kind") == "world":
        run_world_vector(runner, vector, workdir, report, outputs)
        return

    vector_id = vector["id"]
    input_path = os.path.join(TESTDATA, vector["input"])
    prefix = os.path.join(workdir, "%s_%s" % (runner.name, vector_id.replace("/", "_")))

    format_args = []
    if vector["format"] == "network":
        format_args = ["--format", "network"]

    json_path = prefix + ".json"
    code, stderr = runner.run(["decode", input_path, json_path] + format_args)

    expect_error = vector.get("expect_error")

    if expect_error is not None:
        # 読み込みが失敗すること自体が期待値のベクタ
        if code == 0:
            report.fail("%s / %s: エラーになるはずが成功した" % (runner.name, vector_id))
            return

        if expect_error not in stderr:
            report.fail("%s / %s: エラーコードが違う (期待 %s) -> %s"
                        % (runner.name, vector_id, expect_error, stderr.strip()))
            return

        report.ok()
        return

    if code != 0:
        report.fail("%s / %s: decode に失敗した -> %s" % (runner.name, vector_id, stderr.strip()))
        return

    actual_json = read_text(json_path)
    outputs.setdefault(vector_id, {}).setdefault("json", {})[runner.name] = actual_json

    expect_path = os.path.join(TESTDATA, vector["expect"])
    if os.path.isfile(expect_path):
        expected_json = read_text(expect_path)
        if actual_json != expected_json:
            report.fail("%s / %s: 正規化JSON が期待値と違う" % (runner.name, vector_id))
            return
    else:
        report.fail("%s / %s: 期待値ファイルが無い (%s)"
                    % (runner.name, vector_id, vector["expect"]))
        return

    report.ok()

    # ラウンドトリップ: 読んで書き直したバイト列が、展開後の入力と一致すること
    if vector.get("roundtrip", False):
        binary_path = prefix + ".nbt"
        code, stderr = runner.run(["encode", input_path, binary_path] + format_args)

        if code != 0:
            report.fail("%s / %s: encode に失敗した -> %s" % (runner.name, vector_id, stderr.strip()))
            return

        expected_bytes = decompress(read_bytes(input_path), vector["compression"])
        actual_bytes = read_bytes(binary_path)
        outputs.setdefault(vector_id, {}).setdefault("binary", {})[runner.name] = actual_bytes

        if actual_bytes != expected_bytes:
            report.fail("%s / %s: ラウンドトリップでバイトが変わった (%d -> %d バイト)"
                        % (runner.name, vector_id, len(expected_bytes), len(actual_bytes)))
            return

        report.ok()

    # SNBT: 言語間で一致することだけを見る（期待値ファイルは持たない）
    snbt_path = prefix + ".snbt"
    code, stderr = runner.run(["snbt", input_path, snbt_path] + format_args)

    if code != 0:
        report.fail("%s / %s: snbt に失敗した -> %s" % (runner.name, vector_id, stderr.strip()))
        return

    outputs.setdefault(vector_id, {}).setdefault("snbt", {})[runner.name] = read_text(snbt_path)
    report.ok()





def run_world_vector(runner, vector, workdir, report, outputs):
    """チャンク（World レイヤ）のベクタを検証する。

    全ブロックを走査した集計と、決まった手順で編集した結果のバイト列を
    言語間で突き合わせる。パレットとビット詰めが 1 か所でもずれれば必ず出る。
    """
    vector_id = vector["id"]
    input_path = os.path.join(TESTDATA, vector["input"])
    prefix = os.path.join(workdir, "%s_%s" % (runner.name, vector_id.replace("/", "_")))

    report_path = prefix + ".txt"
    code, stderr = runner.run(["chunk-report", input_path, report_path])

    expect_error = vector.get("expect_error")

    if expect_error is not None:
        # 読んだ時点で弾かれること自体が期待値のベクタ
        if code == 0:
            report.fail("%s / %s: エラーになるはずが成功した" % (runner.name, vector_id))
            return

        if expect_error not in stderr:
            report.fail("%s / %s: エラーコードが違う (期待 %s) -> %s"
                        % (runner.name, vector_id, expect_error, stderr.strip()))
            return

        report.ok()
        return

    if code != 0:
        report.fail("%s / %s: chunk-report に失敗した -> %s"
                    % (runner.name, vector_id, stderr.strip()))
        return

    outputs.setdefault(vector_id, {}).setdefault("chunk_report", {})[runner.name] = \
        read_text(report_path)
    report.ok()

    edited_path = prefix + ".edited.nbt"
    code, stderr = runner.run(["chunk-edit", input_path, edited_path])

    if code != 0:
        report.fail("%s / %s: chunk-edit に失敗した -> %s"
                    % (runner.name, vector_id, stderr.strip()))
        return

    outputs.setdefault(vector_id, {}).setdefault("chunk_edited", {})[runner.name] = \
        read_bytes(edited_path)
    report.ok()

    # 編集した結果をもう一度読めること。壊れた出力を作っていないかの確認
    reread_path = prefix + ".reread.txt"
    code, stderr = runner.run(["chunk-report", edited_path, reread_path])

    if code != 0:
        report.fail("%s / %s: 編集した結果を読み直せない -> %s"
                    % (runner.name, vector_id, stderr.strip()))
        return

    outputs.setdefault(vector_id, {}).setdefault("chunk_reread", {})[runner.name] = \
        read_text(reread_path)
    report.ok()


def strip_storage_fields(listing):
    """region-list の出力から「格納のしかた」に依る項目を落とす。

    行の形は「絶対X 絶対Z タイムスタンプ 圧縮方式 圧縮後バイト数 展開後バイト数 キー数」。
    詰め直すと圧縮方式と圧縮後バイト数は当然変わるので、
    中身が保たれたかを見たいときはこの 2 つを外して比べる。
    """
    lines = []

    for line in listing.splitlines():
        fields = line.split(" ")

        # チャンク行だけが 7 項目。region / total の行はそのまま残す
        if len(fields) == 7:
            lines.append(" ".join([fields[0], fields[1], fields[2], fields[5], fields[6]]))
        else:
            lines.append(line)

    return "\n".join(lines)


def run_anvil_vector(runner, vector, workdir, report, outputs):
    """リージョンファイルのベクタを検証する。

    NBT ベクタと違い期待値ファイルは持たず、言語間の一致だけを見る。
    セクタ確保のロジックは実装ごとに書き方が変わりやすいので、
    「詰め直した結果のバイト列」が全言語で同じになることを要にする。
    """
    vector_id = vector["id"]
    input_path = os.path.join(TESTDATA, vector["input"])
    prefix = os.path.join(workdir, "%s_%s" % (runner.name, vector_id.replace("/", "_")))

    # 詰め直した結果も r.X.Z.mca でなければ座標を読み取れないので、専用のディレクトリへ置く
    rewrite_dir = prefix + ".out"
    os.makedirs(rewrite_dir, exist_ok=True)
    rewritten_path = os.path.join(rewrite_dir, os.path.basename(input_path))

    list_path = prefix + ".txt"
    code, stderr = runner.run(["region-list", input_path, list_path])

    expect_error = vector.get("expect_error")

    if expect_error is not None:
        # 開いた時点で弾かれること自体が期待値のベクタ
        if code == 0:
            report.fail("%s / %s: エラーになるはずが成功した" % (runner.name, vector_id))
            return

        if expect_error not in stderr:
            report.fail("%s / %s: エラーコードが違う (期待 %s) -> %s"
                        % (runner.name, vector_id, expect_error, stderr.strip()))
            return

        report.ok()
        return

    if code != 0:
        report.fail("%s / %s: region-list に失敗した -> %s"
                    % (runner.name, vector_id, stderr.strip()))
        return

    outputs.setdefault(vector_id, {}).setdefault("region_list", {})[runner.name] = \
        read_text(list_path)
    report.ok()

    code, stderr = runner.run(["region-rewrite", input_path, rewritten_path])

    if code != 0:
        report.fail("%s / %s: region-rewrite に失敗した -> %s"
                    % (runner.name, vector_id, stderr.strip()))
        return

    rewritten = read_bytes(rewritten_path)

    # 詰め直した結果もセクタ境界に揃っていなければならない
    if len(rewritten) % 4096 != 0:
        report.fail("%s / %s: 詰め直した結果がセクタ境界に揃っていない (%d バイト)"
                    % (runner.name, vector_id, len(rewritten)))
        return

    outputs.setdefault(vector_id, {}).setdefault("region_bytes", {})[runner.name] = rewritten
    report.ok()

    # 詰め直したファイルをもう一度読んで、同じ一覧が得られること
    relist_path = prefix + ".relist.txt"
    code, stderr = runner.run(["region-list", rewritten_path, relist_path])

    if code != 0:
        report.fail("%s / %s: 詰め直した結果を読み直せない -> %s"
                    % (runner.name, vector_id, stderr.strip()))
        return

    # 詰め直しでは圧縮方式が無圧縮に変わるため、その 2 項目を外して比べる
    if strip_storage_fields(read_text(relist_path)) != strip_storage_fields(read_text(list_path)):
        report.fail("%s / %s: 詰め直しの前後でチャンクの中身が変わった" % (runner.name, vector_id))
        return

    report.ok()


def compare_languages(outputs, report):
    """同じベクタに対する言語ごとの出力を相互に突き合わせる。"""
    for vector_id in sorted(outputs.keys()):
        for kind in sorted(outputs[vector_id].keys()):
            by_language = outputs[vector_id][kind]

            if len(by_language) < 2:
                continue

            names = sorted(by_language.keys())
            reference_name = names[0]
            reference_value = by_language[reference_name]

            # 先頭の言語を基準にして残りと比べる
            for name in names[1:]:
                if by_language[name] != reference_value:
                    report.fail("%s / %s: %s と %s で出力が違う"
                                % (vector_id, kind, reference_name, name))
                else:
                    report.ok()


def generate_expect(runner, vectors, report):
    """基準実装の出力から expect/ を作り直す。"""
    generated = 0

    for vector in vectors:
        if vector.get("expect_error") is not None:
            continue

        # Anvil / World ベクタは正規化JSON の期待値を持たない
        if vector.get("kind") in ("anvil", "world"):
            continue

        input_path = os.path.join(TESTDATA, vector["input"])
        expect_path = os.path.join(TESTDATA, vector["expect"])
        os.makedirs(os.path.dirname(expect_path), exist_ok=True)

        format_args = []
        if vector["format"] == "network":
            format_args = ["--format", "network"]

        # 手書きの期待値がある場合は、上書きせず一致するかだけを確かめる
        handwritten = os.path.isfile(expect_path) and vector["id"] == "nbt/hello_world"

        if handwritten:
            with tempfile.TemporaryDirectory() as tmp:
                candidate = os.path.join(tmp, "out.json")
                code, stderr = runner.run(["decode", input_path, candidate] + format_args)

                if code != 0:
                    report.fail("%s: decode に失敗した -> %s" % (vector["id"], stderr.strip()))
                    continue

                if read_text(candidate) != read_text(expect_path):
                    report.fail("%s: 手書きの期待値と基準実装の出力が食い違う" % vector["id"])
                    continue

            report.ok()
            continue

        code, stderr = runner.run(["decode", input_path, expect_path] + format_args)

        if code != 0:
            report.fail("%s: decode に失敗した -> %s" % (vector["id"], stderr.strip()))
            continue

        generated += 1

    print("expect/ を %d 件生成した（手書き分は検証のみ）" % generated)


def main():
    parser = argparse.ArgumentParser(description="SpringNBTLibrary の適合性検証")
    parser.add_argument("--only", action="append", default=None,
                        help="検証する言語を絞る（複数指定可）")
    parser.add_argument("--generate-expect", action="store_true",
                        help="基準実装の出力から expect/ を作り直す")
    args = parser.parse_args()

    if not os.path.isfile(MANIFEST):
        sys.stderr.write("manifest.json が無い。先に spec/tools/build_testdata.py を実行すること\n")
        return 2

    with open(MANIFEST, encoding="utf-8") as handle:
        vectors = json.load(handle)["vectors"]

    runners = build_runners()

    if args.only is not None:
        runners = [runner for runner in runners if runner.name in args.only]

    if len(runners) == 0:
        sys.stderr.write("実行できる検証ツールが無い\n")
        return 2

    print("検証ツール: %s" % ", ".join(runner.name for runner in runners))

    # 使える状態になった言語だけを残す
    available = []
    for runner in runners:
        if runner.build():
            available.append(runner)

    if len(available) == 0:
        sys.stderr.write("ビルドできた検証ツールが無い\n")
        return 2

    report = Report()

    if args.generate_expect:
        reference = None
        for runner in available:
            if runner.name == REFERENCE_LANGUAGE:
                reference = runner

        if reference is None:
            sys.stderr.write("基準実装 (%s) が使えない\n" % REFERENCE_LANGUAGE)
            return 2

        generate_expect(reference, vectors, report)
        print(report.summary())
        if len(report.failures) > 0:
            return 1
        return 0

    outputs = {}
    workdir = tempfile.mkdtemp(prefix="springnbt-conformance-")

    try:
        # 言語 × ベクタの総当たりで検証する
        for runner in available:
            for vector in vectors:
                run_vector(runner, vector, workdir, report, outputs)

        compare_languages(outputs, report)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(report.summary())

    if len(report.failures) > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
