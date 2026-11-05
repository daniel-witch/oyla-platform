from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


class Announcement(models.Model):
    """One article on the Announcements board (the platform's 'newspaper').

    Teachers, coaches and admins publish; everyone reads. Guides (how-tos)
    live here too, under the GUIDE category.
    """

    class Category(models.TextChoices):
        NEWS = "news", "News"
        GUIDE = "guide", "Guide"
        EVENT = "event", "Event"
        NOTICE = "notice", "Notice"

    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=300, blank=True,
                               help_text="One or two sentences shown on the front page.")
    body = models.TextField()
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.NEWS)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="announcements")
    is_pinned = models.BooleanField(default=False, help_text="Pinned articles become the front-page headline.")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def author_name(self):
        return self.author.display_name if self.author else "Oyla Team"

    @property
    def lead(self):
        return self.summary or (self.body[:220] + ("…" if len(self.body) > 220 else ""))


class Message(models.Model):
    """The integrated mailing system: one message from one user to another.

    Every message is also sent as a real email to the recipient's address
    (printed in the terminal while EMAIL_BACKEND is the console backend).
    """

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="received_messages")
    subject = models.CharField(max_length=200)
    body = models.TextField()
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed = models.BooleanField(default=False, help_text="True once the email copy was handed to the mail server.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender} → {self.recipient}: {self.subject}"

    @property
    def is_read(self):
        return self.read_at is not None

    def mark_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])

    def send_email_copy(self):
        """Email the recipient a copy. Never breaks sending if the mail server fails."""
        if not self.recipient.email:
            return False
        try:
            send_mail(
                subject=f"[Oyla] {self.subject}",
                message=(f"{self.sender.display_name} sent you a message on Oyla Platform:\n\n"
                         f"{self.body}\n\n— Reply inside Oyla: Mail → Inbox"),
                from_email=None,
                recipient_list=[self.recipient.email],
                fail_silently=False,
            )
        except Exception:
            return False
        Message.objects.filter(pk=self.pk).update(emailed=True)
        self.emailed = True
        return True
