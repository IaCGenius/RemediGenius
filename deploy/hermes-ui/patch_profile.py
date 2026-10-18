"""Preserve the chosen profile in upstream web-mode WebSocket connections."""
from pathlib import Path
p = Path('/source/app/src/web-bridge/bridge.ts')
s = p.read_text()
changes = {
    'getGatewayWsUrl: async () => {': 'getGatewayWsUrl: async profile => {',
    'if (token) {return withGatewayRoute(buildTokenWsUrl(token), origin)}': "const profileQuery = profile ? `&profile=${encodeURIComponent(profile)}` : ''\n      if (token) {return withGatewayRoute(buildTokenWsUrl(token) + profileQuery, origin)}",
    '`${wsBaseUrl()}/api/ws?ticket=${encodeURIComponent(ticket)}`, origin)': '`${wsBaseUrl()}/api/ws?ticket=${encodeURIComponent(ticket)}${profileQuery}`, origin)',
}
for before, after in changes.items():
    if s.count(before) != 1:
        raise SystemExit('Upstream profile connector changed; review patch before building')
    s = s.replace(before, after)
p.write_text(s)
