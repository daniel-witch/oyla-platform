from django.conf import settings
from django.db import models


class JsonRecord(models.Model):
    """Any piece of JSON a user saves (quiz answers, notes, survey results...).

    `data` is a JSONField, which Django stores natively on both SQLite and
    Postgres, so the same code works locally and on Render.
    """

    title = models.CharField(max_length=255)
    category = models.CharField(
        max_length=100, blank=True,
        help_text='Optional label for grouping, e.g. "quiz", "curriculum", "survey".',
    )
    data = models.JSONField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="json_records",
    )
    teacher_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "JSON record"
        verbose_name_plural = "JSON records"

    def __str__(self):
        return self.title
