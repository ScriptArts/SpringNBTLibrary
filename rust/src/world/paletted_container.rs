//! パレットとビットストレージの組。セクション内のブロック状態やバイオームを格納する。
//!
//! パレットの要素は**生の [`NbtTag`] のまま**持つ。
//! こうすると、触っていないブロックについては Minecraft が書き出したときの
//! プロパティの並び順まで含めてそのまま書き戻せる。
//!
//! 仕様: `docs/spec/31-paletted-container.md`

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::{NbtCompound, NbtList, NbtTag};

use super::bit_storage::BitStorage;

/// `count` 個の値を表すのに必要な最小ビット数。1 なら 0。
pub fn ceil_log2(count: usize) -> usize {
    let mut bits = 0usize;

    // 1 を超える分だけシフトして数える
    while (1usize << bits) < count {
        bits += 1;
    }

    bits
}

/// パレット付きのコンテナ。
#[derive(Debug, Clone)]
pub struct PalettedContainer {
    palette: Vec<NbtTag>,
    entry_count: usize,
    min_bits: usize,
    storage: Option<BitStorage>,
}

impl PalettedContainer {
    /// エントリ数。ブロックなら 4096、バイオームなら 64。
    pub fn entry_count(&self) -> usize {
        self.entry_count
    }

    /// ビット幅の下限。ブロックなら 4、バイオームなら 1。
    pub fn min_bits(&self) -> usize {
        self.min_bits
    }

    /// パレット。
    pub fn palette(&self) -> &[NbtTag] {
        &self.palette
    }

    /// 現在のビット幅。パレットが 1 要素なら 0（記憶域を持たない）。
    pub fn bits_per_entry(&self) -> usize {
        match &self.storage {
            Some(storage) => storage.bits_per_entry(),
            None => 0,
        }
    }

    /// 単一の値で埋めたコンテナを作る。
    pub fn filled(value: NbtTag, entry_count: usize, min_bits: usize) -> PalettedContainer {
        PalettedContainer {
            palette: vec![value],
            entry_count,
            min_bits,
            storage: None,
        }
    }

