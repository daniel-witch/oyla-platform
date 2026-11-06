from datetime import datetime

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from catalog.models import Step
from catalog.mcq import format_pairs, grade, parse_pairs
from enrollment.models import StepCompletion, Feedback, Meetup, Group
from django.http import Http404, JsonResponse
from users.models import EmailVerificationCode, Student
from users.verification import (
    make_pending_signup_token,
    read_pending_signup_token,
    send_verification_email,
    create_role_user_from_payload,
)

from .access import student_can_open_step
from .progress import build_progress
from .calendar_utils import CalEvent, build_month_calendar, upcoming_events
from .forms import SignUpForm, VerifyCodeForm

PENDING_SESSION_KEY = "pending_signup_token"


def signup(request):
    """Step 1: collect role/username/password/email, send a verification code."""
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            token = make_pending_signup_token(data)
            code_obj = EmailVerificationCode.issue(data["email"])
            send_verification_email(data["email"], code_obj.code)
            request.session[PENDING_SESSION_KEY] = token
            messages.info(
                request,
                "We sent a 6-digit verification code to your email. "
                "(Running locally? Check the terminal running 'runserver' - that's where the code is printed.)",
            )
            return redirect("signup_verify")
    else:
        form = SignUpForm()

    return render(request, "portal/signup.html", {"form": form})


def signup_verify(request):
    """Step 2: confirm the code, then actually create the Student/Teacher/Coach."""
    token = request.session.get(PENDING_SESSION_KEY)
    if not token:
        messages.error(request, "No signup in progress. Please sign up first.")
        return redirect("signup")

    try:
        payload = read_pending_signup_token(token)
    except signing.SignatureExpired:
        del request.session[PENDING_SESSION_KEY]
        messages.error(request, "Your verification code expired. Please sign up again.")
        return redirect("signup")
    except signing.BadSignature:
        del request.session[PENDING_SESSION_KEY]
        messages.error(request, "Something went wrong. Please sign up again.")
        return redirect("signup")

    form = VerifyCodeForm(request.POST or None)
    error = None

    if request.method == "POST":
        if "resend" in request.POST:
            code_obj = EmailVerificationCode.issue(payload["email"])
            send_verification_email(payload["email"], code_obj.code)
            messages.info(request, "A new code was sent.")
        elif form.is_valid():
            code = form.cleaned_data["code"]
            if EmailVerificationCode.verify_and_consume(payload["email"], code):
                user = create_role_user_from_payload(payload)
                del request.session[PENDING_SESSION_KEY]
                login(request, user)
                if request.session.get("pending_invite"):
                    return redirect("join_class", token=request.session.pop("pending_invite"))
                return redirect("dashboard")
            else:
                error = "That code is incorrect or has expired."

    return render(request, "portal/signup_verify.html", {
        "form": form, "email": payload["email"], "error": error,
    })


