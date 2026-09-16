from datetime import date, time, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import User, StudentProfile, InstructorProfile, StudentActivity, Notification
from academy.models import Course, Lesson, Material, ClassSession, ClassStudent, Attendance, AttendanceRule, Recording
from assessment.models import Assignment, Submission, Quiz, Question, QuizAttempt, StudentProgress, StudentAlert
from assessment.progress_service import recalculate_student_progress


class Command(BaseCommand):
    help = 'Populates Future Minds Online with official demonstration seed data.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Initializing Future Minds Online Seed Data..."))

        # 0. Attendance Rule Policy
        rule, _ = AttendanceRule.objects.get_or_create(
            name='Default Academy Attendance Policy',
            defaults={
                'early_window_minutes': 15,
                'late_cutoff_minutes': 5,
                'is_active': True,
            }
        )

        # 1. Admin User
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@futureminds.academy',
                'first_name': 'Academy',
                'last_name': 'Director',
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'phone': '+20 100 000 0001'
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin created: admin / admin123"))

        # 2. Instructors
        # Eng. Menna (Python & AI)
        user_menna, created = User.objects.get_or_create(
            username='menna',
            defaults={
                'email': 'menna@futureminds.academy',
                'first_name': 'Menna',
                'last_name': 'El-Sayed',
                'role': User.Role.INSTRUCTOR,
                'phone': '+20 101 234 5678'
            }
        )
        if created:
            user_menna.set_password('instructor123')
            user_menna.save()

        inst_menna, _ = InstructorProfile.objects.get_or_create(
            user=user_menna,
            defaults={
                'title': 'Senior Python & AI Instructor',
                'specialization': 'Python, Machine Learning & Algorithms',
                'bio': 'Passionate about introducing youth and beginners to algorithmic thinking, Python programming, and foundational AI.',
                'experience_years': 4
            }
        )

        # Eng. Karim (Web Dev & Robotics)
        user_karim, created = User.objects.get_or_create(
            username='karim',
            defaults={
                'email': 'karim@futureminds.academy',
                'first_name': 'Karim',
                'last_name': 'Nasser',
                'role': User.Role.INSTRUCTOR,
                'phone': '+20 102 345 6789'
            }
        )
        if created:
            user_karim.set_password('instructor123')
            user_karim.save()

        inst_karim, _ = InstructorProfile.objects.get_or_create(
            user=user_karim,
            defaults={
                'title': 'Full-Stack & Robotics Lead',
                'specialization': 'Full-Stack Web, Embedded Systems & Robotics',
                'bio': 'Experienced software engineer coaching students in web engineering and interactive electronics.',
                'experience_years': 5
            }
        )
        self.stdout.write(self.style.SUCCESS("Instructors created: menna, karim (pass: instructor123)"))

        # 3. Courses
        course_python, _ = Course.objects.get_or_create(
            slug='python-for-young-minds',
            defaults={
                'title': 'Python for Young Minds & Beginners',
                'description': 'Master the world of coding with Python! Learn essential logic, interactive variables, conditional decision trees, iterative loops, and algorithmic problem-solving.',
                'instructor': inst_menna,
                'is_active': True,
            }
        )

        course_web, _ = Course.objects.get_or_create(
            slug='web-development-fundamentals',
            defaults={
                'title': 'Web Development Fundamentals',
                'description': 'Build responsive, modern web experiences using HTML5, modern CSS3 layout engines, and interactive JavaScript.',
                'instructor': inst_karim,
                'is_active': True,
            }
        )

        # 4. Lessons for Python Course
        lessons_data = [
            (1, "Lesson 01: Variables, Input & Output", "Understanding variable types (strings, integers, floats), console input(), and formatted print() statements."),
            (2, "Lesson 02: Conditions & Decision Making", "Controlling program flow using if, elif, and else logic structures with comparative operators."),
            (3, "Lesson 03: Loops & Iteration (for, while)", "Iterating collections with for loops, counter-controlled while loops, and break/continue statements."),
            (4, "Lesson 04: Lists & Data Structures", "Creating, indexing, appending, and slicing dynamic lists in Python."),
            (5, "Lesson 05: Functions & Modular Coding", "Defining reusable functions, passing parameters, and handling return values."),
        ]
        created_lessons = []
        for order, title, summary in lessons_data:
            l, _ = Lesson.objects.get_or_create(
                course=course_python,
                order=order,
                defaults={
                    'title': title,
                    'summary': summary,
                    'content': f"# Code Demonstration for {title}\n\ndef start_learning():\n    topic = '{title}'\n    print(f'Exploring {{topic}} at Future Minds Academy!')\n\nstart_learning()",
                    'duration_mins': 60
                }
            )
            created_lessons.append(l)

        # 5. Students (Online & Offline)
        students_info = [
            ('ahmed', 'Ahmed', 'Hassan', 'ahmed@student.fm', StudentProfile.LearningMode.ONLINE, inst_menna, 'Hassan Mahmoud (Father)', '+20 100 111 2222', ''),
            ('sara', 'Sara', 'Mahmoud', 'sara@student.fm', StudentProfile.LearningMode.ONLINE, inst_menna, 'Mona Zaki (Mother)', '+20 100 333 4444', ''),
            ('omar', 'Omar', 'Youssef', 'omar@student.fm', StudentProfile.LearningMode.OFFLINE, inst_menna, 'Youssef Nabil (Father)', '+20 100 555 6666', 'Cairo Main Center - Lab 2, Seat 08'),
            ('laila', 'Laila', 'Adel', 'laila@student.fm', StudentProfile.LearningMode.ONLINE, inst_karim, 'Adel Fathy (Father)', '+20 100 777 8888', ''),
            ('youssef', 'Youssef', 'Aly', 'youssef@student.fm', StudentProfile.LearningMode.OFFLINE, inst_karim, 'Aly Fawzy (Father)', '+20 100 999 0000', 'Nasr City Hub - Room A3'),
            ('nour', 'Nour', 'Tarek', 'nour@student.fm', StudentProfile.LearningMode.ONLINE, inst_karim, 'Tarek Amer (Father)', '+20 100 123 4567', ''),
        ]

        student_objs = {}
        for uname, fname, lname, email, mode, inst, g_name, g_phone, off_notes in students_info:
            u, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'email': email,
                    'role': User.Role.STUDENT,
                    'phone': g_phone
                }
            )
            if created:
                u.set_password('student123')
                u.save()

            st, _ = StudentProfile.objects.get_or_create(
                user=u,
                defaults={
                    'learning_mode': mode,
                    'assigned_instructor': inst,
                    'emergency_contact': g_name,
                    'emergency_phone': g_phone,
                    'offline_center_notes': off_notes
                }
            )
            # Enroll in python or web
            if inst == inst_menna:
                course_python.enrolled_students.add(st)
            else:
                course_web.enrolled_students.add(st)
            student_objs[uname] = st

        self.stdout.write(self.style.SUCCESS("Students created: ahmed, sara, omar (Online & Offline) (pass: student123)"))

        # 6. Materials
        Material.objects.get_or_create(
            course=course_python,
            lesson=created_lessons[0],
            title='Python Syntax Reference & Cheat Sheet',
            defaults={
                'material_type': Material.MaterialType.PDF,
                'external_link': 'https://docs.python.org/3/',
                'is_published': True
            }
        )
        Material.objects.get_or_create(
            course=course_python,
            lesson=created_lessons[2],
            title='Loops & Iteration Practice Worksheet',
            defaults={
                'material_type': Material.MaterialType.WORKSHEET,
                'external_link': 'https://github.com',
                'is_published': True
            }
        )

        # 7. Class Sessions
        today = timezone.localdate()

        # Session A: TODAY'S LIVE CLASS (ready for testing [JOIN CLASS] button)
        session_today, _ = ClassSession.objects.get_or_create(
            title='Python Session 04 - Loops & Dynamic Problem Solving',
            defaults={
                'course': course_python,
                'instructor': inst_menna,
                'scheduled_date': today,
                'start_time': time(16, 0),
                'end_time': time(17, 30),
                'google_meet_link': 'https://meet.google.com/qrs-tuvw-xyz',
                'status': ClassSession.Status.SCHEDULED
            }
        )
        for uname in ['ahmed', 'sara', 'omar']:
            st = student_objs[uname]
            ClassStudent.objects.get_or_create(class_session=session_today, student=st)
            Attendance.objects.get_or_create(
                class_session=session_today,
                student=st,
                defaults={'status': Attendance.Status.ABSENT}
            )

        # Session B: PAST CLASS with RECORDING (Section 8)
        session_past, _ = ClassSession.objects.get_or_create(
            title='Python Session 01 - Variables, Input & Output Live',
            defaults={
                'course': course_python,
                'instructor': inst_menna,
                'scheduled_date': today - timedelta(days=4),
                'start_time': time(16, 0),
                'end_time': time(17, 30),
                'google_meet_link': 'https://meet.google.com/abc-defg-hij',
                'status': ClassSession.Status.COMPLETED
            }
        )
        for uname in ['ahmed', 'sara', 'omar']:
            st = student_objs[uname]
            ClassStudent.objects.get_or_create(class_session=session_past, student=st)
        
        # Attach Recording
        Recording.objects.get_or_create(
            class_session=session_past,
            defaults={
                'title': 'Session 01 Full Class Recording',
                'recording_url': 'https://meet.google.com/recording/demo-python-01',
                'duration_minutes': 75,
                'notes': 'Complete recording covering variable declarations and interactive user inputs.',
                'is_available': True
            }
        )

        # Attendance for Past Class (Ahmed Present, Sara Late, Omar Present)
        past_start = timezone.make_aware(timezone.datetime.combine(today - timedelta(days=4), time(16, 0)))
        att_ahmed, _ = Attendance.objects.get_or_create(
            class_session=session_past,
            student=student_objs['ahmed'],
            defaults={
                'status': Attendance.Status.PRESENT,
                'join_time': past_start - timedelta(minutes=3),
                'click_join_event': True
            }
        )
        att_sara, _ = Attendance.objects.get_or_create(
            class_session=session_past,
            student=student_objs['sara'],
            defaults={
                'status': Attendance.Status.LATE,
                'join_time': past_start + timedelta(minutes=8),
                'click_join_event': True
            }
        )
        att_omar, _ = Attendance.objects.get_or_create(
            class_session=session_past,
            student=student_objs['omar'],
            defaults={
                'status': Attendance.Status.PRESENT,
                'join_time': past_start - timedelta(minutes=1),
                'click_join_event': True
            }
        )

        # 8. Assignments & Submissions (Section 11)
        hw_functions, _ = Assignment.objects.get_or_create(
            course=course_python,
            title='Python – Functions & Modularity Assignment',
            defaults={
                'lesson': created_lessons[4],
                'instructor': inst_menna,
                'description': 'Write a Python program containing 3 custom functions:\n1. calculate_circle_area(radius)\n2. is_even(number)\n3. greet_student(name, course)\nTest all functions with user input.',
                'max_score': 100,
                'due_date': timezone.now() + timedelta(days=3),
                'is_published': True
            }
        )

        hw_conditionals, _ = Assignment.objects.get_or_create(
            course=course_python,
            title='Conditionals & Decision Trees Logic',
            defaults={
                'lesson': created_lessons[1],
                'instructor': inst_menna,
                'description': 'Build an automated movie ticket pricing system based on age and student status.',
                'max_score': 100,
                'due_date': timezone.now() - timedelta(days=1),
                'is_published': True
            }
        )

        # Submissions
        Submission.objects.get_or_create(
            assignment=hw_conditionals,
            student=student_objs['ahmed'],
            defaults={
                'submission_text': "def ticket_price(age, is_student):\n    if age < 12:\n        return 50\n    elif is_student:\n        return 70\n    else:\n        return 100\n\nprint(ticket_price(15, True))",
                'score': Decimal('95.00'),
                'feedback': 'Excellent structure and clean conditional handling! Full credit for edge cases.',
                'status': Submission.Status.GRADED,
                'graded_at': timezone.now()
            }
        )
        Submission.objects.get_or_create(
            assignment=hw_conditionals,
            student=student_objs['sara'],
            defaults={
                'submission_text': "age = int(input())\nif age < 18:\n    print('Discount')\nelse:\n    print('Standard')",
                'score': Decimal('85.00'),
                'feedback': 'Good logic! Try packaging the code inside a reusable function next time.',
                'status': Submission.Status.GRADED,
                'graded_at': timezone.now()
            }
        )

        # 9. Quizzes & Questions (Section 12)
        quiz_loops, _ = Quiz.objects.get_or_create(
            course=course_python,
            title='Python Loops & Iteration Mastery Quiz',
            defaults={
                'lesson': created_lessons[2],
                'instructor': inst_menna,
                'description': '10-question evaluation testing for loops, range() syntax, while loops, and loop control statements.',
                'time_limit_minutes': 15,
                'passing_percentage': 70,
                'is_published': True
            }
        )

        questions_data = [
            ("What is the output of: for i in range(3): print(i, end=' ')?", "0 1 2", "1 2 3", "0 1 2 3", "1 2", "A", "range(3) produces 0, 1, 2."),
            ("Which statement immediately terminates the loop in Python?", "continue", "break", "pass", "exit()", "B", "The break keyword exits the nearest enclosing loop immediately."),
            ("What does the 'continue' keyword do?", "Exits the program", "Skips to the next iteration", "Repeats the loop from zero", "Throws an error", "B", "continue skips remaining code in current cycle and moves to next."),
            ("How many times will 'while False:' execute?", "0 times", "1 time", "Infinite times", "Throws error", "A", "Condition is immediately False, body never runs."),
            ("What does range(2, 8, 2) generate?", "[2, 4, 6]", "[2, 3, 4, 5, 6, 7]", "[2, 4, 6, 8]", "[4, 6, 8]", "A", "Starts at 2, steps by 2, stops strictly before 8: 2, 4, 6."),
            ("Which loop is best suited when the exact number of iterations is known in advance?", "while loop", "for loop", "infinite loop", "try-catch", "B", "for loops iterate over a known sequence."),
            ("What is the index of the first element in a Python list?", "1", "0", "-1", "None", "B", "Python uses 0-based indexing."),
            ("Which method adds an element to the end of a list?", "push()", "append()", "insert_end()", "add()", "B", "list.append(item) adds item to the end."),
            ("What is the result of len([10, 20, 30])?", "2", "3", "30", "0", "B", "There are 3 items in the list."),
            ("Can a while loop run forever if its condition is never updated?", "No, Python prevents it", "Yes, it creates an infinite loop", "It stops after 100 cycles", "Syntax error", "B", "Without an update condition, an infinite loop is produced."),
        ]
        for prompt, oa, ob, oc, od, correct, expl in questions_data:
            Question.objects.get_or_create(
                quiz=quiz_loops,
                prompt=prompt,
                defaults={
                    'option_a': oa,
                    'option_b': ob,
                    'option_c': oc,
                    'option_d': od,
                    'correct_option': correct,
                    'explanation': expl,
                    'points': 1
                }
            )

        # Quiz Attempt for Ahmed (8/10 -> 80%)
        QuizAttempt.objects.get_or_create(
            quiz=quiz_loops,
            student=student_objs['ahmed'],
            defaults={
                'score': 8,
                'total_questions': 10,
                'percentage': Decimal('80.00'),
                'passed': True,
                'completed_at': timezone.now() - timedelta(days=1)
            }
        )

        # 10. Student Progress Recalculation (Section 13)
        for uname in ['ahmed', 'sara', 'omar']:
            st = student_objs[uname]
            # Log some activities
            StudentActivity.objects.create(
                student=st,
                activity_type=StudentActivity.ActivityType.OPEN_LESSON,
                description=f"Studied Lesson 01: Variables, Input & Output ({course_python.title})"
            )
            StudentActivity.objects.create(
                student=st,
                activity_type=StudentActivity.ActivityType.OPEN_LESSON,
                description=f"Studied Lesson 02: Conditions & Decision Making ({course_python.title})"
            )
            recalculate_student_progress(st, course_python)

        # 11. Student Alerts (Section 17)
        StudentAlert.objects.get_or_create(
            student=student_objs['omar'],
            course=course_python,
            title=f"Low Attendance Risk: {student_objs['omar'].user.display_name}",
            defaults={
                'instructor': inst_menna,
                'alert_type': StudentAlert.AlertType.LOW_ATTENDANCE,
                'message': "Omar Youssef missed 2 consecutive offline sessions in 'Python for Young Minds'. Please follow up with guardian (0100 555 6666).",
                'is_resolved': False
            }
        )
        StudentAlert.objects.get_or_create(
            student=student_objs['sara'],
            course=course_python,
            title=f"Missing Homework: {student_objs['sara'].user.display_name}",
            defaults={
                'instructor': inst_menna,
                'alert_type': StudentAlert.AlertType.MISSING_HOMEWORK,
                'message': "Sara Mahmoud has not submitted the latest Python assignment 'Functions & Modularity'.",
                'is_resolved': False
            }
        )

        # 12. Notifications (Section 15)
        Notification.objects.get_or_create(
            recipient=student_objs['ahmed'].user,
            title="Class Reminder: Python Live Class",
            defaults={
                'message': "Your Python class starts today at 4:00 PM on Google Meet. Make sure to click [JOIN CLASS] to record attendance.",
                'link': f"/classes/{session_today.id}/",
                'notification_type': Notification.NotificationType.CLASS_REMINDER,
                'is_read': False
            }
        )
        Notification.objects.get_or_create(
            recipient=student_objs['ahmed'].user,
            title="Assignment Feedback Received",
            defaults={
                'message': "Eng. Menna evaluated your submission for 'Conditionals & Decision Trees'. Score: 95/100.",
                'link': f"/assignments/{hw_conditionals.id}/",
                'notification_type': Notification.NotificationType.ASSIGNMENT,
                'is_read': True
            }
        )

        self.stdout.write(self.style.SUCCESS("Future Minds Online demo seed data initialized successfully!"))
