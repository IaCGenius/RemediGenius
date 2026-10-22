"""RemediGenius-CE knowledge plugin.

Everything lives in `dashboard/` (the Knowledge tab: manifest, bundle and FastAPI routes). This manifest exists so
Hermes can enable the plugin (`hermes plugins enable rg-knowledge`); the dashboard serves only enabled user plugins.
In chat, `/triage knowledge` shows the knowledge overview without a model call.
"""


def register(ctx):
    return None
