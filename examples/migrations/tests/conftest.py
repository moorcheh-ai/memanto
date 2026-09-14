import sys
from pathlib import Path

# Allow imports like `from mappers import ...` and `from runner import ...`
# when pytest is invoked from the repo root or from examples/migrations/.
_MIGRATIONS = Path(__file__).parent.parent
_REPO_ROOT = _MIGRATIONS.parent.parent

for _p in (_MIGRATIONS, _REPO_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)
