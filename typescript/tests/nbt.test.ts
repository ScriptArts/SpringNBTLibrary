/**
 * NBT レイヤの単体テスト。
 *
 * 他言語版と同じ検証項目を持つ。
 * 共通テストベクタによる言語間比較は spec/run-conformance.sh が担当し、
 * ここでは API の振る舞いを直接確かめる。
 */

import assert from "node:assert/strict";
import test from "node:test";

import { ErrorCode, SpringNbtError } from "../src/errors.js";
import {
  Compression,
  NamedTag,
  NbtByte,
  NbtByteArray,
  NbtCompound,
  NbtDouble,
  NbtFloat,
  NbtFormat,
  NbtInt,
  NbtIntArray,
  NbtList,
  NbtLong,
  NbtLongArray,
  NbtShort,
  NbtString,
  NbtTag,
  TagType,
  detectCompression,
  mutf8,
  readBytes,
  readBytesAll,
  readBytesAt,
  snbt,
  writeBytes,
} from "../src/nbt/index.js";

const UNCOMPRESSED_READ = { compression: Compression.None };
const UNCOMPRESSED_WRITE = { compression: Compression.None };

/** 仕様書どおりに組んだ最小の NBT。 */
function helloWorldBytes(): Uint8Array {
  return Uint8Array.from([
    // ルート: TAG_Compound、名前 "hello world"
    0x0a, 0x00, 0x0b, ...Buffer.from("hello world", "ascii"),
    // 子: TAG_String、名前 "name"、値 "Bananrama"
    0x08, 0x00, 0x04, ...Buffer.from("name", "ascii"),
    0x00, 0x09, ...Buffer.from("Bananrama", "ascii"),
    // ルートの終端
    0x00,
  ]);
}

function assertErrorCode(fn: () => unknown, expected: ErrorCode): void {
  try {
    fn();
  } catch (error) {
    assert.ok(error instanceof SpringNbtError, `SpringNbtError ではない: ${String(error)}`);
    assert.equal(error.code, expected);
    return;
  }

  assert.fail(`例外が送出されなかった (期待 ${expected})`);
}

// ---------------------------------------------------------------------------
// MUTF-8
// ---------------------------------------------------------------------------

test("MUTF-8: ASCII を往復できる", () => {
  assert.deepEqual(mutf8.encode("Bananrama"), new Uint8Array(Buffer.from("Bananrama", "ascii")));
  assert.equal(mutf8.decode(new Uint8Array(Buffer.from("Bananrama", "ascii"))), "Bananrama");
});

test("MUTF-8: U+0000 は C0 80 の 2 バイトになる", () => {
  const sample = "a\u0000b";
  assert.deepEqual(mutf8.encode(sample), Uint8Array.from([0x61, 0xc0, 0x80, 0x62]));
  assert.equal(mutf8.decode(Uint8Array.from([0x61, 0xc0, 0x80, 0x62])), sample);
});

test("MUTF-8: 補助文字は CESU-8 になる", () => {
  const sample = "\u{1F600}";
  const encoded = Uint8Array.from([0xed, 0xa0, 0xbd, 0xed, 0xb8, 0x80]);
  assert.deepEqual(mutf8.encode(sample), encoded);
  assert.equal(mutf8.decode(encoded), sample);
});

test("MUTF-8: 孤立サロゲートも往復できる", () => {
  const lone = "\ud83d";
  assert.deepEqual(mutf8.encode(lone), Uint8Array.from([0xed, 0xa0, 0xbd]));
  assert.equal(mutf8.decode(Uint8Array.from([0xed, 0xa0, 0xbd])), lone);
});

