from sphinx.application import Sphinx
from sphinx.builders.dirhtml import DirectoryHTMLBuilder


def setup(app: Sphinx):
    app.connect("html-page-context", canonical_url)


def canonical_url(app: Sphinx, pagename, templatename, context, doctree):
    """Sphinx 1.8 builds a canonical URL if ``html_baseurl`` config is
    set. However, it builds a URL ending with ".html" when using the
    dirhtml builder, which is incorrect. Detect this and generate the
    correct URL for each page.
    Also accepts the custom, deprecated ``canonical_url`` config as the
    base URL. This will be removed in version 2.1.
    """
    base = app.config.html_baseurl

    if (
        not base
        or not isinstance(app.builder, DirectoryHTMLBuilder)
        or not context["pageurl"]
        or not context["pageurl"].endswith(".html")
    ):
        return

    # Fix pageurl for dirhtml builder if this version of Sphinx still
    # generates .html URLs.
    target = app.builder.get_target_uri(pagename)
    context["pageurl"] = base + target
