#!/usr/bin/env bash
# 4言語の適合性検証を走らせる。中身は spec/tools/run_conformance.py。
#
#   ./spec/run-conformance.sh                 全言語を検証
#   ./spec/run-conformance.sh --only csharp   言語を絞る
#   ./spec/run-conformance.sh --generate-expect
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ツールチェーンへ PATH を通す（未導入のものは検証対象から自動的に外れる）
SPRINGNBT_ENV_QUIET=1 source "${repo_root}/spec/tools/env.sh"

exec python3 "${repo_root}/spec/tools/run_conformance.py" "$@"
