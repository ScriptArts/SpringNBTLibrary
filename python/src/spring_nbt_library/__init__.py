"""SpringNBTLibrary — Minecraft Java版の NBT / Anvil ワールドデータを読み書きするライブラリ

仕様は ``docs/spec/`` を唯一の正とする
対象バージョンは Java版 26.2 (DataVersion 4903)
"""

from .errors import ErrorCode, SpringNbtError

#: このライブラリが扱えるワールド形式の下限となる DataVersion (26.1)
#
# 26.1 で次元とプレイヤーデータの置き場が変わり、いまの形式になった
# これ以降のバージョンは、形式が同じであればそのまま読み書きできる
# これより古いワールドは構成そのものが違うので、
# 読み込み時に UNSUPPORTED_DATA_VERSION の対象になる
MIN_SUPPORTED_DATA_VERSION = 4786

#: 動作を確かめた Minecraft Java版の DataVersion (26.2)
TARGET_DATA_VERSION = 4903

__all__ = ["MIN_SUPPORTED_DATA_VERSION", "TARGET_DATA_VERSION",
           "ErrorCode", "SpringNbtError"]
