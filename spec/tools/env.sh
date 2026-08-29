#!/usr/bin/env bash
# SpringNBTLibrary の開発用ツールチェーンへ PATH を通す。
#   使い方:  source spec/tools/env.sh
#
# Homebrew の keg-only な formula（dotnet@8 / openjdk@21 / python@3.12）は
# /opt/homebrew/bin へ symlink されないため、ここで明示的に前方に置く。

_brew_prefix="${HOMEBREW_PREFIX:-/opt/homebrew}"

for _p in \
    "${_brew_prefix}/opt/dotnet@8/bin" \
    "${_brew_prefix}/opt/openjdk@21/bin" \
    "${_brew_prefix}/opt/python@3.12/libexec/bin" \
    "${HOME}/.cargo/bin" \
    "${_brew_prefix}/opt/rustup/bin"
do
    # 既に PATH に含まれている場合は重複追加しない
    case ":${PATH}:" in
        *":${_p}:"*) ;;
        *) PATH="${_p}:${PATH}" ;;
    esac
done
export PATH

# Maven が使う JDK を明示する（システム既定の JDK が無い環境でも動くように）
export JAVA_HOME="${_brew_prefix}/opt/openjdk@21"

unset _brew_prefix _p

if [ "${SPRINGNBT_ENV_QUIET:-0}" != "1" ]; then
    echo "toolchain:"
    for _c in cargo dotnet java mvn node npm python3; do
        if command -v "${_c}" >/dev/null 2>&1; then
            printf '  %-8s %s\n' "${_c}" "$(command -v "${_c}")"
        else
            printf '  %-8s (未検出)\n' "${_c}"
        fi
    done
    unset _c
fi