test("MUTF-8: 不正な入力を弾く", () => {
  const cases = [
    Uint8Array.from([0x00]),
    Uint8Array.from([0xc1, 0x81]),
    Uint8Array.from([0xf0, 0x9f, 0x98, 0x80]),
    Uint8Array.from([0xe3, 0x81]),
  ];

  // 素の 0x00 / 冗長符号化 / 4バイト形式 / 途中で切れた入力 のすべてを拒否する
  for (const data of cases) {
    assertErrorCode(() => mutf8.decode(data), ErrorCode.MalformedData);
  }
});

test("MUTF-8: byteLength は符号化結果の長さと一致する", () => {
  const sample = "abcあ\u{1F600}";
  assert.equal(mutf8.byteLength(sample), mutf8.encode(sample).length);
});

// ---------------------------------------------------------------------------
// バイナリ読み書き
// ---------------------------------------------------------------------------

test("手で組んだ hello_world を読める", () => {
  const named = readBytes(helloWorldBytes(), UNCOMPRESSED_READ);

  assert.equal(named.name, "hello world");
  assert.equal(named.tag.size, 1);
  assert.equal(named.tag.getString("name"), "Bananrama");
});

test("読んで書き直すと同じバイト列になる", () => {
  const original = helloWorldBytes();
  const named = readBytes(original, UNCOMPRESSED_READ);

  assert.deepEqual(writeBytes(named, UNCOMPRESSED_WRITE), original);
});

test("全13タグ型が往復する", () => {
  const root = buildAllTags();
  const encoded = writeBytes(new NamedTag("", root), UNCOMPRESSED_WRITE);
  const decoded = readBytes(encoded, UNCOMPRESSED_READ);

  assert.deepEqual(writeBytes(decoded, UNCOMPRESSED_WRITE), encoded);
});

test("浮動小数点の特殊値はビットパターンが保たれる", () => {
  const root = new NbtCompound();
  root.set("negative_zero", new NbtDouble(-0));
  root.set("nan", new NbtFloat(Number.NaN));
  root.set("infinity", new NbtDouble(Number.POSITIVE_INFINITY));

  const encoded = writeBytes(new NamedTag("", root), UNCOMPRESSED_WRITE);
  const decoded = readBytes(encoded, UNCOMPRESSED_READ).tag;

  // -0 と +0 は === では区別できないので Object.is で見る
  assert.ok(Object.is(decoded.getDouble("negative_zero"), -0));
  assert.ok(Number.isNaN(decoded.getFloat("nan")));
  assert.equal(decoded.getDouble("infinity"), Number.POSITIVE_INFINITY);
});

test("Compound は挿入順を保つ", () => {
  const root = new NbtCompound();
  root.set("zebra", new NbtInt(1));
  root.set("apple", new NbtInt(2));
  root.set("mango", new NbtInt(3));

  // 既存キーへの再設定は位置を変えない
  root.set("zebra", new NbtInt(9));

  assert.deepEqual([...root.keys()], ["zebra", "apple", "mango"]);

  const encoded = writeBytes(new NamedTag("", root), UNCOMPRESSED_WRITE);
  const decoded = readBytes(encoded, UNCOMPRESSED_READ).tag;

  assert.deepEqual([...decoded.keys()], ["zebra", "apple", "mango"]);
});

test("空リストの要素型は End のまま保たれる", () => {
  const root = new NbtCompound();
  root.set("empty", new NbtList());

  const encoded = writeBytes(new NamedTag("", root), UNCOMPRESSED_WRITE);
  const decoded = readBytes(encoded, UNCOMPRESSED_READ).tag;

  assert.equal(decoded.getList("empty").elementType, TagType.End);
});

test("リストは異なる型の混在を拒否する", () => {
  const list = new NbtList();
  list.add(new NbtInt(1));

  assertErrorCode(() => list.add(new NbtString("x")), ErrorCode.UnexpectedTagType);
});

