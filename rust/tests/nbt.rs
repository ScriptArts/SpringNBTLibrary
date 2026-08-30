//! NBT レイヤの統合テスト。
//!
//! 他言語版と同じ検証項目を持つ。
//! 共通テストベクタによる言語間比較は `spec/run-conformance.sh` が担当し、
//! ここでは API の振る舞いを直接確かめる。

use spring_nbt_library::error::ErrorCode;
use spring_nbt_library::nbt::snbt;
use spring_nbt_library::nbt::tag::{NbtCompound, NbtList, NbtString, NbtTag, TagType};
use spring_nbt_library::nbt::{
    detect_compression, mutf8, read_bytes, write_bytes, Compression, NamedTag, NbtFormat,
    NbtReadOptions, NbtWriteOptions,
};

fn uncompressed_read() -> NbtReadOptions {
    NbtReadOptions { compression: Compression::None, ..NbtReadOptions::default() }
}

fn uncompressed_write() -> NbtWriteOptions {
    NbtWriteOptions::uncompressed()
}

/// 仕様書どおりに組んだ最小の NBT。
fn hello_world_bytes() -> Vec<u8> {
    let mut bytes: Vec<u8> = Vec::new();

    // ルート: TAG_Compound、名前 "hello world"
    bytes.push(0x0A);
    bytes.extend_from_slice(&[0x00, 0x0B]);
    bytes.extend_from_slice(b"hello world");

    // 子: TAG_String、名前 "name"、値 "Bananrama"
    bytes.push(0x08);
    bytes.extend_from_slice(&[0x00, 0x04]);
    bytes.extend_from_slice(b"name");
    bytes.extend_from_slice(&[0x00, 0x09]);
    bytes.extend_from_slice(b"Bananrama");

    // ルートの終端
    bytes.push(0x00);

    bytes
}

/// 全13タグ型を含む Compound を作る。
fn build_all_tags() -> NbtCompound {
    let mut root = NbtCompound::new();
    root.set("byte", NbtTag::Byte(-128));
    root.set("short", NbtTag::Short(32767));
    root.set("int", NbtTag::Int(-2147483648));
    root.set("long", NbtTag::Long(9223372036854775807));
    root.set("float", NbtTag::Float(0.498_231_47));
    root.set("double", NbtTag::Double(0.493_128_713_218_231_5));
    root.set("byte_array", NbtTag::ByteArray(vec![-128, 0, 127]));
    root.set("string", NbtTag::String(NbtString::new("あいう")));
    root.set("int_array", NbtTag::IntArray(vec![i32::MIN, 0, i32::MAX]));
    root.set("long_array", NbtTag::LongArray(vec![i64::MIN, 0, i64::MAX]));

    let mut list = NbtList::with_element_type(TagType::Long);
    list.push(NbtTag::Long(11)).unwrap();
    list.push(NbtTag::Long(12)).unwrap();
    root.set("list", NbtTag::List(list));

    let mut nested = NbtCompound::new();
    nested.set("name", NbtTag::String(NbtString::new("Hampus")));
    nested.set("value", NbtTag::Float(0.75));
    root.set("compound", NbtTag::Compound(nested));

    root
}

/// 指定した深さまで Compound を入れ子にしたバイト列を作る。
fn build_nested_compound(depth: usize) -> Vec<u8> {
    let mut bytes: Vec<u8> = vec![0x0A, 0x00, 0x00];

    // ルート + (depth - 1) 段の入れ子
    for _ in 0..depth - 1 {
        bytes.extend_from_slice(&[0x0A, 0x00, 0x01, b'c']);
    }

    // 内側から順に終端する
    for _ in 0..depth {
        bytes.push(0x00);
    }

    bytes
}

// ---------------------------------------------------------------------------
// MUTF-8
// ---------------------------------------------------------------------------

