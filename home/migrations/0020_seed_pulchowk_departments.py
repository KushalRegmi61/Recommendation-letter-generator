from django.db import migrations

# Pulchowk Campus (IOE) departments and their bachelor-level programs.
# Mechanical and Aerospace is kept as a single combined department (per the
# chosen structure), holding both BME and BAME.
DEPARTMENTS = {
    "Civil": ["BCE"],
    "Electronics and Computer": ["BCT", "BEI"],
    "Electrical": ["BEL"],
    "Mechanical and Aerospace": ["BME", "BAME"],
    "Chemical Engineering": ["BCH"],
    "Architecture": ["BArch"],
}


def seed(apps, schema_editor):
    Department = apps.get_model("home", "Department")
    Program = apps.get_model("home", "Program")
    StudentLoginInfo = apps.get_model("home", "StudentLoginInfo")

    # The legacy aerospace program was stored as "BAS". Rename it to the standard
    # "BAME" when it is unused and BAME does not already exist, so we don't leave
    # two aerospace rows or orphan any student.
    bas = Program.objects.filter(program_name="BAS").first()
    if (
        bas is not None
        and not StudentLoginInfo.objects.filter(program=bas).exists()
        and not Program.objects.filter(program_name="BAME").exists()
    ):
        bas.program_name = "BAME"
        bas.save()

    # Ensure every department and its programs exist (idempotent).
    for dept_name, progs in DEPARTMENTS.items():
        dept, _ = Department.objects.get_or_create(dept_name=dept_name)
        for pname in progs:
            # program_name is globally unique; get_or_create avoids duplicates.
            Program.objects.get_or_create(
                program_name=pname, defaults={"department": dept}
            )

    # Drop the leftover test department "ZZ" if nothing references it.
    zz = Department.objects.filter(dept_name="ZZ").first()
    if (
        zz is not None
        and not StudentLoginInfo.objects.filter(department=zz).exists()
        and not Program.objects.filter(department=zz).exists()
    ):
        zz.delete()


def unseed(apps, schema_editor):
    # Data-only seed; reversing would risk deleting rows students depend on,
    # so leave the seeded departments/programs in place.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0019_application_gender_application_program"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
