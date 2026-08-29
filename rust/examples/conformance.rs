//! 適合性検証ツール。4言語すべてが同じインターフェースで同じ出力を出す。
//!
//! `spec/run-conformance.sh` がこのツールを4言語ぶん起動し、
//! 出力を相互に diff することで「4言語が同一に振る舞う」ことを機械的に確かめる。
//!
//! 仕様: `docs/spec/90-conformance.md` 2.3章

use std::process::ExitCode;

use spring_nbt_library::anvil::{ChunkCompression, RegionFile, RegionFileMode};
use spring_nbt_library::error::Result;
use spring_nbt_library::world::{
    BlockState, Chunk, ChunkReadOptions, ChunkWriteOptions, VersionMismatchAction,
};
use spring_nbt_library::nbt::snbt;
use spring_nbt_library::nbt::tag::{NbtCompound, NbtTag};
use spring_nbt_library::nbt::{
    read_file, write_bytes, Compression, NamedTag, NbtFormat, NbtReadOptions, NbtWriteOptions,
};
use spring_nbt_library::TARGET_DATA_VERSION;

const USAGE: &str = "\
使い方:
  conformance decode  <入力パス> <出力JSONパス> [--format network]
  conformance encode  <入力パス> <出力バイナリパス> [--format network]
  conformance snbt    <入力パス> <出力SNBTパス> [--format network]
  conformance region-list    <入力mcaパス> <出力テキストパス>
  conformance region-rewrite <入力mcaパス> <出力mcaパス>
  conformance chunk-report   <入力チャンクnbt> <出力テキストパス>
  conformance chunk-edit     <入力チャンクnbt> <出力nbtパス>
  conformance version";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();

    if args.is_empty() {
        eprintln!("{USAGE}");
        return ExitCode::from(2);
    }

    match args[0].as_str() {
        "version" => {
            print!("rust spring-nbt-library 0.1.0 target_data_version={TARGET_DATA_VERSION}\n");
            ExitCode::SUCCESS
        }
        "decode" | "encode" | "snbt" | "region-list" | "region-rewrite" | "chunk-report"
        | "chunk-edit" => match run(&args) {
            Ok(code) => code,
            Err(error) => {
                // 4言語で同じ ErrorCode を出すことが検証対象なので、コードを機械可読な形で出す
                eprint!("ERROR {} {}\n", error.code().as_str(), error.message());
                ExitCode::FAILURE
            }
        },
        _ => {
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
    }
}

fn run(args: &[String]) -> Result<ExitCode> {
    if args.len() < 3 {
        eprintln!("{USAGE}");
        return Ok(ExitCode::from(2));
    }

    // チャンク系は World 層を通す
    if args[0] == "chunk-report" || args[0] == "chunk-edit" {
        let mut chunk = read_chunk_file(&args[1])?;

        if args[0] == "chunk-report" {
            std::fs::write(&args[2], chunk_describe(&chunk)?)?;
        } else {
            chunk_edit(&mut chunk)?;
            let named = NamedTag::new("", chunk.to_nbt(&ChunkWriteOptions::default())?);
            std::fs::write(&args[2], write_bytes(&named, &NbtWriteOptions::uncompressed())?)?;
        }

        return Ok(ExitCode::SUCCESS);
    }

    // リージョン系は NBT の読み込みを経由しない
    if args[0] == "region-list" || args[0] == "region-rewrite" {
        let mut region = RegionFile::open(&args[1], RegionFileMode::ReadOnly)?;

        if args[0] == "region-list" {
            std::fs::write(&args[2], region_list(&region)?)?;
        } else {
            region_rewrite(&region, &args[2])?;
        }

        region.close()?;
        return Ok(ExitCode::SUCCESS);
    }

    let format = parse_format(args);
    let read_options = NbtReadOptions { format, ..NbtReadOptions::default() };
    let named = read_file(&args[1], &read_options)?;

    match args[0].as_str() {
        "decode" => {
            std::fs::write(&args[2], normalized_json(&named, format))?;
        }
        "encode" => {
            let write_options = NbtWriteOptions { format, compression: Compression::None };
            std::fs::write(&args[2], write_bytes(&named, &write_options)?)?;
        }
        _ => {
            let tag = NbtTag::Compound(named.tag.clone());
            std::fs::write(&args[2], snbt::write(&tag) + "\n")?;
        }
    }

    Ok(ExitCode::SUCCESS)
}

