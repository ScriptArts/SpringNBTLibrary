"""4言語で共通のエラーモデル

仕様: ``docs/spec/00-conventions.md`` 4章 / ``docs/adr/0005-unified-error-model.md``
"""

from __future__ import annotations

import enum

__all__ = ["ErrorCode", "SpringNbtError"]


class ErrorCode(enum.Enum):
    """エラーの分類
    4言語すべてで同一の集合を持つ
    """

    #: 下位の入出力失敗
    IO = "IO"

    #: バイト列が仕様に反する
    MALFORMED_DATA = "MALFORMED_DATA"

    #: 期待した型と違うタグを取り出した
    UNEXPECTED_TAG_TYPE = "UNEXPECTED_TAG_TYPE"

    #: 仕様上は妥当だが、このビルドでは扱えない
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"

    #: 安全上限を超えた
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"

    #: 呼び出し側の引数が不正
    INVALID_ARGUMENT = "INVALID_ARGUMENT"

    #: 対象バージョン外のデータ
    UNSUPPORTED_DATA_VERSION = "UNSUPPORTED_DATA_VERSION"

    def as_string(self) -> str:
        """適合性テストで言語間比較に使う識別子"""
        return self.value


class SpringNbtError(Exception):
    """本ライブラリが送出する例外
    分類は :attr:`code` で判別する
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return "[%s] %s" % (self.code.as_string(), self.message)

    @staticmethod
    def malformed(message: str) -> "SpringNbtError":
        """``MALFORMED_DATA`` の例外を作る"""
        return SpringNbtError(ErrorCode.MALFORMED_DATA, message)

    @staticmethod
    def invalid_argument(message: str) -> "SpringNbtError":
        """``INVALID_ARGUMENT`` の例外を作る"""
        return SpringNbtError(ErrorCode.INVALID_ARGUMENT, message)

    @staticmethod
    def unexpected_tag_type(message: str) -> "SpringNbtError":
        """``UNEXPECTED_TAG_TYPE`` の例外を作る"""
        return SpringNbtError(ErrorCode.UNEXPECTED_TAG_TYPE, message)

    @staticmethod
    def limit_exceeded(message: str) -> "SpringNbtError":
        """``LIMIT_EXCEEDED`` の例外を作る"""
        return SpringNbtError(ErrorCode.LIMIT_EXCEEDED, message)

    @staticmethod
    def unsupported_feature(message: str) -> "SpringNbtError":
        """``UNSUPPORTED_FEATURE`` の例外を作る"""
        return SpringNbtError(ErrorCode.UNSUPPORTED_FEATURE, message)
