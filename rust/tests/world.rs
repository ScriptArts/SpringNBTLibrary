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

/// セクションの一覧を、指定したYの並びに並べ替えた新しいリストを作る
fn sections_in_order(sections: &NbtList, order: &[i8]) -> NbtTag {
    let mut result = NbtList::with_element_type(TagType::Compound);

    // 指定の順に、Yの合うセクションを探して足す
    for section_y in order {
        // Yの合うセクションだけを足す
        for entry in sections.iter() {
            if let NbtTag::Compound(section) = entry {
                if section.get_byte("Y").unwrap() == *section_y {
                    result.push(entry.clone()).unwrap();
                }
            }
        }
    }

    NbtTag::List(result)
}

/// 書き出したセクションの一覧のYを並べる
fn section_y_order(sections: &NbtList) -> Vec<i8> {
    let mut result = Vec::new();

    // 一覧の並びのままYを取り出す
    for entry in sections.iter() {
        if let NbtTag::Compound(section) = entry {
            result.push(section.get_byte("Y").unwrap());
        }
    }

    result
}

/// 最初のセクションのblock_statesを、palette、data、ほかのキーの順に並べ替える
fn reorder_block_states(root: &mut NbtCompound) {
    let mut sections = root.get_list("sections").unwrap().clone();
    let mut section = match sections.get(0) {
        Some(NbtTag::Compound(section)) => section.clone(),
        _ => panic!("最初のセクションが無い"),
    };
    let container = section.get_compound("block_states").unwrap().clone();
    let mut reordered = NbtCompound::new();
    reordered.set("palette", container.get("palette").unwrap().clone());
    reordered.set("data", container.get("data").unwrap().clone());
    reordered.set_int("extra", 7);
    section.set("block_states", NbtTag::Compound(reordered));
    sections.remove_at(0);
    sections.insert(0, NbtTag::Compound(section)).unwrap();
    root.set("sections", NbtTag::List(sections));
}

/// 書き出したチャンクの最初のセクションのblock_statesのキーの並び
fn first_block_states_keys(written: &NbtCompound) -> Vec<String> {
    let section = match written.get_list("sections").unwrap().get(0) {
        Some(NbtTag::Compound(section)) => section.clone(),
        _ => panic!("最初のセクションが無い"),
    };

    section.get_compound("block_states").unwrap().keys().map(String::from).collect()
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
fn 読んだときのセクションの並びで書き戻す() {
    let mut root = read_file(vector_path("multi_section"), &NbtReadOptions::default()).unwrap().tag;
    let reordered = sections_in_order(root.get_list("sections").unwrap(), &[-2, -4, -3]);
    root.set("sections", reordered);
    let before = chunk_bytes(&root);
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    // Yの昇順でない並びでも、無変更なら元とバイト単位で一致する
    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));

    // 1つのセクションを書き換えても並びは変わらない
    chunk.set_block(0, -48, 0, "minecraft:stone").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();

    assert_eq!(vec![-2, -4, -3], section_y_order(written.get_list("sections").unwrap()));
    assert_eq!(vec![-4, -3, -2], chunk.section_ys());
}

#[test]
fn paletteが先のコンテナはその並びのまま書き戻す() {
    let mut root = read_file(vector_path("palette_17"), &NbtReadOptions::default()).unwrap().tag;
    reorder_block_states(&mut root);
    let before = chunk_bytes(&root);
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    // 無変更なら元とバイト単位で一致する
    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));

    // ビット幅の変わらない書き換えなら、キーの並びもほかのキーも保つ
    chunk.set_block(0, -64, 0, "minecraft:edited").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();

    assert_eq!(vec!["palette", "data", "extra"], first_block_states_keys(&written));
    assert_eq!(18, first_block_palette(&written).len());
}

#[test]
fn dataが要らなくなれば消しまた要るときは読んだときの位置に戻す() {
    let mut root = read_file(vector_path("palette_17"), &NbtReadOptions::default()).unwrap().tag;
    reorder_block_states(&mut root);
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    // パレットが1要素になればdataだけを消し、ほかのキーの位置は保つ
    let section = chunk.section_mut(-4).unwrap();
    section.block_states_mut().unwrap().fill(block_entry("minecraft:stone"));
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert_eq!(vec!["palette", "extra"], first_block_states_keys(&written));

    // 読んだときにあったdataは、読んだときの位置に戻す
    chunk.set_block(0, -64, 0, "minecraft:edited").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert_eq!(vec!["palette", "data", "extra"], first_block_states_keys(&written));
}

