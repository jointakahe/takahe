from core.models import Config


def config_context(request):
    return {
        "config": Config.load_system(),
        "config_identity": (
            Config.load_identity(request.identity) if request.identity else None
        ),
        "top_section": request.path.strip("/").split("/")[0],
    }
