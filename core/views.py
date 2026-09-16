from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .models import User, StudentProfile, InstructorProfile, StudentActivity, Notification
from .decorators import admin_required, instructor_required, student_required
from academy.models import Course, Lesson, ClassSession, Attendance, AttendanceRule
from assessment.models import Assignment, Submission, Quiz, QuizAttempt, StudentProgress, StudentAlert


@never_cache
@csrf_protect
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.display_name}!")
            # Log activity if student
            if user.is_student_role and hasattr(user, 'student_profile'):
                StudentActivity.objects.create(
                    student=user.student_profile,
                    activity_type=StudentActivity.ActivityType.LOGIN,
                    description=f"Logged in to Future Minds Online from {request.META.get('REMOTE_ADDR', 'Web')}"
                )
            return redirect('dashboard_redirect')
        else:
            messages.error(request, "Invalid username or password. Please check credentials.")

    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out safely.")
    return redirect('login')


@login_required
def dashboard_redirect(request):
    """
    Directs users to their respective role-specific dashboard.
    """
    user = request.user
    if user.is_admin_role:
        return redirect('admin_dashboard')
    elif user.is_instructor_role:
        return redirect('instructor_dashboard')
    elif user.is_student_role:
        return redirect('student_dashboard')
    return redirect('profile')


@admin_required
def admin_dashboard(request):
    today = timezone.localdate()
    
    # 1. High-level KPIs
    total_students = StudentProfile.objects.count()
    online_students = StudentProfile.objects.filter(learning_mode=StudentProfile.LearningMode.ONLINE).count()
    offline_students = StudentProfile.objects.filter(learning_mode=StudentProfile.LearningMode.OFFLINE).count()
    total_instructors = InstructorProfile.objects.count()
    total_courses = Course.objects.filter(is_active=True).count()
    classes_today = ClassSession.objects.filter(scheduled_date=today).count()
    
    # Overall attendance rate across all sessions
    total_attendances = Attendance.objects.count()
    present_attendances = Attendance.objects.filter(
        status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]
    ).count()
    attendance_rate = round((present_attendances / total_attendances * 100), 1) if total_attendances > 0 else 100.0

    # Today's classes
    today_sessions = ClassSession.objects.filter(scheduled_date=today).order_by('start_time')
    
    # Recent Activities
    recent_activities = StudentActivity.objects.select_related('student__user').all()[:8]
    
    # Unresolved alerts
    system_alerts = StudentAlert.objects.filter(is_resolved=False).select_related('student__user', 'instructor__user')[:5]

    # Chart Data Preparation
    # Attendance breakdown: Present, Late, Absent
    att_present = Attendance.objects.filter(status=Attendance.Status.PRESENT).count()
    att_late = Attendance.objects.filter(status=Attendance.Status.LATE).count()
    att_absent = Attendance.objects.filter(status=Attendance.Status.ABSENT).count()

    # Course performance: avg progress per course
    courses = Course.objects.filter(is_active=True)[:6]
    course_labels = [c.title[:15] + ('...' if len(c.title) > 15 else '') for c in courses]
    course_perf_data = []
    for c in courses:
        avg_prog = StudentProgress.objects.filter(course=c).aggregate(Avg('overall_percentage'))['overall_percentage__avg'] or 0.0
        course_perf_data.append(round(float(avg_prog), 1))

    context = {
        'total_students': total_students,
        'online_students': online_students,
        'offline_students': offline_students,
        'total_instructors': total_instructors,
        'total_courses': total_courses,
        'classes_today': classes_today,
        'attendance_rate': attendance_rate,
        'today_sessions': today_sessions,
        'recent_activities': recent_activities,
        'system_alerts': system_alerts,
        # Chart JSON-friendly data
        'chart_attendance': [att_present, att_late, att_absent],
        'chart_modes': [online_students, offline_students],
        'course_labels': course_labels,
        'course_perf_data': course_perf_data,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


@instructor_required
def instructor_dashboard(request):
    """
    Instructor Dashboard with STRICT DATA ISOLATION.
    Only data assigned to this instructor is accessible.
    """
    instructor = getattr(request.user, 'instructor_profile', None)
    if not instructor:
        # Fallback if admin viewing instructor dashboard
        instructor = InstructorProfile.objects.first()

    today = timezone.localdate()

    # My Courses
    my_courses = Course.objects.filter(instructor=instructor)
    
    # My Students
    my_students = StudentProfile.objects.filter(
        Q(assigned_instructor=instructor) | Q(courses__instructor=instructor)
    ).distinct()

    # My Classes Today and upcoming
    my_classes_today = ClassSession.objects.filter(
        instructor=instructor,
        scheduled_date=today
    ).order_by('start_time')

    upcoming_classes = ClassSession.objects.filter(
        instructor=instructor,
        scheduled_date__gte=today
    ).exclude(status=ClassSession.Status.COMPLETED).order_by('scheduled_date', 'start_time')[:5]

    # Student Alerts for this instructor
    my_alerts = StudentAlert.objects.filter(
        instructor=instructor,
        is_resolved=False
    ).select_related('student__user', 'course')

    # Pending Submissions to grade
    pending_submissions = Submission.objects.filter(
        assignment__instructor=instructor,
        status=Submission.Status.SUBMITTED
    ).select_related('assignment', 'student__user')[:6]

    # Attendance summary for this instructor's classes
    instructor_sessions = ClassSession.objects.filter(instructor=instructor)
    att_qs = Attendance.objects.filter(class_session__in=instructor_sessions)
    total_att = att_qs.count()
    attended_att = att_qs.filter(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]).count()
    instructor_att_rate = round((attended_att / total_att * 100), 1) if total_att > 0 else 100.0

    context = {
        'instructor': instructor,
        'my_courses': my_courses,
        'my_students': my_students,
        'my_classes_today': my_classes_today,
        'upcoming_classes': upcoming_classes,
        'my_alerts': my_alerts,
        'pending_submissions': pending_submissions,
        'instructor_att_rate': instructor_att_rate,
        'total_my_students': my_students.count(),
    }
    return render(request, 'dashboard/instructor_dashboard.html', context)