#[test]
fn mutf8_roundtrips_and_rejects_invalid_input() {
    // ASCII
    assert_eq!(mutf8::encode("Bananrama"), b"Bananrama");

    // U+0000 は C0 80 の 2 バイトになる
    assert_eq!(mutf8::encode("a\u{0000}b"), vec![0x61, 0xC0, 0x80, 0x62]);

    // 補助文字は CESU-8 になる
    assert_eq!(
        mutf8::encode("\u{1F600}"),
        vec![0xED, 0xA0, 0xBD, 0xED, 0xB8, 0x80]
    );

    // 素の 0x00 / 冗長符号化 / 4バイト形式 / 途中で切れた入力 のすべてを拒否する
    let invalid: Vec<Vec<u8>> = vec![
        vec![0x00],
        vec![0xC1, 0x81],
        vec![0xF0, 0x9F, 0x98, 0x80],
        vec![0xE3, 0x81],
    ];

    for data in invalid {
        let error = mutf8::decode_to_utf16(&data).unwrap_err();
        assert_eq!(error.code(), ErrorCode::MalformedData, "{data:?}");
    }
}

#[test]
fn lone_surrogate_is_kept_in_a_separate_representation() {
    // Rust の String は UTF-8 に限られるため、専用の表現へ退避する
    let value = NbtString::from_utf16(vec![0xD83D]);
    assert!(matches!(value, NbtString::Surrogates(_)));
    assert_eq!(value.as_str(), None);
    assert_eq!(value.to_mutf8(), vec![0xED, 0xA0, 0xBD]);

    // 通常の文字列は Text になる
    let text = NbtString::from_utf16("あ".encode_utf16().collect());
    assert_eq!(text.as_str(), Some("あ"));
}

// ---------------------------------------------------------------------------
// バイナリ読み書き
// ---------------------------------------------------------------------------

#[test]
fn reads_hand_built_hello_world() {
    let named = read_bytes(&hello_world_bytes(), &uncompressed_read()).unwrap();

    assert_eq!(named.name, "hello world");
    assert_eq!(named.tag.len(), 1);
    assert_eq!(named.tag.get_string("name").unwrap(), "Bananrama");
}

#[test]
fn writes_back_the_same_bytes() {
    let original = hello_world_bytes();
    let named = read_bytes(&original, &uncompressed_read()).unwrap();

    assert_eq!(write_bytes(&named, &uncompressed_write()).unwrap(), original);
}

#[test]
fn all_tag_types_roundtrip() {
    let root = build_all_tags();
    let named = NamedTag::new("", root.clone());

    let encoded = write_bytes(&named, &uncompressed_write()).unwrap();
    let decoded = read_bytes(&encoded, &uncompressed_read()).unwrap();

    assert_eq!(decoded.tag, root);
    assert_eq!(write_bytes(&decoded, &uncompressed_write()).unwrap(), encoded);
}

#[test]
fn float_specials_keep_their_bit_pattern() {
    let mut root = NbtCompound::new();
    root.set("negative_zero", NbtTag::Double(-0.0));
    root.set("nan", NbtTag::Float(f32::NAN));
    root.set("infinity", NbtTag::Double(f64::INFINITY));

    let encoded = write_bytes(&NamedTag::new("", root), &uncompressed_write()).unwrap();
    let decoded = read_bytes(&encoded, &uncompressed_read()).unwrap().tag;

    // -0.0 と +0.0 は == では区別できないので、ビットパターンで比較する
    assert_eq!(
        decoded.get_double("negative_zero").unwrap().to_bits(),
        (-0.0f64).to_bits()
    );
    assert!(decoded.get_float("nan").unwrap().is_nan());
    assert_eq!(decoded.get_double("infinity").unwrap(), f64::INFINITY);
}

#[test]
fn compound_keeps_insertion_order() {
    let mut root = NbtCompound::new();
    root.set("zebra", NbtTag::Int(1));
    root.set("apple", NbtTag::Int(2));
    root.set("mango", NbtTag::Int(3));

    // 既存キーへの再設定は位置を変えない
    root.set("zebra", NbtTag::Int(9));

    let keys: Vec<&str> = root.keys().collect();
    assert_eq!(keys, vec!["zebra", "apple", "mango"]);

    let encoded = write_bytes(&NamedTag::new("", root), &uncompressed_write()).unwrap();
    let decoded = read_bytes(&encoded, &uncompressed_read()).unwrap().tag;

    let keys: Vec<&str> = decoded.keys().collect();
    assert_eq!(keys, vec!["zebra", "apple", "mango"]);
}

