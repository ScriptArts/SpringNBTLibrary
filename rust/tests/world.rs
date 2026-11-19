//! World / Blockレイヤ
//!
//! 他言語版と同じ検証項目を持つ
//! 共通テストベクタによる言語間比較は`spec/run-conformance.sh`が担当し、ここではAPIの振る舞いを直接確かめる

use std::cell::RefCell;
use std::path::{Path, PathBuf};
use std::rc::Rc;

use spring_nbt_library::error::{Error, ErrorCode};
use spring_nbt_library::nbt::tag::{NbtCompound, NbtList, NbtString, NbtTag, TagType};
use spring_nbt_library::nbt::{
    read_file, write_bytes, write_file, Compression, NamedTag, NbtReadOptions, NbtWriteOptions,
};
use spring_nbt_library::anvil::{ChunkCompression, RegionFile, RegionFileMode};
use spring_nbt_library::world::{
    ceil_log2, BitStorage, BlockState, Chunk, ChunkReadOptions, ChunkWriteOptions, MinecraftWorld,
    PalettedContainer, VersionMismatchAction, WorldOpenOptions,
};
use spring_nbt_library::{MIN_SUPPORTED_DATA_VERSION, TARGET_DATA_VERSION};

/// 共通テストベクタ（world/*.nbt）のパス
fn vector_path(name: &str) -> PathBuf {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("リポジトリ直下が取れない")
        .join("spec")
        .join("testdata")
        .join("world")
        .join(format!("{name}.nbt"));

    assert!(path.is_file(), "テストベクタが見つからない: world/{name}.nbt");
    path
}

/// テストベクタをチャンクとして読む
fn load_chunk(name: &str) -> Chunk {
    let named = read_file(vector_path(name), &NbtReadOptions::default()).expect("読めない");
    Chunk::from_nbt(named.tag, &ChunkReadOptions::default()).expect("チャンクとして解釈できない")
}

/// プロパティの無いブロックのパレット要素を作る
/// 26.3からはブロックIDだけの文字列で入る
fn block_entry(name: &str) -> NbtTag {
    NbtTag::String(NbtString::new(name))
}

/// 異種リストの要素を包むCompoundを作る
fn wrapped(tag: NbtTag) -> NbtTag {
    let mut wrapper = NbtCompound::new();
    wrapper.set("", tag);
    NbtTag::Compound(wrapper)
}

/// エラーが期待したコードであることを確かめる
fn assert_code(expected: ErrorCode, error: Error) {
    assert_eq!(expected, error.code(), "エラーコードが違う: {error}");
}

/// 26.2までの形式（Name / Properties）のパレット要素を作る
fn name_properties(name: &str, properties: &[(&str, &str)]) -> NbtTag {
    let mut entry = NbtCompound::new();
    entry.set_string("Name", name);

    // プロパティがあるときだけPropertiesを足す
    if !properties.is_empty() {
        let mut properties_tag = NbtCompound::new();

        // 渡された順に入れる
        for (key, value) in properties {
            properties_tag.set_string(key, value);
        }

        entry.set("Properties", NbtTag::Compound(properties_tag));
    }

    NbtTag::Compound(entry)
}

/// 26.3からの形式（id / properties）のパレット要素を作る
fn id_properties(name: &str, properties: &[(&str, &str)]) -> NbtTag {
    let mut entry = NbtCompound::new();
    entry.set_string("id", name);
    let mut properties_tag = NbtCompound::new();

    // 渡された順に入れる
    for (key, value) in properties {
        properties_tag.set_string(key, value);
    }

    entry.set("properties", NbtTag::Compound(properties_tag));
    NbtTag::Compound(entry)
}

/// 扱える形式の下限より古く、1.13より前でもあるDataVersion
/// どの世代でも解釈しない
const PRE_FLATTENING_DATA_VERSION: i32 = 1400;

/// 1.13より前のようにLevelに本体を包み、ブロックを数値IDで持つチャンクを作る
fn pre_flattening_chunk() -> NbtCompound {
    let mut section = NbtCompound::new();
    section.set_byte("Y", 0);
    section.set_byte_array("Blocks", vec![1; 4096]);
    section.set_byte_array("Data", vec![0; 2048]);
    let mut sections = NbtList::with_element_type(TagType::Compound);
    sections.push(NbtTag::Compound(section)).unwrap();

    let mut level = NbtCompound::new();
    level.set_int("xPos", 3);
    level.set_int("zPos", -2);
    level.set("Sections", NbtTag::List(sections));

    let mut root = NbtCompound::new();
    root.set_int("DataVersion", PRE_FLATTENING_DATA_VERSION);
    root.set("Level", NbtTag::Compound(level));
    root
}

/// 1.17までのようにLevelに本体を包んだチャンクを作る
fn level_chunk(data_version: i32) -> NbtCompound {
    let mut level = NbtCompound::new();
    level.set_int("xPos", 0);
    level.set_int("zPos", 0);
    level.set_string("Status", "full");
    level.set("Sections", NbtTag::List(NbtList::with_element_type(TagType::Compound)));

    let mut root = NbtCompound::new();
    root.set_int("DataVersion", data_version);
    root.set("Level", NbtTag::Compound(level));
    root
}

/// チャンクのNBTを無圧縮のバイト列にする
fn chunk_bytes(tag: &NbtCompound) -> Vec<u8> {
    let options = NbtWriteOptions { compression: Compression::None, ..NbtWriteOptions::default() };
    write_bytes(&NamedTag::new("", tag.clone()), &options).unwrap()
}

/// 書き出したチャンクの最初のセクションのブロックのパレット
fn first_block_palette(written: &NbtCompound) -> NbtList {
    let section = match written.get_list("sections").unwrap().get(0) {
        Some(NbtTag::Compound(section)) => section.clone(),
        _ => panic!("最初のセクションが無い"),
    };

    section.get_compound("block_states").unwrap().get_list("palette").unwrap().clone()
}

// ---------------------------------------------------------------------------
// BlockState
// ---------------------------------------------------------------------------

#[test]
fn 名前空間を省略するとminecraftが補われる() {
    let state = BlockState::parse("stone").expect("解釈できない");
    assert_eq!("minecraft:stone", state.name());
    assert!(state.properties().is_empty());
    assert_eq!("minecraft:stone", state.to_string());
}

#[test]
fn プロパティは名前の昇順に並ぶ() {
    let state = BlockState::parse("minecraft:oak_stairs[waterlogged=false,facing=north,half=top]")
        .expect("解釈できない");
    assert_eq!(
        "minecraft:oak_stairs[facing=north,half=top,waterlogged=false]",
        state.to_string()
    );
}

#[test]
fn 並び順が違っても同じブロックとして等しい() {
    let first = BlockState::parse("minecraft:oak_stairs[facing=north,half=top]").unwrap();
    let second = BlockState::parse("minecraft:oak_stairs[half=top,facing=north]").unwrap();
    assert_eq!(first, second);
}

#[test]
fn 名前が同じでもプロパティが違えば等しくない() {
    let first = BlockState::parse("minecraft:oak_stairs[facing=north]").unwrap();
    let second = BlockState::parse("minecraft:oak_stairs[facing=south]").unwrap();
    assert_ne!(first, second);
}

