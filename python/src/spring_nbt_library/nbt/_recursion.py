"""Pythonの再帰上限を仕様の深さ上限に合わせるための補助

Pythonの既定の再帰上限1000のままでは、仕様が定めるネスト深さ上限512まで届かない
引き上げておかないと、ライブラリが``LIMIT_EXCEEDED``を返すより先に
``RecursionError``が出てしまい、他の4言語と挙動が変わる

他の4言語（C# / Java / TypeScript / Rust）は既定のスタックで深さ512を扱えるため、
この調整が要るのはPythonだけである
ただしRustのdebugビルドは1段あたりのスタック消費が大きく、注意が要る
"""

from __future__ import annotations

import contextlib
import sys

from ..errors import SpringNbtError

__all__ = ["DEFAULT_MAX_DEPTH", "headroom", "guard"]

#: ネスト深さの既定上限
#: 仕様が定める値
DEFAULT_MAX_DEPTH = 512

#: NBTのネスト1段あたりに消費するPythonのスタックフレーム数（余裕を見た値）
_FRAMES_PER_LEVEL = 6

#: 再帰上限に上乗せする余白
_RECURSION_MARGIN = 400


@contextlib.contextmanager
def headroom(max_depth: int):
    """仕様上の深さ上限まで再帰できるよう、一時的にPythonの再帰上限を引き上げる"""
    required = (max_depth * _FRAMES_PER_LEVEL) + _RECURSION_MARGIN
    previous = sys.getrecursionlimit()

    # 既に十分大きい場合は触らない
    if required > previous:
        sys.setrecursionlimit(required)

    try:
        yield
    finally:
        sys.setrecursionlimit(previous)


@contextlib.contextmanager
def guard(max_depth: int, message: str):
    """:func:`headroom`に加えて、なお底を突いた場合をLIMIT_EXCEEDEDへ写す"""
    with headroom(max_depth):
        try:
            yield
        except RecursionError as error:
            raise SpringNbtError.limit_exceeded(message) from error