#[test]
fn removing_a_key_keeps_the_remaining_order() {
    let mut root = NbtCompound::new();
    root.set("a", NbtTag::Int(1));
    root.set("b", NbtTag::Int(2));
    root.set("c", NbtTag::Int(3));

    assert!(root.remove("b"));
    assert!(!root.remove("b"));

    let keys: Vec<&str> = root.keys().collect();
    assert_eq!(keys, vec!["a", "c"]);
    assert_eq!(root.get_int("c").unwrap(), 3);
}

#[test]
fn empty_list_keeps_element_type_end() {
    let mut root = NbtCompound::new();
    root.set("empty", NbtTag::List(NbtList::new()));

    let encoded = write_bytes(&NamedTag::new("", root), &uncompressed_write()).unwrap();
    let decoded = read_bytes(&encoded, &uncompressed_read()).unwrap().tag;

    assert_eq!(decoded.get_list("empty").unwrap().element_type(), TagType::End);
}

#[test]
fn list_rejects_mixed_types() {
    let mut list = NbtList::new();
    list.push(NbtTag::Int(1)).unwrap();

    let error = list.push(NbtTag::String(NbtString::new("x"))).unwrap_err();
    assert_eq!(error.code(), ErrorCode::UnexpectedTagType);
}

#[test]
fn list_keeps_element_type_after_clear() {
    let mut list = NbtList::new();
    list.push(NbtTag::Int(1)).unwrap();
    list.clear();

    // 全要素を削除しても確定済みの要素型は維持する
    assert_eq!(list.element_type(), TagType::Int);
    assert!(list.is_empty());
}

#[test]
fn typed_getter_distinguishes_missing_key_from_wrong_type() {
    let mut root = NbtCompound::new();
    root.set("value", NbtTag::String(NbtString::new("text")));

    // キーが無い場合は None
    assert_eq!(root.opt_int("missing").unwrap(), None);

    // 型が違う場合はキーの有無に関わらずエラー
    assert_eq!(
        root.opt_int("value").unwrap_err().code(),
        ErrorCode::UnexpectedTagType
    );
    assert_eq!(
        root.get_int("missing").unwrap_err().code(),
        ErrorCode::InvalidArgument
    );
}

#[test]
fn compression_is_detected_automatically() {
    let named = read_bytes(&hello_world_bytes(), &uncompressed_read()).unwrap();

    // 3 種の方式それぞれで、書き出した結果を方式指定なしで読み戻せること
    for method in [Compression::Gzip, Compression::Zlib, Compression::None] {
        let options = NbtWriteOptions { format: NbtFormat::Java, compression: method };
        let encoded = write_bytes(&named, &options).unwrap();

        assert_eq!(detect_compression(&encoded).unwrap(), method);

        let decoded = read_bytes(&encoded, &NbtReadOptions::default()).unwrap();
        assert_eq!(decoded.tag.get_string("name").unwrap(), "Bananrama");
    }
}

#[test]
fn network_format_has_no_root_name() {
    let mut root = NbtCompound::new();
    root.set("x", NbtTag::Int(1));

    let write_options =
        NbtWriteOptions { format: NbtFormat::Network, compression: Compression::None };
    let encoded = write_bytes(&NamedTag::new("ignored", root), &write_options).unwrap();

    // タグID + ペイロード のみで、名前長の 2 バイトが無い
    assert_eq!(encoded[0], 0x0A);
    assert_eq!(encoded[1], 0x03);

    let read_options = NbtReadOptions {
        format: NbtFormat::Network,
        compression: Compression::None,
        ..NbtReadOptions::default()
    };
    let decoded = read_bytes(&encoded, &read_options).unwrap();

    assert_eq!(decoded.name, "");
    assert_eq!(decoded.tag.get_int("x").unwrap(), 1);
}

