from django.db import models
from core.models import StudentProfile, InstructorProfile
from academy.models import Course, Lesson


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assignments')
    lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments')
    session = models.ForeignKey(
        'academy.ClassSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments'
    )
    instructor = models.ForeignKey(InstructorProfile, on_delete=models.CASCADE, related_name='created_assignments')
    title = models.CharField(max_length=200)
    description = models.TextField(help_text="Instructions, problem description, expectations")
    starter_file = models.FileField(upload_to='assignments/starters/', blank=True, null=True)
    max_score = models.PositiveIntegerField(default=100)
    due_date = models.DateTimeField()
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Submission(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted (Pending Review)'
        GRADED = 'GRADED', 'Graded'
        LATE = 'LATE', 'Late Submission'
        RESUBMIT = 'RESUBMIT', 'Resubmission Requested'

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='submissions')
    submission_file = models.FileField(upload_to='assignments/submissions/', blank=True, null=True)
    submission_text = models.TextField(blank=True, help_text="Answer text, code snippets, or project links")
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['assignment', 'student']
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.student.user.display_name} - {self.assignment.title} ({self.status})"


class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='quizzes')
    lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='quizzes')
    instructor = models.ForeignKey(InstructorProfile, on_delete=models.CASCADE, related_name='created_quizzes')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveIntegerField(default=15, help_text="Duration in minutes (0 for untimed)")
    passing_percentage = models.PositiveIntegerField(default=70)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Quizzes'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Question(models.Model):
    class CorrectChoice(models.TextChoices):
        A = 'A', 'Option A'
        B = 'B', 'Option B'
        C = 'C', 'Option C'
        D = 'D', 'Option D'

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    prompt = models.TextField(help_text="Question text or code snippet to analyze")
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255, blank=True)
    option_d = models.CharField(max_length=255, blank=True)
    correct_option = models.CharField(max_length=1, choices=CorrectChoice.choices)
    explanation = models.TextField(blank=True, help_text="Explanation shown after quiz completion")
    points = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"Q: {self.prompt[:50]}..."


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='quiz_attempts')
    score = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    passed = models.BooleanField(default=False)
    answers = models.JSONField(default=dict, blank=True, help_text="Student's selected choices per question ID")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-completed_at']

    def __str__(self):
        return f"{self.student.user.display_name} - {self.quiz.title}: {self.percentage}%"


class StudentProgress(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='progress_records')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='student_progress_records')
    attendance_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    lessons_completed_count = models.PositiveIntegerField(default=0)
    assignment_score_avg = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    quiz_score_avg = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    overall_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-overall_percentage']

    @property
    def total_course_lessons_count(self):
        total = self.course.lessons.count()
        if total == 0:
            total = self.course.sessions.count()
        return total

    @property
    def lesson_rate(self):
        total = self.total_course_lessons_count
        if total > 0:
            return min(100, int((self.lessons_completed_count / total) * 100))
        return 0

    def __str__(self):
        return f"{self.student.user.display_name} - {self.course.title}: {self.overall_percentage}%"


class StudentAlert(models.Model):
    class AlertType(models.TextChoices):
        LOW_ATTENDANCE = 'LOW_ATTENDANCE', 'Low Attendance Risk'
        MISSING_HOMEWORK = 'MISSING_HOMEWORK', 'Missing Homework'
        LOW_QUIZ_PERFORMANCE = 'LOW_QUIZ_PERFORMANCE', 'Low Quiz Performance'
        INACTIVITY = 'INACTIVITY', 'Prolonged Inactivity'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='alerts')
    instructor = models.ForeignKey(InstructorProfile, on_delete=models.CASCADE, related_name='student_alerts')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)
    alert_type = models.CharField(max_length=30, choices=AlertType.choices)
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.alert_type}] {self.student.user.display_name}: {self.title}"
