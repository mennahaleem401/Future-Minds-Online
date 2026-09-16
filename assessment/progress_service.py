from decimal import Decimal
from django.db.models import Avg
from academy.models import Course, Lesson, ClassSession, Attendance
from .models import Assignment, Submission, Quiz, QuizAttempt, StudentProgress
from core.models import StudentActivity


def recalculate_student_progress(student, course):
    """
    Computes true engagement-based academic progress:
    - Attendance Rate: Classes attended (Present/Late) / total completed classes
    - Lesson Views: Lessons viewed / total lessons in course
    - Assignment Score: Average score % across assigned course assignments
    - Quiz Average: Average score % across course quizzes
    Overall = 25% Attendance + 25% Lessons + 25% Assignments + 25% Quizzes
    """
    # 1. Attendance Rate
    total_completed_classes = ClassSession.objects.filter(
        course=course,
        status=ClassSession.Status.COMPLETED
    ).count()

    if total_completed_classes > 0:
        attended_count = Attendance.objects.filter(
            class_session__course=course,
            class_session__status=ClassSession.Status.COMPLETED,
            student=student,
            status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]
        ).count()
        attendance_rate = (attended_count / total_completed_classes) * 100
    else:
        attendance_rate = 0.0

    # 2. Lessons Completed / Viewed (Attendance + Booklet Download for Sessions, or Lessons viewed)
    total_lessons = Lesson.objects.filter(course=course).count()
    if total_lessons == 0:
        total_lessons = ClassSession.objects.filter(course=course).count()

    viewed_lessons_count = 0
    if total_lessons > 0:
        # Check sessions where student attended (PRESENT or LATE) AND downloaded booklet (if summary_file exists)
        sessions_in_course = ClassSession.objects.filter(course=course)
        if sessions_in_course.exists():
            attended_session_ids = set(Attendance.objects.filter(
                class_session__in=sessions_in_course,
                student=student,
                status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]
            ).values_list('class_session_id', flat=True))

            # Downloaded booklets for this student
            downloaded_session_ids = set()
            booklet_activities = StudentActivity.objects.filter(
                student=student,
                activity_type=StudentActivity.ActivityType.DOWNLOAD_MATERIAL
            )
            for act in booklet_activities:
                s_id = act.metadata.get('session_id') if isinstance(act.metadata, dict) else None
                if s_id:
                    try:
                        downloaded_session_ids.add(int(s_id))
                    except (ValueError, TypeError):
                        pass

            completed_sessions_count = 0
            for s in sessions_in_course:
                if s.id in attended_session_ids:
                    # If session has a booklet, require student to have downloaded it
                    if s.summary_file:
                        if s.id in downloaded_session_ids:
                            completed_sessions_count += 1
                    else:
                        completed_sessions_count += 1

            viewed_lessons_count = completed_sessions_count

        # Also check standard lesson views if any
        standard_lessons_viewed = StudentActivity.objects.filter(
            student=student,
            activity_type__in=[StudentActivity.ActivityType.OPEN_LESSON, StudentActivity.ActivityType.WATCH_LESSON],
            description__icontains=course.title
        ).values('description').distinct().count()

        viewed_lessons_count = max(viewed_lessons_count, standard_lessons_viewed)
        viewed_lessons_count = min(viewed_lessons_count, total_lessons)
        lesson_rate = (viewed_lessons_count / total_lessons) * 100
    else:
        lesson_rate = 0.0

    # 3. Assignment Score Average
    course_assignments = Assignment.objects.filter(course=course, is_published=True)
    total_assignments = course_assignments.count()
    if total_assignments > 0:
        graded_submissions = Submission.objects.filter(
            assignment__in=course_assignments,
            student=student,
            status=Submission.Status.GRADED
        )
        if graded_submissions.exists():
            avg_score = graded_submissions.aggregate(Avg('score'))['score__avg'] or 0.0
            assignment_score_avg = float(avg_score)
        else:
            # Check if any submissions made
            if Submission.objects.filter(assignment__in=course_assignments, student=student).exists():
                assignment_score_avg = 50.0  # Pending grading baseline
            else:
                assignment_score_avg = 0.0
    else:
        assignment_score_avg = 0.0

    # 4. Quiz Average
    course_quizzes = Quiz.objects.filter(course=course, is_published=True)
    total_quizzes = course_quizzes.count()
    if total_quizzes > 0:
        attempts = QuizAttempt.objects.filter(
            quiz__in=course_quizzes,
            student=student
        )
        if attempts.exists():
            quiz_score_avg = float(attempts.aggregate(Avg('percentage'))['percentage__avg'] or 0.0)
        else:
            quiz_score_avg = 0.0
    else:
        quiz_score_avg = 0.0

    # Weighted Overall Percentage based on available components
    weights_total = 0.0
    weighted_sum = 0.0

    if total_completed_classes > 0:
        weighted_sum += attendance_rate
        weights_total += 1.0

    if total_lessons > 0:
        weighted_sum += lesson_rate
        weights_total += 1.0

    if total_assignments > 0:
        weighted_sum += assignment_score_avg
        weights_total += 1.0

    if total_quizzes > 0:
        weighted_sum += quiz_score_avg
        weights_total += 1.0

    if weights_total > 0:
        overall = weighted_sum / weights_total
    else:
        overall = 0.0

    overall = max(0.0, min(100.0, overall))

    progress, _ = StudentProgress.objects.update_or_create(
        student=student,
        course=course,
        defaults={
            'attendance_rate': Decimal(str(round(attendance_rate, 2))),
            'lessons_completed_count': viewed_lessons_count,
            'assignment_score_avg': Decimal(str(round(assignment_score_avg, 2))),
            'quiz_score_avg': Decimal(str(round(quiz_score_avg, 2))),
            'overall_percentage': Decimal(str(round(overall, 2))),
        }
    )
    return progress