/// `--format network` が指定されていればネットワーク形式として読む。
fn parse_format(args: &[String]) -> NbtFormat {
    // 3 番目以降の引数からオプションを探す
    for index in 3..args.len().saturating_sub(1) {
        if args[index] == "--format" && args[index + 1] == "network" {
            return NbtFormat::Network;
        }
    }

    NbtFormat::Java
}



// ---------------------------------------------------------------------------
// チャンク（World レイヤ）
//
// 仕様: docs/spec/90-conformance.md 2.3章
// ---------------------------------------------------------------------------

/// チャンク NBT のファイルを読む。
fn read_chunk_file(path: &str) -> Result<Chunk> {
    let named = read_file(path, &NbtReadOptions::default())?;

    // 検証では DataVersion の違いを警告にせず、そのまま読む
    let options = ChunkReadOptions {
        on_version_mismatch: VersionMismatchAction::Ignore,
        ..ChunkReadOptions::default()
    };
    Chunk::from_nbt(named.tag, &options)
}

/// チャンクの全ブロック・全バイオームを走査して集計する。
///
/// パレットとビットストレージを端から端まで通すので、
/// ビット詰めの実装が 1 か所でもずれれば集計値が変わる。
fn chunk_describe(chunk: &Chunk) -> Result<String> {
    let mut out = format!(
        "chunk {} {} {} {}\n",
        chunk.x()?,
        chunk.z()?,
        chunk.min_section_y()?,
        chunk.status()?
    );

    let mut blocks: std::collections::BTreeMap<String, usize> = std::collections::BTreeMap::new();
    let mut biomes: std::collections::BTreeMap<String, usize> = std::collections::BTreeMap::new();

    for section_y in chunk.section_ys() {
        let section = match chunk.section(section_y) {
            Some(section) => section,
            None => continue,
        };

        let mut block_palette = 0usize;
        let mut biome_palette = 0usize;
        let mut block_bits = 0usize;
        let mut biome_bits = 0usize;

        if let Some(container) = section.block_states() {
            block_palette = container.palette().len();
            block_bits = container.bits_per_entry();
        }

        if let Some(container) = section.biomes() {
            biome_palette = container.palette().len();
            biome_bits = container.bits_per_entry();
        }

        out.push_str(&format!(
            "section {section_y} {block_palette} {block_bits} {biome_palette} {biome_bits}\n"
        ));

        // 全ブロックを 1 つずつ読んで、状態の文字列表現ごとに数える
        for y in 0..16 {
            for z in 0..16 {
                for x in 0..16 {
                    if let Some(block) = chunk.get_block(x, (section_y * 16) + y, z)? {
                        *blocks.entry(block.to_string()).or_insert(0) += 1;
                    }
                }
            }
        }

        // バイオームは 4×4×4 単位なので、4 ブロックおきに見る
        for y in (0..16).step_by(4) {
            for z in (0..16).step_by(4) {
                for x in (0..16).step_by(4) {
                    if let Some(biome) = chunk.get_biome(x, (section_y * 16) + y, z)? {
                        *biomes.entry(biome).or_insert(0) += 1;
                    }
                }
            }
        }
    }

    // 名前の昇順で出すので、内部の並びに関係なく同じ出力になる
    for (key, count) in &blocks {
        out.push_str(&format!("block {key} {count}\n"));
    }

    for (key, count) in &biomes {
        out.push_str(&format!("biome {key} {count}\n"));
    }

    Ok(out)
}

