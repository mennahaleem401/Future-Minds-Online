from datetime import datetime, time, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponseRedirect, Http404
from django.db.models import Q

from core.models import User, StudentProfile, InstructorProfile, StudentActivity, Notification
from core.decorators import admin_required, instructor_required, student_required, instructor_or_admin_required
from .models import Course, Lesson, Material, ClassSession, ClassStudent, Attendance, AttendanceRule, Recording
from .automation import run_session_completion_workflow
from assessment.models import Assignment
from assessment.progress_service import recalculate_student_progress

DAYS_MAPPING = {
    'SAT': 5,  # السبت
    'SUN': 6,  # الأحد
    'MON': 0,  # الإثنين
    'TUE': 1,  # الثلاثاء
    'WED': 2,  # الأربعاء
    'THU': 3,  # الخميس
    'FRI': 4,  # الجمعة
}

DAYS_NAMES_AR = {
    'SAT': 'السبت',
    'SUN': 'الأحد',
    'MON': 'الإثنين',
    'TUE': 'الثلاثاء',
    'WED': 'الأربعاء',
    'THU': 'الخميس',
    'FRI': 'الجمعة',
}


def generate_course_sessions(course, start_date=None, days_list=None, start_time=None, end_time=None, meet_link=None, total_sessions=None, clear_existing=False):
    """
    محرك الجدولة التلقائية لحصص الكورس:
    - ينشئ حصص الكورس كنُسخ متطابقة (حصة 1، حصة 2، ...)
    - يحسب تواريخ الحصص تلقائياً بناءً على أيام الأسبوع المحددة للكورس.
    - يربط جميع الطلاب المقيدين في الكورس تلقائياً بكل حصة ويجهز سجلات الحضور.
    """
    if clear_existing:
        course.sessions.filter(status=ClassSession.Status.SCHEDULED).delete()

    if not start_date:
        start_date = course.start_date or timezone.localdate()
    elif isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start_date = timezone.localdate()

    if days_list is None:
        days_str = course.schedule_days or 'SAT,TUE'
        days_list = [d.strip() for d in days_str.split(',') if d.strip()]
    elif isinstance(days_list, str):
        days_list = [d.strip() for d in days_list.split(',') if d.strip()]

    target_weekdays = {DAYS_MAPPING[d] for d in days_list if d in DAYS_MAPPING}
    if not target_weekdays:
        target_weekdays = {start_date.weekday()}

    parsed_start_time = start_time or course.default_start_time or time(17, 0)
    if isinstance(parsed_start_time, str):
        try:
            parsed_start_time = datetime.strptime(parsed_start_time, '%H:%M').time()
        except (ValueError, TypeError):
            parsed_start_time = time(17, 0)

    parsed_end_time = end_time or course.default_end_time or time(18, 30)
    if isinstance(parsed_end_time, str):
        try:
            parsed_end_time = datetime.strptime(parsed_end_time, '%H:%M').time()
        except (ValueError, TypeError):
            parsed_end_time = time(18, 30)

    meet_link = meet_link or course.default_meet_link or 'https://meet.google.com/abc-defg-hij'
    total_sessions = int(total_sessions or course.total_sessions_count or 8)

    max_existing = course.sessions.order_by('-session_number').first()
    start_num = (max_existing.session_number + 1) if max_existing else 1

    created_sessions = []
    current_date = start_date
    created_count = 0
    enrolled_students = list(course.enrolled_students.all())
    instructor = course.instructor

    max_days = 365
    days_checked = 0

    while created_count < total_sessions and days_checked < max_days:
        if current_date.weekday() in target_weekdays:
            session_num = start_num + created_count
            session = ClassSession.objects.create(
                course=course,
                instructor=instructor,
                session_number=session_num,
                title=f"حصة {session_num}",
                scheduled_date=current_date,
                start_time=parsed_start_time,
                end_time=parsed_end_time,
                google_meet_link=meet_link,
                status=ClassSession.Status.SCHEDULED
            )
            for st in enrolled_students:
                ClassStudent.objects.create(class_session=session, student=st)
                Attendance.objects.create(
                    class_session=session,
                    student=st,
                    status=Attendance.Status.ABSENT
                )
            created_sessions.append(session)
            created_count += 1
        current_date += timedelta(days=1)
        days_checked += 1

    return created_sessions



# ==========================================
# 1. COURSES & LESSONS
# ==========================================

@login_required
def course_list_view(request):
    user = request.user
    query = request.GET.get('q', '').strip()

    if user.is_admin_role:
        courses = Course.objects.all()
    elif user.is_instructor_role:
        instructor = getattr(user, 'instructor_profile', None)
        courses = Course.objects.filter(instructor=instructor)
    else:  # Student
        student = getattr(user, 'student_profile', None)
        courses = student.courses.all() if student else Course.objects.none()

    if query:
        courses = courses.filter(Q(title__icontains=query) | Q(description__icontains=query))

    return render(request, 'courses/list.html', {'courses': courses, 'query': query})