#[test]
fn 読んだときに無かったdataはライブラリの並びで先に置く() {
    let mut root = read_file(vector_path("palette_1"), &NbtReadOptions::default()).unwrap().tag;
    let mut sections = root.get_list("sections").unwrap().clone();
    let mut section = match sections.get(0) {
        Some(NbtTag::Compound(section)) => section.clone(),
        _ => panic!("最初のセクションが無い"),
    };
    let mut container = section.get_compound("block_states").unwrap().clone();
    container.set_int("extra", 7);
    section.set("block_states", NbtTag::Compound(container));
    sections.remove_at(0);
    sections.insert(0, NbtTag::Compound(section)).unwrap();
    root.set("sections", NbtTag::List(sections));
    let before = chunk_bytes(&root);
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    // 無変更なら元とバイト単位で一致する
    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));

    // パレットが育ってdataが要るようになれば、dataを先に置きほかのキーを後ろに残す
    chunk.set_block(0, -64, 0, "minecraft:edited").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert_eq!(vec!["data", "palette", "extra"], first_block_states_keys(&written));
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
fn 扱える形式の下限は1_13() {
    assert_eq!(1519, MIN_SUPPORTED_DATA_VERSION);

    let warnings: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
    let sink = Rc::clone(&warnings);
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Warn,
        on_warning: Some(Box::new(move |message: &str| {
            sink.borrow_mut().push(message.to_string());
        })),
        ..ChunkReadOptions::default()
    };

    // 1.13の正式版より1つ古いチャンクは、読み込みで警告になる
    let mut root = pre_flattening_chunk();
    root.set_int("DataVersion", 1518);
    Chunk::from_nbt(root, &options).unwrap();
    assert_eq!(1, warnings.borrow().len());

    // 1.13の正式版のチャンクは警告を出さない
    Chunk::from_nbt(level_chunk(1519), &options).unwrap();
    assert_eq!(1, warnings.borrow().len());
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

    // ベクタの添字は(位置 * 7) % 5
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
        chunk.get_biome_id(0, 0, 0).map(|_| ()),
        chunk.set_block(0, 0, 0, "minecraft:stone"),
        chunk.set_biome(0, 0, 0, "minecraft:plains"),
        chunk.set_biome_id(0, 0, 0, 1),
        chunk.clear_heightmaps(),
        chunk.invalidate_lighting(),
        chunk.min_section_y().map(|_| ()),
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

#[test]
fn c5の世代で26_2のチャンクを読むとブロックの取得でmalformed_data() {
    let tag = read_file(vector_path("v4903_edit"), &NbtReadOptions::default()).unwrap().tag;
    let options = ChunkReadOptions {
        format_data_version: Some(5023),
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(tag, &options).unwrap();

    // パレットの要素がName / Propertiesなので、26.3の形式としては読めない
    assert_code(ErrorCode::MalformedData, chunk.get_block(0, -64, 0).unwrap_err());
}

#[test]
fn ルートの直下にsectionsがあるチャンクを1_16の世代で読むとmalformed_data() {
    let tag = read_file(vector_path("palette_1"), &NbtReadOptions::default()).unwrap().tag;
    let options = ChunkReadOptions {
        format_data_version: Some(2586),
        ..ChunkReadOptions::default()
    };

    // Levelの無いチャンクを、Levelに本体を包む世代で読ませる
    assert_code(ErrorCode::MalformedData, Chunk::from_nbt(tag, &options).unwrap_err());
}

#[test]
fn 名前空間の無いfullも生成済みとみなす() {
    let mut root = read_file(vector_path("v4903_edit"), &NbtReadOptions::default()).unwrap().tag;
    root.set_string("Status", "full");
    let chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    assert_eq!("full", chunk.status().unwrap());
    assert!(chunk.is_fully_generated());
}

// ---------------------------------------------------------------------------
// 1.16〜1.17の形式（本体がLevelの中）のチャンク
// ---------------------------------------------------------------------------

/// 1.16.5の形式のテストベクタのLevel.Biomesの値
fn level_biome(index: usize) -> i32 {
    ((index * 3) % 11 + 1) as i32
}

/// 1.16.5の形式のテストベクタをNBTのまま読む
fn level_vector() -> NbtCompound {
    read_file(vector_path("v2586_level"), &NbtReadOptions::default()).unwrap().tag
}

/// Levelの中身を書き換える
fn update_level(root: &mut NbtCompound, update: impl FnOnce(&mut NbtCompound)) {
    let mut level = root.get_compound("Level").unwrap().clone();
    update(&mut level);
    root.set("Level", NbtTag::Compound(level));
}

/// Level.SectionsからY位置の合うセクションを探す
fn level_section(root: &NbtCompound, section_y: i8) -> NbtCompound {
    let sections = root.get_compound("Level").unwrap().get_list("Sections").unwrap();

    // Yが一致する要素を返す
    for entry in sections.iter() {
        // Yの合うセクションだけを対象にする
        if let NbtTag::Compound(section) = entry {
            // Yが一致すれば、それが探しているセクション
            if section.get_byte("Y").unwrap() == section_y {
                return section.clone();
            }
        }
    }

    panic!("Y={section_y} のセクションが無い");
}

/// Level.SectionsのうちY位置の合うセクションを書き換える
fn update_level_section(root: &mut NbtCompound, section_y: i8, update: impl Fn(&mut NbtCompound)) {
    update_level(root, |level| {
        let mut sections = NbtList::with_element_type(TagType::Compound);

        // 対象のセクションだけを書き換え、ほかはそのまま並べ直す
        for entry in level.get_list("Sections").unwrap().iter() {
            let mut section = match entry {
                NbtTag::Compound(section) => section.clone(),
                _ => panic!("Sections の要素が compound でない"),
            };

            // Yの合うセクションだけを書き換える
            if section.get_byte("Y").unwrap() == section_y {
                update(&mut section);
            }

            sections.push(NbtTag::Compound(section)).unwrap();
        }

        level.set("Sections", NbtTag::List(sections));
    });
}

/// 付随データの要素の座標を並べる
fn positions(values: &NbtList) -> Vec<(i32, i32, i32)> {
    let mut result = Vec::new();

    // 要素ごとに絶対座標を取り出す
    for entry in values.iter() {
        // 座標を持つのはCompoundの要素だけ
        if let NbtTag::Compound(compound) = entry {
            result.push((
                compound.get_int("x").unwrap(),
                compound.get_int("y").unwrap(),
                compound.get_int("z").unwrap(),
            ));
        }
    }

    result
}

#[test]
fn data_version2586のチャンクも読んだときのセクションの並びで書き戻す() {
    let mut root = level_vector();
    update_level(&mut root, |level| {
        let reordered = sections_in_order(level.get_list("Sections").unwrap(), &[1, -1, 0]);
        level.set("Sections", reordered);
    });
    let before = chunk_bytes(&root);
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    // Yの昇順でない並びでも、無変更なら元とバイト単位で一致する
    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));

    // 1つのセクションを書き換えても並びは変わらない
    chunk.set_block(0, 16, 0, "minecraft:stone").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let sections = written.get_compound("Level").unwrap().get_list("Sections").unwrap();

    assert_eq!(vec![1, -1, 0], section_y_order(sections));
}

