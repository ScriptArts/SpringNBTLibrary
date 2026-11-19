"""SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ

対象は1.16以降のワールド形式 (DataVersion 2529以降)
"""

from .errors import ErrorCode, SpringNbtError

#: このライブラリが扱えるワールド形式の下限となるDataVersion (1.16)
#:
#: 1.16でビット詰めが値を64bitの境目でまたがない形に変わった
#: 2529はMinecraftがこの詰め方へ変換するDataVersionで、1.16の開発版で入った
#: これ以降のチャンクは、読んだときの形式のまま読み書きできる
#: 1.18（DataVersion 2844）でチャンクの本体が``Level``の外へ出て、
#: 26.3（DataVersion 5006）でパレットの要素の形が変わったが、どの形式も扱う
#: これより古いチャンクは形式が違う
#: そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定でUNSUPPORTED_DATA_VERSIONにする
MIN_SUPPORTED_DATA_VERSION = 2529

#: 動作を確かめたMinecraft Java版のDataVersion (26.3)
TARGET_DATA_VERSION = 5023

__all__ = ["MIN_SUPPORTED_DATA_VERSION", "TARGET_DATA_VERSION",
           "ErrorCode", "SpringNbtError"]
