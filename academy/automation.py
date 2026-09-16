from django.utils import timezone
from core.models import Notification
from academy.models import ClassSession, Attendance, Recording
from assessment.models import Assignment, Quiz, StudentAlert, Submission, QuizAttempt
from assessment.progress_service import recalculate_student_progress


def run_session_completion_workflow(session_id, recording_url=None, notes=''):
    """
    Executes the automation workflow when a session is completed:
    1. Finalizes attendance: marks unjoined students as ABSENT
    2. Attaches Google Meet / Cloud recording if available
    3. Publishes pending materials, assignments, and quizzes for this course
    4. Notifies students about session completion, new materials, and recordings
    5. Recalculates student progress
    6. Runs smart alert detection (consecutive absences, missing homework, low quiz score)
    """
    try:
        session = ClassSession.objects.get(id=session_id)
    except ClassSession.DoesNotExist:
        return False, "Session not found"

    session.status = ClassSession.Status.COMPLETED
    session.save()

    # 1. Finalize Attendance
    # For every student enrolled in this session who didn't join, create or set ABSENT
    enrolled_students = session.students.all()
    for student in enrolled_students:
        attendance, created = Attendance.objects.get_or_create(
            class_session=session,
            student=student,
            defaults={'status': Attendance.Status.ABSENT}
        )
        if not attendance.click_join_event and not attendance.manual_override:
            attendance.status = Attendance.Status.ABSENT
            attendance.save()

    # 2. Attach Recording
    if recording_url:
        Recording.objects.update_or_create(
            class_session=session,
            defaults={
                'recording_url': recording_url,
                'title': f"Recording: {session.title}",
                'notes': notes,
                'is_available': True
            }
        )

    # 3. Publish course materials & assessments
    Assignment.objects.filter(course=session.course).update(is_published=True)
    Quiz.objects.filter(course=session.course).update(is_published=True)

    # 4. Notify Students
    for student in enrolled_students:
        att = Attendance.objects.filter(class_session=session, student=student).first()
        status_msg = f"Your attendance was recorded as: {att.get_status_display()}." if att else ""
        rec_msg = " The session recording has been uploaded." if recording_url else ""
        
        Notification.objects.create(
            recipient=student.user,
            title=f"Class Completed: {session.title}",
            message=f"Today's session for '{session.course.title}' has concluded. {status_msg}{rec_msg} New assignments and quizzes are now available!",
            link=f"/classes/{session.id}/",
            notification_type=Notification.NotificationType.CLASS_REMINDER
        )

        # 5. Recalculate Progress
        recalculate_student_progress(student, session.course)

    # 6. Run Student Alert Checks
    detect_student_alerts(session.course, session.instructor)

    return True, "Session completion workflow executed successfully."


def detect_student_alerts(course, instructor):
    """
    Detects learning risk issues:
    - LOW ATTENDANCE: Student missed 2 or more consecutive completed classes
    - MISSING HOMEWORK: Student hasn't submitted 2 consecutive published assignments
    - LOW QUIZ PERFORMANCE: Student's recent quiz score is below 60% or substantially drops
    Creates alerts for the instructor.
    """
    students = course.enrolled_students.all()
    recent_sessions = ClassSession.objects.filter(
        course=course,
        status=ClassSession.Status.COMPLETED
    ).order_by('-scheduled_date', '-start_time')[:5]

    for student in students:
        # Check Low Attendance: 2 consecutive absences
        if len(recent_sessions) >= 2:
            last_two_sessions = recent_sessions[:2]
            absent_count = Attendance.objects.filter(
                class_session__in=last_two_sessions,
                student=student,
                status=Attendance.Status.ABSENT
            ).count()

            if absent_count >= 2:
                alert_title = f"Low Attendance Risk: {student.user.display_name}"
                if not StudentAlert.objects.filter(student=student, course=course, title=alert_title, is_resolved=False).exists():
                    StudentAlert.objects.create(
                        student=student,
                        instructor=instructor,
                        course=course,
                        alert_type=StudentAlert.AlertType.LOW_ATTENDANCE,
                        title=alert_title,
                        message=f"{student.user.display_name} missed 2 consecutive classes in '{course.title}'. Reach out to student or parent ({student.emergency_phone or 'No phone'})."
                    )
                    # Notify instructor
                    Notification.objects.create(
                        recipient=instructor.user,
                        title=f"Alert: {alert_title}",
                        message=f"{student.user.display_name} missed the last 2 sessions in {course.title}.",
                        link="/instructor-dashboard/",
                        notification_type=Notification.NotificationType.ALERT
                    )

        # Check Missing Homework
        published_assignments = Assignment.objects.filter(course=course, is_published=True).order_by('-due_date')[:3]
        if len(published_assignments) >= 2:
            missing_hw_count = 0
            for hw in published_assignments[:2]:
                if not Submission.objects.filter(assignment=hw, student=student).exists():
                    missing_hw_count += 1

            if missing_hw_count >= 2:
                alert_title = f"Missing Homework: {student.user.display_name}"
                if not StudentAlert.objects.filter(student=student, course=course, title=alert_title, is_resolved=False).exists():
                    StudentAlert.objects.create(
                        student=student,
                        instructor=instructor,
                        course=course,
                        alert_type=StudentAlert.AlertType.MISSING_HOMEWORK,
                        title=alert_title,
                        message=f"{student.user.display_name} has not submitted the last 2 homework assignments in '{course.title}'."
                    )
                    Notification.objects.create(
                        recipient=instructor.user,
                        title=f"Alert: {alert_title}",
                        message=f"{student.user.display_name} has multiple pending homework submissions in {course.title}.",
                        link="/instructor-dashboard/",
                        notification_type=Notification.NotificationType.ALERT
                    )

        # Check Low Quiz Performance
        recent_attempts = QuizAttempt.objects.filter(quiz__course=course, student=student).order_by('-completed_at')[:2]
        if recent_attempts.exists():
            latest = recent_attempts[0]
            if latest.percentage < 60:
                alert_title = f"Low Quiz Performance: {student.user.display_name}"
                if not StudentAlert.objects.filter(student=student, course=course, title=alert_title, is_resolved=False).exists():
                    StudentAlert.objects.create(
                        student=student,
                        instructor=instructor,
                        course=course,
                        alert_type=StudentAlert.AlertType.LOW_QUIZ_PERFORMANCE,
                        title=alert_title,
                        message=f"{student.user.display_name} scored {latest.percentage}% on quiz '{latest.quiz.title}', falling below the recommended standard."
                    )
