from datetime import date, time, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import User, StudentProfile, InstructorProfile, StudentActivity
from academy.models import Course, ClassSession, ClassStudent, Attendance, AttendanceRule
from academy.automation import run_session_completion_workflow
from academy.views import generate_course_sessions
from assessment.models import Assignment


class AcademyWorkflowAndSchedulingTests(TestCase):
    def setUp(self):
        self.client = Client()
        AttendanceRule.objects.create(
            name='Test Policy',
            early_window_minutes=15,
            late_cutoff_minutes=5,
            is_active=True
        )

        # Admin
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='password123',
            role=User.Role.ADMIN
        )

        # Instructor
        inst_user = User.objects.create_user(
            username='inst_menna_test',
            password='password123',
            role=User.Role.INSTRUCTOR
        )
        self.instructor = InstructorProfile.objects.create(user=inst_user, specialization='Python')

        # Student
        self.student_user = User.objects.create_user(
            username='student_ahmed_test',
            password='password123',
            role=User.Role.STUDENT
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            learning_mode=StudentProfile.LearningMode.ONLINE
        )

        # Course
        self.course = Course.objects.create(
            title='Python Test Course',
            instructor=self.instructor
        )
        self.course.enrolled_students.add(self.student)

        # Class Session
        today = timezone.localdate()
        self.session = ClassSession.objects.create(
            course=self.course,
            instructor=self.instructor,
            session_number=1,
            title='Python Live Test Session',
            scheduled_date=today,
            start_time=time(16, 0),
            end_time=time(17, 30),
            google_meet_link='https://meet.google.com/test-meet-code',
            status=ClassSession.Status.SCHEDULED
        )
        ClassStudent.objects.create(class_session=self.session, student=self.student)
        Attendance.objects.create(class_session=self.session, student=self.student, status=Attendance.Status.ABSENT)

    def test_student_join_class_records_attendance_and_redirects(self):
        self.session.status = ClassSession.Status.ONGOING
        self.session.save()

        self.client.login(username='student_ahmed_test', password='password123')
        join_url = reverse('join_class', kwargs={'session_id': self.session.id})
        
        response = self.client.get(join_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://meet.google.com/test-meet-code')

        att = Attendance.objects.filter(class_session=self.session, student=self.student).first()
        self.assertIsNotNone(att)
        self.assertTrue(att.click_join_event)
        self.assertIsNotNone(att.join_time)
        self.assertIn(att.status, [Attendance.Status.PRESENT, Attendance.Status.LATE])

    def test_student_and_instructor_blocked_from_joining_before_class_time(self):
        # Set session to tomorrow in the future
        self.session.scheduled_date = timezone.localdate() + timedelta(days=2)
        self.session.status = ClassSession.Status.SCHEDULED
        self.session.save()

        self.assertTrue(self.session.is_before_time)
        self.assertFalse(self.session.is_time_reached)

        join_url = reverse('join_class', kwargs={'session_id': self.session.id})
        detail_url = reverse('class_detail', kwargs={'session_id': self.session.id})

        # 1. Student is blocked and redirected to detail page
        self.client.login(username='student_ahmed_test', password='password123')
        resp_student = self.client.get(join_url)
        self.assertEqual(resp_student.status_code, 302)
        self.assertRedirects(resp_student, detail_url)

        # 2. Instructor is also blocked and redirected to detail page
        self.client.login(username='inst_menna_test', password='password123')
        resp_inst = self.client.get(join_url)
        self.assertEqual(resp_inst.status_code, 302)
        self.assertRedirects(resp_inst, detail_url)

        # 3. Check that the detail page displays the locked state
        resp_page = self.client.get(detail_url)
        self.assertEqual(resp_page.status_code, 200)
        content = resp_page.content.decode('utf-8')
        self.assertIn('يفتح', content)
        self.assertNotIn('ادخل الحصة دلوقتي', content)

    def test_session_completion_workflow_marks_absent_and_completes(self):
        success, msg = run_session_completion_workflow(
            session_id=self.session.id,
            recording_url='https://meet.google.com/test-recording'
        )
        self.assertTrue(success)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, ClassSession.Status.COMPLETED)
        
        att = Attendance.objects.get(class_session=self.session, student=self.student)
        self.assertEqual(att.status, Attendance.Status.ABSENT)
        self.assertTrue(hasattr(self.session, 'recording'))
        self.assertEqual(self.session.recording.recording_url, 'https://meet.google.com/test-recording')

    def test_only_admin_can_create_course(self):
        # Instructor attempt -> should be denied
        self.client.login(username='inst_menna_test', password='password123')
        resp = self.client.get(reverse('course_create'))
        self.assertEqual(resp.status_code, 302)  # redirected away

        # Student attempt -> should be denied
        self.client.login(username='student_ahmed_test', password='password123')
        resp = self.client.get(reverse('course_create'))
        self.assertEqual(resp.status_code, 302)

        # Admin attempt -> Allowed
        self.client.login(username='admin_test', password='password123')
        resp = self.client.get(reverse('course_create'))
        self.assertEqual(resp.status_code, 200)

    def test_auto_generation_of_course_sessions(self):
        """
        Verify that Course sessions are auto-generated on scheduled weekdays (SAT & TUE)
        as replicas with correctly calculated dates and titles (حصة 1, حصة 2...)
        """
        # Pick a Saturday as start date (e.g. 2026-09-19 is Saturday)
        start_date = date(2026, 9, 19)
        self.assertEqual(start_date.weekday(), 5)  # 5 is Saturday

        created_sessions = generate_course_sessions(
            course=self.course,
            start_date=start_date,
            days_list=['SAT', 'TUE'],
            start_time='18:00',
            end_time='19:30',
            meet_link='https://meet.google.com/scheduled-link',
            total_sessions=4,
            clear_existing=True
        )

        self.assertEqual(len(created_sessions), 4)

        # Session 1: Saturday 2026-09-19
        s1 = created_sessions[0]
        self.assertEqual(s1.title, 'حصة 1')
        self.assertEqual(s1.scheduled_date, date(2026, 9, 19))
        self.assertEqual(s1.scheduled_date.weekday(), 5)  # Saturday
        self.assertEqual(str(s1.start_time), '18:00:00')
        self.assertEqual(s1.google_meet_link, 'https://meet.google.com/scheduled-link')
        self.assertIn(self.student, s1.students.all())

        # Session 2: Next Tuesday 2026-09-22
        s2 = created_sessions[1]
        self.assertEqual(s2.title, 'حصة 2')
        self.assertEqual(s2.scheduled_date, date(2026, 9, 22))
        self.assertEqual(s2.scheduled_date.weekday(), 1)  # Tuesday

        # Session 3: Next Saturday 2026-09-26
        s3 = created_sessions[2]
        self.assertEqual(s3.title, 'حصة 3')
        self.assertEqual(s3.scheduled_date, date(2026, 9, 26))
        self.assertEqual(s3.scheduled_date.weekday(), 5)  # Saturday

        # Session 4: Next Tuesday 2026-09-29
        s4 = created_sessions[3]
        self.assertEqual(s4.title, 'حصة 4')
        self.assertEqual(s4.scheduled_date, date(2026, 9, 29))
        self.assertEqual(s4.scheduled_date.weekday(), 1)  # Tuesday

    def test_instructor_can_update_session_title(self):
        self.client.login(username='inst_menna_test', password='password123')
        url = reverse('session_update_title', kwargs={'session_id': self.session.id})
        resp = self.client.post(url, {'title': 'حصة 1: مقدمة في لغة بايثون'})
        self.assertEqual(resp.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.title, 'حصة 1: مقدمة في لغة بايثون')

    def test_instructor_post_class_explanation_and_assignment_after_completion(self):
        self.client.login(username='inst_menna_test', password='password123')
        post_url = reverse('session_post_class_update', kwargs={'session_id': self.session.id})

        # When session is still SCHEDULED, updating summary/homework is disallowed
        resp = self.client.post(post_url, {'summary': 'شرح مبكر'})
        self.session.refresh_from_db()
        self.assertEqual(self.session.summary, '')

        # Complete the session
        self.session.status = ClassSession.Status.COMPLETED
        self.session.save()

        # Now instructor adds summary, recording, and homework
        resp = self.client.post(post_url, {
            'summary': 'تم شرح الـ loops والجمل الشرطية وحل تمارين عملية.',
            'recording_url': 'https://meet.google.com/rec-123',
            'assignment_title': 'واجب الحصة الأولى: تطبيق على For Loop',
            'assignment_description': 'اكتب برنامج يطبع الأرقام الزوجية من 1 لـ 20'
        })
        self.assertEqual(resp.status_code, 302)

        self.session.refresh_from_db()
        self.assertEqual(self.session.summary, 'تم شرح الـ loops والجمل الشرطية وحل تمارين عملية.')
        self.assertEqual(self.session.recording.recording_url, 'https://meet.google.com/rec-123')

        # Assignment must be created and linked to this session
        hw = self.session.assignments.first()
        self.assertIsNotNone(hw)
        self.assertEqual(hw.title, 'واجب الحصة الأولى: تطبيق على For Loop')
        self.assertEqual(hw.course, self.course)

    def test_nonexistent_session_redirects_gracefully_to_classes_list(self):
        self.client.login(username='student_ahmed_test', password='password123')
        # Session 9999 does not exist
        resp = self.client.get(reverse('class_detail', kwargs={'session_id': 9999}))
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('classes_list'))

    def test_student_cannot_see_class_attendance_roster(self):
        # Student views class detail
        self.client.login(username='student_ahmed_test', password='password123')
        resp = self.client.get(reverse('class_detail', kwargs={'session_id': self.session.id}))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertNotIn('كشف حضور الحصة', content)

        # Instructor views class detail -> can see attendance roster
        self.client.login(username='inst_menna_test', password='password123')
        resp_inst = self.client.get(reverse('class_detail', kwargs={'session_id': self.session.id}))
        self.assertEqual(resp_inst.status_code, 200)
        content_inst = resp_inst.content.decode('utf-8')
        self.assertIn('كشف حضور الحصة', content_inst)

    def test_instructor_can_upload_summary_booklet_file(self):
        self.session.status = ClassSession.Status.COMPLETED
        self.session.save()

        self.client.login(username='inst_menna_test', password='password123')
        fake_booklet = SimpleUploadedFile("session_booklet.pdf", b"%PDF-1.4 Fake PDF booklet data", content_type="application/pdf")

        resp = self.client.post(reverse('session_post_class_update', kwargs={'session_id': self.session.id}), {
            'summary': 'تم شرح الجزء الأول من الكورس',
            'summary_file': fake_booklet
        })
        self.assertEqual(resp.status_code, 302)

        self.session.refresh_from_db()
        self.assertTrue(bool(self.session.summary_file))
        self.assertIn('session_booklet', self.session.summary_file.name)
        self.assertEqual(self.session.summary, 'تم شرح الجزء الأول من الكورس')

        # Verify student can see the booklet download link on the class page
        self.client.login(username='student_ahmed_test', password='password123')
        resp_st = self.client.get(reverse('class_detail', kwargs={'session_id': self.session.id}))
        self.assertEqual(resp_st.status_code, 200)
        content = resp_st.content.decode('utf-8')
        self.assertIn('تحميل الملزمة', content)
        self.assertIn('ملزمة / ملف شرح الحصة', content)

    def test_completed_session_moves_to_past_sessions_archive(self):
        # When session is SCHEDULED and date >= today, it appears in upcoming
        self.session.status = ClassSession.Status.SCHEDULED
        self.session.scheduled_date = timezone.localdate()
        self.session.save()

        self.client.login(username='admin_test', password='password123')
        resp = self.client.get(reverse('classes_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.session, resp.context['upcoming_sessions'])
        self.assertNotIn(self.session, resp.context['past_sessions'])

        # When session is COMPLETED, even if date is today, it must be in past_sessions archive
        self.session.status = ClassSession.Status.COMPLETED
        self.session.save()

        resp2 = self.client.get(reverse('classes_list'))
        self.assertEqual(resp2.status_code, 200)
        self.assertNotIn(self.session, resp2.context['upcoming_sessions'])
        self.assertIn(self.session, resp2.context['past_sessions'])

    def test_instructor_dashboard_shows_lock_button_before_session_time(self):
        # Set session for today but 4 hours in the future
        now_time = timezone.localtime()
        future_time = (now_time + timedelta(hours=4)).time()
        future_end = (now_time + timedelta(hours=5)).time()
        self.session.scheduled_date = timezone.localdate()
        self.session.start_time = future_time
        self.session.end_time = future_end
        self.session.status = ClassSession.Status.SCHEDULED
        self.session.save()

        self.client.login(username='inst_menna_test', password='password123')
        resp = self.client.get(reverse('instructor_dashboard'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Must show locked button
        self.assertIn('btn-locked-session', content)
        self.assertIn('مقفول لميعاد الحصة', content)
        self.assertNotIn('ابدأ الحصة', content)

    def test_post_class_update_creates_homework_with_file_only(self):
        self.session.status = ClassSession.Status.COMPLETED
        self.session.save()

        self.client.login(username='inst_menna_test', password='password123')
        post_url = reverse('session_post_class_update', kwargs={'session_id': self.session.id})

        dummy_hw = SimpleUploadedFile("homework_task.pdf", b"%PDF-1.4 dummy content", content_type="application/pdf")
        response = self.client.post(post_url, {
            'assignment_title': '',
            'starter_file': dummy_hw
        })
        self.assertEqual(response.status_code, 302)

        hw = self.session.assignments.first()
        self.assertIsNotNone(hw)
        self.assertEqual(hw.title, f"واجب {self.session.title}")
        self.assertTrue(bool(hw.starter_file))

    def test_post_class_update_updates_existing_homework_file(self):
        self.session.status = ClassSession.Status.COMPLETED
        self.session.save()

        # Create initial assignment
        initial_hw = Assignment.objects.create(
            course=self.session.course,
            session=self.session,
            instructor=self.session.instructor,
            title="واجب الدرس الأول",
            description="حل الأسئلة",
            due_date=timezone.now() + timedelta(days=5)
        )

        self.client.login(username='inst_menna_test', password='password123')
        post_url = reverse('session_post_class_update', kwargs={'session_id': self.session.id})

        new_hw_file = SimpleUploadedFile("updated_template.pptx", b"dummy pptx binary data", content_type="application/vnd.ms-powerpoint")
        response = self.client.post(post_url, {
            'assignment_title': '',
            'starter_file': new_hw_file
        })
        self.assertEqual(response.status_code, 302)

        initial_hw.refresh_from_db()
        self.assertEqual(initial_hw.title, "واجب الدرس الأول")
        self.assertTrue(bool(initial_hw.starter_file))
        self.assertIn("updated_template", initial_hw.starter_file.name)

    def test_download_booklet_and_attendance_completes_lesson(self):
        from assessment.models import StudentProgress
        # Mark session completed with booklet
        self.session.status = ClassSession.Status.COMPLETED
        self.session.summary_file = SimpleUploadedFile("summary_booklet.pdf", b"%PDF dummy booklet", content_type="application/pdf")
        self.session.save()

        # Mark student as PRESENT
        att = Attendance.objects.get(class_session=self.session, student=self.student)
        att.status = Attendance.Status.PRESENT
        att.save()

        self.client.login(username='student_ahmed_test', password='password123')
        download_url = reverse('session_download_booklet', kwargs={'session_id': self.session.id})

        resp = self.client.get(download_url)
        self.assertEqual(resp.status_code, 302)

        # Progress should now have 1 completed lesson
        progress = StudentProgress.objects.get(student=self.student, course=self.course)
        self.assertEqual(progress.lessons_completed_count, 1)
        self.assertGreater(progress.lesson_rate, 0)
        self.assertGreater(progress.overall_percentage, 0)
