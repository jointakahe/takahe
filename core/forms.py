from crispy_forms.helper import FormHelper as BaseFormHelper
from crispy_forms.layout import Submit


class FormHelper(BaseFormHelper):

    submit_text = "Submit"

    def __init__(self, form=None, submit_text=None):
        super().__init__(form)
        self.add_input(Submit("submit", submit_text or "Submit"))
