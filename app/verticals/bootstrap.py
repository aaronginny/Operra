"""Import this module once, early, to populate the vertical registry.

Each vertical registers itself as a side effect of its own module being
imported (see the register_vertical() call at the bottom of
app.services.launch_matcher.handler and app.services.real_estate_notifications).
This module's only job is to force those imports to happen from one place, so
that whatever imports *this* module can be certain the registry is populated
before any dispatch runs.

That guarantee is anchored structurally, not by startup ordering: this module
is imported at the top of app.services.webhook_service, in the same file that
defines dispatch_inbound(). Python fully executes a module's top-level code —
including its imports — before any function defined later in that same file
can be called from anywhere else. So by the time any caller can reach
dispatch_inbound via `from app.services.webhook_service import
process_incoming_message`, this import has already run, regardless of
main.py's own router-import order.

Adding a new vertical (e.g. broker_intel) means adding one import line here,
pointing at whatever module in that vertical's package calls
register_vertical() — nothing else needs to change for the registry to know
about it.
"""

from app.services.launch_matcher import handler as _launch_matcher_handler  # noqa: F401
from app.services import real_estate_notifications as _real_estate_notifications  # noqa: F401
from app.services.broker_intel import handler as _broker_intel_handler  # noqa: F401