#[test]
fn malformed_inputs_are_rejected() {
    let full = hello_world_bytes();

    // 途中で切れた入力
    let truncated = &full[..full.len() - 3];
    assert_eq!(
        read_bytes(truncated, &uncompressed_read()).unwrap_err().code(),
        ErrorCode::MalformedData
    );

    // ルートの後に余分なバイトがある
    let mut trailing = full.clone();
    trailing.push(0xFF);
    assert_eq!(
        read_bytes(&trailing, &uncompressed_read()).unwrap_err().code(),
        ErrorCode::MalformedData
    );

    // 長さ 0x7FFFFFFF を宣言するだけの入力（確保前に弾く）
    let huge = vec![0x0A, 0x00, 0x00, 0x07, 0x00, 0x01, b'a', 0x7F, 0xFF, 0xFF, 0xFF];
    assert_eq!(
        read_bytes(&huge, &uncompressed_read()).unwrap_err().code(),
        ErrorCode::MalformedData
    );

    // 未知のタグID
    let unknown = vec![0x0A, 0x00, 0x00, 0x0D];
    assert_eq!(
        read_bytes(&unknown, &uncompressed_read()).unwrap_err().code(),
        ErrorCode::MalformedData
    );

    // キーが孤立サロゲート（値と違いキーでは許さない）
    let lone_key = vec![
        0x0A, 0x00, 0x00, 0x03, 0x00, 0x03, 0xED, 0xA0, 0xBD, 0x00, 0x00, 0x00, 0x01, 0x00,
    ];
    assert_eq!(
        read_bytes(&lone_key, &uncompressed_read()).unwrap_err().code(),
        ErrorCode::MalformedData
    );
}

#[test]
fn excessive_nesting_is_rejected() {
    // 読み込みは再帰で行うため、深いネストはスタックを使う。
    // debug ビルドはフレームが太く、テストスレッド既定の 2 MiB では 512 段に届かない。
    // 実運用の release ビルドでは 2 MiB でも 2000 段を超えて扱えるが、
    // ここでは測定対象を「深さ上限の判定」に絞るため十分なスタックを与える。
    let handle = std::thread::Builder::new()
        .stack_size(32 * 1024 * 1024)
        .spawn(|| {
            let encoded = build_nested_compound(600);

            assert_eq!(
                read_bytes(&encoded, &uncompressed_read()).unwrap_err().code(),
                ErrorCode::LimitExceeded
            );

            // 上限を上げれば読める
            let relaxed = NbtReadOptions {
                compression: Compression::None,
                max_depth: 1000,
                ..NbtReadOptions::default()
            };
            read_bytes(&encoded, &relaxed).unwrap();
        })
        .unwrap();

    handle.join().unwrap();
}

#[test]
fn write_rejects_auto_compression() {
    let named = NamedTag::new("", NbtCompound::new());
    let options = NbtWriteOptions { format: NbtFormat::Java, compression: Compression::Auto };

    assert_eq!(
        write_bytes(&named, &options).unwrap_err().code(),
        ErrorCode::InvalidArgument
    );
}

// ---------------------------------------------------------------------------
// SNBT
// ---------------------------------------------------------------------------

#[test]
fn suffix_decides_type() {
    let cases: Vec<(&str, TagType)> = vec![
        ("1b", TagType::Byte),
        ("1s", TagType::Short),
        ("1", TagType::Int),
        ("1L", TagType::Long),
        ("1.0f", TagType::Float),
        ("1.0", TagType::Double),
        ("1.0d", TagType::Double),
        ("true", TagType::Byte),
        ("false", TagType::Byte),
        ("hello", TagType::String),
        ("\"hello\"", TagType::String),
    ];

    for (source, expected) in cases {
        assert_eq!(snbt::parse(source).unwrap().tag_type(), expected, "{source}");
    }
}

#[test]
fn hex_suffix_rule_is_fixed() {
    // 仕様 11 の 2.1: 16進では b/d/f を数字として読む。幅接尾辞は s/l のみ
    assert_eq!(snbt::parse("0xFF").unwrap(), NbtTag::Int(255));
    assert_eq!(snbt::parse("0xFFb").unwrap(), NbtTag::Int(4091));
    assert_eq!(snbt::parse("0xFFl").unwrap(), NbtTag::Long(255));
    assert_eq!(snbt::parse("0xFFs").unwrap(), NbtTag::Short(255));
}

#[test]
fn zero_byte_literal_is_not_binary() {
    // 0b は「10進の 0 に Byte 接尾辞」。真偽値の false として広く使われる形
    assert_eq!(snbt::parse("0b").unwrap(), NbtTag::Byte(0));
    assert_eq!(snbt::parse("0b1").unwrap(), NbtTag::Int(1));
    assert_eq!(snbt::parse("0b1001b").unwrap(), NbtTag::Byte(9));
}

