from rest_framework import permissions

from datastore.utils import is_teacher_or_coach


class IsTeacherOrCoach(permissions.BasePermission):
    """Only Teachers, Coaches and superusers."""
    message = "Only teachers and coaches can do this."

    def has_permission(self, request, view):
        return is_teacher_or_coach(request.user)


class IsOwnerOrStaffRole(permissions.BasePermission):
    """Anyone who can SEE an object (queryset decides that) may read it.
    Only its owner (or a superuser) may change or delete it."""
    message = "You can only change your own data."

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_superuser or obj.created_by_id == request.user.pk


def access_level(user):
    """The three access levels of the platform:

    guest          - not logged in: may only browse the public catalog
                     (courses, modules, lessons) and announcements.
    member         - a logged-in student, teacher or coach: reads everything,
                     changes only what their role allows.
    administrator  - superuser / staff: may do everything.
    """
    if not (user and user.is_authenticated):
        return "guest"
    if user.is_superuser or user.is_staff:
        return "administrator"
    return "member"


class RoleWritePermission(permissions.BasePermission):
    """Members (logged-in users) can read. Guests can read only views marked
    `guest_read = True`. Changing data (POST/PUT/PATCH/DELETE) is allowed only
    for administrators and the roles listed on the view as `write_roles`.

    Without this, any logged-in student could delete courses or other users.
    """
    message = "Your role isn't allowed to change this resource."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            # Guest: read-only, and only on the public views.
            return request.method in permissions.SAFE_METHODS and getattr(view, "guest_read", False)
        if request.method in permissions.SAFE_METHODS:
            return True
        if user.is_superuser or user.is_staff:
            return True
        return getattr(user, "role", None) in getattr(view, "write_roles", ())
