namespace SpringNBTLibrary;

/// <summary>
/// 本ライブラリが送出する例外。分類は <see cref="Code"/> で判別する。
/// </summary>
/// <remarks>仕様: <c>docs/spec/00-conventions.md</c> 4章 / <c>docs/adr/0005-unified-error-model.md</c></remarks>
public sealed class SpringNbtException : Exception
{
    /// <summary>分類とメッセージから例外を作る。</summary>
    public SpringNbtException(ErrorCode code, string message)
        : base(message)
    {
        Code = code;
    }

    /// <summary>原因となった下位の例外を保持して例外を作る。</summary>
    public SpringNbtException(ErrorCode code, string message, Exception innerException)
        : base(message, innerException)
    {
        Code = code;
    }

    /// <summary>エラーの分類。</summary>
    public ErrorCode Code { get; }

    /// <inheritdoc/>
    public override string ToString()
    {
        return $"[{Code.AsString()}] {Message}";
    }

    /// <summary><see cref="ErrorCode.MalformedData"/> の例外を作る。</summary>
    public static SpringNbtException Malformed(string message)
    {
        return new SpringNbtException(ErrorCode.MalformedData, message);
    }

    /// <summary><see cref="ErrorCode.InvalidArgument"/> の例外を作る。</summary>
    public static SpringNbtException InvalidArgument(string message)
    {
        return new SpringNbtException(ErrorCode.InvalidArgument, message);
    }

    /// <summary><see cref="ErrorCode.UnexpectedTagType"/> の例外を作る。</summary>
    public static SpringNbtException UnexpectedTagType(string message)
    {
        return new SpringNbtException(ErrorCode.UnexpectedTagType, message);
    }

    /// <summary><see cref="ErrorCode.LimitExceeded"/> の例外を作る。</summary>
    public static SpringNbtException LimitExceeded(string message)
    {
        return new SpringNbtException(ErrorCode.LimitExceeded, message);
    }

    /// <summary><see cref="ErrorCode.UnsupportedFeature"/> の例外を作る。</summary>
    public static SpringNbtException UnsupportedFeature(string message)
    {
        return new SpringNbtException(ErrorCode.UnsupportedFeature, message);
    }
}