#[test]
fn withで作り直しても元は変わらない() {
    let original = BlockState::parse("minecraft:oak_stairs[facing=north]").unwrap();
    let changed = original.with("facing", "south");
    assert_eq!(Some("north"), original.property("facing"));
    assert_eq!(Some("south"), changed.property("facing"));
}

#[test]
fn 存在しないプロパティはnone() {
    let state = BlockState::parse("minecraft:stone").unwrap();
    assert_eq!(None, state.property("facing"));
}

#[test]
fn nbtとの相互変換でプロパティが保たれる() {
    let state = BlockState::parse("minecraft:oak_stairs[facing=north,half=top]").unwrap();
    let nbt = state.to_nbt();

    match &nbt {
        NbtTag::Compound(compound) => {
            assert_eq!(vec!["id", "properties"], compound.keys().collect::<Vec<_>>());
            assert_eq!("minecraft:oak_stairs", compound.get_string("id").unwrap());
            assert_eq!(
                "north",
                compound.get_compound("properties").unwrap().get_string("facing").unwrap()
            );
        }
        other => panic!("compound でない: {other:?}"),
    }

    assert_eq!(state, BlockState::from_nbt(&nbt).unwrap());
}

#[test]
fn プロパティ無しのブロックは文字列になる() {
    let nbt = BlockState::parse("minecraft:air").unwrap().to_nbt();
    assert_eq!(block_entry("minecraft:air"), nbt);
}

#[test]
fn 文字列のパレット要素を読める() {
    let state = BlockState::from_nbt(&block_entry("minecraft:stone")).unwrap();
    assert_eq!("minecraft:stone", state.name());
    assert!(state.properties().is_empty());
}

#[test]
fn 包まれたパレット要素を読める() {
    let state = BlockState::from_nbt(&wrapped(block_entry("minecraft:stone"))).unwrap();
    assert_eq!("minecraft:stone", state.to_string());
}

#[test]
fn propertiesの無いcompoundも読める() {
    let mut entry = NbtCompound::new();
    entry.set("id", block_entry("minecraft:stone"));
    let state = BlockState::from_nbt(&NbtTag::Compound(entry)).unwrap();
    assert_eq!("minecraft:stone", state.to_string());
}

#[test]
fn パレット要素が26_2までの形式ならmalformed_data() {
    let mut entry = NbtCompound::new();
    entry.set("Name", block_entry("minecraft:stone"));

    match BlockState::from_nbt(&NbtTag::Compound(entry)) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::MalformedData, error),
    }
}

#[test]
fn 文字列でもcompoundでもない要素はunexpected_tag_type() {
    match BlockState::from_nbt(&NbtTag::Int(1)) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::UnexpectedTagType, error),
    }
}

/// `Name`と`Properties`を持つパレット要素を作る
fn name_properties_entry(name: &str, properties: &[(&str, NbtTag)]) -> NbtTag {
    let mut entry = NbtCompound::new();
    entry.set("Name", block_entry(name));

    if !properties.is_empty() {
        let mut tag = NbtCompound::new();

        for (key, value) in properties {
            tag.set(*key, value.clone());
        }

        entry.set("Properties", NbtTag::Compound(tag));
    }

    NbtTag::Compound(entry)
}

#[test]
fn data_version2844ではname_propertiesを読む() {
    let entry = name_properties_entry("minecraft:oak_stairs", &[("facing", block_entry("north"))]);
    let state = BlockState::from_nbt_for_data_version(&entry, 2844).unwrap();
    assert_eq!("minecraft:oak_stairs[facing=north]", state.to_string());
}

#[test]
fn data_version2844でidを持つ要素はmalformed_data() {
    let mut entry = NbtCompound::new();
    entry.set("id", block_entry("minecraft:stone"));

    match BlockState::from_nbt_for_data_version(&NbtTag::Compound(entry), 2844) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::MalformedData, error),
    }
}

#[test]
fn data_version2844で文字列の要素はunexpected_tag_type() {
    match BlockState::from_nbt_for_data_version(&block_entry("minecraft:stone"), 2844) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::UnexpectedTagType, error),
    }
}

#[test]
fn data_version2844でpropertiesの値が文字列でなければunexpected_tag_type() {
    let entry = name_properties_entry("minecraft:oak_stairs", &[("facing", NbtTag::Int(1))]);

    match BlockState::from_nbt_for_data_version(&entry, 2844) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::UnexpectedTagType, error),
    }
}

#[test]
fn data_version2844ではname_propertiesで書く() {
    let plain = BlockState::parse("minecraft:stone").unwrap().to_nbt_for_data_version(2844).unwrap();
    assert_eq!(name_properties_entry("minecraft:stone", &[]), plain);

    let stairs = BlockState::parse("minecraft:oak_stairs[half=top,facing=north]").unwrap();
    let nbt = stairs.to_nbt_for_data_version(2844).unwrap();

    match &nbt {
        NbtTag::Compound(compound) => {
            assert_eq!(vec!["Name", "Properties"], compound.keys().collect::<Vec<_>>());
            assert_eq!("minecraft:oak_stairs", compound.get_string("Name").unwrap());
            assert_eq!(
                vec!["facing", "half"],
                compound.get_compound("Properties").unwrap().keys().collect::<Vec<_>>()
            );
        }
        other => panic!("compound でない: {other:?}"),
    }

    assert_eq!(stairs, BlockState::from_nbt_for_data_version(&nbt, 2844).unwrap());
}

#[test]
fn data_version5006以降はfrom_nbtとto_nbtと同じ() {
    // 境界と、動作を確かめたバージョンの両方で確かめる
    for data_version in [5006, 5023] {
        let stairs = BlockState::parse("minecraft:oak_stairs[facing=north,half=top]").unwrap();
        assert_eq!(stairs.to_nbt(), stairs.to_nbt_for_data_version(data_version).unwrap());

        let plain = BlockState::parse("minecraft:stone").unwrap();
        assert_eq!(block_entry("minecraft:stone"), plain.to_nbt_for_data_version(data_version).unwrap());

        assert_eq!(
            plain,
            BlockState::from_nbt_for_data_version(&block_entry("minecraft:stone"), data_version).unwrap()
        );
        assert_eq!(
            stairs,
            BlockState::from_nbt_for_data_version(&stairs.to_nbt(), data_version).unwrap()
        );
        let wrapper = wrapped(block_entry("minecraft:stone"));
        assert_eq!(
            BlockState::from_nbt(&wrapper).unwrap(),
            BlockState::from_nbt_for_data_version(&wrapper, data_version).unwrap()
        );
    }
}

#[test]
fn data_version1519で境界の形式を扱える() {
    let state = BlockState::parse("minecraft:oak_stairs[facing=north]").unwrap();
    let nbt = state.to_nbt_for_data_version(1519).unwrap();
    assert_eq!(state, BlockState::from_nbt_for_data_version(&nbt, 1519).unwrap());
}

