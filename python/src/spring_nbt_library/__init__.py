"""SpringNBTLibrary — Minecraft Java版の NBT / Anvil ワールドデータを読み書きするライブラリ

仕様は ``docs/spec/`` を唯一の正とする
対象バージョンは Java版 26.2 (DataVersion 4903)
"""

from .errors import ErrorCode, SpringNbtError

#: 本ライブラリが対象とする Minecraft Java版の DataVersion (26.2)
TARGET_DATA_VERSION = 4903

__all__ = ["TARGET_DATA_VERSION", "ErrorCode", "SpringNbtError"]
