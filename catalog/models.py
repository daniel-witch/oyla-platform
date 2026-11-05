from urllib.parse import urlparse, parse_qs

from django.core.validators import FileExtensionValidator
from django.db import models

VIDEO_EXTENSIONS = ["mp4", "webm", "m4v", "mov", "ogg"]


def youtube_id_from_url(url):
    """Return the 11-character YouTube video id from any common YouTube URL, else ''."""
    if not url:
        return ""
    try:
        u = urlparse(url.strip())
    except ValueError:
        return ""
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    vid = ""
    if host == "youtu.be":
        vid = u.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com", "music.youtube.com"):
        if u.path == "/watch":
            vid = parse_qs(u.query).get("v", [""])[0]
        else:
            parts = [p for p in u.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in ("embed", "shorts", "live", "v"):
                vid = parts[1]
    vid = vid.strip()
    if len(vid) == 11 and all(c.isalnum() or c in "-_" for c in vid):
        return vid
    return ""


class Course(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    number = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.name


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Lesson(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Step(models.Model):
    class StepType(models.TextChoices):
        VIDEO = "video", "Video"
        TEXT = "text", "Text"
        QUIZ = "quiz", "Quiz"
        PRACTICE = "practice", "Practice"

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="steps")
    title = models.CharField(
        max_length=255, blank=True,
        help_text="The step's name. This is the only text students see in lists - "
                  "the content itself appears only after they open the step.",
    )
    step_type = models.CharField(max_length=20, choices=StepType.choices)
    body = models.TextField(blank=True)
    link = models.URLField(blank=True)
    video_file = models.FileField(
        upload_to="step_videos/", blank=True,
        validators=[FileExtensionValidator(VIDEO_EXTENSIONS)],
        help_text="Upload a video (MP4 recommended). It is stored on this server and plays "
                  "inside the app. If empty, a YouTube link in 'link' is played inside the page instead.",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.lesson.name} — {self.display_name}"

    @property
    def display_name(self):
        """The step's name, or 'Step 3 · Video' if no name was given."""
        return self.title or f"Step {self.order} · {self.get_step_type_display()}"

    @property
    def youtube_id(self):
        """YouTube id from this step's link, or else from its resource's link."""
        vid = youtube_id_from_url(self.link)
        if not vid:
            try:
                vid = youtube_id_from_url(self.resource.link)
            except Exception:   # no resource
                vid = ""
        return vid

    @property
    def has_video(self):
        return bool(self.video_file) or bool(self.youtube_id)


class Resource(models.Model):
    class ResourceType(models.TextChoices):
        VIDEO = "video", "Video"
        TEXT = "text", "Text"
        PDF = "pdf", "PDF"
        LINK = "link", "Link"

    step = models.OneToOneField(Step, on_delete=models.CASCADE, related_name="resource")
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    body = models.TextField(blank=True)
    link = models.URLField(blank=True)

    def __str__(self):
        return f"Resource for {self.step}"

    @property
    def youtube_id(self):
        return youtube_id_from_url(self.link)
