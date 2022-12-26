from django.conf import settings

from activities.models import Post
from core.models import Config
from takahe import __version__
from users.models import Domain, Identity

from .base import api_router


@api_router.get("/v1/instance")
def instance_info(request):
    return {
        "uri": request.headers.get("host", settings.SETUP.MAIN_DOMAIN),
        "title": Config.system.site_name,
        "short_description": "",
        "description": "",
        "email": "",
        "version": f"takahe/{__version__}",
        "urls": {},
        "stats": {
            "user_count": Identity.objects.filter(local=True).count(),
            "status_count": Post.objects.filter(local=True).count(),
            "domain_count": Domain.objects.count(),
        },
        "thumbnail": Config.system.site_banner,
        "languages": ["en"],
        "registrations": (Config.system.signup_allowed),
        "approval_required": False,
        "invites_enabled": False,
        "configuration": {
            "accounts": {},
            "statuses": {
                "max_characters": Config.system.post_length,
                "max_media_attachments": 4,
                "characters_reserved_per_url": 23,
            },
            "media_attachments": {
                "supported_mime_types": [
                    "image/apng",
                    "image/avif",
                    "image/gif",
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                ],
                "image_size_limit": (1024**2) * 10,
                "image_matrix_limit": 2000 * 2000,
            },
        },
        "contact_account": None,
        "rules": [],
    }
