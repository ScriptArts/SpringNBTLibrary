//! ワールドの構成の世代
//! ライブラリの内部だけで使う
//!
//! 世代ごとの違いはこの表に集める
//! ワールドと`level.dat`の読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない

use std::path::{Path, PathBuf};

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::NbtCompound;

use super::chunk_format::OLDEST_FORMAT_DATA_VERSION;

/// L2（26.1以降）が始まるDataVersion
pub(crate) const L2_MIN_DATA_VERSION: i32 = 4786;

/// 標準の次元のIDと、L1でのワールド直下からの相対ディレクトリ
/// 並びがL1の`dimension_ids`の並びになる
const L1_STANDARD_DIMENSIONS: [(&str, &str); 3] = [
    ("minecraft:overworld", ""),
    ("minecraft:the_nether", "DIM-1"),
    ("minecraft:the_end", "DIM1"),
];

/// L1の`Difficulty`の数値に対応する名前
const L1_DIFFICULTIES: [&str; 4] = ["peaceful", "easy", "normal", "hard"];

/// ワールドの構成の世代1つ分
#[derive(Debug)]
pub(crate) struct WorldLayout {
    /// この世代が始まるDataVersion
    #[allow(dead_code)]
    pub(crate) min_data_version: i32,
    /// 標準の次元が直下と`DIM-1/` `DIM1/`に置かれ、`level.dat`にスポーンなどが直に入る構成か
    legacy: bool,
    /// ワールド直下からプレイヤーデータのフォルダまでの道
    player_folder: &'static [&'static str],
    /// 次元のフォルダから付随データのフォルダまでの道
    data_folder: &'static [&'static str],
}

/// L1: 1.13〜1.21.x
static L1: WorldLayout = WorldLayout {
    min_data_version: OLDEST_FORMAT_DATA_VERSION,
    legacy: true,
    player_folder: &["playerdata"],
    data_folder: &["data"],
};

/// L2: 26.1以降
static L2: WorldLayout = WorldLayout {
    min_data_version: L2_MIN_DATA_VERSION,
    legacy: false,
    player_folder: &["players", "data"],
    data_folder: &["data", "minecraft"],
};

impl WorldLayout {
    /// DataVersionから世代を引く
    /// L1より古い値もL1として扱う
    pub(crate) fn for_data_version(data_version: i32) -> &'static WorldLayout {
        // 境界以上ならL2、それ未満はL1
        if data_version >= L2_MIN_DATA_VERSION {
            return &L2;
        }