#[test]
fn data_versionが1519未満ならinvalid_argument() {
    match BlockState::from_nbt_for_data_version(&block_entry("minecraft:stone"), 1518) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }

    match BlockState::parse("minecraft:stone").unwrap().to_nbt_for_data_version(1518) {
        Ok(_) => panic!("書けてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }
}

#[test]
fn 壊れた文字列はinvalid_argument() {
    let broken = [
        "",
        "minecraft:oak_stairs[facing=north",
        "minecraft:oak_stairs[facing]",
        "minecraft:oak_stairs[facing=north,facing=south]",
        "minecraft:oak_stairs[]extra",
    ];

    // 崩し方ごとに同じエラーコードになることを確かめる
    for text in broken {
        match BlockState::parse(text) {
            Ok(_) => panic!("解釈が通ってしまった: {text}"),
            Err(error) => assert_code(ErrorCode::InvalidArgument, error),
        }
    }
}

// ---------------------------------------------------------------------------
// BitStorage
// ---------------------------------------------------------------------------

#[test]
fn 必要なlong数は跨ぎなしで求まる() {
    assert_eq!(256, BitStorage::long_count(4, 4096));
    assert_eq!(342, BitStorage::long_count(5, 4096));
    assert_eq!(1, BitStorage::long_count(1, 64));
    assert_eq!(7, BitStorage::long_count(6, 64));
}

#[test]
fn 書いた値をそのまま読み出せる() {
    let mut storage = BitStorage::create(5, 4096).unwrap();

    // 全エントリに位置由来の値を書いて、取りこぼしが無いか確かめる
    for index in 0..4096 {
        storage.set(index, (index % 32) as u32).unwrap();
    }

    for index in 0..4096 {
        assert_eq!((index % 32) as u32, storage.get(index).unwrap());
    }
}

#[test]
fn long境界を跨がずに詰める() {
    let mut storage = BitStorage::create(5, 4096).unwrap();

    // bits=5なら1つのlongに12個
    // 添字12は次のlongの最下位から始まる
    storage.set(11, 31).unwrap();
    storage.set(12, 1).unwrap();
    let longs = storage.as_longs();

    assert_eq!(31i64 << 55, longs[0]);
    assert_eq!(1i64, longs[1]);
}

#[test]
fn ビット幅を広げても値が保たれる() {
    let mut storage = BitStorage::create(4, 4096).unwrap();

    for index in 0..4096 {
        storage.set(index, (index % 16) as u32).unwrap();
    }

    let widened = storage.resize(5).unwrap();
    assert_eq!(5, widened.bits_per_entry());
    assert_eq!(342, widened.as_longs().len());

    for index in 0..4096 {
        assert_eq!((index % 16) as u32, widened.get(index).unwrap());
    }
}

#[test]
fn ビット幅に対して長さが合わない配列はmalformed_data() {
    match BitStorage::from_longs(vec![0; 100], 4, 4096, false) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::MalformedData, error),
    }
}

#[test]
fn 寛容モードなら長さからビット幅を逆算する() {
    // 4096エントリを342 longで表せるのはbits=5のときだけ
    let storage = BitStorage::from_longs(vec![0; 342], 4, 4096, true).unwrap();
    assert_eq!(5, storage.bits_per_entry());
}

#[test]
fn ビット幅に収まらない値はinvalid_argument() {
    let mut storage = BitStorage::create(4, 64).unwrap();

    match storage.set(0, 16) {
        Ok(()) => panic!("書けてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }
}

#[test]
fn bit_storageの範囲外の添字はinvalid_argument() {
    let storage = BitStorage::create(4, 64).unwrap();

    match storage.get(64) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }
}

// ---------------------------------------------------------------------------
// PalettedContainer
// ---------------------------------------------------------------------------

#[test]
fn 必要ビット数はceil_log2() {
    assert_eq!(0, ceil_log2(1));
    assert_eq!(1, ceil_log2(2));
    assert_eq!(2, ceil_log2(4));
    assert_eq!(3, ceil_log2(5));
    assert_eq!(5, ceil_log2(17));
}

#[test]
fn 単一値のコンテナはdataを持たない() {
    let container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    assert_eq!(0, container.bits_per_entry());

    let nbt = container.to_nbt().unwrap();
    assert!(nbt.opt_long_array("data").unwrap().is_none());
    assert_eq!(1, nbt.get_list("palette").unwrap().len());
}

#[test]
fn 値を足すとパレットとビット幅が広がる() {
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);

    // 17種のブロックを足してパレットを18要素にし、bits=4から5への拡張を起こす
    for index in 0..17 {
        container
            .set(index, block_entry(&format!("minecraft:block_{index}")))
            .unwrap();
    }

    assert_eq!(18, container.palette().len());
    assert_eq!(5, container.bits_per_entry());
    assert_eq!(342, container.to_nbt().unwrap().get_long_array("data").unwrap().len());
}

#[test]
fn 書き出しはdataが先でpaletteが後() {
    // 実データがこの順なので、無変更で書き戻したときにバイト単位で一致する
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    container.set(0, block_entry("minecraft:stone")).unwrap();

    let nbt = container.to_nbt().unwrap();
    let keys: Vec<&str> = nbt.keys().collect();
    assert_eq!(vec!["data", "palette"], keys);
}

#[test]
fn compactで未使用のパレット要素が消える() {
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    container.set(0, block_entry("minecraft:stone")).unwrap();
    container.set(0, block_entry("minecraft:dirt")).unwrap();
    assert_eq!(3, container.palette().len());

    container.compact().unwrap();

    // 残るのは実際に使われているairとdirtの2つ
    assert_eq!(2, container.palette().len());

    assert_eq!(&block_entry("minecraft:dirt"), container.get(0).unwrap());
}

#[test]
fn fillで単一値に戻る() {
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    container.set(0, block_entry("minecraft:stone")).unwrap();
    container.fill(block_entry("minecraft:water"));

    assert_eq!(1, container.palette().len());
    assert_eq!(0, container.bits_per_entry());

    assert_eq!(&block_entry("minecraft:water"), container.get(4095).unwrap());
}

#[test]
fn 文字列だけのパレットは文字列のリストで書く() {
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    container.set(0, block_entry("minecraft:stone")).unwrap();

    let nbt = container.to_nbt().unwrap();
    let palette = nbt.get_list("palette").unwrap();
    assert_eq!(TagType::String, palette.element_type());
    assert_eq!(Some(&block_entry("minecraft:stone")), palette.get(1));
}

#[test]
fn 型が混ざったパレットは文字列を包んでcompoundのリストで書く() {
    let stairs = BlockState::parse("minecraft:oak_stairs[facing=north]").unwrap().to_nbt();
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    container.set(0, stairs.clone()).unwrap();

    let nbt = container.to_nbt().unwrap();
    let palette = nbt.get_list("palette").unwrap();
    assert_eq!(TagType::Compound, palette.element_type());
    assert_eq!(Some(&wrapped(block_entry("minecraft:air"))), palette.get(0));
    assert_eq!(Some(&stairs), palette.get(1));
}

#[test]
fn 包まれたパレットは包みを外して持ち元どおりに書き戻す() {
    let stairs = BlockState::parse("minecraft:oak_stairs[facing=north]").unwrap().to_nbt();
    let mut palette = NbtList::with_element_type(TagType::Compound);
    palette.push(wrapped(block_entry("minecraft:air"))).unwrap();
    palette.push(stairs.clone()).unwrap();

    // パレット2要素ならbits=4で256 long
    let mut nbt = NbtCompound::new();
    nbt.set("data", NbtTag::LongArray(vec![0; 256]));
    nbt.set("palette", NbtTag::List(palette));

    let container = PalettedContainer::from_nbt(&nbt, 4096, 4, false).unwrap();

    // 包みは外れ、要素は文字列とCompoundとして並ぶ
    assert_eq!(block_entry("minecraft:air"), container.palette()[0]);
    assert_eq!(stairs, container.palette()[1]);

    // 書き戻すと、また包まれて元と同じになる
    assert_eq!(nbt, container.to_nbt().unwrap());
}

