from django.db import migrations


def link_by_full_name(apps, schema_editor):
    """Match each TeacherInfo to the User whose full name ends in /<unique_id>.

    This is the convention loginTeacher has relied on: a teacher's User has a
    name of the form "Full Name/<unique_id>".
    """
    TeacherInfo = apps.get_model("home", "TeacherInfo")
    User = apps.get_model("auth", "User")

    taken = set(
        TeacherInfo.objects.filter(user__isnull=False).values_list("user_id", flat=True)
    )
    for teacher in TeacherInfo.objects.filter(user__isnull=True):
        if not teacher.unique_id:
            continue
        suffix = f"/{teacher.unique_id}"
        for user in User.objects.all():
            if user.id in taken:
                continue
            full = f"{user.first_name} {user.last_name}".strip()
            if full.endswith(suffix) or user.first_name.endswith(suffix):
                teacher.user_id = user.id
                teacher.save(update_fields=["user"])
                taken.add(user.id)
                break


def unlink(apps, schema_editor):
    TeacherInfo = apps.get_model("home", "TeacherInfo")
    TeacherInfo.objects.update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0017_teacherinfo_user"),
    ]

    operations = [
        migrations.RunPython(link_by_full_name, unlink),
    ]
