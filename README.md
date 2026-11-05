# Critical Thinking Education Platform — API

Django + Django REST Framework backend for the education platform (Student / Teacher / Coach
roles, Courses → Modules → Lessons → Steps → Resources).

## 1. Client-server infrastructure

- **Server**: Django 5.2 + Django REST Framework. Runs locally with `python manage.py runserver`
  on `http://127.0.0.1:8000`, **and** is deployed to the cloud on [Render](https://render.com)'s
  free tier — see [Section 5](#5-cloud-deployment-render) — with no code changes between the two;
  the same `config/settings.py` reads its config (secret key, debug flag, allowed hosts, database)
  from environment variables, defaulting to the safe local values when they're unset.
- **Database**: SQLite by default (zero setup, file-based, fine for defense/demo). Automatically
  switches to PostgreSQL if a `DATABASE_URL` environment variable is present (e.g. an attached
  Render/Railway/Supabase database) — no code changes either way.
- **Client**: any HTTP client — browser (DRF's browsable API), Postman, curl, or a real frontend
  later. Auth is token-based (`Authorization: Token <key>`), so it works the same from any client.

## 2. Development environment — quick start

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Create the database
python manage.py migrate

# 4. Create an admin/superuser account (for the admin panel + admin-only API actions)
python manage.py createsuperuser

# 5. Run the server
python manage.py runserver
```

Server is now live at `http://127.0.0.1:8000/`. Admin panel: `http://127.0.0.1:8000/admin/`.

## 3. REST API

Base path: `/api/`. Full JSON, standard HTTP verbs and status codes, token authentication.

### Auth endpoints

Signup is **email-verified** and happens in two steps — this is identical on the website and the
API, and both share the exact same verification logic (`users/verification.py`), so there is only
one registration system, not two that could drift apart.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/signup/` | **Step 1.** Body: `role, username, password, first_name, last_name, email`. Validates the data and emails a 6-digit code to `email` (no account yet). Returns `pending_token`. |
| POST | `/api/auth/signup/verify/` | **Step 2.** Body: `pending_token, code`. If the code matches, creates the Student/Teacher/Coach account and returns an auth `token`. |
| POST | `/api/auth/login/` | Body: `username, password`. Returns a token. |
| POST | `/api/auth/logout/` | Authenticated. Deletes the caller's token. |
| GET | `/api/auth/me/` | Authenticated. Returns the caller's own profile. |
| POST | `/api/auth/password-change/` | Authenticated. Body: `old_password, new_password`. Rotates the token. |

Use the returned token on every subsequent request:
```
Authorization: Token <the-token-you-got-back>
```

**Where does the verification code go?** By default the project uses Django's *console* email
backend — free, needs no setup, and good enough for a defense demo: the code is printed straight
into the server's terminal/log (look for a block starting `Content-Type: text/plain`, with a line
like `Your Critical Thinking Education Platform verification code is: 482913`). It's also visible,
without digging through logs, in Django admin under **Users → Email verification codes**. To send
real emails through Gmail instead, set the `EMAIL_BACKEND`/`EMAIL_HOST_*` environment variables
described in `config/settings.py` — never hardcode a real password there.

### Resource endpoints (full CRUD — list / create / retrieve / update / delete)

| Resource | Endpoint |
|---|---|
| Users (read-only) | `/api/users/` |
| Students | `/api/students/` |
| Teachers | `/api/teachers/` |
| Coaches | `/api/coaches/` |
| Courses | `/api/courses/` |
| Modules | `/api/modules/` |
| Lessons | `/api/lessons/` |
| Steps | `/api/steps/` |
| Resources | `/api/resources/` |
| Class Sessions | `/api/class-sessions/` |
| Groups | `/api/groups/` |
| Step Completions | `/api/step-completions/` |
| Feedbacks | `/api/feedbacks/` |
| Meetups | `/api/meetups/` |
| Invite links | `/api/invites/` (+ `POST /api/invites/join/` with `{"token": "..."}` for students) |
| Announcements | `/api/announcements/` |
| Mail messages | `/api/messages/` (`?box=inbox` / `?box=sent`; no PUT/PATCH — a sent message can't be edited) |
| My Enrollments (student, read-only) | `GET /api/my/enrollments/` |
| My profile | `GET` / `PATCH /api/auth/me/` (multipart `photo` field uploads a profile photo) |

Each follows standard REST conventions:
- `GET /api/<resource>/` — list (200)
- `POST /api/<resource>/` — create (201)
- `GET /api/<resource>/<id>/` — retrieve (200)
- `PATCH /api/<resource>/<id>/` — partial update (200)
- `PUT /api/<resource>/<id>/` — full update (200)
- `DELETE /api/<resource>/<id>/` — delete (204)

All endpoints require authentication (`401` if no/invalid token) and return JSON.

### Trying it in a browser

Django REST Framework ships a browsable API — just open any endpoint URL in a browser while
logged into the Django session (e.g. `http://127.0.0.1:8000/api/courses/`) to see a readable,
clickable HTML view of the same JSON API.

### Trying it in Postman

Import `postman_collection.json` (in this repo) into Postman. It has a request for **every**
endpoint (115 requests in 21 folders), and each request checks its own status code and that the
response is JSON, so **Collection → Run** shows a green ✓ per request.

1. Start the server, then in the collection's **Variables** set `admin_password` to your superuser's
   password (`python3 manage.py createsuperuser`). `base_url` defaults to `http://127.0.0.1:8000` —
   change it to the Render URL to test the cloud deployment.
2. **Auth folder (by hand):** send "Signup step 1", copy the 6-digit code from the server terminal
   (or Django admin → Email verification codes) into the `signup_code` variable, send "step 2".
3. **Everything else:** run the collection from the **Admin** folder down to **Cleanup** with the
   Runner. Every "Create" request saves the new id into a variable (`course_id`, `module_id`, …),
   the "Invite links" folder logs in as the student it created and joins the class, and **Cleanup**
   deletes everything the run created (children first), so you can run it again and again.

Usernames get a unique `{{run}}` suffix each run, so repeated runs never clash.

## 3a. New features (second requirements list)

| # | Requirement | Where |
|---|---|---|
| 1 | Click your avatar → personal info (with photo) | Avatar in the top-right of every page; edit at `/profile/` (photo upload) |
| 2 | A completed step can't be undone | Step page has only "Mark complete"; submitted answers are locked (resubmit only if a reviewer asks for a revision). API: students get `403` on changing/deleting a step completion |
| 3 | Change password in 2 ways | User panel: menu → Change password (`/password-change/`). Admin panel: Students/Teachers/Coaches → user → "Reset password" |
| 4 | Study module in the dashboard menu | Menu → **Study Module** (`/study-module/`): course programme, modules, lessons, step counts per type |
| 5 | Students join a class only by an invite link | Teachers/coaches: menu → **Invite links** (`/invites/`). Students open `/join/<token>/` or paste it on My Enrollments. API: `/api/invites/`, `/api/invites/join/` |
| 6 | StudentID / TeacherID / CoachID | Assigned automatically: `STU-00012`, `TCH-00003`, `CCH-00007` (shown in the profile popover, lists, admin) |
| 7 | Only the step's name is shown | Steps have a `title`. Lesson lists show names only; the content appears after opening the step |
| 8 | Announcements panel like a newspaper | Menu → **Announcements** (“The Oyla Gazette”) — headline, columns, guides. Teachers/coaches/admins publish |
| 9 | My Enrollments instead of dashboard | Students land on **My Enrollments** → course → modules → lessons |
| 10 | Only the current module is open | The current module (first unfinished one) has every lesson open; later modules are locked until it's finished; finished modules stay open for review |
| 11 | Feedback for teachers and students | Menu → **Feedback**: students write to their teachers, teachers to their students |
| 12 | Integrated mailing system | Menu → **Mail**: inbox, sent, compose, reply, unread badge. Every message is also emailed (printed in the terminal until SMTP is configured — see the email settings in `config/settings.py`) |

## 3b. Website dashboards (role-specific)

Each role gets its own dashboard at `/` (after logging in), all in a shared visual style:

- **Student** (`templates/portal/dashboard_student.html`): course progress ring, a module/lesson/step
  checklist with a "Mark complete" button on each step (posts to `/steps/<id>/toggle-complete/`), a
  calendar of upcoming class sessions and coach meetups, and a form to request a meetup.
- **Teacher** (`templates/portal/dashboard_teacher.html`): their class sessions with roster avatars,
  a "Start Google Meet" button per class, a calendar of upcoming sessions, and a list of students
  who haven't had feedback recently with a one-line feedback form (posts to
  `/students/<id>/feedback/`, creates a `Feedback` record).
- **Coach** (`templates/portal/dashboard_coach.html`): their assigned students with progress bars,
  pending meetup requests with **Schedule**/**Decline** actions (posts to
  `/meetups/<id>/respond/`), and a calendar of confirmed meetups.

**Google Meet**: `ClassSession` and `Meetup` both have a `meeting_link` field. A teacher/coach can
paste in a real Google Meet link (e.g. copied from a Google Calendar event they created) via the
admin or - for meetups - directly on the "Schedule" form. If left blank, every "Join"/"Start Google
Meet" button falls back to `https://meet.google.com/new`, which starts a brand-new Google Meet call
instantly for whoever clicks it — no Google Cloud project, OAuth consent screen, or API key needed.
This is exposed in the API too: `GET /api/class-sessions/` and `GET /api/meetups/` both return a
`join_link` field with the same logic.

## 3c. JSON data (save any JSON into the database)

The `datastore` app turns the site into a web application that stores JSON in the
project's own database (SQLite locally, Postgres on Render - same code, `JSONField`).

**Website** (log in first; link "My data" in the sidebar):

| URL | What it does |
|-----|--------------|
| `/data/` | Your saved data (teachers/coaches also see their students' data, with a Student column). Search + category filter. |
| `/data/new/` | Paste JSON or upload a `.json` file. "Check my JSON", "Make it neat", "Load example" buttons. Errors show the line number. |
| `/data/<id>/` | Pretty JSON view, Edit / Delete / Download .json. Teachers & coaches can leave a comment. |
| `/data/import-course/` | Teachers/coaches only: import a whole course (modules → lessons → steps → resources) from JSON. |

**API** (token auth, see the "JSON Data" folder in `postman_collection.json`):

| Method | Endpoint | Who |
|--------|----------|-----|
| GET / POST | `/api/json-records/` (`?category=`, `?search=`) | any logged-in user (sees own data; teachers/coaches also their students') |
| GET / PUT / PATCH / DELETE | `/api/json-records/<id>/` | read: anyone who can see it; change/delete: owner only |
| GET | `/api/json-records/<id>/download/` | anyone who can see it |
| POST | `/api/json-records/<id>/comment/` | teachers, coaches |
| POST | `/api/import/course/` (`"update_existing": true` to replace a course with the same `number`) | teachers, coaches |
| GET | `/api/courses/<id>/export/` | any logged-in user |

Rules: `data` must be a JSON object or list, max 1 MB per record, max 200 records per student.
The course import runs in one database transaction - if anything fails, nothing is saved.
Tests: `python3 manage.py test datastore`.

## 3d. Live progress & in-app video

- **No page refresh needed.** On a step page, "Mark complete" / "Submit for review" save in the
  background. The student dashboard has "Mark done" buttons and updates its counters, progress ring,
  module bars and step ticks by itself - instantly when a step is finished in another tab, and every
  15 seconds (so a teacher's approval shows up too). JSON endpoint: `GET /progress/`.
- **Videos play inside the app.** In the admin, open a Step and upload a file in **Video file**
  (MP4 is best). It is stored in the `media/step_videos/` folder and streamed by the server at
  `/steps/<id>/video/` (login required, seeking supported). If a step has no uploaded file but has a
  YouTube link, the video is embedded in the page instead - students never see a link.
- A video step is marked complete automatically when the video finishes.
- On Render's free plan the disk is reset on each deploy, so videos uploaded through the live admin
  disappear. To keep them, put the files in `media/step_videos/` in the project before deploying.

## 3e. Oyla as a web app (installable)

Oyla is a web app served by this same Django server - one project, one database, one deploy.
Students can use it in the browser or **install it like a normal app** with its own icon:

- **Android / Chrome / Edge (phone or computer):** open the site and tap **"Install app"** in the
  menu (or the "Install app" item in Oyla's sidebar / on the login page).
- **iPhone / iPad (Safari):** tap **Share ⬆ → "Add to Home Screen"**.

What makes it an app: `/manifest.webmanifest` (name, icon, full-screen mode), `/sw.js` (service worker
that caches icons and shows `/offline/` when there's no internet) and the icons in
`portal/static/portal/icons/`. Inside the installed app, step pages open in the app itself instead of
new browser tabs. Installing needs HTTPS - it works on the Render site and on `localhost`, but not
on a plain `http://192.168...` address.

## 4. Project structure

```
config/       Django project settings, root URLs
users/        User, Student, Teacher, Coach models, EmailVerificationCode, verification.py (shared signup logic)
catalog/      Course, Module, Lesson, Step, Resource models
enrollment/   ClassSession, Group, StepCompletion, Feedback, Meetup models
portal/       Server-rendered web UI (signup/login/dashboard pages, separate from the API)
api/          DRF serializers, viewsets, auth views, URL routing — the graded API layer
postman_collection.json   Importable request collection covering all API methods
render.yaml, build.sh, Procfile   Render cloud deployment config (see Section 5)
```

## 5. Cloud deployment (Render)

The project is set up to deploy to [Render](https://render.com)'s **free** tier with no paid
account or credit card needed. Render builds the app from `build.sh` (installs dependencies, runs
`collectstatic`, runs migrations) and serves it with `gunicorn` (`Procfile`); static files are
served by `whitenoise`, so no separate static-file host is needed either.

1. Push this project to a GitHub repository (Render deploys from a git repo).
2. Go to [dashboard.render.com](https://dashboard.render.com) → sign up free (e.g. "Sign up with
   GitHub") → **New +** → **Blueprint**.
3. Pick the GitHub repo you just pushed. Render reads `render.yaml` automatically and shows one
   service, `eduplatform`, already configured (free plan, build/start commands, env vars).
4. Click **Apply** / **Create**. Render installs everything, runs the build, and starts the app —
   first deploy takes a few minutes. When it's done you'll have a live URL like
   `https://eduplatform-xxxx.onrender.com`.
5. Visit `https://eduplatform-xxxx.onrender.com/admin/` and create a superuser so you have somewhere
   to log in. Render's dashboard has a **Shell** tab for the service — open it and run:
   ```bash
   python manage.py createsuperuser
   ```
6. Update the Postman collection's `base_url` variable to that URL to run all requests against the
   live deployment instead of localhost.

**Notes:**
- The free plan's disk isn't persistent, so the SQLite database resets on redeploy or after the
  service spins down from inactivity — expected and fine for demo/defense use. To keep data
  permanently, attach a Render Postgres database (Render dashboard → **New +** → **PostgreSQL** →
  free tier), add its **Internal Database URL** as a `DATABASE_URL` environment variable on the
  `eduplatform` service, and add two lines to `requirements.txt` first: `dj-database-url` and
  `psycopg2-binary` (left out by default since they're only needed for Postgres, and
  `psycopg2-binary` has no prebuilt wheel on some very new local Python versions) — then redeploy.
  `config/settings.py` picks up `DATABASE_URL` automatically once those are installed, no other
  code changes needed.
- A free service also spins down after ~15 minutes idle and takes ~30–60s to wake back up on the
  next request — normal for the free tier, not a bug.
- `SECRET_KEY` is auto-generated by Render (`render.yaml`'s `generateValue: true`) — never the
  insecure local default. Verification codes still print to the Render logs (**Logs** tab) with
  the default console email backend, same as locally.
