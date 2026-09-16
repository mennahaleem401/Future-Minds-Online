from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from core.models import User, StudentProfile, InstructorProfile, StudentActivity, Notification
from core.decorators import admin_required, instructor_required, student_required, instructor_or_admin_required
from academy.models import Course, Lesson
from .models import Assignment, Submission, Quiz, Question, QuizAttempt, StudentProgress, StudentAlert
from .progress_service import recalculate_student_progress
from .extractor import extract_questions_from_file


# ==========================================
# 1. ASSIGNMENTS & SUBMISSIONS
# ==========================================

@login_required
def assignment_list_view(request):
    user = request.user

    if user.is_admin_role:
        assignments = Assignment.objects.all()
    elif user.is_instructor_role:
        instructor = getattr(user, 'instructor_profile', None)
        assignments = Assignment.objects.filter(instructor=instructor)
    else:  # Student
        student = getattr(user, 'student_profile', None)
        assignments = Assignment.objects.filter(
            course__in=student.courses.all(),
            is_published=True
        )

    # Attach submission status if student
    if user.is_student_role and student:
        submitted_ids = set(Submission.objects.filter(student=student).values_list('assignment_id', flat=True))
        for a in assignments:
            a.has_submitted = a.id in submitted_ids

    return render(request, 'assignments/list.html', {'assignments': assignments})