#[test]
fn data_version2586のチャンクを読み無変更で書き戻すと元と同じになる() {
    let root = level_vector();
    let before = chunk_bytes(&root);
    let chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    assert_eq!(2586, chunk.data_version().unwrap());
    assert_eq!(2, chunk.x().unwrap());
    assert_eq!(-1, chunk.z().unwrap());
    assert_eq!(0, chunk.min_section_y().unwrap());
    assert_eq!("full", chunk.status().unwrap());
    assert!(chunk.is_fully_generated());
    assert_eq!(vec![-1, 0, 1], chunk.section_ys());

    // ベクタの添字は(位置 * 7) % 5
    let block = |x, y, z| chunk.get_block(x, y, z).unwrap().unwrap().to_string();
    assert_eq!("minecraft:air", block(0, 0, 0));
    assert_eq!("minecraft:dirt", block(1, 0, 0));
    assert_eq!("minecraft:oak_stairs[facing=west,half=top]", block(2, 0, 0));
    assert_eq!("minecraft:stone", block(3, 0, 0));
    assert_eq!("minecraft:oak_stairs[facing=east,half=bottom]", block(4, 0, 0));
    assert_eq!("minecraft:air", block(15, 31, 15));

    // Paletteの無いセクションと、セクションの無い高さはブロックを持たない
    assert!(!chunk.section(-1).unwrap().has_block_states());
    assert!(chunk.get_block(0, -1, 0).unwrap().is_none());
    assert!(chunk.get_block(0, 32, 0).unwrap().is_none());

    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
}

#[test]
fn data_version2586のチャンクでブロックを置くとlevelの付随データが消える() {
    let mut chunk = Chunk::from_nbt(level_vector(), &ChunkReadOptions::default()).unwrap();

    // 絶対座標はx = 32 + 相対x、z = -16 + 相対z
    chunk.set_block(0, 0, 0, "minecraft:stone").unwrap();
    chunk.set_block(1, 0, 1, "minecraft:stone").unwrap();
    chunk.set_block(2, 2, 2, "minecraft:oak_stairs[facing=north]").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let level = written.get_compound("Level").unwrap();

    assert_eq!(vec![(47, 20, -1)], positions(level.get_list("TileEntities").unwrap()));
    assert!(level.get_list("TileTicks").unwrap().is_empty());
    assert_eq!(vec![(40, 5, -10)], positions(level.get_list("LiquidTicks").unwrap()));

    // ルートには付随データのキーを作らない
    assert!(!written.contains_key("block_entities"));
    assert!(!written.contains_key("TileEntities"));

    // パレットの末尾にName / Propertiesの形式で足され、BlockStatesも書き直される
    let section = level_section(&written, 0);
    let palette = section.get_list("Palette").unwrap();
    assert_eq!(
        Some(&name_properties("minecraft:oak_stairs", &[("facing", "north")])),
        palette.get(palette.len() - 1)
    );
    assert_eq!(256, section.get_long_array("BlockStates").unwrap().len());
    assert_eq!(2586, written.get_int("DataVersion").unwrap());

    // 読み直しても同じ状態が返る
    let reread = Chunk::from_nbt(written, &ChunkReadOptions::default()).unwrap();
    assert_eq!(
        "minecraft:oak_stairs[facing=north]",
        reread.get_block(2, 2, 2).unwrap().unwrap().to_string()
    );
    assert_eq!("minecraft:stone", reread.get_block(0, 0, 0).unwrap().unwrap().to_string());
}

