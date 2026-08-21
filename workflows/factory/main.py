"""The `factory` workflow: every request to the Software Factory is one
durable work item on one of seven routes (see software_factory/routes.py)."""
import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from hubzoid import workflow  # noqa: E402

from software_factory import pipeline  # noqa: E402
from software_factory.routes import ROUTES  # noqa: E402


@workflow(work_items=ROUTES)
def factory():
    """Take an engineering request from classification through research, analysis, implementation and an
    independent review to a reviewed draft pull request, or an answer, a plan or a clear stop reason."""
    return pipeline.run()
