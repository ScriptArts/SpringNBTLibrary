"""SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ

対象は26.1で導入されたワールド形式 (DataVersion 4786以降)
"""

from .errors import ErrorCode, SpringNbtError

#: このライブラリが扱えるワールド形式の下限となるDataVersion (26.1)
#:
#: 26.1で次元とプレイヤーデータの置き場が変わり、いまの形式になった
#: これ以降のバージョンは、形式が同じであればそのまま読み書きできる
#: これより古いワールドは構成そのものが違う
#: そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定でUNSUPPORTED_DATA_VERSIONにする
MIN_SUPPORTED_DATA_VERSION = 4786

#: 動作を確かめたMinecraft Java版のDataVersion (26.2)
TARGET_DATA_VERSION = 4903

__all__ = ["MIN_SUPPORTED_DATA_VERSION", "TARGET_DATA_VERSION",
           "ErrorCode", "SpringNbtError"]
