"""RemediGenius-CE GitHub plugin.

Everything lives in `dashboard/` (the GitHub tab: manifest, bundle and FastAPI routes). This manifest exists so Hermes can enable the
plugin (`hermes plugins enable rg-github`); the dashboard serves only enabled user plugins.
"""


def register(ctx):
    return None
