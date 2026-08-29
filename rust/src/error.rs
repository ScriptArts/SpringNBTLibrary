//! 4言語で共通のエラーモデル。
//!
//! 仕様: `docs/spec/00-conventions.md` 4章 / `docs/adr/0005-unified-error-model.md`

use std::fmt;

/// エラーの分類。4言語すべてで同一の集合を持つ。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ErrorCode {
    /// 下位の入出力失敗。
    Io,
    /// バイト列が仕様に反する。
    MalformedData,
    /// 期待した型と違うタグを取り出した。
    UnexpectedTagType,
    /// 仕様上は妥当だが、このビルドでは扱えない。
    UnsupportedFeature,
    /// 安全上限を超えた。
    LimitExceeded,
    /// 呼び出し側の引数が不正。
    InvalidArgument,
    /// 対象バージョン外のデータ。
    UnsupportedDataVersion,
}

impl ErrorCode {
    /// 適合性テストで言語間比較に使う識別子。
    pub fn as_str(self) -> &'static str {
        match self {
            ErrorCode::Io => "IO",
            ErrorCode::MalformedData => "MALFORMED_DATA",
            ErrorCode::UnexpectedTagType => "UNEXPECTED_TAG_TYPE",
            ErrorCode::UnsupportedFeature => "UNSUPPORTED_FEATURE",
            ErrorCode::LimitExceeded => "LIMIT_EXCEEDED",
            ErrorCode::InvalidArgument => "INVALID_ARGUMENT",
            ErrorCode::UnsupportedDataVersion => "UNSUPPORTED_DATA_VERSION",
        }
    }
}

impl fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// 本ライブラリが返すエラー。
#[derive(Debug)]
pub struct Error {
    code: ErrorCode,
    message: String,
    source: Option<Box<dyn std::error::Error + Send + Sync>>,
}

impl Error {
    /// 分類とメッセージからエラーを作る。
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Error { code, message: message.into(), source: None }
    }

    /// 原因となった下位のエラーを保持してエラーを作る。
    pub fn with_source(
        code: ErrorCode,
        message: impl Into<String>,
        source: impl std::error::Error + Send + Sync + 'static,
    ) -> Self {
        Error { code, message: message.into(), source: Some(Box::new(source)) }
    }

    /// エラーの分類。
    pub fn code(&self) -> ErrorCode {
        self.code
    }

    /// 人間向けの説明。
    pub fn message(&self) -> &str {
        &self.message
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}] {}", self.code, self.message)
    }
}

impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        // 原因を保持している場合だけ返す
        match &self.source {
            Some(inner) => Some(inner.as_ref()),
            None => None,
        }
    }
}

impl From<std::io::Error> for Error {
    fn from(value: std::io::Error) -> Self {
        // 下位の入出力エラーは情報を失わないよう原因として保持する
        Error::with_source(ErrorCode::Io, value.to_string(), value)
    }
}

/// 本ライブラリの結果型。
pub type Result<T> = std::result::Result<T, Error>;