#[test]
fn data_version2586のチャンクのバイオームidを読み書きできる() {
    let mut chunk = Chunk::from_nbt(level_vector(), &ChunkReadOptions::default()).unwrap();

    assert_eq!(Some(level_biome(0)), chunk.get_biome_id(0, 0, 0).unwrap());
    assert_eq!(
        Some(level_biome(17 * 16 + 2 * 4 + 1)),
        chunk.get_biome_id(5, 70, 9).unwrap()
    );
    assert_eq!(Some(level_biome(1023)), chunk.get_biome_id(15, 255, 15).unwrap());

    // 高さ0..255の外は値を持たない
    assert_eq!(None, chunk.get_biome_id(0, -1, 0).unwrap());
    assert_eq!(None, chunk.get_biome_id(0, 256, 0).unwrap());

    chunk.set_biome_id(5, 70, 9, 42).unwrap();
    assert!(chunk.is_modified());
    assert_eq!(Some(42), chunk.get_biome_id(4, 68, 8).unwrap());

    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let biomes = written.get_compound("Level").unwrap().get_int_array("Biomes").unwrap();
    assert_eq!(42, biomes[17 * 16 + 2 * 4 + 1]);
}

#[test]
fn 高さ0から255の外へバイオームidを書くとinvalid_argument() {
    // 下端と上端の外を両方確かめる
    for y in [-1, 256] {
        let mut chunk = Chunk::from_nbt(level_vector(), &ChunkReadOptions::default()).unwrap();
        assert_code(ErrorCode::InvalidArgument, chunk.set_biome_id(0, y, 0, 1).unwrap_err());
    }
}

#[test]
fn biomesを読めないチャンクのバイオームidはnoneで書き込めない() {
    let cases = [
        None,
        Some(NbtTag::IntArray(vec![])),
        Some(NbtTag::IntArray(vec![1; 256])),
        Some(NbtTag::ByteArray(vec![1; 256])),
    ];

    // Biomesを持たない形と、読めない形のそれぞれで確かめる
    for biomes in cases {
        let mut root = level_vector();
        update_level(&mut root, |level| {
            level.remove("Biomes");

            // NoneならBiomesを持たないチャンクにする
            if let Some(tag) = biomes {
                level.set("Biomes", tag);
            }
        });

        let before = chunk_bytes(&root);
        let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();
        assert_eq!(None, chunk.get_biome_id(0, 0, 0).unwrap());
        assert_code(ErrorCode::InvalidArgument, chunk.set_biome_id(0, 0, 0, 1).unwrap_err());

        // 元のNBTはそのまま残る
        assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
    }
}

#[test]
fn data_version2586のチャンクではバイオーム名のapiはunsupported_feature() {
    let mut chunk = Chunk::from_nbt(level_vector(), &ChunkReadOptions::default()).unwrap();

    // セクションの無い高さでも、形式で決まるので同じエラーになる
    assert_code(ErrorCode::UnsupportedFeature, chunk.get_biome(0, 0, 0).unwrap_err());
    assert_code(ErrorCode::UnsupportedFeature, chunk.get_biome(0, 200, 0).unwrap_err());
    assert_code(
        ErrorCode::UnsupportedFeature,
        chunk.set_biome(0, 0, 0, "minecraft:plains").unwrap_err(),
    );
}

#[test]
fn バイオームidのapiは1_18以降のチャンクではunsupported_feature() {
    // 26.3の形式と26.2の形式の両方で確かめる
    for name in ["palette_1", "v4903_edit"] {
        let mut chunk = load_chunk(name);
        assert_code(ErrorCode::UnsupportedFeature, chunk.get_biome_id(0, 0, 0).unwrap_err());
        assert_code(ErrorCode::UnsupportedFeature, chunk.set_biome_id(0, 0, 0, 1).unwrap_err());
    }
}

