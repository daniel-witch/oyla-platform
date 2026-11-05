"""Announcements board (#8, a newspaper-style page) and Mail (#12)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from users.models import User

from .models import Announcement, Message


def can_publish(user):
    return getattr(user, "role", None) in ("teacher", "coach") or user.is_superuser or user.is_staff


# ------------------------------------------------------------ announcements

class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "category", "summary", "body", "is_pinned"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10}), "summary": forms.TextInput()}
        labels = {"is_pinned": "Make this the front-page headline"}


@login_required
def announcements(request):
    category = request.GET.get("category", "")
    items = Announcement.objects.select_related("author")
    if category in Announcement.Category.values:
        items = items.filter(category=category)
    items = list(items)
    lead = items[0] if items else None
    return render(request, "communication/announcements.html", {
        "lead": lead, "secondary": items[1:4], "rest": items[4:],
        "categories": Announcement.Category.choices, "category": category,
        "guides": Announcement.objects.filter(category=Announcement.Category.GUIDE)[:6],
        "can_publish": can_publish(request.user),
    })


@login_required
def announcement_detail(request, pk):
    item = get_object_or_404(Announcement.objects.select_related("author"), pk=pk)
    if request.method == "POST" and request.POST.get("action") == "delete":
        if item.author_id == request.user.pk or request.user.is_superuser:
            item.delete()
            messages.info(request, "Announcement deleted.")
            return redirect("announcements")
    return render(request, "communication/announcement_detail.html", {
        "item": item,
        "can_delete": item.author_id == request.user.pk or request.user.is_superuser,
        "more": Announcement.objects.exclude(pk=item.pk)[:4],
    })


@login_required
def announcement_new(request):
    if not can_publish(request.user):
        messages.error(request, "Only teachers, coaches and admins can publish announcements.")
        return redirect("announcements")
    form = AnnouncementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.author = request.user
        item.save()
        messages.info(request, "Announcement published.")
        return redirect("announcement_detail", pk=item.pk)
    return render(request, "communication/announcement_form.html", {"form": form})


# ------------------------------------------------------------ mail

def _recipients(user):
    return User.objects.filter(is_active=True).exclude(pk=user.pk).order_by("role", "first_name", "username")


@login_required
def mail_inbox(request):
    items = Message.objects.filter(recipient=request.user).select_related("sender")
    q = request.GET.get("q", "").strip()
    if q:
        items = items.filter(Q(subject__icontains=q) | Q(body__icontains=q) | Q(sender__username__icontains=q))
    return render(request, "communication/mail_list.html", {"items": items, "box": "inbox", "q": q})


@login_required
def mail_sent(request):
    items = Message.objects.filter(sender=request.user).select_related("recipient")
    return render(request, "communication/mail_list.html", {"items": items, "box": "sent", "q": ""})


@login_required
def mail_detail(request, pk):
    msg = get_object_or_404(
        Message.objects.select_related("sender", "recipient"),
        Q(sender=request.user) | Q(recipient=request.user), pk=pk,
    )
    if msg.recipient_id == request.user.pk:
        msg.mark_read()
    thread = []
    p = msg.parent
    while p is not None and len(thread) < 20:
        thread.append(p)
        p = p.parent
    return render(request, "communication/mail_detail.html", {"msg": msg, "thread": thread})


@login_required
def mail_compose(request):
    recipients = _recipients(request.user)
    parent = None
    if request.GET.get("reply"):
        parent = Message.objects.filter(
            Q(sender=request.user) | Q(recipient=request.user), pk=request.GET["reply"]).first()

    if request.method == "POST":
        to = recipients.filter(pk=request.POST.get("to")).first()
        subject = request.POST.get("subject", "").strip()
        body = request.POST.get("body", "").strip()
        parent = Message.objects.filter(
            Q(sender=request.user) | Q(recipient=request.user), pk=request.POST.get("parent") or 0).first()
        if not to:
            messages.error(request, "Choose who to send the message to.")
        elif not subject or not body:
            messages.error(request, "Write a subject and a message.")
        else:
            msg = Message.objects.create(sender=request.user, recipient=to, subject=subject[:200],
                                         body=body, parent=parent)
            emailed = msg.send_email_copy()
            messages.info(request, f"Message sent to {to.display_name}"
                                   + (" (an email copy was sent too)." if emailed else "."))
            return redirect("mail_sent")
        initial = {"to": request.POST.get("to", ""), "subject": subject, "body": body}
    else:
        to_id = request.GET.get("to", "")
        subject = ""
        if parent:
            other = parent.sender if parent.recipient_id == request.user.pk else parent.recipient
            to_id = str(other.pk)
            subject = parent.subject if parent.subject.lower().startswith("re:") else f"Re: {parent.subject}"
        initial = {"to": to_id, "subject": subject, "body": ""}

    return render(request, "communication/mail_compose.html", {
        "recipients": recipients, "initial": initial, "parent": parent,
    })
