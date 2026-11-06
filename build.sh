#!/usr/bin/env bash
# Render runs this once on every deploy (its "Build Command").
# set -o errexit makes the whole build fail fast if any line here fails,
# instead of silently deploying a broken build.
set -o errexit

pip install -r requirements.txt

# Gathers all static files (admin CSS/JS, DRF browsable-API assets, etc.)
# into STATIC_ROOT so whitenoise can serve them in production.
python manage.py collectstatic --no-input

# Applies any pending migrations so the live database schema is always
# up to date with the code being deployed.
python manage.py migrate

# Adds the Critical Thinking Crash Course (Module 1, Lesson 1) and enrols every
# student. Safe to run on every deploy: it never duplicates anything.
python manage.py add_critical_thinking_course
