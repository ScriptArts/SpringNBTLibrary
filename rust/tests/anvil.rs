//! Anvil リージョンファイルの読み書き。
//!
//! 仕様: `docs/spec/20-anvil-region.md`
//!
//! 他言語版と同じ検証項目を持つ。
//! 共通テストベクタによる言語間比較は `spec/run-conformance.sh` が担当し、
//! ここでは API の振る舞いを直接確かめる。

use std::path::{Path, PathBuf};

use spring_nbt_library::anvil::{
    ChunkCompression, ChunkPos, RegionFile, RegionFileMode, RegionFolder, RegionPos, SECTOR_SIZE,
};
use spring_nbt_library::error::ErrorCode;
use spring_nbt_library::nbt::tag::{NbtCompound, NbtString, NbtTag};
use spring_nbt_library::TARGET_DATA_VERSION;

/// 共通テストベクタのディレクトリ。
fn vector_dir(name: &str) -> PathBuf {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("リポジトリ直下が取れない")
        .join("spec")
        .join("testdata")
        .join("anvil")
        .join(name);

    assert!(path.is_dir(), "テストベクタが見つからない: anvil/{name}");
    path
}

/// テストごとの一時ディレクトリ。破棄時に自動で片付ける。
struct WorkDir {
    path: PathBuf,
}

impl WorkDir {
    fn new(label: &str) -> WorkDir {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("時刻を取得できない")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("springnbt-{label}-{unique}"));
        std::fs::create_dir_all(&path).expect("一時ディレクトリを作れない");
        WorkDir { path }
    }

    fn join(&self, name: &str) -> PathBuf {
        self.path.join(name)
    }

    /// ベクタを一時ディレクトリへ複製し、書き込みテストで原本を汚さないようにする。
    fn copy_vector(&self, name: &str) -> PathBuf {
        let source = vector_dir(name);
        let destination = self.path.join(name);
        std::fs::create_dir_all(&destination).expect("複製先を作れない");

        for entry in std::fs::read_dir(&source).expect("ベクタを読めない").flatten() {
            let target = destination.join(entry.file_name());
            std::fs::copy(entry.path(), target).expect("ベクタを複製できない");
        }

        destination
    }
}

impl Drop for WorkDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}

fn sample_chunk(x: i32, z: i32) -> NbtCompound {
    let mut chunk = NbtCompound::new();
    chunk.set("DataVersion", NbtTag::Int(TARGET_DATA_VERSION));
    chunk.set("xPos", NbtTag::Int(x));
    chunk.set("zPos", NbtTag::Int(z));
    chunk.set("yPos", NbtTag::Int(-4));
    chunk.set("Status", NbtTag::String(NbtString::new("minecraft:full")));
    chunk
}

/// 圧縮しても縮まないバイト列を作る。サイズの制御が効くようにするため。
fn incompressible(length: usize) -> Vec<i8> {
    let mut result = Vec::with_capacity(length);
    let mut state: u32 = 0x12345678;

    // 線形合同法で疑似乱数を作る。テストの再現性を保つため固定の種を使う
    for _ in 0..length {
        state = state.wrapping_mul(1664525).wrapping_add(1013904223);
        result.push((state >> 24) as u8 as i8);
    }

    result
}

fn file_len(path: &Path) -> u64 {
    std::fs::metadata(path).expect("ファイル情報を取れない").len()
}

// ---------------------------------------------------------------------------
// 座標計算
// ---------------------------------------------------------------------------

#[test]
fn chunk_position_math_handles_negative_coordinates() {
    let cases: Vec<(i32, i32, i32, i32, i32, i32)> = vec![
        (0, 0, 0, 0, 0, 0),
        (31, 31, 0, 0, 31, 31),
        (32, 32, 1, 1, 0, 0),
        (-1, -1, -1, -1, 31, 31),
        (-32, -32, -1, -1, 0, 0),
        (-33, -33, -2, -2, 31, 31),
    ];

    // 算術右シフトなので負の座標でも正しく求まる
    for (chunk_x, chunk_z, region_x, region_z, local_x, local_z) in cases {
        let position = ChunkPos::new(chunk_x, chunk_z);
        assert_eq!(position.region(), RegionPos::new(region_x, region_z));
        assert_eq!(position.local_x(), local_x);
        assert_eq!(position.local_z(), local_z);
        assert_eq!(position.index(), (local_x + local_z * 32) as usize);
    }
}

