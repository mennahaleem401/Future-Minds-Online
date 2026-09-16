from django.urls import path
from . import views

urlpatterns = [
    # Courses & Lessons
    path('courses/', views.course_list_view, name='courses_list'),
    path('courses/create/', views.course_create_edit_view, name='course_create'),
    path('courses/<int:course_id>/', views.course_detail_view, name='course_detail'),
    path('courses/<int:course_id>/edit/', views.course_create_edit_view, name='course_edit'),
    path('courses/<int:course_id>/auto-schedule/', views.course_auto_schedule_view, name='course_auto_schedule'),
    path('courses/<int:course_id>/lessons/<int:lesson_id>/', views.lesson_detail_view, name='lesson_detail'),

    # Classes & Google Meet Join Flow
    path('classes/', views.class_list_view, name='classes_list'),
    path('classes/create/', views.class_create_view, name='class_create'),
    path('classes/<int:session_id>/', views.class_detail_view, name='class_detail'),
    path('classes/<int:session_id>/update-title/', views.session_update_title_view, name='session_update_title'),
    path('classes/<int:session_id>/post-class-update/', views.session_post_class_update_view, name='session_post_class_update'),
    path('classes/<int:session_id>/download-booklet/', views.class_download_booklet_view, name='session_download_booklet'),
    path('classes/<int:session_id>/join/', views.join_class_view, name='join_class'),
    path('classes/<int:session_id>/complete/', views.complete_class_view, name='complete_class'),

    # Attendance
    path('attendance/', views.attendance_index_view, name='attendance_index'),
    path('attendance/session/<int:session_id>/', views.attendance_session_view, name='attendance_session'),

    # Students & Instructors Directory
    path('students/', views.students_list_view, name='students_list'),
    path('students/add/', views.student_add_edit_view, name='student_add'),
    path('students/<int:student_id>/', views.student_detail_view, name='student_detail'),
    path('students/<int:student_id>/edit/', views.student_add_edit_view, name='student_edit'),

    path('instructors/', views.instructors_list_view, name='instructors_list'),
    path('instructors/add/', views.instructor_add_edit_view, name='instructor_add'),
    path('instructors/<int:instructor_id>/edit/', views.instructor_add_edit_view, name='instructor_edit'),
]
