"""パレットとビットストレージの組
セクション内のブロック状態やバイオームを格納する

パレットの要素は**生の NbtTag のまま**持つ
こうすると、触っていないブロックについては Minecraft が書き出したときの
プロパティの並び順まで含めてそのまま書き戻せる

仕様: ``docs/spec/31-paletted-container.md``
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..errors import SpringNbtError
from ..nbt import NbtCompound, NbtList, NbtLongArray, NbtTag
from .bit_storage import BitStorage

__all__ = ["PalettedContainer", "ceil_log2"]


def ceil_log2(count: int) -> int:
    """``count`` 個の値を表すのに必要な最小ビット数
    1 なら 0
    """
    bits = 0

    # 1 を超える分だけシフトして数える
    while (1 << bits) < count:
        bits += 1

    return bits


class PalettedContainer:
    """パレット付きのコンテナ"""

    __slots__ = ("_palette", "entry_count", "min_bits", "_storage")

    def __init__(self, entry_count: int, min_bits: int) -> None:
        self._palette: List[NbtTag] = []
        self.entry_count = entry_count
        self.min_bits = min_bits
        self._storage: Optional[BitStorage] = None

    @property
    def palette(self) -> Sequence[NbtTag]:
        """パレット
        読み取り専用として扱うこと
        """
        return self._palette

    @property
    def bits_per_entry(self) -> int:
        """現在のビット幅
        パレットが 1 要素なら 0（記憶域を持たない）
        """
        if self._storage is None:
            return 0

        return self._storage.bits_per_entry

    @staticmethod
    def filled(value: NbtTag, entry_count: int, min_bits: int) -> "PalettedContainer":
        """単一の値で埋めたコンテナを作る"""
        result = PalettedContainer(entry_count, min_bits)
        result._palette.append(value)
        return result

    @staticmethod
    def from_nbt(nbt: NbtCompound, entry_count: int, min_bits: int,
                 lenient_bit_storage: bool = False) -> "PalettedContainer":
        """NBT から読み込む

        :raises SpringNbtError: パレットが空、data の長さが合わない、添字が範囲外のいずれか
        """
        result = PalettedContainer(entry_count, min_bits)
        palette_tag = nbt.opt_list("palette")

        if palette_tag is None or len(palette_tag) == 0:
            raise SpringNbtError.malformed("palette が無いか空")

        # パレットの要素は生の NbtTag のまま持つ
        # 並び順まで元どおりに書き戻すため
        for entry in palette_tag:
            result._palette.append(entry)

        data = nbt.opt_long_array("data")

        if data is None:
            # パレットが 1 要素なら data は無くてよい
            if len(result._palette) != 1:
                raise SpringNbtError.malformed(
                    "palette が %d 要素なのに data が無い" % len(result._palette))

            return result

        bits = max(min_bits, ceil_log2(len(result._palette)))
        result._storage = BitStorage.from_longs(data, bits, entry_count, lenient_bit_storage)

        # 取り出した添字がパレットの範囲に収まっているか確かめる
        # 黙って 0 番目で代替すると、壊れたデータをそうと分からない形で書き戻してしまう
        for index in range(entry_count):
            value = result._storage.get(index)

            if value >= len(result._palette):
                raise SpringNbtError.malformed(
                    "添字 %d の値 %d がパレット（%d 要素）の範囲外"
                    % (index, value, len(result._palette)))

        return result

    def to_nbt(self) -> NbtCompound:
        """NBT へ変換する"""
        result = NbtCompound()
        palette_tag = NbtList()

        # パレットの要素は読んだときのまま書き出す
        for entry in self._palette:
            palette_tag.append(entry)

        # パレットが 1 要素なら data は書かない
        # Minecraft と同じ振る舞い
        if self._storage is not None and len(self._palette) > 1:
            result.set("data", NbtLongArray(self._storage.to_longs()))

        result.set("palette", palette_tag)
        return result

    def get(self, index: int) -> NbtTag:
        """添字の値を取り出す"""
        self._check_index(index)

        # 記憶域が無いということは、全エントリがパレットの 0 番目
        if self._storage is None:
            return self._palette[0]

        return self._palette[self._storage.get(index)]

    def set(self, index: int, value: NbtTag) -> None:
        """添字の値を書き換える
        パレットに無ければ追加する
        """
        self._check_index(index)
        palette_index = self._index_of_or_add(value)

        # 記憶域が無く、書き込む値も 0 番目なら何もしなくてよい
        if self._storage is None and palette_index == 0:
            return

        self._ensure_storage()
        self._storage.set(index, palette_index)

    def fill(self, value: NbtTag) -> None:
        """全エントリを 1 つの値で埋める
        パレットもその 1 要素だけにする
        """
        self._palette = [value]
        self._storage = None

    def compact(self) -> None:
        """どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す

        大量の ``set`` を行う用途で遅くならないよう、明示的に呼んだときだけ実行する
        """
        if self._storage is None:
            return

        used_entries = [False] * len(self._palette)

        # どのパレット要素が実際に使われているかを数える
        for index in range(self.entry_count):
            used_entries[self._storage.get(index)] = True

        compacted = []
        remap = [-1] * len(self._palette)

        # 使われている要素だけを詰め直し、新しい添字を割り当てる
        for old in range(len(self._palette)):
            if not used_entries[old]:
                continue

            remap[old] = len(compacted)
            compacted.append(self._palette[old])

        if len(compacted) == len(self._palette):
            return

        new_bits = max(self.min_bits, ceil_log2(len(compacted)))
        rebuilt = BitStorage.create(new_bits, self.entry_count)

        # 新しい添字へ置き換えながら詰め直す
        for index in range(self.entry_count):
            rebuilt.set(index, remap[self._storage.get(index)])

        self._palette = compacted

        if len(compacted) == 1:
            # 1 要素になったら記憶域を捨てる
            self._storage = None
        else:
            self._storage = rebuilt

    def _index_of_or_add(self, value: NbtTag) -> int:
        """パレット内の位置を返す
        無ければ末尾へ追加する
        """
        # パレットは高々 4096 要素なので線形探索で足りる
        for index in range(len(self._palette)):
            if self._palette[index] == value:
                return index

        self._palette.append(value)
        return len(self._palette) - 1

    def _ensure_storage(self) -> None:
        """現在のパレット長に合うビット幅の記憶域を用意する"""
        required = max(self.min_bits, ceil_log2(len(self._palette)))

        if self._storage is None:
            # これまで単一値だったので、全エントリが 0 番目のまま始まる
            self._storage = BitStorage.create(required, self.entry_count)
            return

        if self._storage.bits_per_entry >= required:
            return

        # パレットが増えてビット幅が足りなくなったら、全体を詰め直す
        self._storage = self._storage.resize(required)

    def _check_index(self, index: int) -> None:
        if index < 0 or index >= self.entry_count:
            raise SpringNbtError.invalid_argument(
                "添字が範囲外: %d (0..%d)" % (index, self.entry_count - 1))