#[test]
fn region_file_name_roundtrips() {
    assert_eq!(RegionPos::new(-1, 2).file_name(), "r.-1.2.mca");
    assert_eq!(RegionPos::from_file_name("r.-1.2.mca"), Some(RegionPos::new(-1, 2)));

    // 形式が違うものは受け付けない
    assert_eq!(RegionPos::from_file_name("r.0.0.mcr"), None);
    assert_eq!(RegionPos::from_file_name("region.mca"), None);
    assert_eq!(RegionPos::from_file_name("r.a.0.mca"), None);
}

// ---------------------------------------------------------------------------
// 読み込み
// ---------------------------------------------------------------------------

#[test]
fn empty_region_has_no_chunks() {
    let region =
        RegionFile::open(vector_dir("empty").join("r.0.0.mca"), RegionFileMode::ReadOnly).unwrap();

    assert!(region.chunk_positions().unwrap().is_empty());
    assert!(!region.has_chunk(0, 0).unwrap());
    assert!(region.read_chunk(0, 0).unwrap().is_none());
}

#[test]
fn reads_single_chunk() {
    let region = RegionFile::open(
        vector_dir("single_chunk").join("r.0.0.mca"),
        RegionFileMode::ReadOnly,
    )
    .unwrap();

    assert_eq!(region.chunk_positions().unwrap(), vec![ChunkPos::new(0, 0)]);
    assert!(region.has_chunk(0, 0).unwrap());

    let chunk = region.read_chunk(0, 0).unwrap().unwrap();
    assert_eq!(chunk.get_int("DataVersion").unwrap(), TARGET_DATA_VERSION);
    assert_eq!(chunk.get_string("Status").unwrap(), "minecraft:full");
    assert_eq!(region.timestamp(0, 0).unwrap(), 1700000000);
}

#[test]
fn reads_every_compression_scheme() {
    let region = RegionFile::open(
        vector_dir("mixed_compression").join("r.0.0.mca"),
        RegionFileMode::ReadOnly,
    )
    .unwrap();

    assert_eq!(
        region.read_chunk_raw(0, 0).unwrap().unwrap().compression,
        ChunkCompression::Gzip
    );
    assert_eq!(
        region.read_chunk_raw(1, 0).unwrap().unwrap().compression,
        ChunkCompression::Zlib
    );
    assert_eq!(
        region.read_chunk_raw(2, 0).unwrap().unwrap().compression,
        ChunkCompression::None
    );

    // 方式が違っても中身は同じように読める
    for x in 0..3 {
        assert_eq!(
            region.read_chunk(x, 0).unwrap().unwrap().get_int("xPos").unwrap(),
            x
        );
    }
}

#[test]
fn reads_lz4_chunks() {
    let region =
        RegionFile::open(vector_dir("lz4").join("r.0.0.mca"), RegionFileMode::ReadOnly).unwrap();

    // 1 ブロック / 2 ブロック連結 / 無圧縮ブロック / 重なりのあるマッチ
    for x in 0..4 {
        assert_eq!(
            region.read_chunk_raw(x, 0).unwrap().unwrap().compression,
            ChunkCompression::Lz4
        );
        assert_eq!(
            region.read_chunk(x, 0).unwrap().unwrap().get_int("xPos").unwrap(),
            x
        );
    }

    // 同じバイトの繰り返しは、重なりのあるマッチとして詰められている
    assert_eq!(
        region.read_chunk(3, 0).unwrap().unwrap().get_string("filler").unwrap(),
        "A".repeat(4000)
    );
}

#[test]
fn rejects_lz4_block_with_broken_magic() {
    let region = RegionFile::open(
        vector_dir("lz4_bad_magic").join("r.0.0.mca"),
        RegionFileMode::ReadOnly,
    )
    .unwrap();

    let error = region.read_chunk(0, 0).unwrap_err();
    assert_eq!(error.code(), ErrorCode::MalformedData);
}

#[test]
fn writing_lz4_is_rejected() {
    let work = WorkDir::new("lz4write");
    let path = work.copy_vector("lz4").join("r.0.0.mca");
    let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();

    // LZ4 は読み込みのみ対応なので、圧縮して書き出すことはできない
    let chunk = region.read_chunk(0, 0).unwrap().unwrap();
    let error = region
        .write_chunk(0, 0, &chunk, ChunkCompression::Lz4)
        .unwrap_err();
    assert_eq!(error.code(), ErrorCode::UnsupportedFeature);
}