@login_required
def dashboard(request):
    user = request.user
    role = user.role
    today = timezone.localdate()

    context = {"user": user, "role": role}

    if request.session.get("pending_invite") and role == "student":
        return redirect("join_class", token=request.session.pop("pending_invite"))

    if role == "student":
        # Students' home is "My Enrollments" (courses -> modules -> lessons).
        return redirect("enrollments")

    if role == "teacher":
        teacher = user.teacher
        context["teacher"] = teacher
        class_sessions = list(
            teacher.class_sessions.select_related("course").prefetch_related("groups__student")
        )
        context["class_sessions"] = class_sessions

        # Students in this teacher's classes who have no feedback yet, or the
        # oldest feedback - simple "needs attention" ordering.
        roster = []
        seen_student_ids = set()
        for cs in class_sessions:
            for g in cs.groups.all():
                if g.student_id in seen_student_ids:
                    continue
                seen_student_ids.add(g.student_id)
                last_feedback = g.student.feedbacks_received.filter(teacher=teacher, direction=Feedback.Direction.TEACHER_TO_STUDENT).order_by("-created_at").first()
                roster.append({"student": g.student, "class_session": cs, "last_feedback": last_feedback})
        never_given = timezone.make_aware(datetime(2000, 1, 1))
        roster.sort(key=lambda r: r["last_feedback"].created_at if r["last_feedback"] else never_given)
        context["roster"] = roster

        context["pending_submissions"] = list(
            StepCompletion.objects.filter(
                status=StepCompletion.Status.PENDING, student_id__in=seen_student_ids,
            ).select_related("student", "step__lesson__module").order_by("completed_at")
        )

        events = [
            CalEvent(when=cs.start_date, title=cs.name, meta=cs.course.name, kind="live", link=cs.join_link)
            for cs in class_sessions
        ]
        weeks, month_label = build_month_calendar(today, events)
        context.update({
            "cal_weeks": weeks, "cal_month_label": month_label,
            "upcoming": upcoming_events(today, events),
        })

    elif role == "coach":
        coach = user.coach
        context["coach"] = coach
        groups = list(coach.class_groups.select_related("student", "class_session__course"))
        context["groups"] = groups
        context["meetup_requests"] = coach.meetups.filter(status=Meetup.Status.REQUESTED).select_related("student")
        context["scheduled_meetups"] = coach.meetups.filter(status=Meetup.Status.SCHEDULED).select_related("student")

        coached_student_ids = [g.student_id for g in groups]
        context["pending_submissions"] = list(
            StepCompletion.objects.filter(
                status=StepCompletion.Status.PENDING, student_id__in=coached_student_ids,
            ).select_related("student", "step__lesson__module").order_by("completed_at")
        )

        events = [
            CalEvent(
                when=m.scheduled_time,
                title=f"Meetup: {m.student.get_full_name() or m.student.username}",
                meta=m.notes or "Scheduled meetup", kind="meetup", link=m.join_link,
            )
            for m in coach.meetups.filter(status=Meetup.Status.SCHEDULED).exclude(scheduled_time=None)
        ]
        weeks, month_label = build_month_calendar(today, events)
        context.update({
            "cal_weeks": weeks, "cal_month_label": month_label,
            "upcoming": upcoming_events(today, events),
        })

    template_name = f"portal/dashboard_{role}.html" if role in ("student", "teacher", "coach") else "portal/dashboard_unknown.html"
    return render(request, template_name, context)


def _wants_json(request):
    """True for background (fetch) requests from the page's JavaScript."""
    return (request.headers.get("x-requested-with") in ("fetch", "XMLHttpRequest")
            or "application/json" in request.headers.get("accept", ""))


@login_required
def student_progress(request):
    """GET /progress/ - the logged-in student's live progress as JSON.
    The dashboard calls this to update itself without a page refresh."""
    if getattr(request.user, "role", None) != "student":
        return JsonResponse({"detail": "Only students have progress."}, status=403)
    return JsonResponse(build_progress(request.user.student))


