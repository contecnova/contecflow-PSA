"""service_desk model package — split from the former 1385-LOC god-file.
Importing this package registers every mapper (all submodules) and
re-exports all enums + models so existing imports keep working."""
from app.models.service_desk._enums import *  # noqa: F403
from app.models.service_desk.catalog import *  # noqa: F403
from app.models.service_desk.cmdb import *  # noqa: F403
from app.models.service_desk.agents import *  # noqa: F403
from app.models.service_desk.tickets import *  # noqa: F403
from app.models.service_desk.sla import *  # noqa: F403
from app.models.service_desk.problems import *  # noqa: F403
from app.models.service_desk.knowledge import *  # noqa: F403
from app.models.service_desk.changes import *  # noqa: F403
from app.models.service_desk.automation import *  # noqa: F403
from app.models.service_desk.ops import *  # noqa: F403
from app.models.service_desk.changes import ChangeRequest  # noqa: F401