#[test]
fn untouched_lz4_chunks_keep_their_compression() {
    let work = WorkDir::new("lz4keep");
    let path = work.copy_vector("lz4").join("r.0.0.mca");
    let before = std::fs::read(&path).unwrap();

    {
        // 触らずに閉じるだけ。生バイトを素通しするので LZ4 のまま残る
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region.close().unwrap();
    }

    assert_eq!(std::fs::read(&path).unwrap(), before);
}

#[test]
fn reads_chunk_stored_in_external_file() {
    let region = RegionFile::open(
        vector_dir("external_mcc").join("r.0.0.mca"),
        RegionFileMode::ReadOnly,
    )
    .unwrap();

    let raw = region.read_chunk_raw(0, 0).unwrap().unwrap();
    assert!(raw.external);
    assert_eq!(raw.compression, ChunkCompression::Zlib);
    assert_eq!(
        region.read_chunk(0, 0).unwrap().unwrap().get_string("Status").unwrap(),
        "minecraft:full"
    );
}

#[test]
fn broken_headers_are_rejected() {
    let vectors = [
        "bad_offset",
        "overlapping_sectors",
        "unaligned_length",
        "offset_out_of_file",
    ];

    for vector in vectors {
        // RegionFile は Debug を実装していないため、unwrap_err ではなく match で受ける
        match RegionFile::open(vector_dir(vector).join("r.0.0.mca"), RegionFileMode::ReadOnly) {
            Ok(_) => panic!("{vector}: エラーになるはずが成功した"),
            Err(error) => assert_eq!(error.code(), ErrorCode::MalformedData, "{vector}"),
        }
    }
}

#[test]
fn chunk_outside_the_region_is_rejected() {
    let region =
        RegionFile::open(vector_dir("empty").join("r.0.0.mca"), RegionFileMode::ReadOnly).unwrap();

    // r.0.0 が担当するのは 0..31 の範囲だけ
    assert_eq!(
        region.has_chunk(32, 0).unwrap_err().code(),
        ErrorCode::InvalidArgument
    );
}

#[test]
fn read_only_region_rejects_writes() {
    let mut region =
        RegionFile::open(vector_dir("empty").join("r.0.0.mca"), RegionFileMode::ReadOnly).unwrap();

    let error = region
        .write_chunk(0, 0, &sample_chunk(0, 0), ChunkCompression::Zlib)
        .unwrap_err();
    assert_eq!(error.code(), ErrorCode::InvalidArgument);
}

// ---------------------------------------------------------------------------
// 書き込み
// ---------------------------------------------------------------------------

#[test]
fn opening_and_flushing_without_changes_keeps_bytes_identical() {
    // 触っていないチャンクの配置を保つことが、既存ワールドを壊さない前提になる
    let work = WorkDir::new("noop");
    let path = work.copy_vector("fragmented").join("r.0.0.mca");
    let original = std::fs::read(&path).unwrap();

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    assert_eq!(std::fs::read(&path).unwrap(), original);
}

#[test]
fn writes_and_reads_back_a_chunk() {
    let work = WorkDir::new("write");
    let path = work.join("r.0.0.mca");

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region
            .write_chunk(3, 4, &sample_chunk(3, 4), ChunkCompression::Zlib)
            .unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
    assert!(reopened.has_chunk(3, 4).unwrap());
    assert_eq!(
        reopened.read_chunk(3, 4).unwrap().unwrap().get_int("xPos").unwrap(),
        3
    );

    // 書き出したファイルは必ずセクタ境界に揃う
    assert_eq!(file_len(&path) % SECTOR_SIZE as u64, 0);
}

#[test]
fn rewriting_the_same_size_keeps_the_chunk_in_place() {
    let work = WorkDir::new("inplace");
    let path = work.copy_vector("fragmented").join("r.0.0.mca");
    let original_length = file_len(&path);

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        // 同じ内容を書き直すので、必要セクタ数は変わらない
        let chunk = region.read_chunk(0, 0).unwrap().unwrap();
        region
            .write_chunk(0, 0, &chunk, ChunkCompression::Zlib)
            .unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    // その場で上書きされるので、ファイルは伸びない
    assert_eq!(file_len(&path), original_length);

    let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
    assert_eq!(reopened.chunk_positions().unwrap().len(), 3);
}

