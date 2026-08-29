//! 添字を 64bit 整数の配列へ詰めた表現。1.16 以降の**跨ぎなし**パッキング。
//!
//! 1 つの `i64` に入りきらない分は、その `i64` の残りビットを未使用のまま捨て、
//! 次の `i64` の最下位ビットから始める。
//!
//! 仕様: `docs/spec/31-paletted-container.md` 2章

use crate::error::{Error, ErrorCode, Result};

/// packed な添字の並び。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BitStorage {
    data: Vec<i64>,
    bits_per_entry: usize,
    entry_count: usize,
}

impl BitStorage {
    /// 1 エントリあたりのビット数。
    pub fn bits_per_entry(&self) -> usize {
        self.bits_per_entry
    }

    /// エントリ数。ブロックなら 4096、バイオームなら 64。
    pub fn entry_count(&self) -> usize {
        self.entry_count
    }

    /// 1 つの `i64` に入るエントリ数。
    pub fn values_per_long(&self) -> usize {
        64 / self.bits_per_entry
    }

    /// すべてゼロで初期化した記憶域を作る。
    pub fn create(bits_per_entry: usize, entry_count: usize) -> Result<BitStorage> {
        if bits_per_entry < 1 || bits_per_entry > 32 {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("ビット幅が範囲外: {bits_per_entry}"),
            ));
        }

        Ok(BitStorage {
            data: vec![0; Self::long_count(bits_per_entry, entry_count)],
            bits_per_entry,
            entry_count,
        })
    }

    /// 既存の `i64` 配列から作る。
    ///
    /// `lenient` が `true` なら、配列長が期待値と違う場合に
    /// 配列長からビット幅を逆算して読む。第三者ツールが書いたデータの救済用。
    pub fn from_longs(
        data: Vec<i64>,
        bits_per_entry: usize,
        entry_count: usize,
        lenient: bool,
    ) -> Result<BitStorage> {
        let expected = Self::long_count(bits_per_entry, entry_count);

        if data.len() == expected {
            return Ok(BitStorage { data, bits_per_entry, entry_count });
        }

        if !lenient {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!(
                    "bits={bits_per_entry} なら data は {expected} long のはずだが {} long",
                    data.len()
                ),
            ));
        }

        // 配列長からビット幅を逆算する。合致する幅が無ければ諦める
        for candidate in 1..=32usize {
            if Self::long_count(candidate, entry_count) == data.len() {
                return Ok(BitStorage { data, bits_per_entry: candidate, entry_count });
            }
        }

        Err(Error::new(
            ErrorCode::MalformedData,
            format!(
                "data の長さ {} long に合うビット幅が無い（エントリ数 {entry_count}）",
                data.len()
            ),
        ))
    }

    /// 必要な `i64` の個数を求める。
    pub fn long_count(bits_per_entry: usize, entry_count: usize) -> usize {
        let values_per_long = 64 / bits_per_entry;
        entry_count.div_ceil(values_per_long)
    }

    /// 添字の値を取り出す。
    pub fn get(&self, index: usize) -> Result<u32> {
        self.check_index(index)?;

        let per_long = self.values_per_long();
        let long_index = index / per_long;
        let bit_offset = (index % per_long) * self.bits_per_entry;
        let mask = (1u64 << self.bits_per_entry) - 1;

        // 符号付きのままシフトすると符号が伸びるので、符号なしへ直してから動かす
        let unsigned = self.data[long_index] as u64;
        Ok(((unsigned >> bit_offset) & mask) as u32)
    }

    /// 添字の値を書き換える。
    pub fn set(&mut self, index: usize, value: u32) -> Result<()> {
        self.check_index(index)?;
        let limit = 1u64 << self.bits_per_entry;

        if value as u64 >= limit {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("値がビット幅に収まらない: {value} (0..{})", limit - 1),
            ));
        }

        let per_long = self.values_per_long();
        let long_index = index / per_long;
        let bit_offset = (index % per_long) * self.bits_per_entry;
        let mask = ((1u64 << self.bits_per_entry) - 1) << bit_offset;

        let current = self.data[long_index] as u64;
        let updated = (current & !mask) | (((value as u64) << bit_offset) & mask);
        self.data[long_index] = updated as i64;
        Ok(())
    }

    /// packed な配列を返す。
    pub fn as_longs(&self) -> &[i64] {
        &self.data
    }

    /// packed な配列を取り出す。
    pub fn into_longs(self) -> Vec<i64> {
        self.data
    }

    /// 別のビット幅へ詰め直した新しい記憶域を返す。
    pub fn resize(&self, new_bits_per_entry: usize) -> Result<BitStorage> {
        let mut result = BitStorage::create(new_bits_per_entry, self.entry_count)?;

        // 全エントリを読み直して新しい幅で詰める
        for index in 0..self.entry_count {
            result.set(index, self.get(index)?)?;
        }

        Ok(result)
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