@student_required
def student_dashboard(request):
    """
    Student Dashboard with immediate action cards, countdown, Join Class, and progress.
    """
    student = getattr(request.user, 'student_profile', None)
    if not student:
        messages.error(request, "Student profile not found.")
        return redirect('profile')

    today = timezone.localdate()
    now_time = timezone.localtime().time()

    # My Enrolled Courses
    enrolled_courses = student.courses.all()

    # Today's Class Session
    today_class = ClassSession.objects.filter(
        students=student,
        scheduled_date=today,
        status__in=[ClassSession.Status.SCHEDULED, ClassSession.Status.ONGOING]
    ).order_by('start_time').first()

    # Next upcoming class
    next_class = ClassSession.objects.filter(
        students=student,
        scheduled_date__gte=today
    ).exclude(status=ClassSession.Status.COMPLETED).order_by('scheduled_date', 'start_time').first()

    # Student Attendance %
    my_attendances = Attendance.objects.filter(student=student)
    total_classes = my_attendances.count()
    attended_classes = my_attendances.filter(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]).count()
    attendance_rate = round((attended_classes / total_classes * 100), 1) if total_classes > 0 else 100.0

    # Course Progress Bars
    progress_records = StudentProgress.objects.filter(student=student).select_related('course')

    # Pending Assignments
    enrolled_assignments = Assignment.objects.filter(
        course__in=enrolled_courses,
        is_published=True
    ).exclude(
        submissions__student=student
    ).order_by('due_date')[:4]

    # Available Quizzes
    available_quizzes = Quiz.objects.filter(
        course__in=enrolled_courses,
        is_published=True
    ).exclude(
        attempts__student=student
    ).order_by('-created_at')[:4]

    # Recent Notifications & Activities
    recent_activities = StudentActivity.objects.filter(student=student)[:6]

    context = {
        'student': student,
        'today_class': today_class,
        'next_class': next_class,
        'attendance_rate': attendance_rate,
        'attended_classes': attended_classes,
        'total_classes': total_classes,
        'enrolled_courses': enrolled_courses,
        'progress_records': progress_records,
        'pending_assignments': enrolled_assignments,
        'available_quizzes': available_quizzes,
        'recent_activities': recent_activities,
    }
    return render(request, 'dashboard/student_dashboard.html', context)


@login_required
def profile_view(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.phone = phone
        request.user.save()
        messages.success(request, "Your profile details have been updated successfully.")
        return redirect('profile')

    return render(request, 'profile.html')


@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(recipient=request.user)
    return render(request, 'notifications/index.html', {'notifications': notifications})


@login_required
def mark_notification_read_api(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notif.is_read = True
    notif.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({'status': 'success', 'unread_count': Notification.objects.filter(recipient=request.user, is_read=False).count()})
    if notif.link:
        return redirect(notif.link)
    return redirect('notifications')


@admin_required
def analytics_view(request):
    total_students = StudentProfile.objects.count()
    online_count = StudentProfile.objects.filter(learning_mode=StudentProfile.LearningMode.ONLINE).count()
    offline_count = StudentProfile.objects.filter(learning_mode=StudentProfile.LearningMode.OFFLINE).count()
    
    total_submissions = Submission.objects.count()
    graded_submissions = Submission.objects.filter(status=Submission.Status.GRADED).count()
    total_attempts = QuizAttempt.objects.count()
    avg_quiz_score = QuizAttempt.objects.aggregate(Avg('percentage'))['percentage__avg'] or 0.0

    context = {
        'total_students': total_students,
        'online_count': online_count,
        'offline_count': offline_count,
        'total_submissions': total_submissions,
        'graded_submissions': graded_submissions,
        'total_attempts': total_attempts,
        'avg_quiz_score': round(float(avg_quiz_score), 1),
    }
    return render(request, 'analytics/index.html', context)


@admin_required
def attendance_rules_settings_view(request):
    rule = AttendanceRule.get_current_rule()
    if request.method == 'POST':
        rule.name = request.POST.get('name', rule.name)
        rule.early_window_minutes = int(request.POST.get('early_window_minutes', rule.early_window_minutes))
        rule.late_cutoff_minutes = int(request.POST.get('late_cutoff_minutes', rule.late_cutoff_minutes))
        rule.save()
        messages.success(request, "Attendance automation policy updated successfully.")
        return redirect('attendance_rules_settings')

    return render(request, 'settings/attendance_rules.html', {'rule': rule})