#[test]
fn growing_chunk_is_relocated_without_breaking_others() {
    let work = WorkDir::new("grow");
    let path = work.copy_vector("fragmented").join("r.0.0.mca");

    // 5 セクタぶんになる大きなチャンクを作る
    let mut big = sample_chunk(0, 0);
    big.set("filler", NbtTag::ByteArray(incompressible(5 * SECTOR_SIZE)));

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region.write_chunk(0, 0, &big, ChunkCompression::Zlib).unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();

    // 動かした結果、他の 2 チャンクが壊れていないこと
    assert_eq!(reopened.chunk_positions().unwrap().len(), 3);
    assert_eq!(
        reopened.read_chunk(5, 3).unwrap().unwrap().get_int("xPos").unwrap(),
        5
    );
    assert_eq!(
        reopened.read_chunk(31, 31).unwrap().unwrap().get_int("xPos").unwrap(),
        31
    );
    assert_eq!(
        reopened
            .read_chunk(0, 0)
            .unwrap()
            .unwrap()
            .get_byte_array("filler")
            .unwrap()
            .len(),
        5 * SECTOR_SIZE
    );
}

#[test]
fn deleted_chunk_disappears_and_others_survive() {
    let work = WorkDir::new("delete");
    let path = work.copy_vector("fragmented").join("r.0.0.mca");

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        assert!(region.delete_chunk(5, 3).unwrap());
        assert!(!region.delete_chunk(5, 3).unwrap());
        region.flush().unwrap();
        region.close().unwrap();
    }

    let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
    assert!(!reopened.has_chunk(5, 3).unwrap());
    assert_eq!(reopened.timestamp(5, 3).unwrap(), 0);
    assert_eq!(reopened.chunk_positions().unwrap().len(), 2);
}

#[test]
fn freed_sectors_are_reused() {
    let work = WorkDir::new("reuse");
    let path = work.copy_vector("fragmented").join("r.0.0.mca");
    let original_length = file_len(&path);

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region.delete_chunk(5, 3).unwrap();
        region
            .write_chunk(7, 7, &sample_chunk(7, 7), ChunkCompression::Zlib)
            .unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    // 空いたセクタへ収まるので、ファイルは伸びない
    assert_eq!(file_len(&path), original_length);

    let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
    assert_eq!(
        reopened.read_chunk(7, 7).unwrap().unwrap().get_int("xPos").unwrap(),
        7
    );
}

#[test]
fn optimize_compacts_the_file() {
    let work = WorkDir::new("optimize");
    let path = work.copy_vector("fragmented").join("r.0.0.mca");
    let original_length = file_len(&path);

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region.optimize().unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    let optimized_length = file_len(&path);

    // 隙間が詰まるぶん小さくなる
    assert!(
        optimized_length < original_length,
        "詰め直しても縮んでいない: {original_length} -> {optimized_length}"
    );
    assert_eq!(optimized_length % SECTOR_SIZE as u64, 0);

    let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
    assert_eq!(reopened.chunk_positions().unwrap().len(), 3);
    assert_eq!(reopened.timestamp(0, 0).unwrap(), 1700000000);
    assert_eq!(
        reopened.read_chunk(31, 31).unwrap().unwrap().get_int("xPos").unwrap(),
        31
    );
}

#[test]
fn huge_chunk_goes_to_external_file_and_comes_back() {
    let work = WorkDir::new("mcc");
    let path = work.join("r.0.0.mca");

    // 1MiB を超えるよう、圧縮の効かないデータを詰める
    let mut huge = sample_chunk(1, 2);
    huge.set("filler", NbtTag::ByteArray(incompressible(1200 * 1024)));

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region.write_chunk(1, 2, &huge, ChunkCompression::None).unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    let external = work.join("c.1.2.mcc");
    assert!(external.exists(), "外部ファイルへ退避されていない");

    {
        let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
        assert!(reopened.read_chunk_raw(1, 2).unwrap().unwrap().external);
        assert_eq!(
            reopened
                .read_chunk(1, 2)
                .unwrap()
                .unwrap()
                .get_byte_array("filler")
                .unwrap()
                .len(),
            1200 * 1024
        );
    }

    // 小さく書き直すと内部へ戻り、外部ファイルは消える
    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region
            .write_chunk(1, 2, &sample_chunk(1, 2), ChunkCompression::Zlib)
            .unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    assert!(!external.exists(), "内部へ戻ったのに外部ファイルが残っている");

    let final_region = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
    assert!(!final_region.read_chunk_raw(1, 2).unwrap().unwrap().external);
}