#[test]
fn extended_integer_literals() {
    assert_eq!(snbt::parse("0x10").unwrap(), NbtTag::Int(16));
    assert_eq!(snbt::parse("0b1001").unwrap(), NbtTag::Int(9));
    assert_eq!(snbt::parse("123_456").unwrap(), NbtTag::Int(123456));
    assert_eq!(snbt::parse("+7").unwrap(), NbtTag::Int(7));
    assert_eq!(snbt::parse("-7").unwrap(), NbtTag::Int(-7));
}

#[test]
fn unsigned_suffix_wraps_to_signed() {
    assert_eq!(snbt::parse("255ub").unwrap(), NbtTag::Byte(-1));
    assert_eq!(snbt::parse("65535us").unwrap(), NbtTag::Short(-1));
    assert_eq!(
        snbt::parse("256ub").unwrap_err().code(),
        ErrorCode::MalformedData
    );
}

#[test]
fn suffixless_integer_is_not_promoted_to_long() {
    assert_eq!(
        snbt::parse("2147483648").unwrap_err().code(),
        ErrorCode::MalformedData
    );
    assert_eq!(snbt::parse("2147483648L").unwrap(), NbtTag::Long(2147483648));
}

#[test]
fn typed_arrays() {
    assert_eq!(snbt::parse("[B; 1b, 2b]").unwrap(), NbtTag::ByteArray(vec![1, 2]));
    assert_eq!(snbt::parse("[I; 1, 2]").unwrap(), NbtTag::IntArray(vec![1, 2]));
    assert_eq!(snbt::parse("[L; 1L, 2L]").unwrap(), NbtTag::LongArray(vec![1, 2]));

    // 接尾辞なしでも範囲内なら受理する（Minecraft 自身がそう書き出すため）
    assert_eq!(snbt::parse("[B; 1, 2]").unwrap(), NbtTag::ByteArray(vec![1, 2]));
    assert_eq!(
        snbt::parse("[B; 200]").unwrap_err().code(),
        ErrorCode::MalformedData
    );
}

#[test]
fn trailing_commas_and_heterogeneous_lists() {
    assert_eq!(snbt::parse_compound("{a:1,b:2,}").unwrap().len(), 2);

    match snbt::parse("[1,2,]").unwrap() {
        NbtTag::List(list) => assert_eq!(list.len(), 2),
        other => panic!("リストではない: {other:?}"),
    }

    // 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
    assert_eq!(
        snbt::parse("[1, \"a\"]").unwrap_err().code(),
        ErrorCode::MalformedData
    );
}

#[test]
fn escape_sequences() {
    assert_eq!(
        snbt::parse("\"\\n\"").unwrap(),
        NbtTag::String(NbtString::new("\n"))
    );
    assert_eq!(
        snbt::parse("\"\\x42\"").unwrap(),
        NbtTag::String(NbtString::new("B"))
    );
    assert_eq!(
        snbt::parse("\"\\u0048\"").unwrap(),
        NbtTag::String(NbtString::new("H"))
    );
    assert_eq!(
        snbt::parse("\"\\s\"").unwrap(),
        NbtTag::String(NbtString::new(" "))
    );
    assert_eq!(
        snbt::parse("\"\\U0001F600\"").unwrap(),
        NbtTag::String(NbtString::new("\u{1F600}"))
    );
    assert_eq!(
        snbt::parse("\"\\N{SNOWMAN}\"").unwrap_err().code(),
        ErrorCode::UnsupportedFeature
    );
}

#[test]
fn functions() {
    assert_eq!(snbt::parse("bool(5)").unwrap(), NbtTag::Byte(1));
    assert_eq!(snbt::parse("bool(0)").unwrap(), NbtTag::Byte(0));
    assert_eq!(
        snbt::parse("uuid(\"00112233-4455-6677-8899-aabbccddeeff\")").unwrap(),
        NbtTag::IntArray(vec![
            0x00112233,
            0x44556677,
            0x8899AABBu32 as i32,
            0xCCDDEEFFu32 as i32,
        ])
    );
}

#[test]
fn snbt_to_nbt_to_snbt_to_nbt_is_stable() {
    // 仕様 11 の 5章: 保証するのは「SNBT -> NBT -> SNBT -> NBT」で NBT が一致すること
    let source = "{ name : 'Bananrama' , list : [ 1L , 2L ] , nested : { flag : true } , \
                  bytes : [B; 1b, -2b] , ratio : 0.5f }";

    let first = snbt::parse(source).unwrap();
    assert_eq!(snbt::parse(&snbt::write(&first)).unwrap(), first);
    assert_eq!(snbt::parse(&snbt::write_pretty(&first)).unwrap(), first);
}

