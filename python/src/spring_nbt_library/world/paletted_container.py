"""パレットとビットストレージの組
セクション内のブロック状態やバイオームを格納する

パレットの要素は**生のNbtTagのまま**持つ
こうすると、触っていないブロックについてはMinecraftが書き出したときの
プロパティの並び順まで含めてそのまま書き戻せる

26.3からは、ブロックのパレットに文字列とCompoundが混ざる
Minecraftはこうした異種リストをCompoundのリストとして保存し、Compoundでない要素を``{"": <値>}``で包む
読むときにこの包みを外して持ち、書くときに要素の型を見て包み直す
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ..errors import SpringNbtError
from ..nbt import NbtCompound, NbtList, NbtLongArray, NbtTag, TagType
from .bit_storage import BitStorage

__all__ = ["PalettedContainer", "ceil_log2"]


def ceil_log2(count: int) -> int:
    """``count``個の値を表すのに必要な最小ビット数
    1なら0
    """
    bits = 0

    # 1を超える分だけシフトして数える
    while (1 << bits) < count:
        bits += 1

    return bits


def _is_list_wrapper(tag: NbtTag) -> bool:
    """異種リストの要素を包むCompoundか
    空のキー1つだけを持つものがそれに当たる（MinecraftのListTagと同じ判定）
    """
    if not isinstance(tag, NbtCompound):
        return False

    return len(tag) == 1 and "" in tag


def _unwrap_list_element(tag: NbtTag) -> NbtTag:
    """異種リストの包みを外す
    包みでなければそのまま返す
    """
    if _is_list_wrapper(tag):
        return tag.get("")

    return tag


def _palette_to_list(entries: Sequence[NbtTag]) -> NbtList:
    """パレットの要素をリストへ詰める

    要素の型がすべて同じならその型のリストにする
    1つでも違えば、Minecraftと同じくCompoundのリストにして、Compoundでない要素と包みに見える要素を包む
    """
    element_type = entries[0].type

    # 先頭と型の違う要素があるか調べる
    for entry in entries:
        # 1つでも違えば、異種リストとしてCompoundのリストにする
        if entry.type != element_type:
            element_type = TagType.COMPOUND
            break

    result = NbtList(element_type)

    # 要素を順にリストへ入れる
    for entry in entries:
        # Compoundのリストでは、Compoundでない要素と包みに見える要素を包む
        if element_type == TagType.COMPOUND and (
                not isinstance(entry, NbtCompound) or _is_list_wrapper(entry)):
            wrapper = NbtCompound()
            wrapper.set("", entry)
            result.append(wrapper)
        else:
            result.append(entry)

    return result


class PalettedContainer:
    """パレット付きのコンテナ"""

    __slots__ = ("_palette", "entry_count", "min_bits", "_storage", "_spanning", "_always_has_data")

    def __init__(self, entry_count: int, min_bits: int) -> None:
        self._palette: List[NbtTag] = []
        self.entry_count = entry_count
        self.min_bits = min_bits
        self._storage: Optional[BitStorage] = None
        self._spanning = False
        self._always_has_data = False

    @property
    def palette(self) -> Sequence[NbtTag]:
        """パレット
        読み取り専用として扱うこと
        """
        return self._palette

    @property
    def bits_per_entry(self) -> int:
        """現在のビット幅
        パレットが1要素なら0（記憶域を持たない）
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
        """NBTから読み込む

        :raises SpringNbtError: パレットが空、dataの長さが合わない、添字がパレット範囲外のいずれか
        """
        palette_tag = nbt.opt_list("palette")

        if palette_tag is None or len(palette_tag) == 0:
            raise SpringNbtError.malformed("palette が無いか空")

        # パレットの要素は生のNbtTagのまま持つ
        # 並び順まで元どおりに書き戻すため
        # 異種リストの包みだけは外しておき、書くときに包み直す
        entries = [_unwrap_list_element(entry) for entry in palette_tag]

        return PalettedContainer._from_parts(
            entries, nbt.opt_long_array("data"), entry_count, min_bits,
            False, False, lenient_bit_storage)

    @staticmethod
    def _from_parts(palette: Sequence[NbtTag], data: Optional[List[int]], entry_count: int,
                    min_bits: int, spanning: bool, always_has_data: bool,
                    lenient_bit_storage: bool) -> "PalettedContainer":
        """パレットとdataから作る（内部用）
        1.13から1.15までの詰め方や、dataが必ず書かれる形式を読むための入口

        :raises SpringNbtError: パレットが空、dataの長さが合わない、添字がパレット範囲外のいずれか
        """
        if len(palette) == 0:
            raise SpringNbtError.malformed("palette が無いか空")

        result = PalettedContainer(entry_count, min_bits)
        result._spanning = spanning
        result._always_has_data = always_has_data
        result._palette.extend(palette)

        if data is None:
            # パレットが1要素ならdataは無くてよい
            if len(result._palette) != 1:
                raise SpringNbtError.malformed(
                    "palette が %d 要素なのに data が無い" % len(result._palette))

            return result

        bits = max(min_bits, ceil_log2(len(result._palette)))
        result._storage = BitStorage._from_longs_with(
            data, bits, entry_count, lenient_bit_storage, spanning)

        # 取り出した添字がパレットの範囲に収まっているか確かめる
        # エラーを出さずに0番目で代替すると、おかしくなったデータをそうと分からない形で書き戻してしまう
        for index in range(entry_count):
            value = result._storage.get(index)

            if value >= len(result._palette):
                raise SpringNbtError.malformed(
                    "添字 %d の値 %d がパレット（%d 要素）の範囲外"
                    % (index, value, len(result._palette)))

        return result

    def _to_parts(self) -> Tuple[List[NbtTag], Optional[List[int]]]:
        """パレットとdataに分けて返す（内部用）
        パレットの要素は異種リストの包みを掛けないまま返す
        dataは、パレットが1要素なら（``always_has_data``でない限り）None
        """
        entries = list(self._palette)

        # パレットが2要素以上なら、記憶域をそのまま返す
        if self._storage is not None and len(self._palette) > 1:
            return entries, self._storage.to_longs()

        # 1要素でもdataを書く形式なら、記憶域が無くてもゼロで埋めた配列を作る
        if self._always_has_data:
            bits = max(self.min_bits, ceil_log2(len(self._palette)))
            zeroed = BitStorage._create_with(bits, self.entry_count, self._spanning)
            return entries, zeroed.to_longs()

        return entries, None

    def to_nbt(self) -> NbtCompound:
        """NBTへ変換する"""
        result = NbtCompound()

        # パレットの要素は読んだときのまま書き出す
        # 型が混ざっていれば、Minecraftと同じく包んでCompoundのリストにする
        palette_tag = _palette_to_list(self._palette)

        # パレットが1要素ならdataは書かない
        # Minecraftと同じ振る舞い
        if self._storage is not None and len(self._palette) > 1:
            result.set("data", NbtLongArray(self._storage.to_longs()))

        result.set("palette", palette_tag)
        return result

    def get(self, index: int) -> NbtTag:
        """添字の値を取り出す"""
        self._check_index(index)

        # 記憶域が無いということは、全エントリがパレットの0番目
        if self._storage is None:
            return self._palette[0]

        return self._palette[self._storage.get(index)]

    def set(self, index: int, value: NbtTag) -> None:
        """添字の値を書き換える
        パレットに無ければ追加する
        """
        self._check_index(index)
        palette_index = self._index_of_or_add(value)

        # 記憶域が無く、書き込む値も0番目なら何もしなくてよい
        if self._storage is None and palette_index == 0:
            return

        self._ensure_storage()
        self._storage.set(index, palette_index)

    def fill(self, value: NbtTag) -> None:
        """全エントリを1つの値で埋める
        パレットもその1要素だけにする
        """
        self._palette = [value]
        self._storage = None

    def compact(self) -> None:
        """どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す

        大量の``set``を行う用途で遅くならないよう、明示的に呼んだときだけ実行する
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
        rebuilt = BitStorage._create_with(new_bits, self.entry_count, self._spanning)

        # 新しい添字へ置き換えながら詰め直す
        for index in range(self.entry_count):
            rebuilt.set(index, remap[self._storage.get(index)])

        self._palette = compacted

        if len(compacted) == 1:
            # 1要素になったら記憶域を捨てる
            self._storage = None
        else:
            self._storage = rebuilt

    def _index_of_or_add(self, value: NbtTag) -> int:
        """パレット内の位置を返す
        無ければ末尾へ追加する
        """
        # パレットは高々4096要素なので線形探索で足りる
        for index in range(len(self._palette)):
            if self._palette[index] == value:
                return index

        self._palette.append(value)
        return len(self._palette) - 1

    def _ensure_storage(self) -> None:
        """現在のパレット長に合うビット幅の記憶域を用意する"""
        required = max(self.min_bits, ceil_log2(len(self._palette)))

        if self._storage is None:
            # これまで単一値だったので、全エントリが0番目のまま始まる
            self._storage = BitStorage._create_with(required, self.entry_count, self._spanning)
            return

        if self._storage.bits_per_entry >= required:
            return

        # パレットが増えてビット幅が足りなくなったら、全体を詰め直す
        self._storage = self._storage.resize(required)

    def _check_index(self, index: int) -> None:
        if index < 0 or index >= self.entry_count:
            raise SpringNbtError.invalid_argument(
                "添字が範囲外: %d (0..%d)" % (index, self.entry_count - 1))
