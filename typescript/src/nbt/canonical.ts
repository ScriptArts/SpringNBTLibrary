/**
 * 浮動小数点の正準10進表記
 *
 * 各言語の標準の数値書式（C# の `"R"`、Java の `Float.toString`、
 * Python の `repr`、Rust の `{}`、JavaScript の `String(x)`）は互いに一致しない
 * 指数表記へ切り替わる閾値も、指数部の桁数も、`E` の大文字小文字も処理系ごとに違う
 * そのままでは SNBT 出力の言語間一致が成立しないため、書式をここで固定する
 *
 * 仕様: `docs/spec/11-snbt.md` 5.1章
 */

/** 固定小数点表記を使う10進指数の下限
/** */
const MIN_FIXED_EXPONENT = -4;

/** 固定小数点表記を使う10進指数の上限
/** */
const MAX_FIXED_EXPONENT = 16;

const scratch = new DataView(new ArrayBuffer(8));

/** 特殊値なら文字列を、そうでなければ undefined を返す
/** */
function special(value: number): string | undefined {
  if (Number.isNaN(value)) {
    return "NaN";
  }

  if (value === Number.POSITIVE_INFINITY) {
    return "Infinity";
  }

  if (value === Number.NEGATIVE_INFINITY) {
    return "-Infinity";
  }

  return undefined;
}

/** binary32 のビットパターンを取り出す
/** */
function floatBits(value: number): number {
  scratch.setFloat32(0, value, false);
  return scratch.getUint32(0, false);
}

/** binary64 のビットパターンを取り出す
/** */
function doubleBits(value: number): bigint {
  scratch.setFloat64(0, value, false);
  return scratch.getBigUint64(0, false);
}

/** binary32 を正準10進表記へ変換する
/** */
export function fromFloat(value: number): string {
  const specialText = special(value);

  if (specialText !== undefined) {
    return specialText;
  }

  const target = floatBits(value);
  const negative = isNegative(value);

  // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
  for (let precision = 1; precision <= 9; precision++) {
    const candidate = value.toExponential(precision - 1);

    if (floatBits(Math.fround(Number(candidate))) === target) {
      return formatExponential(candidate, negative);
    }
  }

  // 9 桁あれば binary32 は必ず往復するので、ここへは来ない
  return formatExponential(value.toExponential(8), negative);
}

/** binary64 を正準10進表記へ変換する
/** */
export function fromDouble(value: number): string {
  const specialText = special(value);

  if (specialText !== undefined) {
    return specialText;
  }

  const target = doubleBits(value);
  const negative = isNegative(value);

  // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
  for (let precision = 1; precision <= 17; precision++) {
    const candidate = value.toExponential(precision - 1);

    if (doubleBits(Number(candidate)) === target) {
      return formatExponential(candidate, negative);
    }
  }

  // 17 桁あれば binary64 は必ず往復するので、ここへは来ない
  return formatExponential(value.toExponential(16), negative);
}

/**
 * 符号が負かどうかを判定する
 *
 * `-0` を `< 0` では判定できないため、ビットの符号で見る
 * JavaScript の `toExponential` は `-0` の符号を落とすので、
 * ここで別に持っておかないと `-0.0d` が `0.0d` になり他言語と食い違う
 */
function isNegative(value: number): boolean {
  if (value < 0) {
    return true;
  }

  return Object.is(value, -0);
}

/** 指数表記の文字列（例 `"7.5e-1"`）から、仕様が定める正準表記を組み立てる
/** */
function formatExponential(exponential: string, negative: boolean): string {
  let index = 0;

  if (exponential[0] === "-" || exponential[0] === "+") {
    index = 1;
  }

  let digits = "";

  // 仮数部の数字だけを集める
  while (index < exponential.length && exponential[index] !== "e" && exponential[index] !== "E") {
    const c = exponential[index];

    if (c >= "0" && c <= "9") {
      digits += c;
    }

    index += 1;
  }

  const exponent = Number.parseInt(exponential.slice(index + 1), 10);

  return compose(negative, trimTrailingZeros(digits), exponent);
}

/** 末尾のゼロを取り除く
/** すべてゼロなら "0" を残す
/** */
function trimTrailingZeros(digits: string): string {
  let end = digits.length;

  // 末尾から連続するゼロを削る
  while (end > 1 && digits[end - 1] === "0") {
    end -= 1;
  }

  return digits.slice(0, end);
}

/** 数字列と10進指数から最終的な文字列を組み立てる
/** */
function compose(negative: boolean, digits: string, exponent: number): string {
  let sign = "";

  if (negative) {
    sign = "-";
  }

  // 値が 0 のときは指数に関わらず 0.0 と書く
  if (digits === "0") {
    return `${sign}0.0`;
  }

  if (exponent < MIN_FIXED_EXPONENT || exponent > MAX_FIXED_EXPONENT) {
    // 指数表記
    let fraction = "0";

    if (digits.length > 1) {
      fraction = digits.slice(1);
    }

    return `${sign}${digits[0]}.${fraction}E${exponent}`;
  }

  if (exponent >= 0) {
    // 整数部は先頭 (exponent + 1) 桁
    // 足りなければゼロで右詰めする
    const integerDigits = exponent + 1;
    let integerPart: string;

    if (digits.length >= integerDigits) {
      integerPart = digits.slice(0, integerDigits);
    } else {
      integerPart = digits.padEnd(integerDigits, "0");
    }

    let fraction = "0";

    if (digits.length > integerDigits) {
      fraction = digits.slice(integerDigits);
    }

    return `${sign}${integerPart}.${fraction}`;
  }

  // 指数が負なら "0." に続けてゼロを詰めてから数字を置く
  return `${sign}0.${"0".repeat(-exponent - 1)}${digits}`;
}