#[test]
fn compactでcompoundが消えると文字列のリストに戻る() {
    let stairs = BlockState::parse("minecraft:oak_stairs[facing=north]").unwrap().to_nbt();
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    container.set(0, stairs).unwrap();
    container.set(0, block_entry("minecraft:stone")).unwrap();

    container.compact().unwrap();

    let nbt = container.to_nbt().unwrap();
    let palette = nbt.get_list("palette").unwrap();
    assert_eq!(TagType::String, palette.element_type());
    assert_eq!(2, palette.len());
}

#[test]
fn paletted_containerの範囲外の添字はinvalid_argument() {
    let container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);

    match container.get(4096) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }
}

// ---------------------------------------------------------------------------
// Chunk
// ---------------------------------------------------------------------------

#[test]
fn パレット1要素のチャンクを読める() {
    let chunk = load_chunk("palette_1");

    assert_eq!(TARGET_DATA_VERSION, chunk.data_version().unwrap());
    assert_eq!(0, chunk.x().unwrap());
    assert_eq!(0, chunk.z().unwrap());
    assert_eq!(-4, chunk.min_section_y().unwrap());
    assert!(chunk.is_fully_generated());
    assert_eq!(vec![-4], chunk.section_ys());
    assert_eq!(
        "minecraft:air",
        chunk.get_block(0, -64, 0).unwrap().unwrap().name()
    );
    assert_eq!(
        Some("minecraft:plains".to_string()),
        chunk.get_biome(0, -64, 0).unwrap()
    );
}

#[test]
fn ビット幅5のチャンクを端から端まで読める() {
    let chunk = load_chunk("palette_17");
    let head = ["minecraft:air", "minecraft:stone"];

    // ベクタの添字は (位置 * 11) % 17
    // パレットの先頭2つだけ名前が違う
    for position in 0..4096i32 {
        let palette_index = ((position * 11) % 17) as usize;
        let block = chunk
            .get_block(position & 15, -64 + (position >> 8), (position >> 4) & 15)
            .unwrap()
            .expect("ブロックが無い");

        if palette_index < 2 {
            assert_eq!(head[palette_index], block.to_string());
        } else {
            assert_eq!(
                format!("minecraft:stone[variant=v{}]", palette_index - 2),
                block.to_string()
            );
        }
    }
}

#[test]
fn セクションの無い高さはnone() {
    let chunk = load_chunk("palette_1");
    assert!(chunk.get_block(0, 100, 0).unwrap().is_none());
    assert!(chunk.section(0).is_none());
}

#[test]
fn 生成途中のチャンクはfullではない() {
    let chunk = load_chunk("proto_chunk");
    assert_eq!("minecraft:structure_starts", chunk.status().unwrap());
    assert!(!chunk.is_fully_generated());
}

#[test]
fn ブロックを置くとその場所だけ変わる() {
    let mut chunk = load_chunk("palette_1");
    let state = BlockState::parse("minecraft:oak_stairs[facing=north,half=top]").unwrap();
    chunk.set_block(3, -60, 7, &state).unwrap();

    assert_eq!(
        "minecraft:oak_stairs[facing=north,half=top]",
        chunk.get_block(3, -60, 7).unwrap().unwrap().to_string()
    );
    assert_eq!(
        "minecraft:air",
        chunk.get_block(3, -60, 6).unwrap().unwrap().name()
    );
    assert_eq!(
        "minecraft:air",
        chunk.get_block(4, -60, 7).unwrap().unwrap().name()
    );
}

#[test]
fn バイオームは4ブロック単位で効く() {
    let mut chunk = load_chunk("palette_1");
    chunk.set_biome(0, -64, 0, "minecraft:desert").unwrap();

    // 同じ4×4×4の枠内はまとめて変わる
    assert_eq!(
        Some("minecraft:desert".to_string()),
        chunk.get_biome(3, -61, 3).unwrap()
    );
    assert_eq!(
        Some("minecraft:plains".to_string()),
        chunk.get_biome(4, -64, 0).unwrap()
    );
}

#[test]
fn チャンクのcompactで未使用のパレット要素が消える() {
    let mut chunk = load_chunk("palette_unused");
    let before = chunk.section(-4).unwrap().to_nbt().unwrap();
    assert_eq!(
        4,
        before.get_compound("block_states").unwrap().get_list("palette").unwrap().len()
    );

    chunk.compact().unwrap();

    let after = chunk.section(-4).unwrap().to_nbt().unwrap();
    assert_eq!(
        2,
        after.get_compound("block_states").unwrap().get_list("palette").unwrap().len()
    );
}

#[test]
fn 無変更で書き戻すと元と同じnbtになる() {
    let named = read_file(vector_path("multi_section"), &NbtReadOptions::default()).unwrap();
    let options = NbtWriteOptions {
        compression: Compression::None,
        ..NbtWriteOptions::default()
    };
    let before = write_bytes(&named, &options).unwrap();

    let name = named.name.clone();
    let chunk = Chunk::from_nbt(named.tag, &ChunkReadOptions::default()).unwrap();
    let rebuilt = NamedTag::new(name, chunk.to_nbt(&ChunkWriteOptions::default()).unwrap());
    let after = write_bytes(&rebuilt, &options).unwrap();

    assert_eq!(before, after);
}

#[test]
fn ブロックを置き換えると同じ座標の付随データが消える() {
    let mut chunk = load_chunk("block_entities");
    assert_eq!(3, chunk.raw().get_list("block_entities").unwrap().len());
    assert_eq!(2, chunk.raw().get_list("block_ticks").unwrap().len());
    assert_eq!(1, chunk.raw().get_list("fluid_ticks").unwrap().len());

    // (0,-64,0)にはchestとblock_tick、(1,-64,1)にはfurnaceとfluid_tickがある
    let stone = BlockState::parse("minecraft:stone").unwrap();
    chunk.set_block(0, -64, 0, &stone).unwrap();
    chunk.set_block(1, -64, 1, &stone).unwrap();

    let entities = chunk.raw().get_list("block_entities").unwrap();

    // 触っていない(15,-50,15)のbarrelだけが残る
    assert_eq!(1, entities.len());

    match entities.get(0).unwrap() {
        NbtTag::Compound(entry) => {
            assert_eq!("minecraft:barrel", entry.get_string("id").unwrap());
        }
        other => panic!("compound でない: {other:?}"),
    }

    let ticks = chunk.raw().get_list("block_ticks").unwrap();
    assert_eq!(1, ticks.len());

    match ticks.get(0).unwrap() {
        NbtTag::Compound(entry) => assert_eq!(15, entry.get_int("x").unwrap()),
        other => panic!("compound でない: {other:?}"),
    }

    assert_eq!(0, chunk.raw().get_list("fluid_ticks").unwrap().len());
}

#[test]
fn 同じブロックを置き直しても付随データは消えない() {
    let mut chunk = load_chunk("block_entities");
    let current = chunk.get_block(0, -64, 0).unwrap().expect("ブロックが無い");

    // 変化が無いなら付随データを触る理由がない
    chunk.set_block(0, -64, 0, &current).unwrap();

    assert_eq!(3, chunk.raw().get_list("block_entities").unwrap().len());
    assert_eq!(2, chunk.raw().get_list("block_ticks").unwrap().len());
}