#[test]
fn write_uses_bare_keys_when_possible() {
    let mut compound = NbtCompound::new();
    compound.set("plain", NbtTag::Int(1));
    compound.set("needs quote", NbtTag::Int(2));

    assert_eq!(
        snbt::write(&NbtTag::Compound(compound)),
        "{plain:1,\"needs quote\":2}"
    );
}

#[test]
fn write_pretty_indents_with_four_spaces() {
    let mut nested = NbtCompound::new();
    nested.set("x", NbtTag::Int(1));
    let mut compound = NbtCompound::new();
    compound.set("inner", NbtTag::Compound(nested));

    assert_eq!(
        snbt::write_pretty(&NbtTag::Compound(compound)),
        "{\n    inner: {\n        x: 1\n    }\n}"
    );
}

#[test]
fn trailing_garbage_is_rejected() {
    assert_eq!(
        snbt::parse("{a:1} junk").unwrap_err().code(),
        ErrorCode::MalformedData
    );
    assert_eq!(
        snbt::parse_compound("42").unwrap_err().code(),
        ErrorCode::UnexpectedTagType
    );
}

// ---------------------------------------------------------------------------
// 浮動小数点の正準10進表記
// ---------------------------------------------------------------------------

#[test]
fn float_formatting() {
    let cases: Vec<(f32, &str)> = vec![
        (1.0, "1.0f"),
        (-1.0, "-1.0f"),
        (0.0, "0.0f"),
        (0.75, "0.75f"),
        (0.498_231_47, "0.49823147f"),
        (2000.0, "2000.0f"),
        (1e20, "1.0E20f"),
        (1e-30, "1.0E-30f"),
        (0.5, "0.5f"),
        (123.456, "123.456f"),
    ];

    for (value, expected) in cases {
        assert_eq!(snbt::write(&NbtTag::Float(value)), expected, "{value}");
    }
}

#[test]
fn double_formatting() {
    let cases: Vec<(f64, &str)> = vec![
        (1.0, "1.0d"),
        (0.015, "0.015d"),
        (2000.0, "2000.0d"),
        (0.493_128_713_218_231_5, "0.4931287132182315d"),
        (3.141_592_653_589_793, "3.141592653589793d"),
        (1e20, "1.0E20d"),
        (1e17, "1.0E17d"),
        (1e16, "10000000000000000.0d"),
        (1e-4, "0.0001d"),
        (1e-5, "1.0E-5d"),
    ];

    for (value, expected) in cases {
        assert_eq!(snbt::write(&NbtTag::Double(value)), expected, "{value}");
    }
}

#[test]
fn negative_zero_keeps_its_sign() {
    assert_eq!(snbt::write(&NbtTag::Double(-0.0)), "-0.0d");
    assert_eq!(snbt::write(&NbtTag::Float(-0.0)), "-0.0f");
}

#[test]
fn special_values() {
    assert_eq!(snbt::write(&NbtTag::Double(f64::NAN)), "NaNd");
    assert_eq!(snbt::write(&NbtTag::Double(f64::INFINITY)), "Infinityd");
    assert_eq!(snbt::write(&NbtTag::Double(f64::NEG_INFINITY)), "-Infinityd");
    assert_eq!(snbt::write(&NbtTag::Float(f32::NAN)), "NaNf");
}

#[test]
fn every_formatted_value_parses_back_to_the_same_bits() {
    let doubles: Vec<f64> = vec![
        0.0,
        -0.0,
        1.0,
        -1.0,
        0.1,
        1.0 / 3.0,
        1e300,
        1e-300,
        f64::MIN_POSITIVE,
        f64::MAX,
        4903.0,
    ];

    // 出力した文字列を読み戻して、ビットパターンが変わらないことを確かめる
    for value in doubles {
        let text = snbt::write(&NbtTag::Double(value));

        match snbt::parse(&text).unwrap() {
            NbtTag::Double(parsed) => assert_eq!(parsed.to_bits(), value.to_bits(), "{text}"),
            other => panic!("Double ではない: {other:?}"),
        }
    }

    let floats: Vec<f32> = vec![
        0.0,
        -0.0,
        1.0,
        -1.0,
        0.1,
        1.0 / 3.0,
        1e30,
        1e-30,
        f32::MIN_POSITIVE,
        f32::MAX,
        4903.0,
    ];

    for value in floats {
        let text = snbt::write(&NbtTag::Float(value));

        match snbt::parse(&text).unwrap() {
            NbtTag::Float(parsed) => assert_eq!(parsed.to_bits(), value.to_bits(), "{text}"),
            other => panic!("Float ではない: {other:?}"),
        }
    }
}

