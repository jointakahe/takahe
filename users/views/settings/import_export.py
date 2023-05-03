import csv

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, View

from users.models import Follow, InboxMessage
from users.views.base import IdentityViewMixin


@method_decorator(login_required, name="dispatch")
class ImportExportPage(IdentityViewMixin, FormView):
    """
    Lets the identity's profile be edited
    """

    template_name = "settings/import_export.html"
    extra_context = {"section": "importexport"}

    class form_class(forms.Form):
        csv = forms.FileField(help_text="The CSV file you want to import")
        import_type = forms.ChoiceField(
            help_text="The type of data you wish to import",
            choices=[("following", "Following list")],
        )

    def form_valid(self, form):
        # Load CSV (we don't touch the DB till the whole file comes in clean)
        try:
            lines = form.cleaned_data["csv"].read().decode("utf-8").splitlines()
            reader = csv.DictReader(lines)
            prepared_data = []
            for row in reader:
                entry = {
                    "handle": row["Account address"],
                    "boosts": not (row["Show boosts"].lower().strip()[0] == "f"),
                }
                if len(entry["handle"].split("@")) != 2:
                    raise ValueError("Handle looks wrong")
                prepared_data.append(entry)
        except (TypeError, ValueError):
            return redirect(".?bad_format=following")
        # For each one, add an inbox message to create that follow
        # We can't do them all inline here as the identity fetch might take ages
        for entry in prepared_data:
            InboxMessage.create_internal(
                {
                    "type": "AddFollow",
                    "source": self.identity.pk,
                    "target_handle": entry["handle"],
                    "boosts": entry["boosts"],
                }
            )
        return redirect(".?success=following")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["numbers"] = {
            "outbound_follows": self.identity.outbound_follows.active().count(),
            "inbound_follows": self.identity.inbound_follows.active().count(),
            "blocks": self.identity.outbound_blocks.active().filter(mute=False).count(),
            "mutes": self.identity.outbound_blocks.active().filter(mute=True).count(),
        }
        context["bad_format"] = self.request.GET.get("bad_format")
        context["success"] = self.request.GET.get("success")
        return context


class CsvView(IdentityViewMixin, View):
    """
    Generic view that exports a queryset as a CSV
    """

    # Mapping of CSV column title to method or model attribute name
    # We rely on the fact that python dicts are stably ordered!
    columns: dict[str, str]

    # Filename to download as
    filename: str = "export.csv"

    def get_queryset(self):
        raise NotImplementedError()

    def get(self, request, *args, **kwargs):
        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{self.filename}"'},
        )
        writer = csv.writer(response)
        writer.writerow(self.columns.keys())
        for item in self.get_queryset(request):
            row = []
            for attrname in self.columns.values():
                # Get value
                getter = getattr(self, attrname, None)
                if getter:
                    value = getter(item)
                elif hasattr(item, attrname):
                    value = getattr(item, attrname)
                else:
                    raise ValueError(f"Cannot export attribute {attrname}")
                # Make it into CSV format
                if type(value) == bool:
                    value = "true" if value else "false"
                elif type(value) == int:
                    value = str(value)
                row.append(value)
            writer.writerow(row)
        return response


class CsvFollowing(CsvView):
    columns = {
        "Account address": "get_handle",
        "Show boosts": "boosts",
        "Notify on new posts": "get_notify",
        "Languages": "get_languages",
    }

    filename = "following.csv"

    def get_queryset(self, request):
        return self.identity.outbound_follows.active()

    def get_handle(self, follow: Follow):
        return follow.target.handle

    def get_notify(self, follow: Follow):
        return False

    def get_languages(self, follow: Follow):
        return ""


class CsvFollowers(CsvView):
    columns = {
        "Account address": "get_handle",
    }

    filename = "followers.csv"

    def get_queryset(self, request):
        return self.identity.inbound_follows.active()

    def get_handle(self, follow: Follow):
        return follow.source.handle