        &L1
    }

    /// `level.dat`の`Data`と、利用者の指定から世代を決める
    ///
    /// 指定があればそれを使い、無ければ`Data.DataVersion`で決める
    /// `DataVersion`が無い古いワールドはL1として扱う
    ///
    /// 指定が扱える下限より小さい場合は`InvalidArgument`
    pub(crate) fn detect(data: &NbtCompound, requested: Option<i32>) -> Result<&'static WorldLayout> {
        if let Some(value) = requested {
            // 指定は下限より小さいと解釈のしようがない
            if value < OLDEST_FORMAT_DATA_VERSION {
                return Err(Error::new(
                    ErrorCode::InvalidArgument,
                    format!(
                        "世代を選ぶDataVersionは{OLDEST_FORMAT_DATA_VERSION}以上でなければならない: {value}"
                    ),
                ));
            }

            return Ok(WorldLayout::for_data_version(value));
        }

        // DataVersionが無いのは1.9より前のワールドなのでL1
        match data.opt_int("DataVersion")? {
            Some(found) => Ok(WorldLayout::for_data_version(found)),
            None => Ok(&L1),
        }
    }

    /// 次元のフォルダのパス
    /// 次元のIDは名前空間つきで渡す
    pub(crate) fn dimension_directory(&self, world_directory: &Path, dimension_id: &str) -> PathBuf {
        // L1の標準の次元は、ワールド直下かDIM-1/ DIM1/に置かれる
        if self.legacy {
            for (standard_id, relative) in L1_STANDARD_DIMENSIONS {
                // 標準の次元ならその専用の場所を返す
                if dimension_id == standard_id {
                    // オーバーワールドはワールドのフォルダそのもの
                    if relative.is_empty() {
                        return world_directory.to_path_buf();
                    }

                    return world_directory.join(relative);
                }
            }
        }

        let colon = dimension_id.find(':').unwrap_or(0);
        world_directory
            .join("dimensions")
            .join(&dimension_id[..colon])
            .join(&dimension_id[colon + 1..])
    }

    /// 次元が存在するか
    pub(crate) fn has_dimension(&self, world_directory: &Path, dimension_id: &str) -> bool {
        let directory = self.dimension_directory(world_directory, dimension_id);

        // L1のオーバーワールドはワールド直下なので、region/の有無で判断する
        if self.legacy && dimension_id == L1_STANDARD_DIMENSIONS[0].0 {
            return directory.join("region").is_dir();
        }

        directory.is_dir()
    }

    /// 存在する次元のIDを返す
    /// L1では標準の3つを固定の順に並べ、そのあとにデータパックの次元をIDの順に並べる
    pub(crate) fn dimension_ids(&self, world_directory: &Path) -> Result<Vec<String>> {
        let mut found: Vec<String> = Vec::new();

        // L1の標準の次元は固定の順で先に並べる
        if self.legacy {
            for (standard_id, _) in L1_STANDARD_DIMENSIONS {
                // 存在する標準の次元だけを数える
                if self.has_dimension(world_directory, standard_id) {
                    found.push(standard_id.to_string());
                }
            }
        }

        let mut extra: Vec<String> = Vec::new();
        let root = world_directory.join("dimensions");

        if root.is_dir() {
            // dimensions/<名前空間>/<パス>/の2段を辿る
            for namespace in std::fs::read_dir(&root)?.flatten() {
                if !namespace.path().is_dir() {
                    continue;
                }

                let namespace_name = namespace.file_name().to_string_lossy().into_owned();

                // 2段目が次元のパス
                for entry in std::fs::read_dir(namespace.path())?.flatten() {
                    let dimension_id =
                        format!("{namespace_name}:{}", entry.file_name().to_string_lossy());

                    // ディレクトリだけを次元として数える
                    // L1では標準の次元をdimensions/の下からは探さない
                    if entry.path().is_dir() && !(self.legacy && found.contains(&dimension_id)) {
                        extra.push(dimension_id);
                    }
                }
            }
        }

        // 走査順がファイルシステム依存にならないよう並べる
        extra.sort();
        found.extend(extra);
        Ok(found)
    }

    /// プレイヤーデータのフォルダのパス
    pub(crate) fn player_directory(&self, world_directory: &Path) -> PathBuf {
        let mut result = world_directory.to_path_buf();

        // フォルダの道を1段ずつ辿る
        for part in self.player_folder {
            result.push(part);
        }

        result
    }

    /// 次元のフォルダの下の付随データのファイルのパス
    pub(crate) fn data_file_path(&self, dimension_directory: &Path, name: &str) -> PathBuf {
        let mut result = dimension_directory.to_path_buf();

        // フォルダの道を1段ずつ辿る
        for part in self.data_folder {
            result.push(part);
        }

        result.push(format!("{name}.dat"));
        result
    }

    /// スポーン地点の`[x, y, z]`
    pub(crate) fn spawn_pos(&self, data: &NbtCompound) -> Result<Vec<i32>> {
        // L1は3つの整数に分かれて入っている
        if self.legacy {
            return Ok(vec![
                data.get_int("SpawnX")?,
                data.get_int("SpawnY")?,
                data.get_int("SpawnZ")?,
            ]);
        }

        Ok(data.get_compound("spawn")?.get_int_array("pos")?.to_vec())
    }

    /// スポーン地点の次元ID
    ///
    /// この世代の`level.dat`に無い場合は`UnsupportedFeature`
    pub(crate) fn spawn_dimension<'a>(&self, data: &'a NbtCompound) -> Result<&'a str> {
        // L1にはスポーン地点の次元を持つキーが無い
        if self.legacy {
            return Err(Error::new(
                ErrorCode::UnsupportedFeature,
                "26.1より前のlevel.datにはスポーン地点の次元が無い",
            ));
        }

        data.get_compound("spawn")?.get_string("dimension")
    }

    /// 難易度（`normal`など）
    ///
    /// 数値が0〜3の外の場合は`MalformedData`
    pub(crate) fn difficulty<'a>(&self, data: &'a NbtCompound) -> Result<&'a str> {
        // L1は0〜3の数値で入っている
        if self.legacy {
            let number = data.get_byte("Difficulty")?;

            // 負の値は符号なしに直すと大きな数になり、表の外として弾かれる
            return match L1_DIFFICULTIES.get(number as u8 as usize) {
                Some(name) => Ok(name),
                _ => Err(Error::new(
                    ErrorCode::MalformedData,
                    format!("Difficultyが0〜3の外: {number}"),
                )),
            };
        }

        data.get_compound("difficulty_settings")?.get_string("difficulty")
    }

    /// ハードコアか
    pub(crate) fn is_hardcore(&self, data: &NbtCompound) -> Result<bool> {
        // L1はDataの直下に入っている
        if self.legacy {
            return data.get_bool("hardcore");
        }

        data.get_compound("difficulty_settings")?.get_bool("hardcore")
    }
}
