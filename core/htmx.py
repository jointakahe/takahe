class HTMXMixin:
    template_name_htmx: str | None = None

    def get_template_name(self):
        if self.request.htmx and self.template_name_htmx:
            return self.template_name_htmx
        else:
            return self.template_name