test("型付き取得子はキー欠落と型不一致を区別する", () => {
  const root = new NbtCompound();
  root.set("value", new NbtString("text"));

  // キーが無い場合は undefined
  assert.equal(root.optInt("missing"), undefined);

  // 型が違う場合はキーの有無に関わらず例外
  assertErrorCode(() => root.optInt("value"), ErrorCode.UnexpectedTagType);
  assertErrorCode(() => root.getInt("missing"), ErrorCode.InvalidArgument);
});

test("圧縮方式が自動判定される", () => {
  const named = readBytes(helloWorldBytes(), UNCOMPRESSED_READ);

  // 3 種の方式それぞれで、書き出した結果を方式指定なしで読み戻せること
  for (const method of [Compression.Gzip, Compression.Zlib, Compression.None]) {
    const encoded = writeBytes(named, { compression: method });
    assert.equal(detectCompression(encoded), method);
    assert.equal(readBytes(encoded).tag.getString("name"), "Bananrama");
  }
});

test("ネットワーク形式はルート名を持たない", () => {
  const root = new NbtCompound();
  root.set("x", new NbtInt(1));

  const encoded = writeBytes(new NamedTag("ignored", root), {
    format: NbtFormat.Network,
    compression: Compression.None,
  });

  // タグID + ペイロード のみで、名前長の 2 バイトが無い
  assert.equal(encoded[0], 0x0a);
  assert.equal(encoded[1], 0x03);

  const decoded = readBytes(encoded, {
    format: NbtFormat.Network,
    compression: Compression.None,
  });

  assert.equal(decoded.name, "");
  assert.equal(decoded.tag.getInt("x"), 1);
});

test("途中で切れた入力を弾く", () => {
  const full = helloWorldBytes();
  assertErrorCode(
    () => readBytes(full.slice(0, full.length - 3), UNCOMPRESSED_READ),
    ErrorCode.MalformedData,
  );
});

test("巨大な宣言長は確保前に弾く", () => {
  // ルート直下に「長さ 0x7FFFFFFF の ByteArray」を宣言するだけの入力
  const data = Uint8Array.from([
    0x0a, 0x00, 0x00, 0x07, 0x00, 0x01, 0x61, 0x7f, 0xff, 0xff, 0xff,
  ]);

  assertErrorCode(() => readBytes(data, UNCOMPRESSED_READ), ErrorCode.MalformedData);
});

test("未知のタグIDを弾く", () => {
  const data = Uint8Array.from([0x0a, 0x00, 0x00, 0x0d]);
  assertErrorCode(() => readBytes(data, UNCOMPRESSED_READ), ErrorCode.MalformedData);
});

test("深すぎるネストを弾く", () => {
  const encoded = buildNestedCompound(600);

  assertErrorCode(() => readBytes(encoded, UNCOMPRESSED_READ), ErrorCode.LimitExceeded);

  // 上限を上げれば読める
  readBytes(encoded, { compression: Compression.None, maxDepth: 1000 });
});

test("ルートの後の余分なバイトを弾く", () => {
  const data = Uint8Array.from([...helloWorldBytes(), 0xff]);
  assertErrorCode(() => readBytes(data, UNCOMPRESSED_READ), ErrorCode.MalformedData);
});

test("書き込みで Auto は指定できない", () => {
  const named = new NamedTag("", new NbtCompound());
  assertErrorCode(
    () => writeBytes(named, { compression: Compression.Auto }),
    ErrorCode.InvalidArgument,
  );
});

test("整数の範囲は構築時に検査される", () => {
  // number は幅を持たないため、構築時に検査しないと書き出しで黙って壊れる
  assertErrorCode(() => new NbtByte(128), ErrorCode.InvalidArgument);
  assertErrorCode(() => new NbtByte(-129), ErrorCode.InvalidArgument);
  assertErrorCode(() => new NbtShort(32768), ErrorCode.InvalidArgument);
  assertErrorCode(() => new NbtInt(2147483648), ErrorCode.InvalidArgument);
  assertErrorCode(() => new NbtLong(9223372036854775808n), ErrorCode.InvalidArgument);
});

