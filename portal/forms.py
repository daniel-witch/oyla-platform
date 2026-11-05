from django import forms
from django.contrib.auth import password_validation


class SignUpForm(forms.Form):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("teacher", "Teacher"),
        ("coach", "Coach"),
    ]

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=True, help_text="A verification code will be sent here.")
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("confirm_password"):
            if cleaned["password"] != cleaned["confirm_password"]:
                raise forms.ValidationError("Passwords don't match.")
        return cleaned

    def clean_password(self):
        password = self.cleaned_data["password"]
        password_validation.validate_password(password)
        return password

    def clean_username(self):
        from users.models import User
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username


class VerifyCodeForm(forms.Form):
    code = forms.CharField(max_length=6, min_length=6, label="Verification code")