#[test]
fn data_version2586のチャンクの高さマップと光源を無効化できる() {
    let mut chunk = Chunk::from_nbt(level_vector(), &ChunkReadOptions::default()).unwrap();
    chunk.clear_heightmaps().unwrap();
    chunk.invalidate_lighting().unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let level = written.get_compound("Level").unwrap();

    assert!(level.opt_compound("Heightmaps").unwrap().is_none());
    assert_eq!(0, level.get_byte("isLightOn").unwrap());

    // ルートには作らない
    assert!(!written.contains_key("isLightOn"));
}

#[test]
fn is_light_onの無いdata_version2586のチャンクは光源を無効化できない() {
    let mut root = level_vector();
    update_level(&mut root, |level| {
        level.remove("isLightOn");
    });
    let before = chunk_bytes(&root);
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    assert_code(ErrorCode::UnsupportedFeature, chunk.invalidate_lighting().unwrap_err());
    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
}

#[test]
fn 生成途中のdata_version2586のチャンクは生成済みではない() {
    let mut root = level_vector();
    update_level(&mut root, |level| level.set_string("Status", "structure_starts"));

    assert!(!Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap().is_fully_generated());
}

#[test]
fn paletteとblock_statesの片方しか無いセクションはブロックを持たない() {
    // BlockStatesだけが無い形と、Paletteだけが無い形の両方で確かめる
    for key in ["BlockStates", "Palette"] {
        let mut root = level_vector();
        update_level_section(&mut root, 1, |section| {
            section.remove(key);
        });
        let before = chunk_bytes(&root);
        let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

        // Minecraftも両方がそろったセクションだけを読むので、ブロックの無いセクションとして扱う
        assert!(!chunk.section(1).unwrap().has_block_states());
        assert!(chunk.get_block(0, 16, 0).unwrap().is_none());
        assert_code(
            ErrorCode::InvalidArgument,
            chunk.set_block(0, 16, 0, "minecraft:stone").unwrap_err(),
        );

        // 元のNBTはそのまま残る
        assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
    }
}

#[test]
fn properties_nameの並びの要素と同じ状態を置いてもパレットは増えない() {
    let root = level_vector();
    let palette_before = level_section(&root, 0).get_list("Palette").unwrap().clone();
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    // 実データと同じくProperties -> Nameの並びで入っている状態を、プロパティの並びを変えて置く
    chunk.set_block(0, 0, 0, "minecraft:oak_stairs[half=bottom,facing=east]").unwrap();
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();

    // 同じ状態の要素を使い回すので、パレットは元のまま
    assert_eq!(&palette_before, level_section(&written, 0).get_list("Palette").unwrap());
    let reread = Chunk::from_nbt(written, &ChunkReadOptions::default()).unwrap();
    assert_eq!(
        "minecraft:oak_stairs[facing=east,half=bottom]",
        reread.get_block(0, 0, 0).unwrap().unwrap().to_string()
    );
}

#[test]
fn paletteの要素がcompoundでなければunexpected_tag_type() {
    let mut root = level_vector();
    update_level_section(&mut root, 1, |section| {
        let mut palette = NbtList::with_element_type(TagType::String);
        palette.push(NbtTag::String(NbtString::new("minecraft:air"))).unwrap();
        section.set("Palette", NbtTag::List(palette));
    });

    assert_code(
        ErrorCode::UnexpectedTagType,
        Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap_err(),
    );
}

// ---------------------------------------------------------------------------
// 1.13〜1.15の形式（ビット詰めが64bitの境目をまたぐ）のチャンク
// ---------------------------------------------------------------------------

/// 1.15.2の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの
fn spanning_states() -> Vec<String> {
    let mut states = vec!["minecraft:air".to_string(), "minecraft:stone".to_string()];

    // 階段は下半分の4方向、上半分の4方向の順に並ぶ
    for half in ["bottom", "top"] {
        // 向きは名前の順に並ぶ
        for facing in ["east", "north", "south", "west"] {
            states.push(format!("minecraft:oak_stairs[facing={facing},half={half}]"));
        }
    }

    // プロパティの無いブロックを後ろに並べる
    for name in ["dirt", "gravel", "sand", "bedrock", "cobblestone", "oak_planks", "glass"] {
        states.push(format!("minecraft:{name}"));
    }

    states
}

/// 1.15.2の形式のテストベクタのLevel.Biomesの値
fn spanning_biome(index: usize) -> i32 {
    ((index * 5) % 13 + 1) as i32
}

/// 1.14.4の形式のテストベクタのLevel.Biomesの値
fn biome_2d(index: usize) -> i32 {
    ((index * 7) % 61 + 1) as i32
}

/// 1.16.5と1.14.4の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの
fn level_states() -> [&'static str; 5] {
    [
        "minecraft:air",
        "minecraft:stone",
        "minecraft:dirt",
        "minecraft:oak_stairs[facing=east,half=bottom]",
        "minecraft:oak_stairs[facing=west,half=top]",
    ]
}