// ---------------------------------------------------------------------------
// タグの等値比較と深い複製
//
// 仕様: docs/spec/10-nbt-binary.md 7.3
// 規則は全言語で同じでなければならない
// 各言語の同名テストと突き合わせて読むこと
// ---------------------------------------------------------------------------

#[test]
fn same_type_same_value_is_equal() {
    assert_eq!(NbtTag::Int(42), NbtTag::Int(42));
    assert_eq!(
        NbtTag::String(NbtString::from("あ")),
        NbtTag::String(NbtString::from("あ"))
    );
    assert_eq!(NbtTag::ByteArray(vec![1, 2]), NbtTag::ByteArray(vec![1, 2]));

    assert_ne!(NbtTag::Int(42), NbtTag::Int(43));
    assert_ne!(NbtTag::ByteArray(vec![1]), NbtTag::ByteArray(vec![1, 2]));
}

#[test]
fn different_tag_type_is_not_equal() {
    // 値が同じでもタグの型が違えば別物
    assert_ne!(NbtTag::Int(1), NbtTag::Short(1));
}

#[test]
fn floats_compare_by_bit_pattern() {
    // NaN 同士は等しく、+0.0 と -0.0 は等しくない
    assert_eq!(NbtTag::Float(f32::NAN), NbtTag::Float(f32::NAN));
    assert_eq!(NbtTag::Double(f64::NAN), NbtTag::Double(f64::NAN));
    assert_ne!(NbtTag::Float(0.0), NbtTag::Float(-0.0));
    assert_ne!(NbtTag::Double(0.0), NbtTag::Double(-0.0));
}

#[test]
fn list_compares_element_type_and_order() {
    let mut left = NbtList::new();
    left.push(NbtTag::Int(1)).unwrap();
    left.push(NbtTag::Int(2)).unwrap();

    let mut same = NbtList::new();
    same.push(NbtTag::Int(1)).unwrap();
    same.push(NbtTag::Int(2)).unwrap();
    assert_eq!(left, same);

    let mut reversed = NbtList::new();
    reversed.push(NbtTag::Int(2)).unwrap();
    reversed.push(NbtTag::Int(1)).unwrap();
    assert_ne!(left, reversed);

    // 空でも要素型が違えば別物
    assert_ne!(
        NbtList::with_element_type(TagType::Int),
        NbtList::with_element_type(TagType::Byte)
    );
}

#[test]
fn compound_compares_insertion_order() {
    let mut left = NbtCompound::new();
    left.set("a", NbtTag::Int(1));
    left.set("b", NbtTag::Int(2));

    let mut same = NbtCompound::new();
    same.set("a", NbtTag::Int(1));
    same.set("b", NbtTag::Int(2));
    assert_eq!(left, same);

    // 中身は同じでも挿入順が違えば別物
    let mut reordered = NbtCompound::new();
    reordered.set("b", NbtTag::Int(2));
    reordered.set("a", NbtTag::Int(1));
    assert_ne!(left, reordered);
}

#[test]
fn clone_is_deep() {
    let mut original = NbtCompound::new();
    let mut inner = NbtList::new();
    inner.push(NbtTag::Int(1)).unwrap();
    original.set("l", NbtTag::List(inner));

    // 複製したほうのリストだけを差し替える
    let mut copied = original.clone();
    let mut inner = copied.get_list("l").unwrap().clone();
    inner.push(NbtTag::Int(2)).unwrap();
    copied.set("l", NbtTag::List(inner));

    assert_eq!(original.get_list("l").unwrap().len(), 1);
    assert_eq!(copied.get_list("l").unwrap().len(), 2);
    assert_ne!(original, copied);
}
