//! World / Block レイヤ。
//!
//! 仕様: `docs/spec/30-chunk-format.md` / `31-paletted-container.md` / `40-world-layout.md`
//!
//! 他言語版と同じ検証項目を持つ。
//! 共通テストベクタによる言語間比較は `spec/run-conformance.sh` が担当し、
//! ここでは API の振る舞いを直接確かめる。

use std::cell::RefCell;
use std::path::{Path, PathBuf};
use std::rc::Rc;

use spring_nbt_library::error::{Error, ErrorCode};
use spring_nbt_library::nbt::tag::{NbtCompound, NbtString, NbtTag};
use spring_nbt_library::nbt::{
    read_file, write_bytes, Compression, NamedTag, NbtReadOptions, NbtWriteOptions,
};
use spring_nbt_library::world::{
    ceil_log2, BitStorage, BlockState, Chunk, ChunkReadOptions, ChunkWriteOptions, MinecraftWorld,
    PalettedContainer, VersionMismatchAction, WorldOpenOptions,
};
use spring_nbt_library::TARGET_DATA_VERSION;

/// 共通テストベクタ（world/*.nbt）のパス。
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

/// テストベクタをチャンクとして読む。
fn load_chunk(name: &str) -> Chunk {
    let named = read_file(vector_path(name), &NbtReadOptions::default()).expect("読めない");
    Chunk::from_nbt(named.tag, &ChunkReadOptions::default()).expect("チャンクとして解釈できない")
}

/// ブロックのパレット要素を作る。
fn block_entry(name: &str) -> NbtTag {
    let mut entry = NbtCompound::new();
    entry.set("Name", NbtTag::String(NbtString::new(name)));
    NbtTag::Compound(entry)
}

/// エラーが期待したコードであることを確かめる。
fn assert_code(expected: ErrorCode, error: Error) {
    assert_eq!(expected, error.code(), "エラーコードが違う: {error}");
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

    assert_eq!("minecraft:oak_stairs", nbt.get_string("Name").unwrap());
    assert_eq!(
        "north",
        nbt.get_compound("Properties").unwrap().get_string("facing").unwrap()
    );
    assert_eq!(state, BlockState::from_nbt(&nbt).unwrap());
}

#[test]
fn プロパティ無しのnbtにはpropertiesを書かない() {
    let nbt = BlockState::parse("minecraft:air").unwrap().to_nbt();
    assert!(nbt.opt_compound("Properties").unwrap().is_none());
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

    // 壊し方ごとに同じエラーコードになることを確かめる
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

    // bits=5 なら 1 つの long に 12 個。12 個目は次の long の最下位から始まる
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
    // 4096 エントリを 342 long で表せるのは bits=5 のときだけ
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

    // パレットを 17 要素まで増やして bits=4 から 5 への拡張を起こす
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

    // 残るのは実際に使われている air と dirt の 2 つ
    assert_eq!(2, container.palette().len());

    match container.get(0).unwrap() {
        NbtTag::Compound(entry) => assert_eq!("minecraft:dirt", entry.get_string("Name").unwrap()),
        other => panic!("compound でない: {other:?}"),
    }
}

#[test]
fn fillで単一値に戻る() {
    let mut container = PalettedContainer::filled(block_entry("minecraft:air"), 4096, 4);
    container.set(0, block_entry("minecraft:stone")).unwrap();
    container.fill(block_entry("minecraft:water"));

    assert_eq!(1, container.palette().len());
    assert_eq!(0, container.bits_per_entry());

    match container.get(4095).unwrap() {
        NbtTag::Compound(entry) => assert_eq!("minecraft:water", entry.get_string("Name").unwrap()),
        other => panic!("compound でない: {other:?}"),
    }
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

    // ベクタの添字は (位置 * 11) % 17。パレット先頭 2 つだけ名前が違う
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

    // 同じ 4×4×4 の枠内はまとめて変わる
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

    // (0,-64,0) には chest と block_tick、(1,-64,1) には furnace と fluid_tick がある
    let stone = BlockState::parse("minecraft:stone").unwrap();
    chunk.set_block(0, -64, 0, &stone).unwrap();
    chunk.set_block(1, -64, 1, &stone).unwrap();

    let entities = chunk.raw().get_list("block_entities").unwrap();

    // 触っていない (15,-50,15) の barrel だけが残る
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
    // 付随データは絶対座標で持つので、チャンク座標を取り違えると
    // 無関係な要素を消してしまう
    let named = read_file(vector_path("block_entities"), &NbtReadOptions::default()).unwrap();
    let mut root = named.tag;
    root.set("xPos", NbtTag::Int(1));
    root.set("zPos", NbtTag::Int(1));

    let mut chunk = Chunk::from_nbt(root, &ChunkReadOptions::default()).unwrap();
    let stone = BlockState::parse("minecraft:stone").unwrap();
    chunk.set_block(0, -64, 0, &stone).unwrap();

    // このチャンクの (0,-64,0) は絶対座標 (16,-64,16)。どれとも一致しない
    assert_eq!(3, chunk.raw().get_list("block_entities").unwrap().len());
}

#[test]
fn 高さマップと光源を無効化できる() {
    let mut chunk = load_chunk("palette_1");
    chunk.clear_heightmaps();
    chunk.invalidate_lighting();

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
// DataVersion の扱い
// ---------------------------------------------------------------------------

/// DataVersion だけを差し替えたチャンクを作る。
fn foreign_chunk() -> NbtCompound {
    let named = read_file(vector_path("palette_1"), &NbtReadOptions::default()).unwrap();
    let mut root = named.tag;
    root.set("DataVersion", NbtTag::Int(3953));
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
        lenient_bit_storage: false,
    };

    let chunk = Chunk::from_nbt(foreign_chunk(), &options).unwrap();
    assert_eq!(3953, chunk.data_version().unwrap());
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
        lenient_bit_storage: false,
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
fn 許可すれば対象バージョンとして書き戻す() {
    let read = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        ..ChunkReadOptions::default()
    };
    let chunk = Chunk::from_nbt(foreign_chunk(), &read).unwrap();
    let write = ChunkWriteOptions {
        allow_foreign_data_version: true,
    };

    // 書き戻しは常に対象バージョンへ揃える
    let written = chunk.to_nbt(&write).unwrap();
    assert_eq!(TARGET_DATA_VERSION, written.get_int("DataVersion").unwrap());
}

#[test]
fn 対象バージョンのチャンクはそのまま書き戻せる() {
    let chunk = load_chunk("palette_1");
    let written = chunk.to_nbt(&ChunkWriteOptions::default()).unwrap();
    assert_eq!(TARGET_DATA_VERSION, written.get_int("DataVersion").unwrap());
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
