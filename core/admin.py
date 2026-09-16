from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, StudentProfile, InstructorProfile, StudentActivity, Notification


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'phone', 'is_staff']
    list_filter = ['role', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('صلاحيات فيوتشر مايندز', {'fields': ('role', 'phone', 'profile_picture')}),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'learning_mode', 'assigned_instructor', 'emergency_contact', 'emergency_phone']
    list_filter = ['learning_mode', 'assigned_instructor']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'emergency_contact']


@admin.register(InstructorProfile)
class InstructorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'specialization', 'experience_years', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'specialization']


@admin.register(StudentActivity)
class StudentActivityAdmin(admin.ModelAdmin):
    list_display = ['student', 'activity_type', 'description', 'timestamp']
    list_filter = ['activity_type', 'timestamp']
    search_fields = ['student__user__username', 'description']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['recipient__username', 'title', 'message']
