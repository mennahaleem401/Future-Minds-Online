from datetime import datetime, timedelta
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from core.models import InstructorProfile, StudentProfile


class Course(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    instructor = models.ForeignKey(
        InstructorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses'
    )
    thumbnail = models.ImageField(upload_to='courses/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    enrolled_students = models.ManyToManyField(
        StudentProfile,
        blank=True,
        related_name='courses'
    )
    # Recurring schedule settings for auto-generating sessions
    schedule_days = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="أيام الحصص مفصولة بفواصل، مثل: SAT,TUE"
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="تاريخ بداية الكورس (أول حصة)"
    )
    default_start_time = models.TimeField(null=True, blank=True)
    default_end_time = models.TimeField(null=True, blank=True)
    default_meet_link = models.URLField(
        blank=True,
        default='https://meet.google.com/abc-defg-hij',
        help_text="رابط جوجل ميت المعتمد لحصص الكورس"
    )
    total_sessions_count = models.PositiveIntegerField(
        default=8,
        help_text="عدد الحصص الإجمالي المطلوب جدولتها"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    summary = models.TextField(blank=True, help_text="Key takeaways and outline")
    content = models.TextField(blank=True, help_text="Lesson notes, syntax explanations, and examples")
    video_url = models.URLField(blank=True, help_text="Embedded video explanation / tutorial link")
    duration_mins = models.PositiveIntegerField(default=45)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        unique_together = ['course', 'order']

    def __str__(self):
        return f"{self.course.title} - Lesson {self.order:02d}: {self.title}"


class Material(models.Model):
    class MaterialType(models.TextChoices):
        PDF = 'PDF', 'PDF Document'
        IMAGE = 'IMAGE', 'Infographic / Diagram'
        WORKSHEET = 'WORKSHEET', 'Exercise Worksheet'
        NOTES = 'NOTES', 'Lecture Summary'
        CODE = 'CODE', 'Code Starter / Solution'
        OTHER = 'OTHER', 'Educational File'

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='materials')
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='materials'
    )
    title = models.CharField(max_length=200)
    material_type = models.CharField(
        max_length=20,
        choices=MaterialType.choices,
        default=MaterialType.PDF
    )
    file = models.FileField(upload_to='materials/', blank=True, null=True)
    external_link = models.URLField(blank=True, help_text="Optional external Drive / GitHub / Resource URL")
    is_published = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"[{self.material_type}] {self.title}"


class ClassSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        ONGOING = 'ONGOING', 'Live / Ongoing'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    instructor = models.ForeignKey(InstructorProfile, on_delete=models.CASCADE, related_name='sessions')
    title = models.CharField(max_length=200)
    scheduled_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    google_meet_link = models.URLField(
        default='https://meet.google.com/abc-defg-hij',
        help_text="Google Meet link for this session"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    session_number = models.PositiveIntegerField(default=1, help_text="رقم الحصة في الكورس (حصة 1، 2...)")
    summary = models.TextField(
        blank=True,
        default='',
        help_text="شرح الحصة وملخص ما تم إنجازه (يضيفه المدرس بعد انتهاء الحصة)"
    )
    summary_file = models.FileField(
        upload_to='session_summaries/',
        blank=True,
        null=True,
        help_text="ملف أو ملزمة شرح الحصة (PDF / مستندات)"
    )
    students = models.ManyToManyField(
        StudentProfile,
        through='ClassStudent',
        related_name='scheduled_classes',
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_date', 'start_time']

    def get_start_datetime(self):
        tz = timezone.get_current_timezone()
        dt = datetime.combine(self.scheduled_date, self.start_time)
        return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt

    def get_end_datetime(self):
        tz = timezone.get_current_timezone()
        dt = datetime.combine(self.scheduled_date, self.end_time)
        return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt

    @property
    def is_time_reached(self):
        """
        True if the current time has reached the session start window.
        """
        if self.status in [self.Status.COMPLETED, self.Status.CANCELLED]:
            return False
        if self.status == self.Status.ONGOING:
            return True

        now = timezone.localtime()
        rule = AttendanceRule.get_current_rule()
        early_mins = rule.early_window_minutes if rule else 15
        start_window = self.get_start_datetime() - timedelta(minutes=early_mins)
        end_window = self.get_end_datetime()
        return start_window <= now <= end_window

    @property
    def is_before_time(self):
        """
        True if the session start window has not arrived yet.
        """
        if self.status in [self.Status.COMPLETED, self.Status.CANCELLED, self.Status.ONGOING]:
            return False
        now = timezone.localtime()
        rule = AttendanceRule.get_current_rule()
        early_mins = rule.early_window_minutes if rule else 15
        start_window = self.get_start_datetime() - timedelta(minutes=early_mins)
        return now < start_window

    def __str__(self):
        start_str = self.start_time.strftime('%H:%M') if hasattr(self.start_time, 'strftime') else str(self.start_time)
        return f"{self.course.title} | {self.scheduled_date} {start_str} ({self.instructor.user.display_name})"


class ClassStudent(models.Model):
    class_session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name='enrollment_entries')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='class_session_entries')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['class_session', 'student']

    def __str__(self):
        return f"{self.student.user.display_name} in {self.class_session.title}"


class AttendanceRule(models.Model):
    name = models.CharField(max_length=100, default='Default Academy Attendance Policy')
    early_window_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Allow students to join up to N minutes before class start"
    )
    late_cutoff_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Joining within N minutes of start is PRESENT; after this is marked LATE"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (Early: -{self.early_window_minutes}m, Late cutoff: +{self.late_cutoff_minutes}m)"

    @classmethod
    def get_current_rule(cls):
        rule = cls.objects.filter(is_active=True).first()
        if not rule:
            rule = cls.objects.create(
                name='Default Policy',
                early_window_minutes=15,
                late_cutoff_minutes=5,
                is_active=True
            )
        return rule


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'PRESENT', 'Present'
        LATE = 'LATE', 'Late'
        ABSENT = 'ABSENT', 'Absent'

    class_session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name='attendances')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABSENT)
    join_time = models.DateTimeField(null=True, blank=True, help_text="Timestamp when student clicked Join Class")
    click_join_event = models.BooleanField(default=False)
    manual_override = models.BooleanField(default=False, help_text="Flag if attendance was updated manually by instructor/admin")
    notes = models.CharField(max_length=255, blank=True)
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['class_session', 'student']
        ordering = ['-class_session__scheduled_date', 'student__user__first_name']

    def __str__(self):
        return f"{self.student.user.display_name} - {self.class_session.title}: {self.status}"


class Recording(models.Model):
    class_session = models.OneToOneField(ClassSession, on_delete=models.CASCADE, related_name='recording')
    title = models.CharField(max_length=200, default='Session Recording')
    recording_url = models.URLField(help_text="Google Meet or Cloud Recording Link")
    duration_minutes = models.PositiveIntegerField(default=60)
    notes = models.TextField(blank=True)
    is_available = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recording: {self.class_session.title}"