#[test]
fn 別のチャンクの同じ相対座標は消さない() {
    // 付随データは絶対座標で持つので、チャンク座標を間違えると無関係な要素を消してしまう
    let named = read_file(vector_path("block_entities"), &NbtReadOptions::default()).unwrap();
    let mut root = named.tag;
    root.set("xPos", NbtTag::Int(1));
    root.set("zPos", NbtTag::Int(1));

    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();
    let stone = BlockState::parse("minecraft:stone").unwrap();
    chunk.set_block(0, -64, 0, &stone).unwrap();

    // このチャンクの(0,-64,0)は絶対座標(16,-64,16)
    // どれとも一致しない
    assert_eq!(3, chunk.raw().get_list("block_entities").unwrap().len());
}

#[test]
fn 高さマップと光源を無効化できる() {
    let mut chunk = load_chunk("palette_1");
    chunk.clear_heightmaps().unwrap();
    chunk.invalidate_lighting().unwrap();

    let raw = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert!(raw.opt_compound("Heightmaps").unwrap().is_none());
    assert!(!raw.get_bool("isLightOn").unwrap());
}

#[test]
fn 添字が範囲外のチャンクはmalformed_data() {
    let named = read_file(
        vector_path("palette_index_out_of_range"),
        &NbtReadOptions::default(),
    )
    .unwrap();

    match Chunk::from_nbt(named.tag, &ChunkReadOptions::default()) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::MalformedData, error),
    }
}

#[test]
fn data長が合わないチャンクはmalformed_data() {
    let named = read_file(
        vector_path("bitstorage_wrong_length"),
        &NbtReadOptions::default(),
    )
    .unwrap();

    match Chunk::from_nbt(named.tag, &ChunkReadOptions::default()) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::MalformedData, error),
    }
}

#[test]
fn チャンク内の相対座標が範囲外ならinvalid_argument() {
    let chunk = load_chunk("palette_1");

    match chunk.get_block(16, -64, 0) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }
}

// ---------------------------------------------------------------------------
// DataVersionの扱い
// ---------------------------------------------------------------------------

/// DataVersionだけを、扱える形式の下限より古い値に差し替えたチャンクを作る
fn foreign_chunk() -> NbtCompound {
    let named = read_file(vector_path("palette_1"), &NbtReadOptions::default()).unwrap();
    let mut root = named.tag;
    root.set("DataVersion", NbtTag::Int(PRE_FLATTENING_DATA_VERSION));
    root
}

#[test]
fn 既定では警告として通す() {
    let warnings: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
    let sink = Rc::clone(&warnings);
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Warn,
        on_warning: Some(Box::new(move |message: &str| {
            sink.borrow_mut().push(message.to_string());
        })),
        ..ChunkReadOptions::default()
    };

    let chunk = Chunk::from_nbt(foreign_chunk(), &options).unwrap();
    assert_eq!(PRE_FLATTENING_DATA_VERSION, chunk.data_version().unwrap());
    assert_eq!(1, warnings.borrow().len());
}

#[test]
fn data_versionが26_2のチャンクは警告を出さずに読める() {
    let warnings: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
    let sink = Rc::clone(&warnings);
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Warn,
        on_warning: Some(Box::new(move |message: &str| {
            sink.borrow_mut().push(message.to_string());
        })),
        ..ChunkReadOptions::default()
    };

    // 26.2の形式も扱う形式に含まれる
    let named = read_file(vector_path("palette_old_format"), &NbtReadOptions::default()).unwrap();
    Chunk::from_nbt(named.tag, &options).unwrap();
    assert!(warnings.borrow().is_empty());
}

#[test]
fn 扱える形式の下限は1_18() {
    assert_eq!(2844, MIN_SUPPORTED_DATA_VERSION);
}

#[test]
fn errorを指定すると読み込みで弾く() {
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Error,
        ..ChunkReadOptions::default()
    };

    match Chunk::from_nbt(foreign_chunk(), &options) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::UnsupportedDataVersion, error),
    }
}

#[test]
fn ignoreなら何も起きない() {
    let warnings: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
    let sink = Rc::clone(&warnings);
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        on_warning: Some(Box::new(move |message: &str| {
            sink.borrow_mut().push(message.to_string());
        })),
        ..ChunkReadOptions::default()
    };

    Chunk::from_nbt(foreign_chunk(), &options).unwrap();
    assert!(warnings.borrow().is_empty());
}

#[test]
fn 別バージョン由来のチャンクは既定で書き戻せない() {
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(foreign_chunk(), &options).unwrap();

    match chunk.to_nbt(&ChunkWriteOptions::default()) {
        Ok(_) => panic!("書けてしまった"),
        Err(error) => assert_code(ErrorCode::UnsupportedDataVersion, error),
    }
}

#[test]
fn 許可すれば古いチャンクも元のバージョンのまま書き戻せる() {
    let read = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(foreign_chunk(), &read).unwrap();
    let write = ChunkWriteOptions {
        allow_foreign_data_version: true,
    };

    // DataVersionは読んだ値のまま残す
    let written = chunk.to_nbt(&write).unwrap();
    assert_eq!(PRE_FLATTENING_DATA_VERSION, written.get_int("DataVersion").unwrap());
}

/// 対象より新しいDataVersionを持つチャンクを作る
fn newer_chunk() -> NbtCompound {
    let named = read_file(vector_path("palette_1"), &NbtReadOptions::default()).unwrap();
    let mut root = named.tag;
    root.set_int("DataVersion", 5100);
    root
}

#[test]
fn 新しいバージョンのチャンクは警告を出さない() {
    let warnings: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
    let sink = Rc::clone(&warnings);
    let read = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Warn,
        on_warning: Some(Box::new(move |message: &str| {
            sink.borrow_mut().push(message.to_string());
        })),
        ..ChunkReadOptions::default()
    };

    // 形式が同じであれば、新しいバージョンでも警告を出さずに読める
    let chunk = Chunk::from_nbt(newer_chunk(), &read).unwrap();
    assert_eq!(chunk.data_version().unwrap(), 5100);
    assert!(warnings.borrow().is_empty());
}

#[test]
fn 新しいバージョンのチャンクはエラー設定でも通る() {
    let read = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Error,
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(newer_chunk(), &read).unwrap();
    assert_eq!(chunk.data_version().unwrap(), 5100);
}

#[test]
fn 新しいバージョンのチャンクはそのまま書き戻せる() {
    let chunk = Chunk::from_nbt(newer_chunk(), &ChunkReadOptions::default()).unwrap();

    // 許可を出さなくても書き戻せて、DataVersionも変わらない
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert_eq!(5100, written.get_int("DataVersion").unwrap());
}

#[test]
fn 対象バージョンのチャンクはそのまま書き戻せる() {
    let chunk = load_chunk("palette_1");
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert_eq!(TARGET_DATA_VERSION, written.get_int("DataVersion").unwrap());
}

// ---------------------------------------------------------------------------
// チャンクの形式の世代
// ---------------------------------------------------------------------------