@login_required
def course_detail_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    user = request.user

    # Security check: If instructor, cannot access other instructor's private course unless admin
    if user.is_instructor_role and not user.is_admin_role:
        if course.instructor and course.instructor.user != user:
            messages.error(request, "غير مسموح لك بعرض كورس خاص بمدرس آخر.")
            return redirect('courses_list')

    # Security check: If student, must be enrolled
    if user.is_student_role:
        student = getattr(user, 'student_profile', None)
        if not course.enrolled_students.filter(id=student.id).exists():
            messages.error(request, "أنت غير مسجل في هذا الكورس.")
            return redirect('courses_list')
        
        # Log activity
        StudentActivity.objects.create(
            student=student,
            activity_type=StudentActivity.ActivityType.OPEN_COURSE,
            description=f"فتح تفاصيل كورس '{course.title}'"
        )

    lessons = course.lessons.all().order_by('order')
    materials = course.materials.filter(is_published=True)
    sessions = course.sessions.all().prefetch_related('assignments', 'students').order_by('scheduled_date', 'start_time')

    days_choices = [
        ('SAT', 'السبت'),
        ('SUN', 'الأحد'),
        ('MON', 'الإثنين'),
        ('TUE', 'الثلاثاء'),
        ('WED', 'الأربعاء'),
        ('THU', 'الخميس'),
        ('FRI', 'الجمعة'),
    ]
    course_schedule_days = [d.strip() for d in (course.schedule_days or '').split(',') if d.strip()]

    context = {
        'course': course,
        'lessons': lessons,
        'materials': materials,
        'sessions': sessions,
        'total_sessions': sessions.count(),
        'completed_sessions': sessions.filter(status=ClassSession.Status.COMPLETED).count(),
        'days_choices': days_choices,
        'course_schedule_days': course_schedule_days,
        'can_manage_course': user.is_admin_role,
        'is_course_instructor': user.is_instructor_role and course.instructor and course.instructor.user == user,
        'today': timezone.localdate(),
    }
    return render(request, 'courses/detail.html', context)


