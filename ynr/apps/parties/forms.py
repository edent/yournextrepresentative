from django import forms
from django.core.exceptions import ValidationError

from parties.models import Party
from people.forms.fields import CurrentUnlockedBallotsField


class PartyIdentifierInput(forms.CharField):
    def clean(self, value):
        if not value:
            return value
        try:
            return (
                Party.objects.current().get(ec_id__iexact=value.strip()).ec_id
            )
        except Party.DoesNotExist:
            raise ValidationError(
                f"'{value}' is not a current party " f"identifier"
            )


class PartySelectField(forms.MultiWidget):
    def __init__(self, choices, attrs=None):
        widgets = [
            forms.Select(
                choices=choices,
                attrs={"disabled": True, "class": "party_widget_select"},
            ),
            forms.TextInput(attrs={"class": "party_widget_input"}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return value
        else:
            return ["", ""]


class PartyIdentifierField(forms.MultiValueField):
    def compress(self, data_list):
        if data_list:
            return self.to_python([v for v in data_list if v][-1])
        return None

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop("choices", Party.objects.default_party_choices())

        kwargs["require_all_fields"] = False
        kwargs["label"] = "Party"

        fields = (
            forms.ChoiceField(required=False, disabled=True),
            PartyIdentifierInput(required=False),
        )
        super().__init__(fields, *args, **kwargs)
        self.widget = PartySelectField(choices=choices)
        self.widget.widgets[0].choices = choices
        self.fields[0].choices = choices

    def to_python(self, value):
        if not value:
            return value
        return Party.objects.get(ec_id=value)


class PopulatePartiesMixin:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        register = None
        for field_name, field_class in self.fields.items():
            if not isinstance(field_class, CurrentUnlockedBallotsField):
                continue
            if field_name in self.initial:
                ballot = field_class.to_python(self.initial[field_name])
                register = ballot.post.party_set.slug

        # Popluate the choices
        for field_name, field_class in self.fields.items():
            if not isinstance(field_class, PartyIdentifierField):
                continue

            if field_name not in self.initial:
                continue

            initial_for_field = self.initial[field_name]

            if not isinstance(initial_for_field, (list, tuple)):
                continue

            if not len(initial_for_field) == 2:
                continue

            extra_party_id = initial_for_field[1]
            if not extra_party_id:
                continue

            # Set the initial value of the select
            self.initial[field_name][0] = extra_party_id

            choices = Party.objects.default_party_choices(register)
            existing_ids = []
            for p_id, value in choices:
                if isinstance(value, list):
                    for item in value:
                        existing_ids.append(item[0])
                else:
                    existing_ids.append(p_id)
            already_in_select = extra_party_id in existing_ids

            if not already_in_select:
                extra_party = Party.objects.get(ec_id=extra_party_id).name
                choices.insert(1, (extra_party_id, extra_party))
            self.fields[field_name] = PartyIdentifierField(choices=choices)
            self.fields[field_name].fields[0].choices = choices
