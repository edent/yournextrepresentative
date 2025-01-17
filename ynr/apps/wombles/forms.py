from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class LoginForm(forms.Form):
    """
    Login form for a User.
    """

    email = forms.EmailField(required=True)

    def clean_email(self):
        """
        Normalize the entered email
        """
        email = self.cleaned_data["email"]
        return User.objects.normalize_email(email)


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username",)

    username = forms.CharField(
        max_length=50,
        help_text="Your username is displayed publicly. We don't accept email addresses or '@' symbols",
    )

    def __init__(self, *args, **kwargs):
        super(UserProfileForm, self).__init__(*args, **kwargs)
        # We add a fake username before people first sign up. Don't show this to the user and ask them to
        # enter their own
        if self.initial and self.initial.get("username", "").startswith("@@"):
            self.initial["username"] = ""

    def clean_username(self):
        username = self.cleaned_data["username"]

        if "@" in username:
            raise ValidationError(
                "Usernames can't be email addresses or contain an '@' symbol"
            )

        user = User.objects.filter(username__iexact=username)
        if user:
            raise ValidationError("A user with that username already exists.")
        return username