@login_required
def assignment_detail_view(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = request.user

    # Security check: Instructor isolation
    if user.is_instructor_role and not user.is_admin_role:
        if assignment.instructor.user != user:
            messages.error(request, "Access denied.")
            return redirect('assignments_list')

    # If student, fetch their submission
    student_submission = None
    if user.is_student_role:
        student = getattr(user, 'student_profile', None)
        student_submission = Submission.objects.filter(assignment=assignment, student=student).first()

    # If instructor or admin, show all student submissions
    submissions = None
    if user.is_instructor_role or user.is_admin_role:
        submissions = assignment.submissions.select_related('student__user').all()

    context = {
        'assignment': assignment,
        'student_submission': student_submission,
        'submissions': submissions,
        'can_grade': user.is_admin_role or (user.is_instructor_role and assignment.instructor.user == user),
    }
    return render(request, 'assignments/detail.html', context)


@instructor_or_admin_required
def assignment_create_view(request):
    user = request.user
    if user.is_admin_role:
        courses = Course.objects.filter(is_active=True)
        instructors = InstructorProfile.objects.all()
    else:
        instructor = getattr(user, 'instructor_profile', None)
        courses = Course.objects.filter(instructor=instructor, is_active=True)
        instructors = [instructor]

    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        lesson_id = request.POST.get('lesson_id')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        max_score = int(request.POST.get('max_score', 100))
        due_date = request.POST.get('due_date')
        starter_file = request.FILES.get('starter_file')

        course = get_object_or_404(Course, id=course_id)
        lesson = Lesson.objects.filter(id=lesson_id).first() if lesson_id else None
        inst = getattr(user, 'instructor_profile', None) or course.instructor

        assignment = Assignment.objects.create(
            course=course,
            lesson=lesson,
            instructor=inst,
            title=title,
            description=description,
            max_score=max_score,
            due_date=due_date,
            starter_file=starter_file,
            is_published=True
        )

        # Notify enrolled students
        for student in course.enrolled_students.all():
            Notification.objects.create(
                recipient=student.user,
                title=f"New Assignment: {assignment.title}",
                message=f"Eng. {inst.user.display_name} has assigned homework in {course.title}. Due date: {assignment.due_date}.",
                link=f"/assignments/{assignment.id}/",
                notification_type=Notification.NotificationType.ASSIGNMENT
            )

        messages.success(request, f"Assignment '{assignment.title}' created and published.")
        return redirect('assignment_detail', assignment_id=assignment.id)

    return render(request, 'assignments/form.html', {'courses': courses, 'instructors': instructors})


@student_required
def assignment_submit_view(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    student = getattr(request.user, 'student_profile', None)

    if request.method == 'POST':
        submission_text = request.POST.get('submission_text', '').strip()
        submission_file = request.FILES.get('submission_file')

        submission, created = Submission.objects.get_or_create(
            assignment=assignment,
            student=student,
            defaults={
                'submission_text': submission_text,
                'submission_file': submission_file,
                'status': Submission.Status.SUBMITTED
            }
        )

        if not created:
            submission.submission_text = submission_text
            if submission_file:
                submission.submission_file = submission_file
            submission.status = Submission.Status.SUBMITTED
            submission.submitted_at = timezone.now()
            submission.save()

        # Log Activity
        StudentActivity.objects.create(
            student=student,
            activity_type=StudentActivity.ActivityType.SUBMIT_ASSIGNMENT,
            description=f"Submitted homework for '{assignment.title}'"
        )

        # Notify Instructor
        Notification.objects.create(
            recipient=assignment.instructor.user,
            title=f"New Submission: {student.user.display_name}",
            message=f"{student.user.display_name} submitted homework for '{assignment.title}'.",
            link=f"/assignments/{assignment.id}/",
            notification_type=Notification.NotificationType.ASSIGNMENT
        )

        # Recalculate student progress
        recalculate_student_progress(student, assignment.course)

        messages.success(request, "Assignment submitted successfully! Your instructor will review and grade it.")
        return redirect('assignment_detail', assignment_id=assignment.id)

    return redirect('assignment_detail', assignment_id=assignment.id)


@instructor_or_admin_required
def submission_grade_view(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id)
    user = request.user

    if user.is_instructor_role and not user.is_admin_role:
        if submission.assignment.instructor.user != user:
            messages.error(request, "Access denied.")
            return redirect('assignments_list')

    if request.method == 'POST':
        score = request.POST.get('score')
        feedback = request.POST.get('feedback', '').strip()

        submission.score = Decimal(score) if score else 0.0
        submission.feedback = feedback
        submission.status = Submission.Status.GRADED
        submission.graded_at = timezone.now()
        submission.save()

        # Recalculate student progress
        recalculate_student_progress(submission.student, submission.assignment.course)

        # Notify student
        Notification.objects.create(
            recipient=submission.student.user,
            title=f"Assignment Graded: {submission.assignment.title}",
            message=f"You received {submission.score}/{submission.assignment.max_score} with feedback: '{submission.feedback[:80]}...'",
            link=f"/assignments/{submission.assignment.id}/",
            notification_type=Notification.NotificationType.ASSIGNMENT
        )

        messages.success(request, f"Graded submission for {submission.student.user.display_name}: Score {submission.score}")
        return redirect('assignment_detail', assignment_id=submission.assignment.id)

    return redirect('assignment_detail', assignment_id=submission.assignment.id)


# ==========================================
# 2. QUIZZES
# ==========================================

@login_required
def quiz_list_view(request):
    user = request.user

    if user.is_admin_role:
        quizzes = Quiz.objects.all()
    elif user.is_instructor_role:
        instructor = getattr(user, 'instructor_profile', None)
        quizzes = Quiz.objects.filter(instructor=instructor)
    else:  # Student
        student = getattr(user, 'student_profile', None)
        quizzes = Quiz.objects.filter(course__in=student.courses.all(), is_published=True)

    if user.is_student_role and student:
        attempts_map = {att.quiz_id: att for att in QuizAttempt.objects.filter(student=student)}
        for q in quizzes:
            q.user_attempt = attempts_map.get(q.id)

    return render(request, 'quizzes/list.html', {'quizzes': quizzes})


@login_required
def quiz_detail_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user = request.user
    questions = quiz.questions.all().order_by('id')
    questions_count = questions.count()

    attempts = []
    if user.is_student_role:
        student = getattr(user, 'student_profile', None)
        attempts = QuizAttempt.objects.filter(quiz=quiz, student=student)
    else:
        attempts = QuizAttempt.objects.filter(quiz=quiz).select_related('student__user')[:50]

    can_manage = user.is_admin_role or (user.is_instructor_role and quiz.instructor.user == user)

    context = {
        'quiz': quiz,
        'questions': questions,
        'questions_count': questions_count,
        'attempts': attempts,
        'can_manage': can_manage,
    }
    return render(request, 'quizzes/detail.html', context)


@instructor_or_admin_required
def question_edit_view(request, question_id):
    """
    تعديل سؤال فردي في الكويز (صلاحية المدرس والأدمن)
    """
    question = get_object_or_404(Question, id=question_id)
    user = request.user

    if user.is_instructor_role and not user.is_admin_role:
        if question.quiz.instructor.user != user:
            messages.error(request, "غير مسموح لك بتعديل أسئلة كويز مدرس آخر.")
            return redirect('quiz_detail', quiz_id=question.quiz.id)

    if request.method == 'POST':
        prompt = request.POST.get('prompt', '').strip()
        option_a = request.POST.get('option_a', '').strip()
        option_b = request.POST.get('option_b', '').strip()
        option_c = request.POST.get('option_c', '').strip()
        option_d = request.POST.get('option_d', '').strip()
        correct_option = request.POST.get('correct_option', 'A').strip().upper()
        explanation = request.POST.get('explanation', '').strip()
        try:
            points = int(request.POST.get('points', 1))
        except (ValueError, TypeError):
            points = 1

        if not prompt:
            messages.error(request, "نص السؤال مطلوب ولا يمكن تركه فارغاً.")
            return redirect('quiz_detail', quiz_id=question.quiz.id)

        question.prompt = prompt
        question.option_a = option_a or 'صواب (True)'
        question.option_b = option_b or 'خطأ (False)'
        question.option_c = option_c
        question.option_d = option_d
        question.correct_option = correct_option if correct_option in ['A', 'B', 'C', 'D'] else 'A'
        question.explanation = explanation
        question.points = max(1, points)
        question.save()

        messages.success(request, "تم حفظ وتحديث بيانات السؤال بنجاح.")

    return redirect('quiz_detail', quiz_id=question.quiz.id)


@instructor_or_admin_required
def question_delete_view(request, question_id):
    """
    حذف سؤال فردي من الكويز (صلاحية المدرس والأدمن)
    """
    question = get_object_or_404(Question, id=question_id)
    user = request.user

    if user.is_instructor_role and not user.is_admin_role:
        if question.quiz.instructor.user != user:
            messages.error(request, "غير مسموح لك بحذف أسئلة كويز مدرس آخر.")
            return redirect('quiz_detail', quiz_id=question.quiz.id)

    quiz_id = question.quiz.id
    if request.method == 'POST':
        question.delete()
        messages.success(request, "تم حذف السؤال من الكويز بنجاح.")

    return redirect('quiz_detail', quiz_id=quiz_id)


@instructor_or_admin_required
def question_add_single_view(request, quiz_id):
    """
    إضافة سؤال جديد فردياً لكويز موجود
    """
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user = request.user

    if user.is_instructor_role and not user.is_admin_role:
        if quiz.instructor.user != user:
            messages.error(request, "غير مسموح لك بإضافة أسئلة إلى كويز مدرس آخر.")
            return redirect('quiz_detail', quiz_id=quiz.id)

    if request.method == 'POST':
        prompt = request.POST.get('prompt', '').strip()
        option_a = request.POST.get('option_a', '').strip()
        option_b = request.POST.get('option_b', '').strip()
        option_c = request.POST.get('option_c', '').strip()
        option_d = request.POST.get('option_d', '').strip()
        correct_option = request.POST.get('correct_option', 'A').strip().upper()
        explanation = request.POST.get('explanation', '').strip()
        try:
            points = int(request.POST.get('points', 1))
        except (ValueError, TypeError):
            points = 1

        if not prompt:
            messages.error(request, "نص السؤال مطلوب.")
            return redirect('quiz_detail', quiz_id=quiz.id)

        Question.objects.create(
            quiz=quiz,
            prompt=prompt,
            option_a=option_a or 'صواب (True)',
            option_b=option_b or 'خطأ (False)',
            option_c=option_c,
            option_d=option_d,
            correct_option=correct_option if correct_option in ['A', 'B', 'C', 'D'] else 'A',
            explanation=explanation,
            points=max(1, points)
        )

        messages.success(request, f"تمت إضافة السؤال الجديد بنجاح. إجمالي الأسئلة الآن: {quiz.questions.count()}.")

    return redirect('quiz_detail', quiz_id=quiz.id)


@instructor_or_admin_required
def quiz_create_view(request):
    user = request.user
    if user.is_admin_role:
        courses = Course.objects.filter(is_active=True)
    else:
        instructor = getattr(user, 'instructor_profile', None)
        courses = Course.objects.filter(instructor=instructor, is_active=True)

    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        time_limit = int(request.POST.get('time_limit_minutes', 15))
        passing_pct = int(request.POST.get('passing_percentage', 70))
        questions_file = request.FILES.get('questions_file')

        course = get_object_or_404(Course, id=course_id)
        inst = getattr(user, 'instructor_profile', None) or course.instructor

        quiz = Quiz.objects.create(
            course=course,
            instructor=inst,
            title=title,
            description=description,
            time_limit_minutes=time_limit,
            passing_percentage=passing_pct,
            is_published=True
        )

        # 1. Extract questions from uploaded file if provided (.docx, .xlsx, .csv, .txt, .json)
        extracted_count = 0
        if questions_file:
            extracted_questions, error_msg = extract_questions_from_file(questions_file)
            if error_msg:
                messages.warning(request, f"تنبيه بخصوص ملف الأسئلة: {error_msg}")
            for q_data in extracted_questions:
                Question.objects.create(quiz=quiz, **q_data)
                extracted_count += 1

        # 2. Parse manual questions from form (if any)
        manual_count = 0
        for i in range(1, 11):
            prompt = request.POST.get(f'q_{i}_prompt', '').strip()
            if prompt:
                opt_a = request.POST.get(f'q_{i}_opt_a', '').strip()
                opt_b = request.POST.get(f'q_{i}_opt_b', '').strip()
                opt_c = request.POST.get(f'q_{i}_opt_c', '').strip()
                opt_d = request.POST.get(f'q_{i}_opt_d', '').strip()
                correct = request.POST.get(f'q_{i}_correct', 'A')
                expl = request.POST.get(f'q_{i}_explanation', '').strip()

                Question.objects.create(
                    quiz=quiz,
                    prompt=prompt,
                    option_a=opt_a or 'صواب (True)',
                    option_b=opt_b or 'خطأ (False)',
                    option_c=opt_c,
                    option_d=opt_d,
                    correct_option=correct,
                    explanation=expl
                )
                manual_count += 1

        total_q = quiz.questions.count()
        success_msg = f"تم إنشاء الكويز '{quiz.title}' بنجاح مع {total_q} أسئلة."
        if extracted_count > 0:
            success_msg += f" (تم استخراج {extracted_count} سؤال من الملف المرفوع)."
        messages.success(request, success_msg)
        return redirect('quiz_detail', quiz_id=quiz.id)

    return render(request, 'quizzes/form.html', {'courses': courses})


@instructor_or_admin_required
def quiz_upload_questions_view(request, quiz_id):
    """
    استخراج وإضافة أسئلة لكويز قائم من ملف مرفوع
    """
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user = request.user

    if user.is_instructor_role and not user.is_admin_role:
        if quiz.instructor.user != user:
            messages.error(request, "غير مسموح لك بتعديل كويز مدرس آخر.")
            return redirect('quiz_detail', quiz_id=quiz.id)

    if request.method == 'POST':
        questions_file = request.FILES.get('questions_file')
        replace_existing = request.POST.get('replace_existing') == '1'

        if not questions_file:
            messages.error(request, "يرجى اختيار ملف أسئلة صالح.")
            return redirect('quiz_detail', quiz_id=quiz.id)

        extracted_questions, error_msg = extract_questions_from_file(questions_file)
        if error_msg:
            messages.error(request, error_msg)
            return redirect('quiz_detail', quiz_id=quiz.id)

        if not extracted_questions:
            messages.warning(request, "لم يتم العثور على أي أسئلة صالحة في الملف المرفوع.")
            return redirect('quiz_detail', quiz_id=quiz.id)

        if replace_existing:
            quiz.questions.all().delete()

        for q_data in extracted_questions:
            Question.objects.create(quiz=quiz, **q_data)

        messages.success(
            request,
            f"تم استخراج وإضافة {len(extracted_questions)} سؤال بنجاح إلى الكويز '{quiz.title}'! إجمالي الأسئلة الآن: {quiz.questions.count()}."
        )

    return redirect('quiz_detail', quiz_id=quiz.id)


@student_required
def quiz_take_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, is_published=True)
    questions = quiz.questions.all()
    student = getattr(request.user, 'student_profile', None)

    # 1. منع الطالب من دخول أو إعادة الكويز أكثر من مرة
    existing_attempt = QuizAttempt.objects.filter(quiz=quiz, student=student).first()
    if existing_attempt:
        messages.warning(request, "لقد قمت بحل هذا الكويز مسبقاً، ولا يُسمح بإعادة المحاولة.")
        return render(request, 'quizzes/result.html', {
            'quiz': quiz,
            'attempt': existing_attempt,
            'questions': questions,
            'student_answers': existing_attempt.answers or {},
            'already_submitted': True
        })

    if request.method == 'POST':
        score = 0
        total = questions.count()
        student_answers = {}

        for q in questions:
            chosen = request.POST.get(f"q_{q.id}")
            student_answers[str(q.id)] = chosen
            if chosen and chosen.upper() == q.correct_option.upper():
                score += q.points

        total_points = sum(q.points for q in questions) or 1
        percentage = round((score / total_points) * 100, 2)
        passed = percentage >= quiz.passing_percentage

        attempt = QuizAttempt.objects.create(
            quiz=quiz,
            student=student,
            score=score,
            total_questions=total,
            percentage=Decimal(str(percentage)),
            passed=passed,
            answers=student_answers,
            completed_at=timezone.now()
        )

        # Log Activity
        StudentActivity.objects.create(
            student=student,
            activity_type=StudentActivity.ActivityType.COMPLETE_QUIZ,
            description=f"Completed quiz '{quiz.title}': Scored {score}/{total_points} ({percentage}%)"
        )

        # Recalculate student progress
        recalculate_student_progress(student, quiz.course)

        messages.success(request, f"تم إنهاء الكويز بنجاح! نتيجتك: {percentage}% ({'ناجح' if passed else 'راسب'}).")
        return render(request, 'quizzes/result.html', {
            'quiz': quiz,
            'attempt': attempt,
            'questions': questions,
            'student_answers': student_answers
        })

    return render(request, 'quizzes/take.html', {'quiz': quiz, 'questions': questions})


# ==========================================
# 3. STUDENT PROGRESS & ALERTS
# ==========================================

@login_required
def progress_index_view(request, student_id=None):
    user = request.user
    if student_id and (user.is_admin_role or user.is_instructor_role):
        student = get_object_or_404(StudentProfile, id=student_id)
    elif user.is_student_role:
        student = getattr(user, 'student_profile', None)
    else:
        # Fallback to first student for preview
        student = StudentProfile.objects.first()

    progress_records = StudentProgress.objects.filter(student=student).select_related('course')
    
    # Recalculate live
    if student:
        for course in student.courses.all():
            recalculate_student_progress(student, course)
        progress_records = StudentProgress.objects.filter(student=student).select_related('course')

    return render(request, 'progress/index.html', {
        'student': student,
        'progress_records': progress_records
    })


@instructor_or_admin_required
def resolve_alert_view(request, alert_id):
    alert = get_object_or_404(StudentAlert, id=alert_id)
    alert.is_resolved = True
    alert.save()
    messages.success(request, f"Alert for {alert.student.user.display_name} marked as resolved.")
    return redirect('instructor_dashboard')
