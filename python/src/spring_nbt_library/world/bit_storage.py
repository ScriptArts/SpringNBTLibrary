"""添字を64bit整数の配列へ詰めた表現
1.16以降の**跨ぎなし**パッキング

1つの値に入りきらない分は、その値の残りビットを未使用のまま捨て、
次の値の最下位ビットから始める

Pythonの整数は無限精度なので、i64として扱う箇所では
値を取り出すときは符号なしへ、書き込むときは符号付きへ明示的に変換する
"""

from __future__ import annotations

from typing import List

from ..errors import SpringNbtError

__all__ = ["BitStorage"]

_MASK64 = 0xFFFFFFFFFFFFFFFF


class BitStorage:
    """packedな添字の並び"""

    __slots__ = ("_data", "bits_per_entry", "entry_count", "_spanning")

    def __init__(self, data: List[int], bits_per_entry: int, entry_count: int) -> None:
        self._data = data
        self.bits_per_entry = bits_per_entry
        self.entry_count = entry_count
        self._spanning = False

    @staticmethod
    def _build(data: List[int], bits_per_entry: int, entry_count: int,
               spanning: bool) -> "BitStorage":
        """詰め方を指定して組み立てる（内部用）"""
        result = BitStorage(data, bits_per_entry, entry_count)
        result._spanning = spanning
        return result

    @property
    def values_per_long(self) -> int:
        """1つの64bit値に入るエントリ数"""
        return 64 // self.bits_per_entry

    @staticmethod
    def create(bits_per_entry: int, entry_count: int) -> "BitStorage":
        """すべてゼロで初期化した記憶域を作る"""
        return BitStorage._create_with(bits_per_entry, entry_count, False)

    @staticmethod
    def _create_with(bits_per_entry: int, entry_count: int, spanning: bool) -> "BitStorage":
        """詰め方を指定して、すべてゼロで初期化した記憶域を作る（内部用）"""
        if bits_per_entry < 1 or bits_per_entry > 32:
            raise SpringNbtError.invalid_argument("ビット幅が範囲外: %d" % bits_per_entry)

        length = BitStorage._long_count_with(bits_per_entry, entry_count, spanning)
        return BitStorage._build([0] * length, bits_per_entry, entry_count, spanning)

    @staticmethod
    def from_longs(data: List[int], bits_per_entry: int, entry_count: int,
                   lenient: bool = False) -> "BitStorage":
        """既存の64bit配列から作る

        :param lenient: Trueなら、配列長が期待値と違う場合に配列長からビット幅を逆算して読む
            第三者ツールが書いたデータの救済用
        :raises SpringNbtError: 配列長が期待値と一致しない場合
        """
        return BitStorage._from_longs_with(data, bits_per_entry, entry_count, lenient, False)

    @staticmethod
    def _from_longs_with(data: List[int], bits_per_entry: int, entry_count: int,
                         lenient: bool, spanning: bool) -> "BitStorage":
        """詰め方を指定して、既存の64bit配列から作る（内部用）"""
        expected = BitStorage._long_count_with(bits_per_entry, entry_count, spanning)

        if len(data) == expected:
            return BitStorage._build(list(data), bits_per_entry, entry_count, spanning)

        if not lenient:
            raise SpringNbtError.malformed(
                "bits=%d なら data は %d long のはずだが %d long"
                % (bits_per_entry, expected, len(data)))

        # 配列長からビット幅を逆算する
        # 合致する幅が無ければ諦める
        for candidate in range(1, 33):
            if BitStorage._long_count_with(candidate, entry_count, spanning) == len(data):
                return BitStorage._build(list(data), candidate, entry_count, spanning)

        raise SpringNbtError.malformed(
            "data の長さ %d long に合うビット幅が無い（エントリ数 %d）" % (len(data), entry_count))

    @staticmethod
    def long_count(bits_per_entry: int, entry_count: int) -> int:
        """必要な64bit値の個数を求める"""
        return BitStorage._long_count_with(bits_per_entry, entry_count, False)

    @staticmethod
    def _long_count_with(bits_per_entry: int, entry_count: int, spanning: bool) -> int:
        """詰め方を指定して、必要な64bit値の個数を求める（内部用）"""
        # またぐ詰め方なら、全ビットを隙間なく並べた長さになる
        if spanning:
            return (entry_count * bits_per_entry + 63) // 64

        values_per_long = 64 // bits_per_entry
        return (entry_count + values_per_long - 1) // values_per_long

    def get(self, index: int) -> int:
        """添字の値を取り出す"""
        self._check_index(index)

        mask = (1 << self.bits_per_entry) - 1

        # またぐ詰め方なら、隣の64bit値へ続く分を上位ビットとして足す
        if self._spanning:
            bit_index = index * self.bits_per_entry
            span_long_index = bit_index >> 6
            span_offset = bit_index & 63
            span_value = (self._data[span_long_index] & _MASK64) >> span_offset

            # 次の64bit値へ続く場合は、続き分を左へずらして重ねる
            if span_offset + self.bits_per_entry > 64:
                span_value |= (self._data[span_long_index + 1] & _MASK64) << (64 - span_offset)

            return span_value & mask

        per_long = self.values_per_long
        long_index = index // per_long
        bit_offset = (index % per_long) * self.bits_per_entry

        # 符号付きのままシフトすると上位ビットが伸びるので、符号なしへ直してから動かす
        return ((self._data[long_index] & _MASK64) >> bit_offset) & mask

    def set(self, index: int, value: int) -> None:
        """添字の値を書き換える"""
        self._check_index(index)
        limit = 1 << self.bits_per_entry

        if value < 0 or value >= limit:
            raise SpringNbtError.invalid_argument(
                "値がビット幅に収まらない: %d (0..%d)" % (value, limit - 1))

        # またぐ詰め方なら、隣の64bit値へ続く分も書き込む
        if self._spanning:
            bit_index = index * self.bits_per_entry
            span_long_index = bit_index >> 6
            span_offset = bit_index & 63
            span_mask = limit - 1

            low = self._data[span_long_index] & _MASK64
            low_updated = (low & ~(span_mask << span_offset) & _MASK64) | ((value << span_offset) & _MASK64)
            self._data[span_long_index] = _to_signed(low_updated)

            # 次の64bit値へ続く場合は、続き分の下位ビットを書き換える
            if span_offset + self.bits_per_entry > 64:
                shift = 64 - span_offset
                high = self._data[span_long_index + 1] & _MASK64
                high_updated = (high & ~(span_mask >> shift) & _MASK64) | (value >> shift)
                self._data[span_long_index + 1] = _to_signed(high_updated)

            return

        per_long = self.values_per_long
        long_index = index // per_long
        bit_offset = (index % per_long) * self.bits_per_entry
        mask = ((1 << self.bits_per_entry) - 1) << bit_offset

        current = self._data[long_index] & _MASK64
        updated = (current & ~mask & _MASK64) | ((value << bit_offset) & mask)
        self._data[long_index] = _to_signed(updated)

    def to_longs(self) -> List[int]:
        """packedな配列を返す
        内部の配列をそのまま返す（コピーしない）
        """
        return self._data

    def resize(self, new_bits_per_entry: int) -> "BitStorage":
        """別のビット幅へ詰め直した新しい記憶域を返す"""
        result = BitStorage._create_with(new_bits_per_entry, self.entry_count, self._spanning)

        # 全エントリを読み直して新しい幅で詰める
        for index in range(self.entry_count):
            result.set(index, self.get(index))

        return result

    def _check_index(self, index: int) -> None:
        if index < 0 or index >= self.entry_count:
            raise SpringNbtError.invalid_argument(
                "添字が範囲外: %d (0..%d)" % (index, self.entry_count - 1))


def _to_signed(value: int) -> int:
    """符号なし64bitを符号付きへ読み替える"""
    if value >= (1 << 63):
        return value - (1 << 64)

    return value