/// 決まった手順でチャンクを編集する。全言語で同じ結果になるはず。
///
/// パレット拡張・ビット幅の再計算・未使用要素の掃除を一通り通す。
fn chunk_edit(chunk: &mut Chunk) -> Result<()> {
    let base_y = chunk.min_section_y()? * 16;

    // パレットに無いブロックを次々に置き、ビット幅の拡張を起こす
    for index in 0..20i32 {
        let state = BlockState::parse(&format!("minecraft:edited_{index}[step={index}]"))?;
        chunk.set_block(index % 16, base_y + (index / 16), index % 16, &state)?;
    }

    // プロパティ付きのブロックを、名前は同じで状態違いで置く
    chunk.set_block(1, base_y + 2, 1, &BlockState::parse("minecraft:oak_stairs[facing=north,half=top]")?)?;
    chunk.set_block(2, base_y + 2, 2, &BlockState::parse("minecraft:oak_stairs[half=top,facing=north]")?)?;
    chunk.set_block(3, base_y + 2, 3, &BlockState::parse("oak_stairs[facing=south]")?)?;

    // バイオームも書き換える
    chunk.set_biome(0, base_y, 0, "minecraft:desert")?;
    chunk.set_biome(8, base_y + 8, 8, "minecraft:jungle")?;

    // 使われなくなったパレット要素を掃除する
    chunk.compact()?;

    // 高さマップと光源は再計算しないので、無効化して Minecraft に任せる
    chunk.clear_heightmaps();
    chunk.invalidate_lighting();
    Ok(())
}

// ---------------------------------------------------------------------------
// リージョンファイル
//
// 仕様: docs/spec/90-conformance.md 2.3章
// ---------------------------------------------------------------------------

/// 存在するチャンクを 1 行 1 チャンクで書き出す。並びはロケーションテーブルの添字順。
///
/// 各行は「絶対X 絶対Z タイムスタンプ 圧縮方式 圧縮後バイト数 展開後バイト数 キー数」。
fn region_list(region: &RegionFile) -> Result<String> {
    let mut out = format!("region {} {}\n", region.region_x(), region.region_z());
    let mut total = 0usize;

    for position in region.chunk_positions()? {
        let raw = match region.read_chunk_raw(position.x, position.z)? {
            Some(value) => value,
            None => continue,
        };

        let chunk = region.read_chunk(position.x, position.z)?;
        let mut key_count = 0usize;
        let mut plain_length = 0usize;

        if let Some(tag) = chunk {
            key_count = tag.len();
            let named = NamedTag::new("", tag);
            plain_length = write_bytes(&named, &NbtWriteOptions::uncompressed())?.len();
        }

        out.push_str(&format!(
            "{} {} {} {} {} {} {}\n",
            position.x,
            position.z,
            region.timestamp(position.x, position.z)?,
            raw.compression.as_str(),
            raw.data.len(),
            plain_length,
            key_count
        ));
        total += 1;
    }

    out.push_str(&format!("total {total}\n"));
    Ok(out)
}

/// 全チャンクを読み直し、無圧縮で新しいリージョンへ詰め直して書き出す。
///
/// 無圧縮にするのは、zlib の出力が処理系ごとに違い、
/// 圧縮したままでは言語間でバイトが一致しないため。
fn region_rewrite(source: &RegionFile, output_path: &str) -> Result<()> {
    // 途中結果が残らないよう、書き出し先は必ず作り直す
    if std::path::Path::new(output_path).exists() {
        std::fs::remove_file(output_path)?;
    }

    let mut destination = RegionFile::open(output_path, RegionFileMode::ReadWrite)?;

    for position in source.chunk_positions()? {
        let chunk = match source.read_chunk(position.x, position.z)? {
            Some(value) => value,
            None => continue,
        };

        destination.write_chunk(position.x, position.z, &chunk, ChunkCompression::None)?;
        destination.set_timestamp(
            position.x,
            position.z,
            source.timestamp(position.x, position.z)?,
        )?;
    }

    destination.flush()?;
    destination.close()
}

// ---------------------------------------------------------------------------
// 正規化JSON
//
// 浮動小数点をビットパターンで、64bit 整数を10進文字列で表すのが要。
// 10進表記の丸めや JSON 数値の精度は処理系ごとに差が出るため、
// そのまま出すと4言語の出力が一致しない。
//
// 仕様: docs/spec/00-conventions.md 6章
// ---------------------------------------------------------------------------

fn normalized_json(named: &NamedTag, format: NbtFormat) -> String {
    let format_name = match format {
        NbtFormat::Network => "network",
        NbtFormat::Java => "java",
    };

    let mut out = String::from("{\"format\":");
    append_ascii(&mut out, format_name);
    out.push_str(",\"root_name\":");
    append_string(&mut out, &named.name.encode_utf16().collect::<Vec<u16>>());
    out.push_str(",\"root\":");
    append_tag(&mut out, &NbtTag::Compound(named.tag.clone()));
    out.push_str("}\n");
    out
}