/// 1.15.2の形式のテストベクタをNBTのまま読む
fn spanning_vector() -> NbtCompound {
    read_file(vector_path("v2230_spanning"), &NbtReadOptions::default()).unwrap().tag
}

/// 1.14.4の形式のテストベクタをNBTのまま読む
fn biomes_2d_vector() -> NbtCompound {
    read_file(vector_path("v1976_biomes_2d"), &NbtReadOptions::default()).unwrap().tag
}

#[test]
fn data_version2230のまたぐ詰め方のチャンクを読み無変更で書き戻すと元と同じになる() {
    let root = spanning_vector();
    let before = chunk_bytes(&root);
    let chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();
    let states = spanning_states();

    assert_eq!(2230, chunk.data_version().unwrap());
    assert_eq!(-3, chunk.x().unwrap());
    assert_eq!(5, chunk.z().unwrap());
    assert_eq!(0, chunk.min_section_y().unwrap());
    assert!(chunk.is_fully_generated());
    assert_eq!(vec![-1, 0, 1], chunk.section_ys());
    let container = chunk.section(0).unwrap().block_states().unwrap();
    assert_eq!(17, container.palette().len());
    assert_eq!(5, container.bits_per_entry());

    // ベクタの添字は(位置 * 7) % 17
    // ビット幅5なので、位置12や25の値は64bitの境目をまたぐ
    let block = |x, y, z| chunk.get_block(x, y, z).unwrap().unwrap().to_string();
    assert_eq!(states[(12 * 7) % 17], block(12, 0, 0));
    assert_eq!(states[(25 * 7) % 17], block(9, 0, 1));

    // 全ブロックが元の添字どおりに読める
    for position in 0..4096 {
        let actual = block(position & 15, position >> 8, (position >> 4) & 15);
        assert_eq!(states[(position as usize * 7) % 17], actual);
    }

    assert_eq!("minecraft:air", block(15, 31, 15));
    assert!(chunk.get_block(0, -1, 0).unwrap().is_none());

    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
}

#[test]
fn data_version2230のチャンクでパレットが育ってもまたぐ詰め方で書き戻す() {
    let mut chunk = Chunk::from_nbt(spanning_vector(), &ChunkReadOptions::default()).unwrap();
    let states = spanning_states();

    // 20種類を足してパレットを37要素にし、ビット幅を5から6へ広げる
    for index in 0..20 {
        let state = format!("minecraft:edited_{index}");
        chunk.set_block(index % 16, index / 16, 0, state.as_str()).unwrap();
    }

    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let section = level_section(&written, 0);

    // またぐ詰め方なので、長さはceil(4096 * 6 / 64) = 384
    assert_eq!(37, section.get_list("Palette").unwrap().len());
    assert_eq!(384, section.get_long_array("BlockStates").unwrap().len());
    assert_eq!(2230, written.get_int("DataVersion").unwrap());

    let reread = Chunk::from_nbt(written, &ChunkReadOptions::default()).unwrap();

    // 置いたブロックと、触っていないブロックの両方が読み直せる
    for position in 0..4096 {
        let x = position & 15;
        let y = position >> 8;
        let z = (position >> 4) & 15;
        let index = (y * 16) + x;
        let block = reread.get_block(x, y, z).unwrap().unwrap().to_string();

        // 置いた位置だけ新しい状態になる
        if z == 0 && index < 20 {
            assert_eq!(format!("minecraft:edited_{index}"), block);
        } else {
            assert_eq!(states[(position as usize * 7) % 17], block);
        }
    }
}

#[test]
fn data_version2230のチャンクのバイオームidは4ブロック単位で読める() {
    let chunk = Chunk::from_nbt(spanning_vector(), &ChunkReadOptions::default()).unwrap();

    assert_eq!(
        Some(spanning_biome(17 * 16 + 2 * 4 + 1)),
        chunk.get_biome_id(5, 70, 9).unwrap()
    );
    assert_eq!(None, chunk.get_biome_id(0, 256, 0).unwrap());
}

#[test]
fn data_version1976のチャンクを読み無変更で書き戻すと元と同じになる() {
    let root = biomes_2d_vector();
    let before = chunk_bytes(&root);
    let chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    assert_eq!(1976, chunk.data_version().unwrap());
    assert_eq!(4, chunk.x().unwrap());
    assert_eq!(-2, chunk.z().unwrap());
    assert_eq!(0, chunk.min_section_y().unwrap());
    assert_eq!(vec![0, 1], chunk.section_ys());

    // ベクタの添字は(位置 * 7) % 5
    let block = |x, y, z| chunk.get_block(x, y, z).unwrap().unwrap().to_string();
    assert_eq!("minecraft:air", block(0, 0, 0));
    assert_eq!("minecraft:dirt", block(1, 0, 0));
    assert_eq!("minecraft:oak_stairs[facing=west,half=top]", block(2, 0, 0));
    assert_eq!("minecraft:stone", block(3, 0, 0));
    assert_eq!("minecraft:oak_stairs[facing=east,half=bottom]", block(4, 0, 0));
    assert_eq!("minecraft:air", block(15, 31, 15));

    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
}

