#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
revision=a4065941f12be7967436261d9934784e381d423c
package=${ARCHIFY_PACKAGE:-work/archify-upstream/archify}
if [ ! -f "$package/bin/archify.mjs" ]; then
  git clone --no-checkout https://github.com/tt-a1i/archify.git work/archify-upstream
  git -C work/archify-upstream checkout "$revision"
fi
if [ "$(git -C "$package" rev-parse HEAD)" != "$revision" ]; then
  echo "Use the pinned Archify revision $revision; no installation was overwritten." >&2
  exit 1
fi
export ARCHIFY_UPDATE_CHECK_DISABLED=1
mkdir -p work/architecture-build
review=$(mktemp -d work/architecture-build/review-XXXXXX)
node "$package/bin/archify.mjs" finalize architecture architecture/agentsim.architecture.json work/architecture-build/architecture.html --repo-root . --quality showcase --json --out-dir "$review"
cp work/architecture-build/architecture.html static/architecture.html
ARCHIFY_REVIEW_DIR="$review" python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
root=Path(os.environ['ARCHIFY_REVIEW_DIR'])
summary=json.loads((root/'architecture.finalize-summary.json').read_text())
assert summary['ok'] and all(v=='pass' for v in summary['gates'].values())
proof={
 'generator':'Archify 3.2.0',
 'upstream':'https://github.com/tt-a1i/archify',
 'revision':'a4065941f12be7967436261d9934784e381d423c',
 'source':'architecture/agentsim.architecture.json',
 'sourceSha256':hashlib.sha256(Path('architecture/agentsim.architecture.json').read_bytes()).hexdigest(),
 'output':'static/architecture.html',
 'outputSha256':hashlib.sha256(Path('static/architecture.html').read_bytes()).hexdigest(),
 'gates':summary['gates'],
 'visualReview':'Not part of the build; inspect the embedded viewer after UI changes.'
}
Path('architecture/verification.json').write_text(json.dumps(proof,indent=2)+'\n')
PY