@login_required
def step_detail(request, step_id):
    """Every step opens on its own page, in its own tab.

    - Student: see the full step content. Video/text steps have a simple
      "Mark complete" toggle. Quiz/practice steps are a real submission -
      the student types an answer and submits it; it goes to PENDING until
      a teacher or coach reviews it.
    - Teacher/coach: instead of the student's view, see every submission
      their own students have made on this step, with Approve / Needs
      revision controls.
    """
    step = get_object_or_404(
        Step.objects.select_related("lesson__module__course", "resource"), pk=step_id
    )
    role = getattr(request.user, "role", None)
    # Quiz/practice steps take an answer - and so does any step with multiple-choice questions
    # (e.g. a video or text step followed by 3 questions).
    needs_review = step.step_type in (Step.StepType.QUIZ, Step.StepType.PRACTICE) or step.mcq is not None

    if role == "student":
        student = request.user.student
        allowed, reason = student_can_open_step(student, step)
        if not allowed:
            if _wants_json(request):
                return JsonResponse({"ok": False, "message": reason}, status=403)
            messages.error(request, reason)
            return redirect("enrollments")

        completion = StepCompletion.objects.filter(student=student, step=step).first()

        if request.method == "POST":
            # Completing a step is one-way: there is no "undo". Video/text steps can
            # only be marked complete; quiz/practice answers can only be (re)submitted
            # while there is no answer yet or the reviewer asked for a revision.
            ok, msg = True, ""
            mcq = step.mcq if needs_review else None
            if mcq:
                # Multiple choice: checked at once, so the student can review mistakes straight away.
                chosen = {}
                for q in mcq["questions"]:
                    letter = request.POST.get(f"q{q['number']}", "").strip().upper()
                    if letter in [o["letter"] for o in q["options"]]:
                        chosen[q["number"]] = letter
                if completion and completion.status != StepCompletion.Status.REJECTED:
                    ok, msg = False, "You already submitted this step — it can't be changed or undone."
                elif len(chosen) < len(mcq["questions"]):
                    ok, msg = False, "Choose an answer for every question before submitting."
                else:
                    score, total, _ = grade(mcq, chosen)
                    StepCompletion.objects.update_or_create(
                        student=student, step=step,
                        defaults={
                            "answer": format_pairs(chosen),
                            "status": StepCompletion.Status.APPROVED,
                            "reviewed_by": None, "reviewed_at": timezone.now(),
                            "review_note": f"Checked automatically: {score} of {total} correct.",
                        },
                    )
                    msg = f"Checked: {score} of {total} correct."
            elif needs_review:
                answer = request.POST.get("answer", "").strip()
                if completion and completion.status != StepCompletion.Status.REJECTED:
                    ok, msg = False, "You already submitted this step — it can't be changed or undone."
                elif not answer:
                    ok, msg = False, "Write an answer before submitting."
                else:
                    StepCompletion.objects.update_or_create(
                        student=student, step=step,
                        defaults={
                            "answer": answer,
                            "status": StepCompletion.Status.PENDING,
                            "reviewed_by": None, "reviewed_at": None, "review_note": "",
                        },
                    )
                    msg = "Submitted — your teacher or coach will review it."
            else:
                if completion:
                    msg = "This step is already completed."
                else:
                    StepCompletion.objects.create(
                        student=student, step=step, status=StepCompletion.Status.APPROVED,
                    )
                    msg = "Step completed ✓"

            if _wants_json(request):
                completion = StepCompletion.objects.filter(student=student, step=step).first()
                return JsonResponse({
                    "ok": ok, "message": msg, "step_id": step.id,
                    "status": completion.status if completion else None,
                    "answer": completion.answer if completion else "",
                    "progress": build_progress(student),
                }, status=200 if ok else 400)
            (messages.info if ok else messages.error)(request, msg)
            return redirect("step_detail", step_id=step.id)

        lesson_steps = list(step.lesson.steps.all())
        idx = [x.pk for x in lesson_steps].index(step.pk)
        mcq = step.mcq if needs_review else None
        mcq_score = mcq_total = mcq_results = None
        if mcq and completion and completion.answer:
            mcq_score, mcq_total, mcq_results = grade(mcq, parse_pairs(completion.answer))
        return render(request, "portal/step_detail.html", {
            "step": step, "completion": completion, "needs_review": needs_review,
            "mcq": mcq, "mcq_score": mcq_score, "mcq_total": mcq_total, "mcq_results": mcq_results,
            "can_submit": needs_review and (completion is None or completion.status == StepCompletion.Status.REJECTED),
            "prev_step": lesson_steps[idx - 1] if idx > 0 else None,
            "next_step": lesson_steps[idx + 1] if idx + 1 < len(lesson_steps) else None,
        })

    elif role in ("teacher", "coach") or request.user.is_staff or request.user.is_superuser:
        if role == "teacher":
            my_student_ids = Group.objects.filter(
                class_session__teacher=request.user.teacher
            ).values_list("student_id", flat=True)
        elif role == "coach":
            my_student_ids = Group.objects.filter(
                coach=request.user.coach
            ).values_list("student_id", flat=True)
        else:
            # Admin accounts (no role): see and review every student's submissions.
            my_student_ids = Student.objects.values_list("id", flat=True)

        if request.method == "POST":
            completion = get_object_or_404(
                StepCompletion, pk=request.POST.get("completion_id"), step=step,
                student_id__in=my_student_ids,
            )
            action = request.POST.get("action")
            if action in ("approve", "reject"):
                completion.status = (
                    StepCompletion.Status.APPROVED if action == "approve" else StepCompletion.Status.REJECTED
                )
                completion.reviewed_by = request.user
                completion.reviewed_at = timezone.now()
                completion.review_note = request.POST.get("review_note", "").strip()
                completion.save()
                messages.info(request, "Review saved.")
            return redirect("step_detail", step_id=step.id)

        submissions = StepCompletion.objects.filter(
            step=step, student_id__in=my_student_ids,
        ).select_related("student").order_by("-completed_at")
        return render(request, "portal/step_detail_review.html", {
            "step": step, "submissions": submissions, "needs_review": needs_review,
        })

    raise Http404


