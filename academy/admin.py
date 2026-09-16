from django.contrib import admin
from .models import Course, Lesson, Material, ClassSession, ClassStudent, Attendance, AttendanceRule, Recording


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'instructor', 'is_active', 'created_at']
    list_filter = ['is_active', 'instructor']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order', 'duration_mins']
    list_filter = ['course']
    search_fields = ['title', 'content']


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'lesson', 'material_type', 'is_published', 'uploaded_at']
    list_filter = ['material_type', 'is_published', 'course']


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'instructor', 'scheduled_date', 'start_time', 'status']
    list_filter = ['status', 'scheduled_date', 'instructor', 'course']
    search_fields = ['title', 'google_meet_link']


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'class_session', 'status', 'join_time', 'click_join_event', 'manual_override']
    list_filter = ['status', 'click_join_event', 'manual_override', 'class_session__scheduled_date']
    search_fields = ['student__user__username', 'class_session__title']


@admin.register(AttendanceRule)
class AttendanceRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'early_window_minutes', 'late_cutoff_minutes', 'is_active']


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    list_display = ['class_session', 'title', 'is_available', 'added_at']