#[test]
fn data_version4903のチャンクを読み無変更で書き戻すと元と同じになる() {
    let tag = read_file(vector_path("v4903_edit"), &NbtReadOptions::default()).unwrap().tag;
    let before = chunk_bytes(&tag);
    let chunk = Chunk::from_nbt(tag, &ChunkReadOptions::default()).unwrap();

    // ベクタの添字は (位置 * 7) % 5
    let block = |x: i32| chunk.get_block(x, -64, 0).unwrap().unwrap().to_string();
    assert_eq!(4903, chunk.data_version().unwrap());
    assert_eq!("minecraft:air", block(0));
    assert_eq!("minecraft:dirt", block(1));
    assert_eq!("minecraft:oak_stairs[facing=west,half=top]", block(2));
    assert_eq!("minecraft:stone", block(3));
    assert_eq!("minecraft:oak_stairs[facing=east,half=bottom]", block(4));
    assert_eq!(Some("minecraft:plains".to_string()), chunk.get_biome(0, -64, 0).unwrap());

    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert_eq!(before, chunk_bytes(&written));
}

#[test]
fn data_version4903のチャンクに置いたブロックはname_propertiesで入る() {
    let mut chunk = load_chunk("v4903_edit");
    chunk.set_block(5, -64, 5, "minecraft:oak_stairs[facing=north]").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();

    // パレットの末尾に26.2の形式で足される
    let palette = first_block_palette(&written);
    assert_eq!(
        Some(&name_properties("minecraft:oak_stairs", &[("facing", "north")])),
        palette.get(palette.len() - 1)
    );

    // DataVersionは読んだ値のまま
    assert_eq!(4903, written.get_int("DataVersion").unwrap());

    // 読み直しても同じ状態が返る
    let reread = Chunk::from_nbt(written, &ChunkReadOptions::default()).unwrap();
    assert_eq!(
        "minecraft:oak_stairs[facing=north]",
        reread.get_block(5, -64, 5).unwrap().unwrap().to_string()
    );
}

#[test]
fn 形式の違うチャンクはそれぞれ読んだ形式で書き出す() {
    let mut older = load_chunk("v4903_edit");
    let mut newer = load_chunk("palette_5");

    // 2つのチャンクに同じ手順で同じブロックを置く
    for chunk in [&mut older, &mut newer] {
        chunk.set_block(5, -64, 5, "minecraft:oak_stairs[facing=north]").unwrap();
        chunk.set_block(6, -64, 6, "minecraft:edited_plain").unwrap();
    }

    let older_written = older.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let older_palette = first_block_palette(&older_written);
    assert_eq!(
        Some(&name_properties("minecraft:oak_stairs", &[("facing", "north")])),
        older_palette.get(older_palette.len() - 2)
    );
    assert_eq!(
        Some(&name_properties("minecraft:edited_plain", &[])),
        older_palette.get(older_palette.len() - 1)
    );
    assert_eq!(4903, older_written.get_int("DataVersion").unwrap());

    let newer_written = newer.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let newer_palette = first_block_palette(&newer_written);

    // 型の混ざったパレットはCompoundのリストになり、文字列の要素だけが包まれる
    assert_eq!(
        Some(&id_properties("minecraft:oak_stairs", &[("facing", "north")])),
        newer_palette.get(newer_palette.len() - 2)
    );
    assert_eq!(
        Some(&wrapped(block_entry("minecraft:edited_plain"))),
        newer_palette.get(newer_palette.len() - 1)
    );
    assert_eq!(TARGET_DATA_VERSION, newer_written.get_int("DataVersion").unwrap());
}

#[test]
fn 指定した世代とlevelの有無が食い違えばmalformed_data() {
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        format_data_version: Some(5023),
        ..ChunkReadOptions::default()
    };

    // Levelを持つチャンクを、Levelの無い世代で読ませる
    match Chunk::from_nbt(level_chunk(2586), &options) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::MalformedData, error),
    }
}

#[test]
fn 世代を指定しても下限より古いチャンクは書き戻せない() {
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        format_data_version: Some(5023),
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(pre_flattening_chunk(), &options).unwrap();

    match chunk.to_nbt(&ChunkWriteOptions::default()) {
        Ok(_) => panic!("書けてしまった"),
        Err(error) => assert_code(ErrorCode::UnsupportedDataVersion, error),
    }
}

#[test]
fn 世代に1519未満を指定するとinvalid_argument() {
    let named = read_file(vector_path("palette_1"), &NbtReadOptions::default()).unwrap();
    let options = ChunkReadOptions {
        format_data_version: Some(1518),
        ..ChunkReadOptions::default()
    };

    match Chunk::from_nbt(named.tag, &options) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }
}

#[test]
fn data_versionが1519未満のチャンクは元のnbtだけを持つ() {
    let root = pre_flattening_chunk();
    let before = chunk_bytes(&root);
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        ..ChunkReadOptions::default()
    };
    let mut chunk = Chunk::from_nbt(root, &options).unwrap();

    // 座標はLevelの中から読み、セクションは解釈しない
    assert_eq!(3, chunk.x().unwrap());
    assert_eq!(-2, chunk.z().unwrap());
    assert!(chunk.section_ys().is_empty());

    // ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
    let results = vec![
        chunk.get_block(0, 0, 0).map(|_| ()),
        chunk.get_biome(0, 0, 0).map(|_| ()),
        chunk.set_block(0, 0, 0, "minecraft:stone"),
        chunk.set_biome(0, 0, 0, "minecraft:plains"),
        chunk.clear_heightmaps(),
        chunk.invalidate_lighting(),
    ];

    // 操作ごとにUnsupportedDataVersionになることを確かめる
    for result in results {
        match result {
            Ok(()) => panic!("操作できてしまった"),
            Err(error) => assert_code(ErrorCode::UnsupportedDataVersion, error),
        }
    }

    // 許可すれば、読んだNBTがそのまま返る
    let write = ChunkWriteOptions {
        allow_foreign_data_version: true,
    };
    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&write).unwrap()));
}

