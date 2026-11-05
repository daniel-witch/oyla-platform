# Oyla Platform: project description (Lab 0)

**Oyla** (Kazakh *ойла*, "think") is a web platform for teaching critical thinking. Teachers build step-by-step courses, students work through them one step at a time, and coaches support students in small groups. The platform has a REST API (Django REST Framework) and a website that uses the same backend.

## Problem and goal

Critical-thinking lessons need more than videos: students must answer, get feedback and move on only when they are ready. Oyla gives each student a clear path (course → module → lesson → step), lets teachers check open answers, and lets coaches follow their students' progress.

## Users and roles

| Access level | Who | What they can do |
|---|---|---|
| Guest | Anyone who is not logged in | Browse the course catalog (courses, modules, lessons) and announcements; sign up; log in |
| Member: Student | Learner | Join a class with an invite link, complete steps, submit quiz/practice answers, write feedback, request meetups, send messages |
| Member: Teacher | Course author | Create and edit course content, run class sessions, review submissions, write feedback, publish announcements |
| Member: Coach | Mentor | Lead groups of students, review submissions, handle meetups, publish announcements |
| Administrator | Superuser / staff | Everything, including creating, changing and deleting user accounts |

## Main entities and how they relate

```
User ─┬─ Student ──< Group >── Coach
      ├─ Teacher ──< ClassSession >── Course
      └─ Coach                         │
                                       └──< Module ──< Lesson ──< Step ──< Resource
Student ──< StepCompletion >── Step          (status: approved / pending / rejected)
Student ──< Feedback >── Teacher             Student ──< Meetup >── Coach
ClassSession ──< ClassInvite                 User ──< Message >── User      Announcement
```

- **Course → Module → Lesson → Step → Resource**: each child points to its parent (one-to-many).
- **ClassSession** links a **Teacher** to a **Course**; a **Group** puts a **Student** (and a **Coach**) into a class session.
- **StepCompletion** records a student's progress and answers on each step.

## Main features

- Two-step sign-up with an e-mail verification code; token login for the API, session login for the website.
- Modules unlock one at a time; video/text steps are self-completed, quiz/practice answers wait for a teacher's or coach's approval.
- Invite links to join a class, Google Meet links, a calendar, announcements and an internal mail system.
- Role dashboards on the website and a combined `GET /api/dashboard/` in the API.

## Technology

Django 5.2, Django REST Framework 3.18, SQLite (PostgreSQL via `DATABASE_URL`), Gunicorn + WhiteNoise, deployment to Render (`render.yaml`, `build.sh`). Testing with Django's test runner (58 tests) and Postman / Newman (177 requests in 4 folders).

## How the project meets the lab requirements

| Requirement | Where it is met |
|---|---|
| Project description uploaded | This file (`PROJECT_DESCRIPTION.md`) |
| At least 3 entities, related | 19 database models; e.g. Course → Module → Lesson → Step (foreign keys), ClassSession, Group |
| 5 methods per entity (list + 4 CRUD) | Every resource under `/api/<name>/`: GET list, POST, GET one, PUT/PATCH, DELETE (18 resources) |
| A resource combined from several entities | `GET /api/dashboard/` (User + Course + Step/StepCompletion + Group + ClassSession + Announcement + Message); also `GET /api/my/enrollments/`, `GET /api/auth/me/` |
| Pagination | Every list: `?limit=10&offset=20` → `{count, next, previous, results}` (max 100 per page) |
| Filtering | Every list: by fields (`?course=3`, `?step_type=quiz`, `?status=pending`), text search (`?search=logic`), sorting (`?ordering=-name`) |
| Uses a database | SQLite locally (`db.sqlite3`), PostgreSQL in the cloud; 19 models with migrations |
| At least 3 roles (guest, member, administrator) | Guest (not logged in), member (student / teacher / coach), administrator; `access_level` is shown in `/api/auth/me/` and checked in `api/permissions.py` |
| Client-server, quick environment, REST, all methods, collections (Lab 1) | Django server + Postman client; 3 commands to start; `postman_collection.json` |