test("Long は bigint で保持され精度が落ちない", () => {
  // number では 2^53 を超える整数を正確に表せないため bigint を使う
  const root = new NbtCompound();
  root.set("seed", new NbtLong(-4172144997902289642n));

  const encoded = writeBytes(new NamedTag("", root), UNCOMPRESSED_WRITE);
  const decoded = readBytes(encoded, UNCOMPRESSED_READ).tag;

  assert.equal(decoded.getLong("seed"), -4172144997902289642n);
});

test("Float は構築時に binary32 へ丸められる", () => {
  const value = new NbtFloat(0.1).value;
  assert.equal(value, Math.fround(0.1));
  assert.notEqual(value, 0.1);
});

function buildAllTags(): NbtCompound {
  const root = new NbtCompound();
  root.set("byte", new NbtByte(-128));
  root.set("short", new NbtShort(32767));
  root.set("int", new NbtInt(-2147483648));
  root.set("long", new NbtLong(9223372036854775807n));
  root.set("float", new NbtFloat(0.49823147));
  root.set("double", new NbtDouble(0.4931287132182315));
  root.set("byte_array", new NbtByteArray(Int8Array.from([-128, 0, 127])));
  root.set("string", new NbtString("あいう"));
  root.set("int_array", new NbtIntArray(Int32Array.from([-2147483648, 0, 2147483647])));
  root.set(
    "long_array",
    new NbtLongArray(BigInt64Array.from([-9223372036854775808n, 0n, 9223372036854775807n])),
  );

  const list = new NbtList(TagType.Long);
  list.add(new NbtLong(11n));
  list.add(new NbtLong(12n));
  root.set("list", list);

  const nested = new NbtCompound();
  nested.set("name", new NbtString("Hampus"));
  nested.set("value", new NbtFloat(0.75));
  root.set("compound", nested);

  return root;
}

function buildNestedCompound(depth: number): Uint8Array {
  const bytes: number[] = [0x0a, 0x00, 0x00];

  // ルート + (depth - 1) 段の入れ子
  for (let index = 0; index < depth - 1; index++) {
    bytes.push(0x0a, 0x00, 0x01, 0x63);
  }

  // 内側から順に終端する
  for (let index = 0; index < depth; index++) {
    bytes.push(0x00);
  }

  return Uint8Array.from(bytes);
}

// ---------------------------------------------------------------------------
// SNBT
// ---------------------------------------------------------------------------

test("接尾辞が型を決める", () => {
  const cases: Array<[string, TagType]> = [
    ["1b", TagType.Byte],
    ["1s", TagType.Short],
    ["1", TagType.Int],
    ["1L", TagType.Long],
    ["1.0f", TagType.Float],
    ["1.0", TagType.Double],
    ["1.0d", TagType.Double],
    ["true", TagType.Byte],
    ["false", TagType.Byte],
    ["hello", TagType.String],
    ['"hello"', TagType.String],
  ];

  for (const [source, expected] of cases) {
    assert.equal(snbt.parse(source).type, expected, source);
  }
});

test("拡張された整数リテラル", () => {
  const cases: Array<[string, number]> = [
    ["0x10", 16],
    ["0b1001", 9],
    ["123_456", 123456],
    ["+7", 7],
    ["-7", -7],
  ];

  for (const [source, expected] of cases) {
    const tag = snbt.parse(source) as NbtInt;
    assert.equal(tag.type, TagType.Int, source);
    assert.equal(tag.value, expected, source);
  }
});

test("16進リテラルの接尾辞の扱いは仕様で固定されている", () => {
  // 仕様 11 の 2.1: 16進では b/d/f を数字として読む。幅接尾辞は s/l のみ
  assert.equal((snbt.parse("0xFF") as NbtInt).value, 255);
  assert.equal((snbt.parse("0xFFb") as NbtInt).value, 4091);
  assert.equal((snbt.parse("0xFFl") as NbtLong).value, 255n);
  assert.equal((snbt.parse("0xFFs") as NbtShort).value, 255);
});