#[test]
fn 世代を選んだdata_versionを返す() {
    let tag = read_file(vector_path("v4903_edit"), &NbtReadOptions::default()).unwrap().tag;
    let chunk = Chunk::from_nbt(tag.clone(), &ChunkReadOptions::default()).unwrap();
    assert_eq!(4903, chunk.format_data_version());

    // 指定すれば、チャンク自身のDataVersionではなくその値になる
    let options = ChunkReadOptions {
        format_data_version: Some(5023),
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(tag, &options).unwrap();
    assert_eq!(5023, chunk.format_data_version());
    assert_eq!(4903, chunk.data_version().unwrap());
}

// ---------------------------------------------------------------------------
// MinecraftWorld
// ---------------------------------------------------------------------------

#[test]
fn 存在しないディレクトリはio() {
    let missing = std::env::temp_dir().join("springnbt-missing-world-rs");

    match MinecraftWorld::open(&missing, WorldOpenOptions::default()) {
        Ok(_) => panic!("開けてしまった"),
        Err(error) => assert_code(ErrorCode::Io, error),
    }
}

#[test]
fn level_datが無いディレクトリはio() {
    let work = std::env::temp_dir().join(format!("springnbt-world-{}", std::process::id()));
    std::fs::create_dir_all(&work).unwrap();

    let result = MinecraftWorld::open(&work, WorldOpenOptions::default());

    // 判定の前に一時ディレクトリを片付ける
    std::fs::remove_dir_all(&work).unwrap();

    match result {
        Ok(_) => panic!("開けてしまった"),
        Err(error) => assert_code(ErrorCode::Io, error),
    }
}

#[test]
fn 次元経由で読んだチャンクの警告も通知先へ届く() {
    let work = std::env::temp_dir().join(format!("springnbt-warn-{}", std::process::id()));
    let region = work.join("dimensions").join("minecraft").join("overworld").join("region");
    std::fs::create_dir_all(&region).unwrap();

    // DataVersionが扱える形式より古いチャンクを1つだけ持つワールドを作る
    write_level(&work, |data| data.set_int("DataVersion", 5023));

    {
        let mut file = RegionFile::open(region.join("r.0.0.mca"), RegionFileMode::ReadWrite).unwrap();
        file.write_chunk(0, 0, &foreign_chunk(), ChunkCompression::Zlib).unwrap();
        file.close().unwrap();
    }

    let warnings: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
    let sink = Rc::clone(&warnings);
    let options = WorldOpenOptions {
        chunk_read: ChunkReadOptions {
            on_warning: Some(Box::new(move |message: &str| {
                sink.borrow_mut().push(message.to_string());
            })),
            ..ChunkReadOptions::default()
        },
        ..WorldOpenOptions::default()
    };

    let found = {
        let mut world = MinecraftWorld::open(&work, options).unwrap();
        let overworld = world.dimension("minecraft:overworld").unwrap().unwrap();
        let found = overworld.chunk(0, 0).unwrap().is_some();
        world.close().unwrap();
        found
    };

    // 判定の前に一時ディレクトリを片付ける
    std::fs::remove_dir_all(&work).unwrap();

    // ワールドを開くときに渡した通知先が、次元経由の読み込みでも呼ばれる
    assert!(found);
    assert_eq!(1, warnings.borrow().len());
}


// ---------------------------------------------------------------------------
// ワールドの構成の世代（L1とL2）
// ---------------------------------------------------------------------------

/// テストごとに別の一時フォルダを作る
fn temp_world(name: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!("springnbt-layout-{name}-{}", std::process::id()));

    // 前回の残りがあれば消してから作る
    let _ = std::fs::remove_dir_all(&path);
    std::fs::create_dir_all(&path).unwrap();
    path
}

/// `Data`に`fill`で項目を足したlevel.datを書く
fn write_level(directory: &Path, fill: impl FnOnce(&mut NbtCompound)) {
    let mut data = NbtCompound::new();
    fill(&mut data);

    let mut root = NbtCompound::new();
    root.set("Data", NbtTag::Compound(data));
    write_file(
        directory.join("level.dat"),
        &NamedTag::new("", root),
        &NbtWriteOptions::default(),
    )
    .unwrap();
}

/// `fill`で項目を足した.datを、フォルダごと作って書く
fn write_dat(path: &Path, fill: impl FnOnce(&mut NbtCompound)) {
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    let mut root = NbtCompound::new();
    fill(&mut root);
    write_file(path, &NamedTag::new("", root), &NbtWriteOptions::default()).unwrap();
}

/// L1の合成ワールドを作る
fn make_l1_world(name: &str) -> PathBuf {
    let work = temp_world(name);
    write_level(&work, |data| data.set_int("DataVersion", 3953));

    // 標準の3次元と、データパックの次元のフォルダを作る
    for folder in ["region", "DIM-1/region", "DIM1/region", "dimensions/mymap/arena/region"] {
        std::fs::create_dir_all(work.join(folder)).unwrap();
    }

    work
}

