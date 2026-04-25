# DEPRECATED — this file is dead code.
# The service_desk/ package (service_desk/__init__.py) takes precedence at import time.
# All handlers have been migrated to the sub-modules:
#   tickets.py, kb.py, cmdb.py, sla.py, oncall.py, templates.py, analytics.py, misc.py
# This file can be deleted once the migration is confirmed stable.
raise ImportError("service_desk.py should never be imported — use the service_desk/ package instead")