@login_required
def give_feedback(request, student_id):
    """Teacher writes a short feedback note for one of their students.

    Only a teacher may call this, and only for a student who is actually
    in one of their class sessions (not just any student in the system).
    """
    if request.method != "POST" or getattr(request.user, "role", None) != "teacher":
        return redirect("dashboard")

    teacher = request.user.teacher
    content = request.POST.get("content", "").strip()
    in_a_class = Group.objects.filter(class_session__teacher=teacher, student_id=student_id).exists()

    if not in_a_class:
        messages.error(request, "That student isn't in one of your classes.")
    elif not content:
        messages.error(request, "Feedback can't be empty.")
    else:
        student = get_object_or_404(Student, pk=student_id)
        Feedback.objects.create(teacher=teacher, student=student, content=content)
        messages.info(request, f"Feedback sent to {student.get_full_name() or student.username}.")

    return redirect("dashboard")


@login_required
def respond_meetup(request, meetup_id):
    """Coach accepts (schedules) or declines a meetup request.

    'Schedule' expects a datetime-local input (`scheduled_time`) and an
    optional real Google Meet link (`meeting_link`) - left blank, the
    student/coach fall back to an instant Meet link automatically.
    """
    if request.method != "POST" or getattr(request.user, "role", None) != "coach":
        return redirect("dashboard")

    coach = request.user.coach
    meetup = get_object_or_404(Meetup, pk=meetup_id, coach=coach)
    action = request.POST.get("action")

    if action == "schedule":
        raw_time = request.POST.get("scheduled_time")
        parsed = None
        if raw_time:
            naive = datetime.fromisoformat(raw_time)
            parsed = timezone.make_aware(naive) if timezone.is_naive(naive) else naive
        if not parsed:
            messages.error(request, "Pick a date and time to schedule this meetup.")
            return redirect("dashboard")
        meetup.status = Meetup.Status.SCHEDULED
        meetup.scheduled_time = parsed
        meetup.meeting_link = request.POST.get("meeting_link", "").strip()
        meetup.save()
        messages.info(request, "Meetup scheduled.")
    elif action == "decline":
        meetup.status = Meetup.Status.RESOLVED
        meetup.save()
        messages.info(request, "Meetup request declined.")

    return redirect("dashboard")


@login_required
def request_meetup(request):
    """Student requests a meetup with their assigned coach."""
    if request.method != "POST" or getattr(request.user, "role", None) != "student":
        return redirect("dashboard")

    student = request.user.student
    notes = request.POST.get("notes", "").strip()
    group = student.class_groups.exclude(coach=None).select_related("coach").first()
    coach = group.coach if group else None

    if not coach:
        messages.error(request, "You don't have a coach assigned yet.")
    else:
        Meetup.objects.create(student=student, coach=coach, notes=notes)
        messages.info(request, "Meetup requested — your coach will confirm a time.")

    return redirect("dashboard")
