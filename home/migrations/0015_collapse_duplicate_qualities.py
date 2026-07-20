from django.db import migrations


def collapse_duplicate_qualities(apps, schema_editor):
    """Keep one Qualities row per Application before the unique constraint lands.

    ``studentform2`` deletes-then-recreates, so the highest pk is the current
    row; anything lower is an orphan left by a previously failed cycle.
    """
    Qualities = apps.get_model("home", "Qualities")
    seen = set()
    for row in Qualities.objects.order_by("application_id", "-id"):
        if row.application_id in seen:
            print(
                f"  dropping duplicate Qualities id={row.id} "
                f"for application {row.application_id}"
            )
            row.delete()
        else:
            seen.add(row.application_id)


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0014_customtemplates_template_system_xor_owned"),
    ]

    operations = [
        # Irreversible by nature: deleted rows cannot be resurrected, and
        # pretending otherwise in a reverse handler would be dishonest.
        migrations.RunPython(
            collapse_duplicate_qualities, migrations.RunPython.noop
        ),
    ]
