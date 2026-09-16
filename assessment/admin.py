from django.contrib import admin
from .models import Assignment, Submission, Quiz, Question, QuizAttempt, StudentProgress, StudentAlert


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'instructor', 'max_score', 'due_date', 'is_published']
    list_filter = ['course', 'instructor', 'is_published']
    search_fields = ['title', 'description']


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ['student', 'assignment', 'score', 'status', 'submitted_at']
    list_filter = ['status', 'assignment__course']
    search_fields = ['student__user__username', 'assignment__title']


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'time_limit_minutes', 'passing_percentage', 'is_published']
    list_filter = ['course', 'is_published']
    search_fields = ['title']
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['prompt', 'quiz', 'correct_option', 'points']
    list_filter = ['quiz']


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'quiz', 'score', 'total_questions', 'percentage', 'passed', 'completed_at']
    list_filter = ['passed', 'quiz']


@admin.register(StudentProgress)
class StudentProgressAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'overall_percentage', 'attendance_rate', 'last_updated']
    list_filter = ['course']


@admin.register(StudentAlert)
class StudentAlertAdmin(admin.ModelAdmin):
    list_display = ['student', 'instructor', 'alert_type', 'title', 'is_resolved', 'created_at']
    list_filter = ['alert_type', 'is_resolved']
