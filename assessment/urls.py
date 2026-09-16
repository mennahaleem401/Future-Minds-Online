from django.urls import path
from . import views

urlpatterns = [
    # Assignments
    path('assignments/', views.assignment_list_view, name='assignments_list'),
    path('assignments/create/', views.assignment_create_view, name='assignment_create'),
    path('assignments/<int:assignment_id>/', views.assignment_detail_view, name='assignment_detail'),
    path('assignments/<int:assignment_id>/submit/', views.assignment_submit_view, name='assignment_submit'),
    path('submissions/<int:submission_id>/grade/', views.submission_grade_view, name='submission_grade'),

    # Quizzes & Questions
    path('quizzes/', views.quiz_list_view, name='quizzes_list'),
    path('quizzes/create/', views.quiz_create_view, name='quiz_create'),
    path('quizzes/<int:quiz_id>/', views.quiz_detail_view, name='quiz_detail'),
    path('quizzes/<int:quiz_id>/take/', views.quiz_take_view, name='quiz_take'),
    path('quizzes/<int:quiz_id>/upload-questions/', views.quiz_upload_questions_view, name='quiz_upload_questions'),
    path('quizzes/<int:quiz_id>/questions/add/', views.question_add_single_view, name='question_add_single'),
    path('questions/<int:question_id>/edit/', views.question_edit_view, name='question_edit'),
    path('questions/<int:question_id>/delete/', views.question_delete_view, name='question_delete'),

    # Progress
    path('progress/', views.progress_index_view, name='progress_index'),
    path('progress/student/<int:student_id>/', views.progress_index_view, name='progress_student'),

    # Alerts
    path('alerts/<int:alert_id>/resolve/', views.resolve_alert_view, name='resolve_alert'),
]
