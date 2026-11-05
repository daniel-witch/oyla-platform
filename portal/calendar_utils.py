"""Small, dependency-free month-calendar builder shared by all three
dashboards (student/teacher/coach). Turns a flat list of "events"
(class sessions, meetups) into the week-by-week grid the templates render,
plus a short "Upcoming" list.

Kept deliberately simple - no external calendar library - since all we
need is one month, one dot per event type, and a chronological list.
"""
import calendar as _calendar
from dataclasses import dataclass, field
from datetime import date, datetime

from django.utils import timezone as _tz


@dataclass
class CalEvent:
    when: datetime
    title: str
    meta: str
    kind: str  # "live" (class session) or "meetup"
    link: str


@dataclass
class CalDay:
    date: date
    in_month: bool
    is_today: bool
    events: list = field(default_factory=list)


def build_month_calendar(today: date, events: list[CalEvent]):
    """Returns (weeks, month_label) where weeks is a list of 7-CalDay lists
    (Monday-first, like the mockups), covering the full weeks that contain
    the 1st and last day of today's month."""
    year, month = today.year, today.month
    cal = _calendar.Calendar(firstweekday=0)  # Monday first
    by_day = {}
    for ev in events:
        by_day.setdefault(ev.when.date(), []).append(ev)

    weeks = []
    week = []
    for d in cal.itermonthdates(year, month):
        week.append(CalDay(
            date=d,
            in_month=(d.month == month),
            is_today=(d == today),
            events=sorted(by_day.get(d, []), key=lambda e: e.when),
        ))
        if len(week) == 7:
            weeks.append(week)
            week = []

    month_label = today.strftime("%B %Y")
    return weeks, month_label


def upcoming_events(today: date, events: list[CalEvent], limit: int = 5):
    """Events from the start of today onward, soonest first.

    `today` is a plain date (from timezone.localdate()); `event.when` comes
    straight from a model DateTimeField, which - since USE_TZ=True in
    settings.py - is always timezone-aware. So the comparison point below
    is made aware too, the same way, rather than comparing a naive and an
    aware datetime (which Python refuses to do).
    """
    start_of_today = _tz.make_aware(datetime.combine(today, datetime.min.time()))
    future = [e for e in events if e.when >= start_of_today]
    return sorted(future, key=lambda e: e.when)[:limit]