#[test]
fn data_version1976のチャンクでパレットが育ってもまたぐ詰め方で書き戻す() {
    let mut chunk = Chunk::from_nbt(biomes_2d_vector(), &ChunkReadOptions::default()).unwrap();
    let states = level_states();

    // 12種類を足してパレットを17要素にし、ビット幅を4から5へ広げる
    for index in 0..12 {
        let state = format!("minecraft:edited_{index}");
        chunk.set_block(index, 0, 0, state.as_str()).unwrap();
    }

    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let section = level_section(&written, 0);

    // またぐ詰め方なので、長さはceil(4096 * 5 / 64) = 320（またがない詰め方なら342）
    assert_eq!(17, section.get_list("Palette").unwrap().len());
    assert_eq!(320, section.get_long_array("BlockStates").unwrap().len());

    let reread = Chunk::from_nbt(written, &ChunkReadOptions::default()).unwrap();

    // 置いたブロックと、触っていないブロックの両方が読み直せる
    for position in 0..4096 {
        let block = reread
            .get_block(position & 15, position >> 8, (position >> 4) & 15)
            .unwrap()
            .unwrap()
            .to_string();

        // 置いた位置だけ新しい状態になる
        if position < 12 {
            assert_eq!(format!("minecraft:edited_{position}"), block);
        } else {
            assert_eq!(states[(position as usize * 7) % 5], block);
        }
    }
}

#[test]
fn data_version1976のバイオームidは高さに関係なく列ごとに読み書きできる() {
    let mut chunk = Chunk::from_nbt(biomes_2d_vector(), &ChunkReadOptions::default()).unwrap();

    // 添字はz * 16 + xで、yは見ない
    assert_eq!(Some(biome_2d(7 * 16 + 3)), chunk.get_biome_id(3, 0, 7).unwrap());
    assert_eq!(Some(biome_2d(7 * 16 + 3)), chunk.get_biome_id(3, 200, 7).unwrap());
    assert_eq!(Some(biome_2d(7 * 16 + 3)), chunk.get_biome_id(3, -10, 7).unwrap());
    assert_eq!(Some(biome_2d(7 * 16 + 3)), chunk.get_biome_id(3, 300, 7).unwrap());
    assert_eq!(Some(biome_2d(3 * 16 + 7)), chunk.get_biome_id(7, 0, 3).unwrap());

    chunk.set_biome_id(3, 1000, 7, 42).unwrap();
    assert!(chunk.is_modified());
    assert_eq!(Some(42), chunk.get_biome_id(3, 0, 7).unwrap());

    // 同じ列の値だけが変わる
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    let biomes = written.get_compound("Level").unwrap().get_int_array("Biomes").unwrap();
    assert_eq!(42, biomes[7 * 16 + 3]);
    assert_eq!(biome_2d(3 * 16 + 7), biomes[3 * 16 + 7]);
}

#[test]
fn data_version1976のbiomesを読めないチャンクのバイオームidはnoneで書き込めない() {
    let cases = [
        None,
        Some(NbtTag::IntArray(vec![])),
        Some(NbtTag::IntArray(vec![1; 1024])),
        Some(NbtTag::ByteArray(vec![1; 256])),
    ];

    // Biomesを持たない形と、読めない形のそれぞれで確かめる
    for biomes in cases {
        let mut root = biomes_2d_vector();
        update_level(&mut root, |level| {
            level.remove("Biomes");

            // NoneならBiomesを持たないチャンクにする
            if let Some(tag) = biomes {
                level.set("Biomes", tag);
            }
        });

        let before = chunk_bytes(&root);
        let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();
        assert_eq!(None, chunk.get_biome_id(0, 0, 0).unwrap());
        assert_code(ErrorCode::InvalidArgument, chunk.set_biome_id(0, 0, 0, 1).unwrap_err());

        // 元のNBTはそのまま残る
        assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
    }
}

#[test]
fn data_version1976のチャンクではバイオーム名のapiはunsupported_feature() {
    let chunk = Chunk::from_nbt(biomes_2d_vector(), &ChunkReadOptions::default()).unwrap();

    assert_code(ErrorCode::UnsupportedFeature, chunk.get_biome(0, 0, 0).unwrap_err());
}

