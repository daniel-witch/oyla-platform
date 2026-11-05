from django.db import migrations


def fill_codes(apps, schema_editor):
    """Give every existing Student/Teacher/Coach their personal ID."""
    for model_name, field, prefix in (("Student", "student_code", "STU"),
                                      ("Teacher", "teacher_code", "TCH"),
                                      ("Coach", "coach_code", "CCH")):
        Model = apps.get_model("users", model_name)
        for obj in Model.objects.filter(**{f"{field}__isnull": True}):
            Model.objects.filter(pk=obj.pk).update(**{field: f"{prefix}-{obj.pk:05d}"})


class Migration(migrations.Migration):
    dependencies = [("users", "0005_coach_coach_code_student_student_code_and_more")]
    operations = [migrations.RunPython(fill_codes, migrations.RunPython.noop)]
