from django import forms
from home.models import StudentLoginInfo, Subject, TeacherInfo
from django.core.exceptions import ValidationError

class StudentForm(forms.ModelForm):
    username = forms.CharField(max_length=120, help_text="Enter Name:")
    roll_number = forms.CharField(max_length=9, help_text="Roll no: ")
    dob = forms.DateField(help_text="Date of Birth")
    gender = forms.CharField(max_length=10, help_text="Gender")


    class Meta:
        model = StudentLoginInfo
        fields = ['username', 'roll_number', 'dob', 'department', 'program', 'gender', 'password', 'photo']
        exclude = ('department','program',)

class SubjectChipsWidget(forms.TextInput):
    """Posts one value per chip, so the field reads back a list of names."""

    def value_from_datadict(self, data, files, name):
        if hasattr(data, "getlist"):
            return data.getlist(name)
        return data.get(name)


class SubjectChipsField(forms.Field):
    """Subject names typed in one at a time and posted as removable chips.

    A plain string is still accepted and still splits on commas, so the field
    works unchanged when JavaScript never runs.
    """

    widget = SubjectChipsWidget

    def to_python(self, value):
        if value in self.empty_values:
            return []
        if isinstance(value, str):
            value = [value]

        max_length = Subject._meta.get_field("sub_name").max_length
        names, seen = [], set()
        for entry in value:
            for part in str(entry).split(","):
                name = part.strip()
                if not name or name.casefold() in seen:
                    continue
                if len(name) > max_length:
                    raise ValidationError(
                        "Keep each subject under %d characters." % max_length
                    )
                seen.add(name.casefold())
                names.append(name)
        return names


## 78 batch
class TeacherInfoForm(forms.ModelForm):

    password = forms.CharField(widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=True)
    # The shared Subject pool starts out empty, so the checkbox list alone gave a
    # professor nothing to tick and no way to register. This lets them type the
    # subject they teach even when no such row exists yet.
    new_subjects = SubjectChipsField(
        required=False,
        label="Add your own subject",
    )

    class Meta:
        model = TeacherInfo
        fields = ['name', 'title', 'phone', 'email', 'department', 'images', 'subjects']

        widgets = {
            'subjects': forms.CheckboxSelectMultiple(),  # Or use forms.SelectMultiple() if you prefer a dropdown
        }

    # Keep the subject inputs together, directly under the profile image field.
    field_order = [
        'name', 'title', 'phone', 'email', 'department', 'images',
        'subjects', 'new_subjects', 'password', 'confirm_password',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ticking a box is now optional: typing a subject is an equal way in.
        self.fields['subjects'].required = False

    def save_new_subjects(self, teacher_info):
        """Attach the typed-in subjects. Call after ``save_m2m()``.

        Existing rows are reused case-insensitively, matching ``addSubjects``,
        so the shared pool does not fill up with "DBMS" / "dbms" duplicates.
        """
        for name in self.cleaned_data.get("new_subjects") or []:
            subject = Subject.objects.filter(sub_name__iexact=name).first()
            if subject is None:
                subject = Subject.objects.create(sub_name=name)
            teacher_info.subjects.add(subject)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise ValidationError("Passwords do not match")
        return cleaned_data
