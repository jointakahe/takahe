from django import forms
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from users.decorators import admin_required
from users.models import Announcement
from users.views.admin.generic import HTMXActionView


@method_decorator(admin_required, name="dispatch")
class AnnouncementsRoot(ListView):

    template_name = "admin/announcements.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.extra_context = {
            "section": "announcements",
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        reports = Announcement.objects.order_by("created")
        return reports


@method_decorator(admin_required, name="dispatch")
class AnnouncementCreate(CreateView):

    model = Announcement
    template_name = "admin/announcement_create.html"
    extra_context = {"section": "announcements"}
    success_url = Announcement.urls.admin_root

    class form_class(forms.ModelForm):
        class Meta:
            model = Announcement
            fields = ["text", "published", "start", "end"]
            widgets = {
                "published": forms.Select(
                    choices=[(True, "Published"), (False, "Draft")]
                )
            }


@method_decorator(admin_required, name="dispatch")
class AnnouncementEdit(UpdateView):

    model = Announcement
    template_name = "admin/announcement_edit.html"
    extra_context = {"section": "announcements"}
    success_url = Announcement.urls.admin_root

    class form_class(AnnouncementCreate.form_class):
        pass


@method_decorator(admin_required, name="dispatch")
class AnnouncementDelete(DeleteView):

    model = Announcement
    template_name = "admin/announcement_delete.html"
    success_url = Announcement.urls.admin_root


class AnnouncementPublish(HTMXActionView):
    """
    Marks the announcement as published.
    """

    model = Announcement

    def action(self, announcement: Announcement):
        announcement.published = True
        announcement.save()


class AnnouncementUnpublish(HTMXActionView):
    """
    Marks the announcement as unpublished.
    """

    model = Announcement

    def action(self, announcement: Announcement):
        announcement.published = False
        announcement.save()