test("0b は 2 進リテラルではなく Byte の 0", () => {
  assert.equal(snbt.parse("0b").type, TagType.Byte);
  assert.equal((snbt.parse("0b") as NbtByte).value, 0);
  assert.equal((snbt.parse("0b1") as NbtInt).value, 1);
  assert.equal((snbt.parse("0b1001b") as NbtByte).value, 9);
});

test("符号なし接尾辞は符号付きへ読み替えられる", () => {
  assert.equal((snbt.parse("255ub") as NbtByte).value, -1);
  assert.equal((snbt.parse("65535us") as NbtShort).value, -1);
  assertErrorCode(() => snbt.parse("256ub"), ErrorCode.MalformedData);
});

test("接尾辞なし整数は Long へ格上げされない", () => {
  assertErrorCode(() => snbt.parse("2147483648"), ErrorCode.MalformedData);
  assert.equal((snbt.parse("2147483648L") as NbtLong).value, 2147483648n);
});

test("型付き配列", () => {
  assert.deepEqual((snbt.parse("[B; 1b, 2b]") as NbtByteArray).value, Int8Array.from([1, 2]));
  assert.deepEqual((snbt.parse("[I; 1, 2]") as NbtIntArray).value, Int32Array.from([1, 2]));
  assert.deepEqual(
    (snbt.parse("[L; 1L, 2L]") as NbtLongArray).value,
    BigInt64Array.from([1n, 2n]),
  );

  // 接尾辞なしでも範囲内なら受理する（Minecraft 自身がそう書き出すため）
  assert.deepEqual((snbt.parse("[B; 1, 2]") as NbtByteArray).value, Int8Array.from([1, 2]));
  assertErrorCode(() => snbt.parse("[B; 200]"), ErrorCode.MalformedData);
});

test("末尾カンマを許す", () => {
  assert.equal(snbt.parseCompound("{a:1,b:2,}").size, 2);
  assert.equal((snbt.parse("[1,2,]") as NbtList).size, 2);
});

test("異種リストは受理しない", () => {
  // バイナリ NBT へ写せないため受理しない (adr/0006)
  assertErrorCode(() => snbt.parse('[1, "a"]'), ErrorCode.MalformedData);
});

test("エスケープシーケンス", () => {
  assert.equal((snbt.parse('"\\n"') as NbtString).value, "\n");
  assert.equal((snbt.parse('"\\x42"') as NbtString).value, "B");
  assert.equal((snbt.parse('"\\u0048"') as NbtString).value, "H");
  assert.equal((snbt.parse('"\\s"') as NbtString).value, " ");
  assert.equal((snbt.parse('"\\U0001F600"') as NbtString).value, "\u{1F600}");
  assertErrorCode(() => snbt.parse('"\\N{SNOWMAN}"'), ErrorCode.UnsupportedFeature);
});

test("単一引用符の文字列", () => {
  assert.equal((snbt.parse("'say \"hi\"'") as NbtString).value, 'say "hi"');
});

test("bool() と uuid()", () => {
  assert.equal((snbt.parse("bool(5)") as NbtByte).value, 1);
  assert.equal((snbt.parse("bool(0)") as NbtByte).value, 0);

  const uuid = snbt.parse('uuid("00112233-4455-6677-8899-aabbccddeeff")') as NbtIntArray;
  assert.deepEqual(uuid.value, Int32Array.from([0x00112233, 0x44556677, -0x77665545, -0x33221101]));
});

test("SNBT -> NBT -> SNBT -> NBT で NBT が一致する", () => {
  const source =
    "{ name : 'Bananrama' , list : [ 1L , 2L ] , nested : { flag : true } , " +
    "bytes : [B; 1b, -2b] , ratio : 0.5f }";

  const first = snbt.parse(source);
  assert.equal(snbt.write(snbt.parse(snbt.write(first))), snbt.write(first));
  assert.equal(snbt.write(snbt.parse(snbt.writePretty(first))), snbt.write(first));
});

