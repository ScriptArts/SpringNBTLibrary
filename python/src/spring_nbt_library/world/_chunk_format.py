"""チャンクの形式の世代
ライブラリの内部だけで使う
公開APIには出さない

世代ごとの違いはこの表に集める
チャンクの読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
"""

from __future__ import annotations

import enum
from typing import Optional, Tuple

#: ブロックのパレット要素が``id`` / ``properties``の形式になるDataVersion（26.3）
#: これ未満は``Name`` / ``Properties``の形式
PALETTE_ID_FORMAT_DATA_VERSION = 5006

#: DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版）
OLDEST_FORMAT_DATA_VERSION = 1519

#: ルートの直下に置かれる、ブロックに紐づく付随データのキー（1.18以降）
_ROOT_BLOCK_DATA_KEYS = ("block_entities", "block_ticks", "fluid_ticks")

#: ``Level``の中に置かれる、ブロックに紐づく付随データのキー（1.17まで）
_LEVEL_BLOCK_DATA_KEYS = ("TileEntities", "TileTicks", "LiquidTicks")


class BlockStorage(enum.Enum):
    """セクションのブロックの持ち方"""

    #: セクションの``block_states``にあるパレット付きコンテナ（``palette`` / ``data``）
    #: パレットが1要素なら``data``を持たない
    CONTAINER = "container"

    #: セクションの直下の``Palette``と``BlockStates``
    #: ``BlockStates``はパレットが1要素でも必ずある
    SECTION_PALETTE = "section_palette"


class BiomeStorage(enum.Enum):
    """バイオームの持ち方"""

    #: セクションごとのパレット付きコンテナ
    PALETTED = "paletted"

    #: チャンクの列ごとの数値のバイオームID（``int[256]``）
    IDS_2D = "ids_2d"

    #: 4×4×4ブロックごとの数値のバイオームID（``int[1024]``）
    IDS_3D = "ids_3d"


class ChunkFormat:
    """チャンクの形式の世代1つ分"""

    __slots__ = ("min_data_version", "wrapped_in_level", "sections_key",
                 "palette_data_version", "spanning_bit_storage", "block_storage",
                 "biome_storage", "block_data_keys", "has_y_pos", "adds_light_flag")

    def __init__(self, min_data_version: int, wrapped_in_level: bool, sections_key: str,
                 palette_data_version: int, spanning_bit_storage: bool,
                 block_storage: BlockStorage, biome_storage: BiomeStorage,
                 block_data_keys: Tuple[str, str, str], has_y_pos: bool,
                 adds_light_flag: bool) -> None:
        #: この世代が始まるDataVersion
        self.min_data_version = min_data_version
        #: チャンクの本体が``Level``の中にあるか
        self.wrapped_in_level = wrapped_in_level
        #: セクションの一覧のキー
        self.sections_key = sections_key
        #: パレットの要素と:class:`BlockState`の変換に渡すDataVersion
        self.palette_data_version = palette_data_version
        #: ビット詰めで値が64bitの境目をまたぐか
        self.spanning_bit_storage = spanning_bit_storage
        #: セクションのブロックの持ち方
        self.block_storage = block_storage
        #: バイオームの持ち方
        self.biome_storage = biome_storage
        #: ブロックを置き換えたときに取り除く付随データのキー
        self.block_data_keys = block_data_keys
        #: ルートに最下段セクションのY位置（``yPos``）があるか
        #: 無い世代では、セクションは0段目から始まる
        self.has_y_pos = has_y_pos
        #: ``isLightOn``の無いチャンクで光源を無効化するとき、``isLightOn``を書き足すか
        #: 1.17までは生成途中のチャンクに``isLightOn``が無く、書き足すと元に無いキーが増えるので足さない
        self.adds_light_flag = adds_light_flag

    @staticmethod
    def for_data_version(data_version: int) -> Optional["ChunkFormat"]:
        """DataVersionから世代を引く
        表にあるどの世代よりも古ければNone
        """
        result = None

        # 表は境界の昇順に並ぶので、境界以上の最後の世代が当てはまる
        for chunk_format in _FORMATS:
            # 境界に届いた世代だけを候補にする
            if data_version >= chunk_format.min_data_version:
                result = chunk_format

        return result


#: 世代の表
#: 境界のDataVersionの昇順に並べる
_FORMATS = (
    # C3: 1.16〜1.17.x
    # 本体はLevelの中で、ブロックはセクションの直下のPalette / BlockStates
    # バイオームは4×4×4ブロックごとの数値のID
    ChunkFormat(
        min_data_version=2529,
        wrapped_in_level=True,
        sections_key="Sections",
        palette_data_version=2529,
        spanning_bit_storage=False,
        block_storage=BlockStorage.SECTION_PALETTE,
        biome_storage=BiomeStorage.IDS_3D,
        block_data_keys=_LEVEL_BLOCK_DATA_KEYS,
        has_y_pos=False,
        adds_light_flag=False),
    # C4: 1.18〜26.2
    # Levelが無くなり、パレットの要素はName / Properties
    ChunkFormat(
        min_data_version=2844,
        wrapped_in_level=False,
        sections_key="sections",
        palette_data_version=2844,
        spanning_bit_storage=False,
        block_storage=BlockStorage.CONTAINER,
        biome_storage=BiomeStorage.PALETTED,
        block_data_keys=_ROOT_BLOCK_DATA_KEYS,
        has_y_pos=True,
        adds_light_flag=True),
    # C5: 26.3以降
    # パレットの要素は文字列かid / properties
    ChunkFormat(
        min_data_version=PALETTE_ID_FORMAT_DATA_VERSION,
        wrapped_in_level=False,
        sections_key="sections",
        palette_data_version=PALETTE_ID_FORMAT_DATA_VERSION,
        spanning_bit_storage=False,
        block_storage=BlockStorage.CONTAINER,
        biome_storage=BiomeStorage.PALETTED,
        block_data_keys=_ROOT_BLOCK_DATA_KEYS,
        has_y_pos=True,
        adds_light_flag=True),
)
