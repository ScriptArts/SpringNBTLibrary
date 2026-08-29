"""添字を 64bit 整数の配列へ詰めた表現
1.16 以降の**跨ぎなし**パッキング

1 つの値に入りきらない分は、その値の残りビットを未使用のまま捨て、
次の値の最下位ビットから始める

Python の整数は無限精度なので、i64 として扱う箇所では
読み込み時に符号付きへ、書き込み時に符号なしへ明示的に変換する

仕様: ``docs/spec/31-paletted-container.md`` 2章
"""

from __future__ import annotations

from typing import List

from ..errors import SpringNbtError

__all__ = ["BitStorage"]

_MASK64 = 0xFFFFFFFFFFFFFFFF


class BitStorage:
    """packed な添字の並び"""

    __slots__ = ("_data", "bits_per_entry", "entry_count")

    def __init__(self, data: List[int], bits_per_entry: int, entry_count: int) -> None:
        self._data = data
        self.bits_per_entry = bits_per_entry
        self.entry_count = entry_count

    @property
    def values_per_long(self) -> int:
        """1 つの 64bit 値に入るエントリ数"""
        return 64 // self.bits_per_entry

    @staticmethod
    def create(bits_per_entry: int, entry_count: int) -> "BitStorage":
        """すべてゼロで初期化した記憶域を作る"""
        if bits_per_entry < 1 or bits_per_entry > 32:
            raise SpringNbtError.invalid_argument("ビット幅が範囲外: %d" % bits_per_entry)

        length = BitStorage.long_count(bits_per_entry, entry_count)
        return BitStorage([0] * length, bits_per_entry, entry_count)

    @staticmethod
    def from_longs(data: List[int], bits_per_entry: int, entry_count: int,
                   lenient: bool = False) -> "BitStorage":
        """既存の 64bit 配列から作る

        :param lenient: True なら配列長からビット幅を逆算して読む（第三者ツール由来の救済）
        :raises SpringNbtError: 配列長が期待値と一致しない場合
        """
        expected = BitStorage.long_count(bits_per_entry, entry_count)

        if len(data) == expected:
            return BitStorage(list(data), bits_per_entry, entry_count)

        if not lenient:
            raise SpringNbtError.malformed(
                "bits=%d なら data は %d long のはずだが %d long"
                % (bits_per_entry, expected, len(data)))

        # 配列長からビット幅を逆算する
        # 合致する幅が無ければ諦める
        for candidate in range(1, 33):
            if BitStorage.long_count(candidate, entry_count) == len(data):
                return BitStorage(list(data), candidate, entry_count)

        raise SpringNbtError.malformed(
            "data の長さ %d long に合うビット幅が無い（エントリ数 %d）" % (len(data), entry_count))

    @staticmethod
    def long_count(bits_per_entry: int, entry_count: int) -> int:
        """必要な 64bit 値の個数を求める"""
        values_per_long = 64 // bits_per_entry
        return (entry_count + values_per_long - 1) // values_per_long

    def get(self, index: int) -> int:
        """添字の値を取り出す"""
        self._check_index(index)

        per_long = self.values_per_long
        long_index = index // per_long
        bit_offset = (index % per_long) * self.bits_per_entry
        mask = (1 << self.bits_per_entry) - 1

        # 符号付きのままシフトすると符号が伸びるので、符号なしへ直してから動かす
        return ((self._data[long_index] & _MASK64) >> bit_offset) & mask

    def set(self, index: int, value: int) -> None:
        """添字の値を書き換える"""
        self._check_index(index)
        limit = 1 << self.bits_per_entry

        if value < 0 or value >= limit:
            raise SpringNbtError.invalid_argument(
                "値がビット幅に収まらない: %d (0..%d)" % (value, limit - 1))

        per_long = self.values_per_long
        long_index = index // per_long
        bit_offset = (index % per_long) * self.bits_per_entry
        mask = ((1 << self.bits_per_entry) - 1) << bit_offset

        current = self._data[long_index] & _MASK64
        updated = (current & ~mask & _MASK64) | ((value << bit_offset) & mask)
        self._data[long_index] = _to_signed(updated)

    def to_longs(self) -> List[int]:
        """packed な配列を返す
        内部の配列をそのまま返す（コピーしない）
        """
        return self._data

    def resize(self, new_bits_per_entry: int) -> "BitStorage":
        """別のビット幅へ詰め直した新しい記憶域を返す"""
        result = BitStorage.create(new_bits_per_entry, self.entry_count)

        # 全エントリを読み直して新しい幅で詰める
        for index in range(self.entry_count):
            result.set(index, self.get(index))

        return result

    def _check_index(self, index: int) -> None:
        if index < 0 or index >= self.entry_count:
            raise SpringNbtError.invalid_argument(
                "添字が範囲外: %d (0..%d)" % (index, self.entry_count - 1))


def _to_signed(value: int) -> int:
    """符号なし 64bit を符号付きへ読み替える"""
    if value >= (1 << 63):
        return value - (1 << 64)

    return value
