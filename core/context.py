from core.config import Config


def config_context(request):
    return {
        "config": Config.load(),
    }