@admin_required
def course_create_edit_view(request, course_id=None):
    course = get_object_or_404(Course, id=course_id) if course_id else None
    instructors = InstructorProfile.objects.all()
    all_students = StudentProfile.objects.all()

    days_choices = [
        ('SAT', 'السبت'),
        ('SUN', 'الأحد'),
        ('MON', 'الإثنين'),
        ('TUE', 'الثلاثاء'),
        ('WED', 'الأربعاء'),
        ('THU', 'الخميس'),
        ('FRI', 'الجمعة'),
    ]

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        instructor_id = request.POST.get('instructor_id')
        is_active = request.POST.get('is_active') == 'on'

        # Schedule parameters
        schedule_days = request.POST.getlist('schedule_days')
        start_date_val = request.POST.get('start_date')
        start_time_val = request.POST.get('start_time')
        end_time_val = request.POST.get('end_time')
        meet_link_val = request.POST.get('default_meet_link', '').strip()
        total_sessions_val = request.POST.get('total_sessions_count')
        selected_student_ids = request.POST.getlist('enrolled_students')
        auto_generate = request.POST.get('auto_generate_sessions') == 'on'

        instructor = InstructorProfile.objects.filter(id=instructor_id).first() if instructor_id else None

        parsed_start_date = None
        if start_date_val:
            try:
                parsed_start_date = datetime.strptime(start_date_val, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass

        parsed_start_time = None
        if start_time_val:
            try:
                parsed_start_time = datetime.strptime(start_time_val, '%H:%M').time()
            except (ValueError, TypeError):
                pass

        parsed_end_time = None
        if end_time_val:
            try:
                parsed_end_time = datetime.strptime(end_time_val, '%H:%M').time()
            except (ValueError, TypeError):
                pass

        parsed_total_sessions = 8
        if total_sessions_val:
            try:
                parsed_total_sessions = int(total_sessions_val)
            except (ValueError, TypeError):
                pass

        if course:
            course.title = title
            course.description = description
            course.instructor = instructor
            course.is_active = is_active
            course.schedule_days = ','.join(schedule_days)
            if parsed_start_date:
                course.start_date = parsed_start_date
            if parsed_start_time:
                course.default_start_time = parsed_start_time
            if parsed_end_time:
                course.default_end_time = parsed_end_time
            if meet_link_val:
                course.default_meet_link = meet_link_val
            course.total_sessions_count = parsed_total_sessions
            course.save()

            if selected_student_ids:
                course.enrolled_students.set(selected_student_ids)

            messages.success(request, f"تم تحديث بيانات الكورس '{course.title}' بنجاح.")
        else:
            course = Course.objects.create(
                title=title,
                description=description,
                instructor=instructor,
                is_active=is_active,
                schedule_days=','.join(schedule_days),
                start_date=parsed_start_date or timezone.localdate(),
                default_start_time=parsed_start_time or time(17, 0),
                default_end_time=parsed_end_time or time(18, 30),
                default_meet_link=meet_link_val or 'https://meet.google.com/abc-defg-hij',
                total_sessions_count=parsed_total_sessions
            )
            if selected_student_ids:
                course.enrolled_students.set(selected_student_ids)

            # Auto-generate sessions if checked and instructor exists
            if auto_generate and instructor:
                created_sessions = generate_course_sessions(
                    course=course,
                    start_date=parsed_start_date,
                    days_list=schedule_days,
                    start_time=parsed_start_time,
                    end_time=parsed_end_time,
                    meet_link=meet_link_val,
                    total_sessions=parsed_total_sessions
                )
                messages.success(request, f"تم إنشاء الكورس '{course.title}' وتوليد {len(created_sessions)} حصة تلقائياً بنجاح!")
            else:
                messages.success(request, f"تم إنشاء الكورس '{course.title}' بنجاح.")

        return redirect('course_detail', course_id=course.id)

    selected_days = [d.strip() for d in (course.schedule_days or '').split(',') if d.strip()] if course else ['SAT', 'TUE']
    current_enrolled_ids = list(course.enrolled_students.values_list('id', flat=True)) if course else []

    return render(request, 'courses/form.html', {
        'course': course,
        'instructors': instructors,
        'all_students': all_students,
        'days_choices': days_choices,
        'selected_days': selected_days,
        'current_enrolled_ids': current_enrolled_ids,
        'today': timezone.localdate(),
    })


@admin_required
def course_auto_schedule_view(request, course_id):
    """
    الجدولة التلقائية لحصص الكورس من قبل الأدمن فقط
    """
    course = get_object_or_404(Course, id=course_id)
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        days = request.POST.getlist('schedule_days')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        meet_link = request.POST.get('google_meet_link', '').strip()
        total_sessions = request.POST.get('total_sessions')
        clear_existing = request.POST.get('clear_existing') == 'on'

        if days:
            course.schedule_days = ','.join(days)
        if start_date:
            try:
                course.start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        if start_time:
            try:
                course.default_start_time = datetime.strptime(start_time, '%H:%M').time()
            except (ValueError, TypeError):
                pass
        if end_time:
            try:
                course.default_end_time = datetime.strptime(end_time, '%H:%M').time()
            except (ValueError, TypeError):
                pass
        if meet_link:
            course.default_meet_link = meet_link
        if total_sessions:
            try:
                course.total_sessions_count = int(total_sessions)
            except (ValueError, TypeError):
                pass
        course.save()

        created = generate_course_sessions(
            course=course,
            start_date=start_date,
            days_list=days,
            start_time=start_time,
            end_time=end_time,
            meet_link=meet_link,
            total_sessions=total_sessions,
            clear_existing=clear_existing
        )
        messages.success(request, f"تم جدولة {len(created)} حصة بنجاح لكورس '{course.title}'!")
    return redirect('course_detail', course_id=course.id)


@login_required
def lesson_detail_view(request, course_id, lesson_id):
    course = get_object_or_404(Course, id=course_id)
    lesson = get_object_or_404(Lesson, id=lesson_id, course=course)
    user = request.user

    if user.is_student_role:
        student = getattr(user, 'student_profile', None)
        StudentActivity.objects.create(
            student=student,
            activity_type=StudentActivity.ActivityType.OPEN_LESSON,
            description=f"Studied Lesson {lesson.order}: {lesson.title} ({course.title})"
        )
        # Recalculate progress with lesson count
        recalculate_student_progress(student, course)

    materials = lesson.materials.filter(is_published=True)
    assignments = lesson.assignments.filter(is_published=True)
    quizzes = lesson.quizzes.filter(is_published=True)

    all_lessons = course.lessons.all().order_by('order')

    context = {
        'course': course,
        'lesson': lesson,
        'materials': materials,
        'assignments': assignments,
        'quizzes': quizzes,
        'all_lessons': all_lessons,
    }
    return render(request, 'courses/lesson_detail.html', context)


# ==========================================
# 2. CLASS SESSIONS & GOOGLE MEET JOIN
# ==========================================

@login_required
def class_list_view(request):
    user = request.user
    today = timezone.localdate()

    if user.is_admin_role:
        sessions = ClassSession.objects.all()
    elif user.is_instructor_role:
        instructor = getattr(user, 'instructor_profile', None)
        sessions = ClassSession.objects.filter(instructor=instructor)
    else:  # Student
        student = getattr(user, 'student_profile', None)
        sessions = ClassSession.objects.filter(students=student)

    # الحصص القادمة والشغالة (التي لم تنته بعد)
    upcoming_sessions = sessions.filter(
        scheduled_date__gte=today
    ).exclude(
        status=ClassSession.Status.COMPLETED
    ).order_by('scheduled_date', 'start_time')

    # أرشيف الحصص السابقة (المنتهية أو التي مضى تاريخها)
    past_sessions = sessions.filter(
        Q(status=ClassSession.Status.COMPLETED) | Q(scheduled_date__lt=today)
    ).order_by('-scheduled_date', '-start_time')

    context = {
        'upcoming_sessions': upcoming_sessions,
        'past_sessions': past_sessions,
        'today': today,
    }
    return render(request, 'classes/list.html', context)


@admin_required
def class_create_view(request):
    user = request.user
    courses = Course.objects.filter(is_active=True)
    instructors = InstructorProfile.objects.all()
    students = StudentProfile.objects.all()

    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        instructor_id = request.POST.get('instructor_id')
        title = request.POST.get('title', '').strip()
        scheduled_date = request.POST.get('scheduled_date')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        google_meet_link = request.POST.get('google_meet_link', '').strip()
        selected_student_ids = request.POST.getlist('students')

        course = get_object_or_404(Course, id=course_id)
        inst = get_object_or_404(InstructorProfile, id=instructor_id)

        parsed_start_time = start_time
        parsed_end_time = end_time
        try:
            if isinstance(start_time, str) and start_time:
                parsed_start_time = datetime.strptime(start_time, '%H:%M').time()
            if isinstance(end_time, str) and end_time:
                parsed_end_time = datetime.strptime(end_time, '%H:%M').time()
        except (ValueError, TypeError):
            pass

        max_num = course.sessions.order_by('-session_number').first()
        next_num = (max_num.session_number + 1) if max_num else 1

        session = ClassSession.objects.create(
            course=course,
            instructor=inst,
            session_number=next_num,
            title=title or f"حصة {next_num}",
            scheduled_date=scheduled_date,
            start_time=parsed_start_time,
            end_time=parsed_end_time,
            google_meet_link=google_meet_link or 'https://meet.google.com/abc-defg-hij',
            status=ClassSession.Status.SCHEDULED
        )

        start_display = session.start_time.strftime('%H:%M') if hasattr(session.start_time, 'strftime') else str(session.start_time)

        for s_id in selected_student_ids:
            st = StudentProfile.objects.filter(id=s_id).first()
            if st:
                ClassStudent.objects.create(class_session=session, student=st)
                Attendance.objects.create(class_session=session, student=st, status=Attendance.Status.ABSENT)
                Notification.objects.create(
                    recipient=st.user,
                    title=f"ميعاد حصة جديدة: {session.title}",
                    message=f"عندك حصة يوم {session.scheduled_date} الساعة {start_display} مع م/ {inst.user.display_name}.",
                    link=f"/classes/{session.id}/",
                    notification_type=Notification.NotificationType.CLASS_REMINDER
                )

        messages.success(request, f"تم جدولة حصة '{session.title}' بنجاح لـ {len(selected_student_ids)} طالب.")
        return redirect('class_detail', session_id=session.id)

    return render(request, 'classes/form.html', {
        'courses': courses,
        'instructors': instructors,
        'students': students,
    })


@login_required
def class_detail_view(request, session_id):
    session = ClassSession.objects.filter(id=session_id).first()
    if not session:
        messages.warning(request, "الحصة دي مش موجودة أو تم تحديث ميعادها وجدولتها من الإدارة.")
        return redirect('classes_list')

    user = request.user

    # Security check for instructor data isolation
    if user.is_instructor_role and not user.is_admin_role:
        if session.instructor.user != user:
            messages.error(request, "غير مسموح لك بعرض حصص مدرس آخر.")
            return redirect('classes_list')

    # Security check for student
    my_attendance = None
    has_downloaded_booklet = False
    is_lesson_completed = False
    if user.is_student_role:
        student = getattr(user, 'student_profile', None)
        if not session.students.filter(id=student.id).exists():
            messages.error(request, "أنت غير مسجل في هذه الحصة.")
            return redirect('classes_list')
        my_attendance = session.attendances.filter(student=student).first()

        # Check booklet download activity
        has_downloaded_booklet = StudentActivity.objects.filter(
            student=student,
            activity_type=StudentActivity.ActivityType.DOWNLOAD_MATERIAL,
            metadata__session_id=session.id
        ).exists() or StudentActivity.objects.filter(
            student=student,
            activity_type=StudentActivity.ActivityType.DOWNLOAD_MATERIAL,
            description__icontains=session.title
        ).exists()

        is_attended = my_attendance and my_attendance.status in [Attendance.Status.PRESENT, Attendance.Status.LATE]
        if is_attended and (has_downloaded_booklet or not session.summary_file):
            is_lesson_completed = True

    attendances = session.attendances.select_related('student__user').all() if not user.is_student_role else []
    recording = getattr(session, 'recording', None)
    assignments = session.assignments.all()

    can_manage = user.is_admin_role or (user.is_instructor_role and session.instructor.user == user)
    is_instructor_owner = user.is_instructor_role and session.instructor.user == user

    context = {
        'session': session,
        'attendances': attendances,
        'my_attendance': my_attendance,
        'has_downloaded_booklet': has_downloaded_booklet,
        'is_lesson_completed': is_lesson_completed,
        'recording': recording,
        'assignments': assignments,
        'can_manage': can_manage,
        'is_instructor_owner': is_instructor_owner,
        'is_admin': user.is_admin_role,
        'is_completed': session.status == ClassSession.Status.COMPLETED,
    }
    return render(request, 'classes/detail.html', context)


@instructor_or_admin_required
def session_update_title_view(request, session_id):
    """
    تعديل اسم الحصة فقط (صلاحية المدرس والأدمن)
    """
    session = ClassSession.objects.filter(id=session_id).first()
    if not session:
        messages.warning(request, "الحصة المطلوبة غير موجودة.")
        return redirect('classes_list')

    user = request.user
    if user.is_instructor_role and not user.is_admin_role:
        if session.instructor.user != user:
            messages.error(request, "غير مسموح لك بتعديل حصة مدرس آخر.")
            return redirect('class_detail', session_id=session.id)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if title:
            session.title = title
            session.save()
            messages.success(request, f"تم تحديث اسم الحصة إلى: '{title}'")
        else:
            messages.error(request, "اسم الحصة لا يمكن أن يكون فارغاً.")

    return redirect('class_detail', session_id=session.id)


@login_required
def join_class_view(request, session_id):
    """
    GOOGLE MEET JOIN & ATTENDANCE AUTOMATION ENGINE
    """
    session = ClassSession.objects.filter(id=session_id).first()
    if not session:
        messages.warning(request, "الحصة دي مش موجودة أو تم تحديث ميعادها.")
        return redirect('classes_list')

    user = request.user

    # 1. Block access if session is completed
    if session.status == ClassSession.Status.COMPLETED:
        messages.info(request, "الحصة دي انتهت بالفعل.")
        return redirect('class_detail', session_id=session.id)

    # 2. Block access if class scheduled time has not arrived yet (Admins can preview)
    if not user.is_admin_role and session.is_before_time:
        time_str = session.start_time.strftime('%I:%M %p')
        date_str = session.scheduled_date.strftime('%Y-%m-%d')
        messages.warning(request, f"ميعاد الحصة لسه مجاش. الزرار هيفتح في ميعاد الحصة المحدد (يوم {date_str} الساعة {time_str}).")
        return redirect('class_detail', session_id=session.id)

    # 3. Instructor Access
    if user.is_instructor_role:
        if session.instructor.user != user:
            messages.error(request, "غير مسموح لك بالدخول لحصة مدرس آخر.")
            return redirect('class_detail', session_id=session.id)
        if session.status == ClassSession.Status.SCHEDULED:
            session.status = ClassSession.Status.ONGOING
            session.save()
        return HttpResponseRedirect(session.google_meet_link)

    if user.is_admin_role:
        return HttpResponseRedirect(session.google_meet_link)

    student = getattr(user, 'student_profile', None)
    if not student or not session.students.filter(id=student.id).exists():
        messages.error(request, "أنت غير مسجل في هذه الحصة.")
        return redirect('classes_list')

    # 1. Log Student Activity
    StudentActivity.objects.create(
        student=student,
        activity_type=StudentActivity.ActivityType.JOIN_CLASS,
        description=f"الضغط على [ادخل الحصة] لحصة '{session.title}' عبر جوجل ميت",
        metadata={'session_id': session.id, 'google_meet_link': session.google_meet_link}
    )

    # 2. Evaluate Attendance Rule
    rule = AttendanceRule.get_current_rule()
    now = timezone.localtime()
    session_start_dt = timezone.make_aware(
        datetime.combine(session.scheduled_date, session.start_time),
        timezone.get_current_timezone()
    )

    minutes_diff = (now - session_start_dt).total_seconds() / 60.0

    if minutes_diff <= rule.late_cutoff_minutes:
        status = Attendance.Status.PRESENT
    else:
        status = Attendance.Status.LATE

    # 3. Update or Create Attendance Record
    attendance, _ = Attendance.objects.get_or_create(
        class_session=session,
        student=student
    )
    if attendance.status != Attendance.Status.PRESENT or status == Attendance.Status.PRESENT:
        attendance.status = status
    attendance.join_time = now
    attendance.click_join_event = True
    attendance.save()

    # 4. Update session to ONGOING if it was SCHEDULED
    if session.status == ClassSession.Status.SCHEDULED:
        session.status = ClassSession.Status.ONGOING
        session.save()

    # 5. Recalculate student progress
    recalculate_student_progress(student, session.course)

    # 6. Redirect to official Google Meet URL
    return HttpResponseRedirect(session.google_meet_link)


@instructor_or_admin_required
def session_post_class_update_view(request, session_id):
    """
    تحديث شرح الحصة والواجب والتسجيل بعد انتهاء الحصة
    """
    session = ClassSession.objects.filter(id=session_id).first()
    if not session:
        messages.warning(request, "الحصة المطلوبة غير موجودة أو تم حذفها.")
        return redirect('classes_list')

    user = request.user
    if user.is_instructor_role and not user.is_admin_role:
        if session.instructor.user != user:
            messages.error(request, "غير مسموح لك بتعديل حصة مدرس آخر.")
            return redirect('class_detail', session_id=session.id)

    # Restriction: Only when class is completed!
    if session.status != ClassSession.Status.COMPLETED:
        messages.error(request, "شرح الحصة والواجب يمكن إضافتهما فقط بعد انتهاء الحصة.")
        return redirect('class_detail', session_id=session.id)

    if request.method == 'POST':
        summary = request.POST.get('summary', '').strip()
        summary_file = request.FILES.get('summary_file')
        recording_url = request.POST.get('recording_url', '').strip()

        session.summary = summary
        if summary_file:
            session.summary_file = summary_file
        session.save()

        if recording_url:
            Recording.objects.update_or_create(
                class_session=session,
                defaults={
                    'recording_url': recording_url,
                    'title': f"تسجيل: {session.title}",
                    'notes': summary[:200] if summary else 'تسجيل الحصة',
                    'is_available': True
                }
            )

        assignment_title = request.POST.get('assignment_title', '').strip()
        assignment_desc = request.POST.get('assignment_description', '').strip()
        due_date_str = request.POST.get('assignment_due_date')
        starter_file = request.FILES.get('starter_file')

        existing_assignment = session.assignments.first()

        # If user uploaded a starter file, or entered title/description, or if an assignment exists
        if starter_file or assignment_title or assignment_desc or (existing_assignment and due_date_str):
            if not assignment_title:
                assignment_title = existing_assignment.title if existing_assignment else f"واجب {session.title}"

            if not assignment_desc:
                assignment_desc = existing_assignment.description if existing_assignment else "يرجى حل المطلوب في ملف الواجب وتسليمه قبل انتهاء الموعد المحدد."

            parsed_due = None
            if due_date_str:
                try:
                    parsed_due = timezone.make_aware(datetime.fromisoformat(due_date_str))
                except Exception:
                    pass
            if not parsed_due:
                parsed_due = existing_assignment.due_date if existing_assignment else (timezone.now() + timedelta(days=7))

            if existing_assignment:
                existing_assignment.title = assignment_title
                existing_assignment.description = assignment_desc
                existing_assignment.due_date = parsed_due
                if starter_file:
                    existing_assignment.starter_file = starter_file
                existing_assignment.is_published = True
                existing_assignment.save()
            else:
                Assignment.objects.create(
                    course=session.course,
                    session=session,
                    instructor=session.instructor,
                    title=assignment_title,
                    description=assignment_desc,
                    due_date=parsed_due,
                    starter_file=starter_file,
                    is_published=True
                )

        messages.success(request, "تم حفظ وتحديث شرح الحصة والواجب والتسجيل بنجاح.")

    return redirect('class_detail', session_id=session.id)


@login_required
def class_download_booklet_view(request, session_id):
    """
    تحميل ملزمة الحصة مع تسجيل نشاط الطالب وتحديث التقدم الدراسي
    (حضور الحصة + تحميل الملزمة = إتمام دراسة الدرس)
    """
    session = get_object_or_404(ClassSession, id=session_id)
    user = request.user

    # Security check for student
    if user.is_student_role:
        student = getattr(user, 'student_profile', None)
        if not session.students.filter(id=student.id).exists():
            messages.error(request, "أنت غير مسجل في هذه الحصة.")
            return redirect('classes_list')

        if not session.summary_file:
            messages.warning(request, "لم يتم رفع ملزمة لهذه الحصة بعد.")
            return redirect('class_detail', session_id=session.id)

        # Record booklet download activity
        StudentActivity.objects.create(
            student=student,
            activity_type=StudentActivity.ActivityType.DOWNLOAD_MATERIAL,
            description=f"تحميل ملزمة {session.title} - {session.course.title}",
            metadata={'session_id': session.id, 'file': session.summary_file.name}
        )

        # Check if student attended
        attendance = Attendance.objects.filter(class_session=session, student=student).first()
        is_attended = attendance and attendance.status in [Attendance.Status.PRESENT, Attendance.Status.LATE]

        if is_attended:
            StudentActivity.objects.get_or_create(
                student=student,
                activity_type=StudentActivity.ActivityType.WATCH_LESSON,
                description=f"مذاكرة وإتمام درس: {session.title} ({session.course.title})",
                metadata={'session_id': session.id}
            )

        # Recalculate student progress
        recalculate_student_progress(student, session.course)

        return redirect(session.summary_file.url)

    # For instructors and admin
    if not session.summary_file:
        messages.warning(request, "لم يتم رفع ملزمة لهذه الحصة بعد.")
        return redirect('class_detail', session_id=session.id)

    return redirect(session.summary_file.url)


@instructor_or_admin_required
def complete_class_view(request, session_id):
    """
    إنهاء الحصة وتثبيت الحضور، وإتاحة كتابة شرح الحصة ورفع الواجب والتسجيل
    """
    session = ClassSession.objects.filter(id=session_id).first()
    if not session:
        messages.warning(request, "الحصة المطلوبة غير موجودة أو تم حذفها.")
        return redirect('classes_list')

    user = request.user
    if user.is_instructor_role and not user.is_admin_role:
        if session.instructor.user != user:
            messages.error(request, "غير مسموح لك بإنهاء حصة مدرس آخر.")
            return redirect('class_detail', session_id=session.id)

    if request.method == 'POST':
        recording_url = request.POST.get('recording_url', '').strip()
        summary = request.POST.get('summary', '').strip()
        summary_file = request.FILES.get('summary_file')
        notes = request.POST.get('notes', '').strip()

        if summary:
            session.summary = summary
        if summary_file:
            session.summary_file = summary_file
        if summary or summary_file:
            session.save()

        success, msg = run_session_completion_workflow(
            session_id=session.id,
            recording_url=recording_url if recording_url else None,
            notes=notes or summary
        )

        assignment_title = request.POST.get('assignment_title', '').strip()
        assignment_desc = request.POST.get('assignment_description', '').strip()
        due_date_str = request.POST.get('assignment_due_date')
        starter_file = request.FILES.get('starter_file')

        existing_assignment = session.assignments.first()

        if starter_file or assignment_title or assignment_desc:
            if not assignment_title:
                assignment_title = existing_assignment.title if existing_assignment else f"واجب {session.title}"

            if not assignment_desc:
                assignment_desc = existing_assignment.description if existing_assignment else "يرجى حل المطلوب في ملف الواجب وتسليمه قبل انتهاء الموعد المحدد."

            parsed_due = None
            if due_date_str:
                try:
                    parsed_due = timezone.make_aware(datetime.fromisoformat(due_date_str))
                except Exception:
                    pass
            if not parsed_due:
                parsed_due = existing_assignment.due_date if existing_assignment else (timezone.now() + timedelta(days=7))

            if existing_assignment:
                existing_assignment.title = assignment_title
                existing_assignment.description = assignment_desc
                existing_assignment.due_date = parsed_due
                if starter_file:
                    existing_assignment.starter_file = starter_file
                existing_assignment.is_published = True
                existing_assignment.save()
            else:
                Assignment.objects.create(
                    course=session.course,
                    session=session,
                    instructor=session.instructor,
                    title=assignment_title,
                    description=assignment_desc,
                    due_date=parsed_due,
                    starter_file=starter_file,
                    is_published=True
                )

        if success:
            messages.success(request, f"تم إنهاء الحصة '{session.title}'، تثبيت الحضور، وحفظ الشرح والواجب بنجاح.")
        else:
            messages.error(request, msg)

    return redirect('class_detail', session_id=session.id)


# ==========================================
# 3. ATTENDANCE MANAGEMENT
# ==========================================

@instructor_or_admin_required
def attendance_index_view(request):
    user = request.user
    if user.is_admin_role:
        sessions = ClassSession.objects.all().order_by('-scheduled_date')
    else:
        instructor = getattr(user, 'instructor_profile', None)
        sessions = ClassSession.objects.filter(instructor=instructor).order_by('-scheduled_date')

    # Summary numbers
    all_att = Attendance.objects.filter(class_session__in=sessions)
    total = all_att.count()
    present_cnt = all_att.filter(status=Attendance.Status.PRESENT).count()
    late_cnt = all_att.filter(status=Attendance.Status.LATE).count()
    absent_cnt = all_att.filter(status=Attendance.Status.ABSENT).count()

    context = {
        'sessions': sessions,
        'total': total,
        'present_cnt': present_cnt,
        'late_cnt': late_cnt,
        'absent_cnt': absent_cnt,
    }
    return render(request, 'attendance/index.html', context)


@instructor_or_admin_required
def attendance_session_view(request, session_id):
    session = ClassSession.objects.filter(id=session_id).first()
    if not session:
        messages.warning(request, "الحصة المطلوبة غير موجودة.")
        return redirect('attendance_index')

    user = request.user

    if user.is_instructor_role and not user.is_admin_role:
        if session.instructor.user != user:
            messages.error(request, "Access denied.")
            return redirect('attendance_index')

    if request.method == 'POST':
        # Update attendance entries
        for att in session.attendances.all():
            field_name = f"status_{att.id}"
            if field_name in request.POST:
                new_status = request.POST.get(field_name)
                if new_status in [Attendance.Status.PRESENT, Attendance.Status.LATE, Attendance.Status.ABSENT]:
                    att.status = new_status
                    att.manual_override = True
                    att.save()
                    recalculate_student_progress(att.student, session.course)

        messages.success(request, "Attendance roster updated successfully.")
        return redirect('attendance_session', session_id=session.id)

    attendances = session.attendances.select_related('student__user').all()
    return render(request, 'attendance/session_attendance.html', {'session': session, 'attendances': attendances})


# ==========================================
# 4. STUDENTS & INSTRUCTORS DIRECTORY
# ==========================================

@login_required
def students_list_view(request):
    user = request.user
    query = request.GET.get('q', '').strip()
    mode_filter = request.GET.get('mode', '')

    if user.is_admin_role:
        students = StudentProfile.objects.select_related('user', 'assigned_instructor__user').all()
    elif user.is_instructor_role:
        instructor = getattr(user, 'instructor_profile', None)
        students = StudentProfile.objects.filter(
            Q(assigned_instructor=instructor) | Q(courses__instructor=instructor)
        ).distinct().select_related('user', 'assigned_instructor__user')
    else:
        raise Http404("Not accessible")

    if query:
        students = students.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
    if mode_filter in [StudentProfile.LearningMode.ONLINE, StudentProfile.LearningMode.OFFLINE]:
        students = students.filter(learning_mode=mode_filter)

    return render(request, 'students/list.html', {
        'students': students,
        'query': query,
        'mode_filter': mode_filter
    })


@admin_required
def student_add_edit_view(request, student_id=None):
    student = get_object_or_404(StudentProfile, id=student_id) if student_id else None
    instructors = InstructorProfile.objects.all()
    courses = Course.objects.filter(is_active=True)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        learning_mode = request.POST.get('learning_mode', StudentProfile.LearningMode.ONLINE)
        instructor_id = request.POST.get('instructor_id')
        phone = request.POST.get('phone', '').strip()
        emergency_contact = request.POST.get('emergency_contact', '').strip()
        emergency_phone = request.POST.get('emergency_phone', '').strip()
        offline_center_notes = request.POST.get('offline_center_notes', '').strip()
        selected_courses = request.POST.getlist('courses')
        password = request.POST.get('password', '')

        instructor = InstructorProfile.objects.filter(id=instructor_id).first() if instructor_id else None

        if student:
            u = student.user
            u.first_name = first_name
            u.last_name = last_name
            u.email = email
            u.phone = phone
            if password:
                u.set_password(password)
            u.save()

            student.learning_mode = learning_mode
            student.assigned_instructor = instructor
            student.emergency_contact = emergency_contact
            student.emergency_phone = emergency_phone
            student.offline_center_notes = offline_center_notes
            student.save()
            student.courses.set(selected_courses)
            messages.success(request, f"Student '{u.display_name}' updated successfully.")
        else:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists. Choose a different one.")
                return render(request, 'students/form.html', {'student': student, 'instructors': instructors, 'courses': courses})

            u = User.objects.create_user(
                username=username,
                email=email,
                password=password or 'student123',
                first_name=first_name,
                last_name=last_name,
                role=User.Role.STUDENT,
                phone=phone
            )
            student = StudentProfile.objects.create(
                user=u,
                learning_mode=learning_mode,
                assigned_instructor=instructor,
                emergency_contact=emergency_contact,
                emergency_phone=emergency_phone,
                offline_center_notes=offline_center_notes
            )
            student.courses.set(selected_courses)
            messages.success(request, f"Student '{u.display_name}' created successfully.")

        return redirect('student_detail', student_id=student.id)

    return render(request, 'students/form.html', {
        'student': student,
        'instructors': instructors,
        'courses': courses,
    })


@login_required
def student_detail_view(request, student_id):
    student = get_object_or_404(StudentProfile, id=student_id)
    user = request.user

    # Security check: Instructor can only view if assigned or teaching this student
    if user.is_instructor_role and not user.is_admin_role:
        instructor = getattr(user, 'instructor_profile', None)
        if student.assigned_instructor != instructor and not student.courses.filter(instructor=instructor).exists():
            messages.error(request, "Access denied. You do not have permission to view this student's profile.")
            return redirect('students_list')

    progress_records = student.progress_records.select_related('course').all()
    attendances = student.attendances.select_related('class_session__course').order_by('-class_session__scheduled_date')[:10]
    submissions = student.submissions.select_related('assignment__course').order_by('-submitted_at')[:8]
    quiz_attempts = student.quiz_attempts.select_related('quiz__course').order_by('-completed_at')[:8]
    activities = student.activities.all()[:10]

    context = {
        'student': student,
        'progress_records': progress_records,
        'attendances': attendances,
        'submissions': submissions,
        'quiz_attempts': quiz_attempts,
        'activities': activities,
    }
    return render(request, 'students/detail.html', context)


@admin_required
def instructors_list_view(request):
    instructors = InstructorProfile.objects.select_related('user').all()
    return render(request, 'instructors/list.html', {'instructors': instructors})


@admin_required
def instructor_add_edit_view(request, instructor_id=None):
    inst = get_object_or_404(InstructorProfile, id=instructor_id) if instructor_id else None

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        specialization = request.POST.get('specialization', '').strip()
        bio = request.POST.get('bio', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '')

        if inst:
            u = inst.user
            u.first_name = first_name
            u.last_name = last_name
            u.email = email
            u.phone = phone
            if password:
                u.set_password(password)
            u.save()

            inst.specialization = specialization
            inst.bio = bio
            inst.save()
            messages.success(request, f"Instructor Eng. {u.display_name} updated successfully.")
        else:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists.")
                return render(request, 'instructors/form.html', {'instructor': inst})

            u = User.objects.create_user(
                username=username,
                email=email,
                password=password or 'instructor123',
                first_name=first_name,
                last_name=last_name,
                role=User.Role.INSTRUCTOR,
                phone=phone
            )
            inst = InstructorProfile.objects.create(
                user=u,
                specialization=specialization,
                bio=bio
            )
            messages.success(request, f"Instructor Eng. {u.display_name} registered successfully.")

        return redirect('instructors_list')

    return render(request, 'instructors/form.html', {'instructor': inst})