#[test]
fn is_light_onの無い1_13の形式のチャンクは光源を無効化できない() {
    let mut root = biomes_2d_vector();
    root.set_int("DataVersion", 1519);
    update_level(&mut root, |level| {
        level.remove("isLightOn");
    });
    let before = chunk_bytes(&root);
    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    assert_code(ErrorCode::UnsupportedFeature, chunk.invalidate_lighting().unwrap_err());
    assert_eq!(before, chunk_bytes(&chunk.to_nbt(&ChunkWriteOptions::default()).unwrap()));
}

#[test]
fn 形式が1_14までならpostprocessedとfullchunkも生成済みとみなす() {
    let cases = [
        ("full", true),
        ("postprocessed", true),
        ("fullchunk", true),
        ("mobs_spawned", false),
        ("decorated", false),
    ];

    // 生成段階ごとに確かめる
    for (status, expected) in cases {
        let mut root = biomes_2d_vector();
        update_level(&mut root, |level| level.set_string("Status", status));

        let chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();
        assert_eq!(expected, chunk.is_fully_generated(), "Status {status}");
    }
}

#[test]
fn 形式が1_15ならpostprocessedを生成済みとみなさない() {
    let mut root = spanning_vector();
    update_level(&mut root, |level| level.set_string("Status", "postprocessed"));

    assert!(!Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap().is_fully_generated());
}

#[test]
fn statusの無いチャンクは生成済みとみなさない() {
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        ..ChunkReadOptions::default()
    };
    let mut legacy = biomes_2d_vector();
    update_level(&mut legacy, |level| {
        level.remove("Status");
    });

    // 1.13より前のチャンクはStatusを持たない
    assert!(!Chunk::from_nbt(pre_flattening_chunk(), &options).unwrap().is_fully_generated());
    assert!(!Chunk::from_nbt(legacy, &ChunkReadOptions::default()).unwrap().is_fully_generated());
}

#[test]
fn statusが文字列でないチャンクは生成済みとみなさない() {
    let mut root = biomes_2d_vector();
    update_level(&mut root, |level| level.set_int("Status", 1));
    let chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();

    // 生成段階の取得子は、いまと同じく型の違いをエラーにする
    assert_eq!(ErrorCode::UnexpectedTagType, chunk.status().unwrap_err().code());
    assert!(!chunk.is_fully_generated());
}

#[test]
fn data_versionの無いチャンクは元のnbtだけを持つ() {
    let mut root = pre_flattening_chunk();
    root.remove("DataVersion");
    let before = chunk_bytes(&root);
    let warnings: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
    let sink = Rc::clone(&warnings);
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Warn,
        on_warning: Some(Box::new(move |message: &str| {
            sink.borrow_mut().push(message.to_string());
        })),
        ..ChunkReadOptions::default()
    };
    let mut chunk = Chunk::from_nbt(root, &options).unwrap();

    // 1.13より前と同じく、読み込みで警告になる
    assert_eq!(1, warnings.borrow().len());

    // 座標はLevelの中から読み、セクションは解釈しない
    assert_eq!(3, chunk.x().unwrap());
    assert_eq!(-2, chunk.z().unwrap());
    assert!(chunk.section_ys().is_empty());
    assert_eq!(-1, chunk.format_data_version());

    // DataVersionの取得子は無ければエラーになる（いまと同じ）
    assert!(chunk.data_version().is_err());

    // ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
    let results = vec![
        chunk.get_block(0, 0, 0).map(|_| ()),
        chunk.get_biome(0, 0, 0).map(|_| ()),
        chunk.get_biome_id(0, 0, 0).map(|_| ()),
        chunk.min_section_y().map(|_| ()),
        chunk.to_nbt(&ChunkWriteOptions::default()).map(|_| ()),
        chunk.set_block(0, 0, 0, "minecraft:stone"),
        chunk.set_biome(0, 0, 0, "minecraft:plains"),
        chunk.set_biome_id(0, 0, 0, 1),
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
fn data_versionの無いチャンクはerrorなら読み込みで弾く() {
    let mut root = pre_flattening_chunk();
    root.remove("DataVersion");
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Error,
        ..ChunkReadOptions::default()
    };

    match Chunk::from_nbt(root, &options) {
        Ok(_) => panic!("読めてしまった"),
        Err(error) => assert_code(ErrorCode::UnsupportedDataVersion, error),
    }
}

#[test]
fn data_versionの無いチャンクも世代を指定すればその値を返す() {
    let mut root = pre_flattening_chunk();
    root.remove("DataVersion");
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        format_data_version: Some(2230),
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(root, &options).unwrap();

    // 指定しても世代は選ばず、元のNBTだけを持つ
    assert_eq!(2230, chunk.format_data_version());
    assert_code(ErrorCode::UnsupportedDataVersion, chunk.get_block(0, 0, 0).unwrap_err());
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
