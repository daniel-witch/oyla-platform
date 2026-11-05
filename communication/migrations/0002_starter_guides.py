from django.db import migrations

GUIDES = [
    {
        "title": "Welcome to Oyla Platform",
        "summary": "Everything you need to start: your enrollments, the study module, mail and announcements.",
        "category": "notice",
        "is_pinned": True,
        "body": (
            "Welcome! Here is how the platform is organised.\n\n"
            "• My Enrollments – your courses. Open a course to see its modules, open a module to see its lessons and steps.\n"
            "• Study Module – the programme of each course: its modules, lessons and how many steps of each kind they contain.\n"
            "• Announcements – this page. News, events and guides from your teachers and coaches.\n"
            "• Mail – send messages to your teacher, coach or classmates. A copy of every message is also emailed.\n"
            "• Feedback – students and teachers can write feedback to each other.\n\n"
            "Click your avatar (top right) to see your personal information and your personal ID."
        ),
    },
    {
        "title": "How to join a class",
        "summary": "You can only join a class through an invite link from your teacher or coach.",
        "category": "guide",
        "is_pinned": False,
        "body": (
            "1. Your teacher or coach creates an invite link for your class (Invite links in their menu).\n"
            "2. They send you the link, for example https://<site>/join/abc123…\n"
            "3. Open the link. If you are not logged in, log in or sign up first – you will come back to the link automatically.\n"
            "4. The class and its course appear in My Enrollments.\n\n"
            "You can also paste the link (or just its code) into the 'Join a class' box on My Enrollments."
        ),
    },
    {
        "title": "How modules unlock and how steps are completed",
        "summary": "Finish every step of the current module to unlock the next one. Completed steps can't be undone.",
        "category": "guide",
        "is_pinned": False,
        "body": (
            "• Inside your current module, every lesson is open.\n"
            "• The next module unlocks when every step of the current one is completed (quiz and practice "
            "answers count once submitted; if a teacher asks for a revision, resubmit it).\n"
            "• Video and text steps: press 'Mark complete'. Videos are completed automatically when they end.\n"
            "• Quiz and practice steps: write your answer and submit it for review.\n"
            "• A completed step stays completed – there is no undo."
        ),
    },
]


def add_guides(apps, schema_editor):
    Announcement = apps.get_model("communication", "Announcement")
    for g in GUIDES:
        Announcement.objects.get_or_create(title=g["title"], defaults=g)


def remove_guides(apps, schema_editor):
    Announcement = apps.get_model("communication", "Announcement")
    Announcement.objects.filter(title__in=[g["title"] for g in GUIDES], author=None).delete()


class Migration(migrations.Migration):
    dependencies = [("communication", "0001_initial")]
    operations = [migrations.RunPython(add_guides, remove_guides)]
