/**
 * 4言語で共通のエラーモデル。
 *
 * 仕様: `docs/spec/00-conventions.md` 4章 / `docs/adr/0005-unified-error-model.md`
 */

/** エラーの分類。全言語で同一の集合を持つ。 */
export enum ErrorCode {
  /** 下位の入出力失敗。 */
  Io = "IO",

  /** バイト列が仕様に反する。 */
  MalformedData = "MALFORMED_DATA",

  /** 期待した型と違うタグを取り出した。 */
  UnexpectedTagType = "UNEXPECTED_TAG_TYPE",

  /** 仕様上は妥当だが、このビルドでは扱えない。 */
  UnsupportedFeature = "UNSUPPORTED_FEATURE",

  /** 安全上限を超えた。 */
  LimitExceeded = "LIMIT_EXCEEDED",

  /** 呼び出し側の引数が不正。 */
  InvalidArgument = "INVALID_ARGUMENT",

  /** 対象バージョン外のデータ。 */
  UnsupportedDataVersion = "UNSUPPORTED_DATA_VERSION",
}

/** 適合性テストで言語間比較に使う識別子を返す。 */
export function errorCodeAsString(code: ErrorCode): string {
  return code;
}

/** 本ライブラリが送出する例外。分類は {@link SpringNbtError.code} で判別する。 */
export class SpringNbtError extends Error {
  /** エラーの分類。 */
  readonly code: ErrorCode;

  constructor(code: ErrorCode, message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "SpringNbtError";
    this.code = code;
  }

  override toString(): string {
    return `[${this.code}] ${this.message}`;
  }

  /** {@link ErrorCode.MalformedData} の例外を作る。 */
  static malformed(message: string): SpringNbtError {
    return new SpringNbtError(ErrorCode.MalformedData, message);
  }

  /** {@link ErrorCode.InvalidArgument} の例外を作る。 */
  static invalidArgument(message: string): SpringNbtError {
    return new SpringNbtError(ErrorCode.InvalidArgument, message);
  }

  /** {@link ErrorCode.UnexpectedTagType} の例外を作る。 */
  static unexpectedTagType(message: string): SpringNbtError {
    return new SpringNbtError(ErrorCode.UnexpectedTagType, message);
  }

  /** {@link ErrorCode.LimitExceeded} の例外を作る。 */
  static limitExceeded(message: string): SpringNbtError {
    return new SpringNbtError(ErrorCode.LimitExceeded, message);
  }

  /** {@link ErrorCode.UnsupportedFeature} の例外を作る。 */
  static unsupportedFeature(message: string): SpringNbtError {
    return new SpringNbtError(ErrorCode.UnsupportedFeature, message);
  }
}
