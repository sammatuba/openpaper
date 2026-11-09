"""Mount MCP middleware without swallowing the main application's redirects."""

from starlette.routing import Match, Mount
from starlette.types import Scope


class MCPRouteMount(Mount):
    """Delegate only paths registered by the MCP app, retaining its middleware."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope = super().matches(scope)
        if match != Match.NONE:
            mounted_scope = {**scope, **child_scope}
            for route in self.routes:
                if route.matches(mounted_scope)[0] != Match.NONE:
                    return match, child_scope
        return Match.NONE, {}
