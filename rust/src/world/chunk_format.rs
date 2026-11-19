//! チャンクの形式の世代
//! ライブラリの内部だけで使う
//!
//! 世代ごとの違いはこの表に集める
//! チャンクの読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない

/// ブロックのパレット要素が`id` / `properties`の形式になるDataVersion（26.3）
/// これ未満は`Name` / `Properties`の形式
pub(crate) const PALETTE_ID_FORMAT_DATA_VERSION: i32 = 5006;

/// DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版）
pub(crate) const OLDEST_FORMAT_DATA_VERSION: i32 = 1519;

/// ルートの直下に置かれる、ブロックに紐づく付随データのキー（1.18以降）
const ROOT_BLOCK_DATA_KEYS: [&str; 3] = ["block_entities", "block_ticks", "fluid_ticks"];

/// `Level`の中に置かれる、ブロックに紐づく付随データのキー（1.17まで）
const LEVEL_BLOCK_DATA_KEYS: [&str; 3] = ["TileEntities", "TileTicks", "LiquidTicks"];

/// セクションのブロックの持ち方
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BlockStorage {
    /// セクションの`block_states`にあるパレット付きコンテナ（`palette` / `data`）
    /// パレットが1要素なら`data`を持たない
    Container,
    /// セクションの直下の`Palette`と`BlockStates`
    /// `BlockStates`はパレットが1要素でも必ずある
    SectionPalette,
}

/// バイオームの持ち方
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BiomeStorage {
    /// セクションごとのパレット付きコンテナ
    Paletted,
    /// チャンクの列ごとの数値のバイオームID（`int[256]`）
    // 1.14までの世代を表に足したときに使う
    #[allow(dead_code)]
    Ids2D,
    /// 4×4×4ブロックごとの数値のバイオームID（`int[1024]`）
    Ids3D,
}

/// チャンクの形式の世代1つ分
#[derive(Debug)]
pub(crate) struct ChunkFormat {
    /// この世代が始まるDataVersion
    pub(crate) min_data_version: i32,
    /// チャンクの本体が`Level`の中にあるか
    pub(crate) wrapped_in_level: bool,
    /// セクションの一覧のキー
    pub(crate) sections_key: &'static str,
    /// パレットの要素と`BlockState`の変換に渡すDataVersion
    pub(crate) palette_data_version: i32,
    /// ビット詰めで値が64bitの境目をまたぐか
    pub(crate) spanning_bit_storage: bool,
    /// セクションのブロックの持ち方
    pub(crate) block_storage: BlockStorage,
    /// バイオームの持ち方
    pub(crate) biome_storage: BiomeStorage,
    /// ブロックを置き換えたときに取り除く付随データのキー
    pub(crate) block_data_keys: [&'static str; 3],
    /// ルートに最下段セクションのY位置（`yPos`）があるか
    /// 無い世代では、セクションは0段目から始まる
    pub(crate) has_y_pos: bool,
    /// `isLightOn`の無いチャンクで光源を無効化するとき、`isLightOn`を書き足すか
    /// 1.17までは生成途中のチャンクに`isLightOn`が無く、書き足すと元に無いキーが増えるので足さない
    pub(crate) adds_light_flag: bool,
}

/// 世代の表
/// 境界のDataVersionの昇順に並べる
static FORMATS: [ChunkFormat; 3] = [
    // C3: 1.16〜1.17.x
    // 本体はLevelの中で、ブロックはセクションの直下のPalette / BlockStates
    // バイオームは4×4×4ブロックごとの数値のID
    ChunkFormat {
        min_data_version: 2529,
        wrapped_in_level: true,
        sections_key: "Sections",
        palette_data_version: 2529,
        spanning_bit_storage: false,
        block_storage: BlockStorage::SectionPalette,
        biome_storage: BiomeStorage::Ids3D,
        block_data_keys: LEVEL_BLOCK_DATA_KEYS,
        has_y_pos: false,
        adds_light_flag: false,
    },
    // C4: 1.18〜26.2
    // Levelが無くなり、パレットの要素はName / Properties
    ChunkFormat {
        min_data_version: 2844,
        wrapped_in_level: false,
        sections_key: "sections",
        palette_data_version: 2844,
        spanning_bit_storage: false,
        block_storage: BlockStorage::Container,
        biome_storage: BiomeStorage::Paletted,
        block_data_keys: ROOT_BLOCK_DATA_KEYS,
        has_y_pos: true,
        adds_light_flag: true,
    },
    // C5: 26.3以降
    // パレットの要素は文字列かid / properties
    ChunkFormat {
        min_data_version: PALETTE_ID_FORMAT_DATA_VERSION,
        wrapped_in_level: false,
        sections_key: "sections",
        palette_data_version: PALETTE_ID_FORMAT_DATA_VERSION,
        spanning_bit_storage: false,
        block_storage: BlockStorage::Container,
        biome_storage: BiomeStorage::Paletted,
        block_data_keys: ROOT_BLOCK_DATA_KEYS,
        has_y_pos: true,
        adds_light_flag: true,
    },
];

impl ChunkFormat {
    /// DataVersionから世代を引く
    /// 表にあるどの世代よりも古ければ`None`
    pub(crate) fn for_data_version(data_version: i32) -> Option<&'static ChunkFormat> {
        let mut result = None;

        // 表は境界の昇順に並ぶので、境界以上の最後の世代が当てはまる
        for format in FORMATS.iter() {
            // 境界に届いた世代だけを候補にする
            if data_version >= format.min_data_version {
                result = Some(format);
            }
        }

        result
    }
}
