from django.test import TestCase, Client
from django.urls import reverse
from core.models import User, StudentProfile, InstructorProfile


class RBACPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Admin
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            password='password123',
            role=User.Role.ADMIN
        )
        # Instructor
        self.inst_user = User.objects.create_user(
            username='inst_test',
            password='password123',
            role=User.Role.INSTRUCTOR
        )
        self.inst_profile = InstructorProfile.objects.create(user=self.inst_user, specialization='Python')

        # Student
        self.student_user = User.objects.create_user(
            username='student_test',
            password='password123',
            role=User.Role.STUDENT
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            learning_mode=StudentProfile.LearningMode.ONLINE
        )

    def test_student_cannot_access_admin_dashboard(self):
        self.client.login(username='student_test', password='password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard_redirect'))

    def test_student_cannot_access_instructor_dashboard(self):
        self.client.login(username='student_test', password='password123')
        response = self.client.get(reverse('instructor_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard_redirect'))

    def test_admin_can_access_admin_dashboard(self):
        self.client.login(username='admin_test', password='password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_instructor_can_access_instructor_dashboard(self):
        self.client.login(username='inst_test', password='password123')
        response = self.client.get(reverse('instructor_dashboard'))
        self.assertEqual(response.status_code, 200)