#[test]
fn timestamp_can_be_set_explicitly() {
    let work = WorkDir::new("timestamp");
    let path = work.join("r.0.0.mca");

    {
        let mut region = RegionFile::open(&path, RegionFileMode::ReadWrite).unwrap();
        region
            .write_chunk(0, 0, &sample_chunk(0, 0), ChunkCompression::Zlib)
            .unwrap();
        region.set_timestamp(0, 0, 1234567890).unwrap();
        region.flush().unwrap();
        region.close().unwrap();
    }

    let reopened = RegionFile::open(&path, RegionFileMode::ReadOnly).unwrap();
    assert_eq!(reopened.timestamp(0, 0).unwrap(), 1234567890);
}

// ---------------------------------------------------------------------------
// RegionFolder
// ---------------------------------------------------------------------------

#[test]
fn folder_resolves_chunks_across_regions() {
    let work = WorkDir::new("folder");

    {
        let mut folder = RegionFolder::open(&work.path, RegionFileMode::ReadWrite).unwrap();
        folder
            .write_chunk(0, 0, &sample_chunk(0, 0), ChunkCompression::Zlib)
            .unwrap();
        folder
            .write_chunk(-1, -1, &sample_chunk(-1, -1), ChunkCompression::Zlib)
            .unwrap();
        folder
            .write_chunk(40, 40, &sample_chunk(40, 40), ChunkCompression::Zlib)
            .unwrap();
        folder.flush().unwrap();
        folder.close().unwrap();
    }

    // 3 つの異なるリージョンへ振り分けられる
    for name in ["r.0.0.mca", "r.-1.-1.mca", "r.1.1.mca"] {
        assert!(work.join(name).exists(), "{name} が作られていない");
    }

    let mut reopened = RegionFolder::open(&work.path, RegionFileMode::ReadOnly).unwrap();
    assert_eq!(reopened.region_positions().unwrap().len(), 3);
    assert_eq!(reopened.chunk_positions().unwrap().len(), 3);
    assert_eq!(
        reopened
            .read_chunk(-1, -1)
            .unwrap()
            .unwrap()
            .get_int("xPos")
            .unwrap(),
        -1
    );
    assert!(reopened.read_chunk(100, 100).unwrap().is_none());
    assert!(!reopened.has_chunk(100, 100).unwrap());
}

#[test]
fn キャッシュ上限を超えると古いリージョンから閉じる() {
    let work = WorkDir::new("lru");

    // 上限 2 で 4 リージョンへ書く。古いものは閉じられるが内容は失われない
    {
        let mut folder =
            RegionFolder::open_with_limit(&work.path, RegionFileMode::ReadWrite, 2).unwrap();

        for region in 0..4i32 {
            folder
                .write_chunk(
                    region * 32,
                    0,
                    &sample_chunk(region * 32, 0),
                    ChunkCompression::Zlib,
                )
                .unwrap();
            assert!(folder.cached_region_count() <= 2);
        }

        folder.flush().unwrap();
        folder.close().unwrap();
    }

    // 追い出されたリージョンも、書き出されてから閉じられている
    let mut reopened = RegionFolder::open(&work.path, RegionFileMode::ReadOnly).unwrap();
    assert_eq!(4, reopened.region_positions().unwrap().len());

    for region in 0..4i32 {
        let chunk = reopened.read_chunk(region * 32, 0).unwrap().expect("チャンクが無い");
        assert_eq!(region * 32, chunk.get_int("xPos").unwrap());
    }
}

#[test]
fn キャッシュ上限が0ならinvalid_argument() {
    let work = WorkDir::new("lru-limit");

    match RegionFolder::open_with_limit(&work.path, RegionFileMode::ReadOnly, 0) {
        Ok(_) => panic!("開けてしまった"),
        Err(error) => assert_eq!(ErrorCode::InvalidArgument, error.code()),
    }
}
