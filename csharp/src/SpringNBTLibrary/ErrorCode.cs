namespace SpringNBTLibrary;

/// <summary>
/// エラーの分類。4言語すべてで同一の集合を持つ。
/// </summary>
/// <remarks>仕様: <c>docs/spec/00-conventions.md</c> 4章</remarks>
public enum ErrorCode
{
    /// <summary>下位の入出力失敗。</summary>
    Io,

    /// <summary>バイト列が仕様に反する。</summary>
    MalformedData,

    /// <summary>期待した型と違うタグを取り出した。</summary>
    UnexpectedTagType,

    /// <summary>仕様上は妥当だが、このビルドでは扱えない。</summary>
    UnsupportedFeature,

    /// <summary>安全上限を超えた。</summary>
    LimitExceeded,

    /// <summary>呼び出し側の引数が不正。</summary>
    InvalidArgument,

    /// <summary>対象バージョン外のデータ。</summary>
    UnsupportedDataVersion,
}

/// <summary><see cref="ErrorCode"/> の拡張メソッド。</summary>
public static class ErrorCodeExtensions
{
    /// <summary>
    /// 適合性テストで言語間比較に使う識別子を返す。
    /// </summary>
    public static string AsString(this ErrorCode code)
    {
        switch (code)
        {
            case ErrorCode.Io:
                return "IO";
            case ErrorCode.MalformedData:
                return "MALFORMED_DATA";
            case ErrorCode.UnexpectedTagType:
                return "UNEXPECTED_TAG_TYPE";
            case ErrorCode.UnsupportedFeature:
                return "UNSUPPORTED_FEATURE";
            case ErrorCode.LimitExceeded:
                return "LIMIT_EXCEEDED";
            case ErrorCode.InvalidArgument:
                return "INVALID_ARGUMENT";
            case ErrorCode.UnsupportedDataVersion:
                return "UNSUPPORTED_DATA_VERSION";
            default:
                throw new ArgumentOutOfRangeException(nameof(code), code, "未知の ErrorCode");
        }
    }
}