    /// NBT から読み込む。
    pub fn from_nbt(
        nbt: &NbtCompound,
        entry_count: usize,
        min_bits: usize,
        lenient_bit_storage: bool,
    ) -> Result<PalettedContainer> {
        let palette_tag = match nbt.opt_list("palette")? {
            Some(list) if !list.is_empty() => list,
            _ => {
                return Err(Error::new(ErrorCode::MalformedData, "palette が無いか空"));
            }
        };

        let palette: Vec<NbtTag> = palette_tag.iter().cloned().collect();

        let data = match nbt.opt_long_array("data")? {
            Some(values) => values.to_vec(),
            None => {
                // パレットが 1 要素なら data は無くてよい
                if palette.len() != 1 {
                    return Err(Error::new(
                        ErrorCode::MalformedData,
                        format!("palette が {} 要素なのに data が無い", palette.len()),
                    ));
                }

                return Ok(PalettedContainer {
                    palette,
                    entry_count,
                    min_bits,
                    storage: None,
                });
            }
        };

        let bits = min_bits.max(ceil_log2(palette.len()));
        let storage = BitStorage::from_longs(data, bits, entry_count, lenient_bit_storage)?;

        // 取り出した添字がパレットの範囲に収まっているか確かめる。
        // 黙って 0 番目で代替すると、壊れたデータをそうと分からない形で書き戻してしまう
        for index in 0..entry_count {
            let value = storage.get(index)? as usize;

            if value >= palette.len() {
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    format!(
                        "添字 {index} の値 {value} がパレット（{} 要素）の範囲外",
                        palette.len()
                    ),
                ));
            }
        }

        Ok(PalettedContainer {
            palette,
            entry_count,
            min_bits,
            storage: Some(storage),
        })
    }

    /// NBT へ変換する。
    pub fn to_nbt(&self) -> Result<NbtCompound> {
        let mut result = NbtCompound::new();
        let mut palette_tag = NbtList::new();

        // パレットの要素は読んだときのまま書き出す
        for entry in &self.palette {
            palette_tag.push(entry.clone())?;
        }

        // パレットが 1 要素なら data は書かない。Minecraft と同じ振る舞い
        if let Some(storage) = &self.storage {
            // パレットが 1 要素なら data は書かない
            if self.palette.len() > 1 {
                result.set("data", NbtTag::LongArray(storage.as_longs().to_vec()));
            }
        }

        result.set("palette", NbtTag::List(palette_tag));
        Ok(result)
    }

    /// 添字の値を取り出す。
    pub fn get(&self, index: usize) -> Result<&NbtTag> {
        self.check_index(index)?;

        // 記憶域が無いということは、全エントリがパレットの 0 番目
        match &self.storage {
            None => Ok(&self.palette[0]),
            Some(storage) => Ok(&self.palette[storage.get(index)? as usize]),
        }
    }

    /// 添字の値を書き換える。パレットに無ければ追加する。
    pub fn set(&mut self, index: usize, value: NbtTag) -> Result<()> {
        self.check_index(index)?;
        let palette_index = self.index_of_or_add(value);

        // 記憶域が無く、書き込む値も 0 番目なら何もしなくてよい
        if self.storage.is_none() && palette_index == 0 {
            return Ok(());
        }

        self.ensure_storage()?;

        match &mut self.storage {
            Some(storage) => storage.set(index, palette_index as u32),
            None => Ok(()),
        }
    }

    /// 全エントリを 1 つの値で埋める。パレットもその 1 要素だけにする。
    pub fn fill(&mut self, value: NbtTag) {
        self.palette.clear();
        self.palette.push(value);
        self.storage = None;
    }

    /// どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す。
    ///
    /// 大量の `set` を行う用途で遅くならないよう、明示的に呼んだときだけ実行する。
    pub fn compact(&mut self) -> Result<()> {
        let storage = match &self.storage {
            Some(storage) => storage.clone(),
            None => return Ok(()),
        };

        let mut used_entries = vec![false; self.palette.len()];

        // どのパレット要素が実際に使われているかを数える
        for index in 0..self.entry_count {
            used_entries[storage.get(index)? as usize] = true;
        }

        let mut compacted: Vec<NbtTag> = Vec::new();
        let mut remap = vec![0usize; self.palette.len()];

        // 使われている要素だけを詰め直し、新しい添字を割り当てる
        for old in 0..self.palette.len() {
            if !used_entries[old] {
                continue;
            }

            remap[old] = compacted.len();
            compacted.push(self.palette[old].clone());
        }

        if compacted.len() == self.palette.len() {
            return Ok(());
        }

        let new_bits = self.min_bits.max(ceil_log2(compacted.len()));
        let mut rebuilt = BitStorage::create(new_bits, self.entry_count)?;

        // 新しい添字へ置き換えながら詰め直す
        for index in 0..self.entry_count {
            rebuilt.set(index, remap[storage.get(index)? as usize] as u32)?;
        }

        let single = compacted.len() == 1;
        self.palette = compacted;

        if single {
            // 1 要素になったら記憶域を捨てる
            self.storage = None;
        } else {
            self.storage = Some(rebuilt);
        }

        Ok(())
    }

    /// パレット内の位置を返す。無ければ末尾へ追加する。
    fn index_of_or_add(&mut self, value: NbtTag) -> usize {
        // パレットは高々 4096 要素なので線形探索で足りる
        for index in 0..self.palette.len() {
            if self.palette[index] == value {
                return index;
            }
        }

        self.palette.push(value);
        self.palette.len() - 1
    }

    /// 現在のパレット長に合うビット幅の記憶域を用意する。
    fn ensure_storage(&mut self) -> Result<()> {
        let required = self.min_bits.max(ceil_log2(self.palette.len()));

        match &self.storage {
            None => {
                // これまで単一値だったので、全エントリが 0 番目のまま始まる
                self.storage = Some(BitStorage::create(required, self.entry_count)?);
                Ok(())
            }
            Some(storage) => {
                if storage.bits_per_entry() >= required {
                    return Ok(());
                }

                // パレットが増えてビット幅が足りなくなったら、全体を詰め直す
                self.storage = Some(storage.resize(required)?);
                Ok(())
            }
        }
    }

    fn check_index(&self, index: usize) -> Result<()> {
        if index >= self.entry_count {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("添字が範囲外: {index} (0..{})", self.entry_count - 1),
            ));
        }

        Ok(())
    }
}