test("書き出しは可能ならキーを引用符なしにする", () => {
  const compound = new NbtCompound();
  compound.set("plain", new NbtInt(1));
  compound.set("needs quote", new NbtInt(2));

  assert.equal(snbt.write(compound), '{plain:1,"needs quote":2}');
});

test("整形出力は空白 4 個でインデントする", () => {
  const nested = new NbtCompound();
  nested.set("x", new NbtInt(1));
  const compound = new NbtCompound();
  compound.set("inner", nested);

  assert.equal(snbt.writePretty(compound), "{\n    inner: {\n        x: 1\n    }\n}");
});

test("値の後の余分な文字を弾く", () => {
  assertErrorCode(() => snbt.parse("{a:1} junk"), ErrorCode.MalformedData);
  assertErrorCode(() => snbt.parseCompound("42"), ErrorCode.UnexpectedTagType);
});

// ---------------------------------------------------------------------------
// 浮動小数点の正準10進表記
// ---------------------------------------------------------------------------

test("Float の正準10進表記", () => {
  const cases: Array<[number, string]> = [
    [1.0, "1.0f"],
    [-1.0, "-1.0f"],
    [0.0, "0.0f"],
    [0.75, "0.75f"],
    [0.49823147, "0.49823147f"],
    [2000.0, "2000.0f"],
    [1e20, "1.0E20f"],
    [1e-30, "1.0E-30f"],
    [0.5, "0.5f"],
    [123.456, "123.456f"],
  ];

  for (const [value, expected] of cases) {
    assert.equal(snbt.write(new NbtFloat(value)), expected, String(value));
  }
});

test("Double の正準10進表記", () => {
  const cases: Array<[number, string]> = [
    [1.0, "1.0d"],
    [0.015, "0.015d"],
    [2000.0, "2000.0d"],
    [0.4931287132182315, "0.4931287132182315d"],
    [3.141592653589793, "3.141592653589793d"],
    [1e20, "1.0E20d"],
    [1e17, "1.0E17d"],
    [1e16, "10000000000000000.0d"],
    [1e-4, "0.0001d"],
    [1e-5, "1.0E-5d"],
  ];

  for (const [value, expected] of cases) {
    assert.equal(snbt.write(new NbtDouble(value)), expected, String(value));
  }
});

test("負のゼロは符号を保つ", () => {
  // JavaScript の toExponential は -0 の符号を落とすため、ここが崩れやすい
  assert.equal(snbt.write(new NbtDouble(-0)), "-0.0d");
  assert.equal(snbt.write(new NbtFloat(-0)), "-0.0f");
});

test("特殊値の表記", () => {
  assert.equal(snbt.write(new NbtDouble(Number.NaN)), "NaNd");
  assert.equal(snbt.write(new NbtDouble(Number.POSITIVE_INFINITY)), "Infinityd");
  assert.equal(snbt.write(new NbtDouble(Number.NEGATIVE_INFINITY)), "-Infinityd");
  assert.equal(snbt.write(new NbtFloat(Number.NaN)), "NaNf");
});

test("書き出した表記を読み戻すとビットが一致する", () => {
  const doubles = [0, -0, 1, -1, 0.1, 1 / 3, 1e300, 1e-300, 4903];
  const view = new DataView(new ArrayBuffer(8));

  for (const value of doubles) {
    const parsed = snbt.parse(snbt.write(new NbtDouble(value))) as NbtDouble;
    view.setFloat64(0, value, false);
    const expected = view.getBigUint64(0, false);
    view.setFloat64(0, parsed.value, false);
    assert.equal(view.getBigUint64(0, false), expected, String(value));
  }

  const floats = [0, -0, 1, -1, 0.1, 1 / 3, 1e30, 1e-30, 4903];

  for (const value of floats) {
    const source = new NbtFloat(value);
    const parsed = snbt.parse(snbt.write(source)) as NbtFloat;
    view.setFloat32(0, source.value, false);
    const expected = view.getUint32(0, false);
    view.setFloat32(0, parsed.value, false);
    assert.equal(view.getUint32(0, false), expected, String(value));
  }
});