#[test]
fn world_l1_dimensions() {
    let work = make_l1_world("dimensions");
    let mut world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();

    assert_eq!(
        vec!["minecraft:overworld", "minecraft:the_nether", "minecraft:the_end", "mymap:arena"],
        world.dimension_ids().unwrap()
    );
    assert_eq!(work, world.dimension("minecraft:overworld").unwrap().unwrap().directory());
    assert_eq!(
        work.join("DIM-1"),
        world.dimension("minecraft:the_nether").unwrap().unwrap().directory()
    );
    assert_eq!(
        work.join("DIM1"),
        world.dimension("minecraft:the_end").unwrap().unwrap().directory()
    );
    assert_eq!(
        work.join("dimensions").join("mymap").join("arena"),
        world.dimension("mymap:arena").unwrap().unwrap().directory()
    );

    // 次元が無ければNone
    assert!(world.dimension("mymap:missing").unwrap().is_none());

    world.close().unwrap();
    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn l1で存在しない標準の次元は並ばない() {
    let work = temp_world("missing-standard");
    write_level(&work, |data| data.set_int("DataVersion", 3953));
    std::fs::create_dir_all(work.join("region")).unwrap();

    let mut world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert_eq!(vec!["minecraft:overworld"], world.dimension_ids().unwrap());
    assert!(world.dimension("minecraft:the_nether").unwrap().is_none());

    world.close().unwrap();
    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn l1ではdimensionsの下の標準の次元は並ばない() {
    let work = temp_world("standard-under-dimensions");
    write_level(&work, |data| data.set_int("DataVersion", 3953));
    std::fs::create_dir_all(work.join("dimensions/minecraft/the_nether/region")).unwrap();

    let mut world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert!(!world.dimension_ids().unwrap().contains(&"minecraft:the_nether".to_string()));
    assert!(world.dimension("minecraft:the_nether").unwrap().is_none());

    world.close().unwrap();
    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn world_l1_players() {
    let work = make_l1_world("players");
    write_dat(&work.join("playerdata").join("b-uuid.dat"), |root| root.set_int("Health", 20));
    write_dat(&work.join("playerdata").join("a-uuid.dat"), |root| root.set_int("Health", 7));

    let world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert_eq!(vec!["a-uuid", "b-uuid"], world.player_ids().unwrap());
    assert_eq!(7, world.player("a-uuid").unwrap().unwrap().get_int("Health").unwrap());
    assert!(world.player("missing").unwrap().is_none());

    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn world_l1_data_file() {
    let work = make_l1_world("data-file");
    write_dat(&work.join("data").join("scoreboard.dat"), |root| root.set_int("Value", 1));
    write_dat(&work.join("DIM-1").join("data").join("raids_nether.dat"), |root| {
        root.set_int("Value", 2)
    });

    let mut world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert_eq!(1, world.data_file("scoreboard").unwrap().unwrap().get_int("Value").unwrap());
    assert!(world.data_file("missing").unwrap().is_none());

    let nether = world.dimension("minecraft:the_nether").unwrap().unwrap();
    assert_eq!(2, nether.data_file("raids_nether").unwrap().unwrap().get_int("Value").unwrap());

    // オーバーワールドの次元は、ワールドと同じdata/を読む
    let overworld = world.dimension("minecraft:overworld").unwrap().unwrap();
    assert_eq!(1, overworld.data_file("scoreboard").unwrap().unwrap().get_int("Value").unwrap());

    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn level_data_l1_getters() {
    let work = temp_world("l1-getters");
    write_level(&work, |data| {
        data.set_int("DataVersion", 3953);
        data.set_int("SpawnX", 10);
        data.set_int("SpawnY", 64);
        data.set_int("SpawnZ", -5);
        data.set_byte("Difficulty", 2);
        data.set_byte("hardcore", 1);
    });

    let world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert_eq!(vec![10, 64, -5], world.level().spawn_pos().unwrap());
    assert_eq!("normal", world.level().difficulty().unwrap());
    assert!(world.level().is_hardcore().unwrap());

    match world.level().spawn_dimension() {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::UnsupportedFeature, error),
    }

    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn l1の難易度は数値を名前に直す() {
    // 0〜3をそれぞれ名前に直せる
    for (number, name) in [(0, "peaceful"), (1, "easy"), (2, "normal"), (3, "hard")] {
        let work = temp_world(&format!("difficulty-{number}"));
        write_level(&work, |data| {
            data.set_int("DataVersion", 3953);
            data.set_byte("Difficulty", number);
        });

        let world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
        assert_eq!(name, world.level().difficulty().unwrap());

        std::fs::remove_dir_all(&work).unwrap();
    }
}

#[test]
fn l1の難易度が範囲外ならmalformed_data() {
    // 範囲の外側の両端を確かめる
    for (index, number) in [-1i8, 4].into_iter().enumerate() {
        let work = temp_world(&format!("difficulty-range-{index}"));
        write_level(&work, |data| {
            data.set_int("DataVersion", 3953);
            data.set_byte("Difficulty", number);
        });

        let world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();

        match world.level().difficulty() {
            Ok(_) => panic!("読めてしまった"),
            Err(error) => assert_code(ErrorCode::MalformedData, error),
        }

        std::fs::remove_dir_all(&work).unwrap();
    }
}

#[test]
fn world_l2_unchanged() {
    let work = temp_world("l2");
    write_level(&work, |data| {
        data.set_int("DataVersion", 5023);

        let mut spawn = NbtCompound::new();
        spawn.set_int_array("pos", vec![1, 2, 3]);
        spawn.set_string("dimension", "minecraft:overworld");
        data.set("spawn", NbtTag::Compound(spawn));

        let mut settings = NbtCompound::new();
        settings.set_string("difficulty", "hard");
        settings.set_byte("hardcore", 1);
        data.set("difficulty_settings", NbtTag::Compound(settings));
    });

    std::fs::create_dir_all(work.join("dimensions/minecraft/overworld")).unwrap();
    std::fs::create_dir_all(work.join("dimensions/minecraft/the_end")).unwrap();
    write_dat(&work.join("players/data/u.dat"), |root| root.set_int("Health", 3));
    write_dat(&work.join("data/minecraft/weather.dat"), |root| root.set_int("Value", 4));
    write_dat(&work.join("dimensions/minecraft/the_end/data/minecraft/raids.dat"), |root| {
        root.set_int("Value", 5)
    });

    let mut world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert_eq!(vec![1, 2, 3], world.level().spawn_pos().unwrap());
    assert_eq!("minecraft:overworld", world.level().spawn_dimension().unwrap());
    assert_eq!("hard", world.level().difficulty().unwrap());
    assert!(world.level().is_hardcore().unwrap());
    assert_eq!(
        vec!["minecraft:overworld", "minecraft:the_end"],
        world.dimension_ids().unwrap()
    );
    assert_eq!(vec!["u"], world.player_ids().unwrap());
    assert_eq!(4, world.data_file("weather").unwrap().unwrap().get_int("Value").unwrap());

    let end = world.dimension("the_end").unwrap().unwrap();
    assert_eq!(5, end.data_file("raids").unwrap().unwrap().get_int("Value").unwrap());

    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn data_versionが無いlevel_datはl1として読む() {
    let work = temp_world("no-data-version");
    write_level(&work, |_| {});
    std::fs::create_dir_all(work.join("DIM1")).unwrap();

    let world = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert_eq!(vec!["minecraft:the_end"], world.dimension_ids().unwrap());

    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn world_override_layout() {
    let work = temp_world("override");

    // level.datは26.3を名乗るが、構成はL1
    write_level(&work, |data| {
        data.set_int("DataVersion", 5023);
        data.set_int("SpawnX", 1);
        data.set_int("SpawnY", 2);
        data.set_int("SpawnZ", 3);
    });
    std::fs::create_dir_all(work.join("region")).unwrap();

    let plain = MinecraftWorld::open(&work, WorldOpenOptions::default()).unwrap();
    assert!(plain.dimension_ids().unwrap().is_empty());

    let options = WorldOpenOptions { format_data_version: Some(3953), ..WorldOpenOptions::default() };
    let world = MinecraftWorld::open(&work, options).unwrap();
    assert_eq!(vec!["minecraft:overworld"], world.dimension_ids().unwrap());
    assert_eq!(vec![1, 2, 3], world.level().spawn_pos().unwrap());

    let invalid = WorldOpenOptions { format_data_version: Some(1518), ..WorldOpenOptions::default() };

    match MinecraftWorld::open(&work, invalid) {
        Ok(_) => panic!("開けてしまった"),
        Err(error) => assert_code(ErrorCode::InvalidArgument, error),
    }

    std::fs::remove_dir_all(&work).unwrap();
}

#[test]
fn ワールドの指定は読むチャンクの世代にも効く() {
    let work = temp_world("override-chunk");
    write_level(&work, |data| data.set_int("DataVersion", 5023));
    let region = work.join("dimensions").join("minecraft").join("overworld").join("region");
    std::fs::create_dir_all(&region).unwrap();

    {
        let mut file = RegionFile::open(region.join("r.0.0.mca"), RegionFileMode::ReadWrite).unwrap();
        let named = read_file(vector_path("palette_1"), &NbtReadOptions::default()).unwrap();
        file.write_chunk(0, 0, &named.tag, ChunkCompression::Zlib).unwrap();
        file.close().unwrap();
    }

    // ワールドの指定がchunk_readの指定より優先される
    let options = WorldOpenOptions {
        chunk_read: ChunkReadOptions {
            format_data_version: Some(5023),
            ..ChunkReadOptions::default()
        },
        format_data_version: Some(5006),
        ..WorldOpenOptions::default()
    };

    let mut world = MinecraftWorld::open(&work, options).unwrap();
    let overworld = world.dimension("minecraft:overworld").unwrap().unwrap();
    let loaded = overworld.chunk(0, 0).unwrap().unwrap();
    assert_eq!(5006, loaded.format_data_version());

    std::fs::remove_dir_all(&work).unwrap();
}

// ---------------------------------------------------------------------------
// 文字列でのブロック指定と、変更の印
// ---------------------------------------------------------------------------

#[test]
fn accepts_a_block_state_written_as_text() {
    let mut chunk = load_chunk("palette_1");
    chunk.set_block(3, -60, 7, "minecraft:oak_stairs[facing=north,half=top]").unwrap();

    assert_eq!(
        chunk.get_block(3, -60, 7).unwrap().unwrap().to_string(),
        "minecraft:oak_stairs[facing=north,half=top]"
    );
}

#[test]
fn marks_the_chunk_as_modified() {
    let mut chunk = load_chunk("palette_1");
    assert!(!chunk.is_modified());

    chunk.set_block(3, -60, 7, "minecraft:stone").unwrap();
    assert!(chunk.is_modified());

    // 保存済みとして印を外せる
    chunk.set_is_modified(false);
    assert!(!chunk.is_modified());

    // 同じ状態を置き直すだけなら何も起きないので印も付かない
    chunk.set_block(3, -60, 7, "minecraft:stone").unwrap();
    assert!(!chunk.is_modified());

    chunk.clear_heightmaps().unwrap();
    assert!(chunk.is_modified());
}