fn append_tag(out: &mut String, tag: &NbtTag) {
    out.push_str("{\"type\":");
    append_ascii(out, tag.tag_type().as_str());

    // list だけは value の前に element_type が入る（仕様が定めるキー順）
    if let NbtTag::List(list) = tag {
        out.push_str(",\"element_type\":");
        append_ascii(out, list.element_type().as_str());
    }

    out.push_str(",\"value\":");

    match tag {
        NbtTag::Byte(value) => out.push_str(&value.to_string()),
        NbtTag::Short(value) => out.push_str(&value.to_string()),
        NbtTag::Int(value) => out.push_str(&value.to_string()),
        // 64bit 整数は JSON 数値だと処理系によって精度が落ちるため10進文字列で表す
        NbtTag::Long(value) => append_ascii(out, &value.to_string()),
        NbtTag::Float(value) => append_ascii(out, &format!("0x{:08x}", value.to_bits())),
        NbtTag::Double(value) => append_ascii(out, &format!("0x{:016x}", value.to_bits())),
        NbtTag::String(value) => {
            append_string(out, &value.to_utf16());

            // MUTF-8 のバイト列も併記する。孤立サロゲートなど UTF-8 に写せない値を厳密に比較するため
            out.push_str(",\"mutf8\":");
            append_ascii(out, &to_hex(&value.to_mutf8()));
        }
        NbtTag::ByteArray(values) => append_number_array(out, values),
        NbtTag::IntArray(values) => append_number_array(out, values),
        NbtTag::LongArray(values) => {
            // 64bit 整数は10進文字列の配列で表す
            out.push('[');

            for (index, value) in values.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }

                append_ascii(out, &value.to_string());
            }

            out.push(']');
        }
        NbtTag::List(list) => {
            out.push('[');

            for (index, item) in list.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }

                append_tag(out, item);
            }

            out.push(']');
        }
        NbtTag::Compound(compound) => append_compound(out, compound),
    }

    out.push('}');
}

fn append_compound(out: &mut String, compound: &NbtCompound) {
    // JSON オブジェクトだと挿入順の保持が処理系依存になるため、組の配列で表す
    out.push('[');

    for (index, (key, value)) in compound.iter().enumerate() {
        if index > 0 {
            out.push(',');
        }

        out.push('[');
        append_string(out, &key.encode_utf16().collect::<Vec<u16>>());
        out.push(',');
        append_tag(out, value);
        out.push(']');
    }

    out.push(']');
}

fn append_number_array<T: std::fmt::Display>(out: &mut String, values: &[T]) {
    out.push('[');

    for (index, value) in values.iter().enumerate() {
        if index > 0 {
            out.push(',');
        }

        out.push_str(&value.to_string());
    }

    out.push(']');
}

fn to_hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);

    for value in bytes {
        out.push_str(&format!("{value:02x}"));
    }

    out
}

/// ASCII だけの文字列を JSON 文字列として書く。
fn append_ascii(out: &mut String, text: &str) {
    append_string(out, &text.encode_utf16().collect::<Vec<u16>>());
}

/// JSON 文字列を書き出す。非 ASCII は必ず `\uXXXX` へ逃がす。
///
/// エスケープの単位は UTF-16 コード単位。
/// C# / Java と桁数を揃えるため、補助文字はサロゲートペアの 2 つに分けて出す。
fn append_string(out: &mut String, units: &[u16]) {
    out.push('"');

    for unit in units {
        match *unit {
            0x22 => out.push_str("\\\""),
            0x5C => out.push_str("\\\\"),
            0x08 => out.push_str("\\b"),
            0x0C => out.push_str("\\f"),
            0x0A => out.push_str("\\n"),
            0x0D => out.push_str("\\r"),
            0x09 => out.push_str("\\t"),
            value => {
                // ASCII の印字可能文字だけ生で出し、それ以外は \uXXXX にする
                if (0x20..=0x7E).contains(&value) {
                    out.push(value as u8 as char);
                } else {
                    out.push_str(&format!("\\u{value:04x}"));
                }
            }
        }
    }

    out.push('"');
}
