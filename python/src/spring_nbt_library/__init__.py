"""SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ

対象は1.13以降のワールド形式 (DataVersion 1519以降)
"""

from .errors import ErrorCode, SpringNbtError

#: このライブラリが扱えるワールド形式の下限となるDataVersion (1.13)
#:
#: 1.13でブロックの持ち方が数値のIDからパレットへ変わった
#: 1519は1.13の正式版のDataVersion
#: これ以降のチャンクは、読んだときの形式のまま読み書きできる
#: 1.16（DataVersion 2529）でビット詰めが値を64bitの境目でまたがない形に変わり、
#: 1.18（DataVersion 2844）でチャンクの本体が``Level``の外へ出て、
#: 26.3（DataVersion 5006）でパレットの要素の形が変わったが、どの形式も扱う
#: これより古いチャンクと、DataVersionの無いチャンク（1.9より前）は形式が違う
#: そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定でUNSUPPORTED_DATA_VERSIONにする
MIN_SUPPORTED_DATA_VERSION = 1519

#: 動作を確かめたMinecraft Java版のDataVersion (26.3)
TARGET_DATA_VERSION = 5023

__all__ = ["MIN_SUPPORTED_DATA_VERSION", "TARGET_DATA_VERSION",
           "ErrorCode", "SpringNbtError"]
