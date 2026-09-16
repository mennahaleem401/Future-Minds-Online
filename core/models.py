from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Academy Admin'
        INSTRUCTOR = 'INSTRUCTOR', 'Instructor'
        STUDENT = 'STUDENT', 'Student'
        PARENT = 'PARENT', 'Parent'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='avatars/', blank=True, null=True)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_instructor_role(self):
        return self.role == self.Role.INSTRUCTOR

    @property
    def is_student_role(self):
        return self.role == self.Role.STUDENT

    @property
    def is_parent_role(self):
        return self.role == self.Role.PARENT

    @property
    def display_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full if full else self.username


class InstructorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='instructor_profile')
    title = models.CharField(max_length=100, default='Instructor')
    specialization = models.CharField(max_length=150, blank=True, help_text='e.g. Python & AI, Robotics, Web Development')
    bio = models.TextField(blank=True)
    experience_years = models.PositiveIntegerField(default=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Eng. {self.user.display_name} ({self.specialization})"


class StudentProfile(models.Model):
    class LearningMode(models.TextChoices):
        ONLINE = 'ONLINE', 'Online Student'
        OFFLINE = 'OFFLINE', 'Offline (In-Person) Student'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    learning_mode = models.CharField(
        max_length=20,
        choices=LearningMode.choices,
        default=LearningMode.ONLINE,
        help_text='Indicates whether student attends online via Google Meet or physically at the Academy'
    )
    assigned_instructor = models.ForeignKey(
        InstructorProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_students'
    )
    date_of_birth = models.DateField(null=True, blank=True)
    emergency_contact = models.CharField(max_length=100, blank=True, help_text="Parent / Guardian Name")
    emergency_phone = models.CharField(max_length=20, blank=True)
    offline_center_notes = models.TextField(blank=True, help_text="Notes for offline branch attendance/desk")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        mode_label = "Online" if self.learning_mode == self.LearningMode.ONLINE else "Offline"
        return f"{self.user.display_name} [{mode_label}]"


class StudentActivity(models.Model):
    class ActivityType(models.TextChoices):
        LOGIN = 'LOGIN', 'Logged In'
        OPEN_COURSE = 'OPEN_COURSE', 'Opened Course'
        OPEN_LESSON = 'OPEN_LESSON', 'Viewed Lesson'
        WATCH_LESSON = 'WATCH_LESSON', 'Watched Lesson Video'
        DOWNLOAD_MATERIAL = 'DOWNLOAD_MATERIAL', 'Downloaded Learning Material'
        JOIN_CLASS = 'JOIN_CLASS', 'Clicked Join Class (Google Meet)'
        SUBMIT_ASSIGNMENT = 'SUBMIT_ASSIGNMENT', 'Submitted Assignment'
        COMPLETE_QUIZ = 'COMPLETE_QUIZ', 'Completed Quiz'
        OTHER = 'OTHER', 'General Activity'

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    description = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Student Activities'

    def __str__(self):
        return f"{self.student.user.username} - {self.activity_type} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        CLASS_REMINDER = 'CLASS_REMINDER', 'Class Reminder'
        ASSIGNMENT = 'ASSIGNMENT', 'Assignment'
        QUIZ = 'QUIZ', 'Quiz'
        ATTENDANCE = 'ATTENDANCE', 'Attendance'
        ALERT = 'ALERT', 'Student Alert'
        SYSTEM = 'SYSTEM', 'System Announcement'

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True, default='')
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices, default=NotificationType.SYSTEM)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"To: {self.recipient.username} - {self.title}"
