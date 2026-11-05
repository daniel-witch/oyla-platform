from django import forms
from django.utils.translation import gettext_lazy as _

from .utils import parse_json_text, check_data_rules, FriendlyJSONError, MAX_RECORD_BYTES


def _read_json_input(cleaned, form):
    """Use the uploaded file if there is one, otherwise the pasted text.
    Stores error line info on the form so the template can highlight it."""
    upload = cleaned.get("json_file")
    text = cleaned.get("json_text", "")
    if upload:
        if upload.size > MAX_RECORD_BYTES:
            raise forms.ValidationError(_("This file is too big. The limit is 1 MB."))
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError(_("This file isn't a text/JSON file. Please upload a .json file."))
        cleaned["json_text"] = text
        form.data = form.data.copy()
        form.data["json_text"] = text          # show the file's content in the textarea
    try:
        return parse_json_text(text)
    except FriendlyJSONError as e:
        form.error_line = e.line
        form.error_column = e.column
        form.error_line_text = e.line_text
        raise forms.ValidationError(e.message)


class JsonRecordForm(forms.Form):
    title = forms.CharField(label=_("Title"), max_length=255,
                            widget=forms.TextInput(attrs={"placeholder": _("e.g. My quiz answers")}))
    category = forms.CharField(label=_("Category (optional)"), max_length=100, required=False,
                               widget=forms.TextInput(attrs={"placeholder": _("e.g. quiz, survey, notes")}))
    json_text = forms.CharField(label=_("Your JSON"), required=False,
                                widget=forms.Textarea(attrs={"rows": 14, "spellcheck": "false", "id": "json-box"}))
    json_file = forms.FileField(label=_("…or upload a .json file"), required=False,
                                widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}))

    error_line = None
    error_column = None
    error_line_text = ""

    def clean(self):
        cleaned = super().clean()
        try:
            data = _read_json_input(cleaned, self)
        except forms.ValidationError as e:
            self.add_error("json_text", e)
            return cleaned
        problem = check_data_rules(data)
        if problem:
            self.add_error("json_text", problem)
        cleaned["data"] = data
        return cleaned


class CourseImportForm(forms.Form):
    json_text = forms.CharField(label=_("Course JSON"), required=False,
                                widget=forms.Textarea(attrs={"rows": 18, "spellcheck": "false", "id": "json-box"}))
    json_file = forms.FileField(label=_("…or upload a .json file"), required=False,
                                widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}))
    update_existing = forms.BooleanField(
        label=_("If a course with the same number already exists, replace its content"), required=False)

    error_line = None
    error_column = None
    error_line_text = ""

    def clean(self):
        cleaned = super().clean()
        try:
            cleaned["data"] = _read_json_input(cleaned, self)
        except forms.ValidationError as e:
            self.add_error("json_text", e)
        return cleaned


class TeacherCommentForm(forms.Form):
    teacher_comment = forms.CharField(label=_("Comment for the student"), required=False, max_length=5000,
                                      widget=forms.Textarea(attrs={"rows": 3}))