test("equals: 同じ型で同じ値なら等しい", () => {
  assert.ok(new NbtInt(42).equals(new NbtInt(42)));
  assert.ok(new NbtLong(42n).equals(new NbtLong(42n)));
  assert.ok(new NbtString("あ").equals(new NbtString("あ")));
  assert.ok(new NbtByteArray(Int8Array.from([1, 2])).equals(new NbtByteArray(Int8Array.from([1, 2]))));

  assert.ok(!new NbtInt(42).equals(new NbtInt(43)));
  assert.ok(!new NbtByteArray(Int8Array.from([1])).equals(new NbtByteArray(Int8Array.from([1, 2]))));
});

test("equals: 型が違えば等しくない", () => {
  // 値が同じでもタグの型が違えば別物
  assert.ok(!new NbtInt(1).equals(new NbtShort(1)));
  assert.ok(!new NbtInt(1).equals(1));
  assert.ok(!new NbtInt(1).equals(undefined));
});

test("equals: 浮動小数点はビットパターンで比べる", () => {
  // NaN 同士は等しく、+0.0 と -0.0 は等しくない
  assert.ok(new NbtFloat(NaN).equals(new NbtFloat(NaN)));
  assert.ok(new NbtDouble(NaN).equals(new NbtDouble(NaN)));
  assert.ok(!new NbtFloat(0).equals(new NbtFloat(-0)));
  assert.ok(!new NbtDouble(0).equals(new NbtDouble(-0)));
});

test("equals: リストは要素型と並びを見る", () => {
  const left = new NbtList();
  left.add(new NbtInt(1));
  left.add(new NbtInt(2));

  const right = new NbtList();
  right.add(new NbtInt(1));
  right.add(new NbtInt(2));
  assert.ok(left.equals(right));

  const reversed = new NbtList();
  reversed.add(new NbtInt(2));
  reversed.add(new NbtInt(1));
  assert.ok(!left.equals(reversed));

  // 空でも要素型が違えば別物
  assert.ok(!new NbtList(TagType.Int).equals(new NbtList(TagType.Byte)));
});

test("equals: Compound はキーの並び順も見る", () => {
  const left = new NbtCompound();
  left.set("a", new NbtInt(1));
  left.set("b", new NbtInt(2));

  const same = new NbtCompound();
  same.set("a", new NbtInt(1));
  same.set("b", new NbtInt(2));
  assert.ok(left.equals(same));

  // 中身は同じでも挿入順が違えば別物
  const reordered = new NbtCompound();
  reordered.set("b", new NbtInt(2));
  reordered.set("a", new NbtInt(1));
  assert.ok(!left.equals(reordered));
});

test("copy: 深いコピーになっている", () => {
  const original = new NbtCompound();
  const inner = new NbtList();
  inner.add(new NbtInt(1));
  original.set("l", inner);

  const copied = original.copy();
  copied.getList("l").add(new NbtInt(2));

  assert.equal(original.getList("l").size, 1);
  assert.equal(copied.getList("l").size, 2);
  assert.ok(!original.equals(copied));
});

test("連なった NBT を位置指定で順に読み進められる", () => {
  const joined = concat(helloWorldBytes(), helloWorldBytes(), helloWorldBytes());
  let offset = 0;
  let count = 0;

  // 直前の終了位置を次の開始位置にして読み進める
  while (offset < joined.length) {
    const result = readBytesAt(joined, offset, UNCOMPRESSED_READ);
    assert.equal(result.tag.name, "hello world");
    assert.equal((result.tag.tag as NbtCompound).getString("name"), "Bananrama");
    offset = result.end;
    count++;
  }

  assert.equal(count, 3);
  assert.equal(offset, joined.length);
});

