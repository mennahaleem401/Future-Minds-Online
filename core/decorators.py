from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_admin_role:
            messages.error(request, "Access denied. Academy Administrator privileges are required.")
            return redirect('dashboard_redirect')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def instructor_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_instructor_role or request.user.is_admin_role):
            messages.error(request, "Access denied. Instructor access only.")
            return redirect('dashboard_redirect')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def student_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_student_role:
            messages.error(request, "Access denied. Student access only.")
            return redirect('dashboard_redirect')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def instructor_or_admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_instructor_role or request.user.is_admin_role):
            messages.error(request, "Access denied. Restricted to Instructors and Administrators.")
            return redirect('dashboard_redirect')
        return view_func(request, *args, **kwargs)
    return _wrapped_view