test("連なった NBT をまとめて読める", () => {
  const joined = concat(helloWorldBytes(), helloWorldBytes());
  const tags = readBytesAll(joined, UNCOMPRESSED_READ);

  assert.equal(tags.length, 2);
  assert.equal(tags[0].name, "hello world");
  assert.equal(tags[1].name, "hello world");
});

test("空の入力からは 0 個読める", () => {
  assert.deepEqual(readBytesAll(new Uint8Array(0), UNCOMPRESSED_READ), []);
});

test("範囲外の位置を弾く", () => {
  const bytes = helloWorldBytes();

  assert.throws(
    () => readBytesAt(bytes, bytes.length + 1, UNCOMPRESSED_READ),
    (error: SpringNbtError) => error.code === ErrorCode.InvalidArgument,
  );
});

test("位置を指定した読み込みでは圧縮を扱えない", () => {
  assert.throws(
    () => readBytesAt(helloWorldBytes(), 0, { compression: Compression.Gzip }),
    (error: SpringNbtError) => error.code === ErrorCode.InvalidArgument,
  );
});

test("型付き設定子は取得子と対になっている", () => {
  const root = new NbtCompound();
  root.setByte("b", -128);
  root.setShort("s", 32767);
  root.setInt("i", -2147483648);
  root.setLong("l", 9223372036854775807n);
  root.setFloat("f", 1.5);
  root.setDouble("d", -2.25);
  root.setBool("t", true);
  root.setBool("n", false);
  root.setString("str", "Bananrama");
  root.setByteArray("ba", Int8Array.from([1, -1]));
  root.setIntArray("ia", Int32Array.from([1, -1]));
  root.setLongArray("la", BigInt64Array.from([1n, -1n]));

  assert.equal(root.getByte("b"), -128);
  assert.equal(root.getShort("s"), 32767);
  assert.equal(root.getInt("i"), -2147483648);
  assert.equal(root.getLong("l"), 9223372036854775807n);
  assert.equal(root.getFloat("f"), 1.5);
  assert.equal(root.getDouble("d"), -2.25);
  assert.equal(root.getBool("t"), true);
  assert.equal(root.getBool("n"), false);
  assert.equal(root.getString("str"), "Bananrama");
  assert.deepEqual(root.getByteArray("ba"), Int8Array.from([1, -1]));
  assert.deepEqual(root.getIntArray("ia"), Int32Array.from([1, -1]));
  assert.deepEqual(root.getLongArray("la"), BigInt64Array.from([1n, -1n]));

  // 真偽値は TAG_Byte の 0 / 1 として入る
  assert.equal(root.get("t").type, TagType.Byte);
});

test("型付き設定子は挿入順を変えない", () => {
  const root = new NbtCompound();
  root.setInt("a", 1);
  root.setInt("b", 2);

  // 既存キーへの再設定は位置を変えない
  root.setInt("a", 3);

  assert.deepEqual([...root.keys()], ["a", "b"]);
  assert.equal(root.getInt("a"), 3);
});

/** 複数のバイト列をつなぐ。 */
function concat(...parts: Uint8Array[]): Uint8Array {
  let total = 0;

  // まず全体の長さを数える
  for (const part of parts) {
    total += part.length;
  }

  const joined = new Uint8Array(total);
  let written = 0;

  // 与えられた順にそのままつなぐ
  for (const part of parts) {
    joined.set(part, written);
    written += part.length;
  }

  return joined;
}

/** 型が推論できることを確かめるだけの参照（未使用変数の警告を避ける）。 */
const _tagTypeReference: NbtTag | undefined = undefined;
void _tagTypeReference;
