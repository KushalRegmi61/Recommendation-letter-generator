from django.test import TestCase, SimpleTestCase, override_settings

from home.models import (
    Application, University, Academics, Department, Program,
    StudentLoginInfo, TeacherInfo,
)


class ModelFieldTests(TestCase):
    def _make_application(self):
        dept = Department.objects.create(dept_name="BCT")
        program = Program.objects.create(program_name="BE", department=dept)
        student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=dept, program=program, dob="2000-01-01",
        )
        prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=dept,
        )
        return Application.objects.create(std=student, professor=prof)

    def test_application_has_new_fields(self):
        app = self._make_application()
        app.first_name = "Alice"
        app.middle_name = ""
        app.last_name = "Sharma"
        app.contact_number = "9800000000"
        app.applied_level = "Masters"
        app.known_roles = "instructor,thesis supervisor"
        app.years_known = "3"
        app.enrollment_batch = "075"
        app.passed_year = "2079"
        app.professional_experience = "Intern at X"
        app.strong_points = "Diligent"
        app.weak_points = "Perfectionist"
        app.save()
        app.refresh_from_db()
        self.assertEqual(app.applied_level, "Masters")
        self.assertEqual(app.known_roles, "instructor,thesis supervisor")
        self.assertIsNone(app.generated_at)

    def test_university_has_country(self):
        app = self._make_application()
        uni = University.objects.create(
            uni_name="MIT", country="USA", application=app,
        )
        uni.refresh_from_db()
        self.assertEqual(uni.country, "USA")

    def test_academics_has_final_percentage(self):
        app = self._make_application()
        aca = Academics.objects.create(
            application=app, final_percentage="82.5",
        )
        aca.refresh_from_db()
        self.assertEqual(aca.final_percentage, "82.5")


class ComposeFullNameTests(SimpleTestCase):
    def test_joins_all_three_parts(self):
        from home.intake import compose_full_name
        self.assertEqual(compose_full_name("Alice", "B", "Sharma"), "Alice B Sharma")

    def test_skips_blank_middle(self):
        from home.intake import compose_full_name
        self.assertEqual(compose_full_name("Alice", "", "Sharma"), "Alice Sharma")

    def test_strips_and_handles_none(self):
        from home.intake import compose_full_name
        self.assertEqual(compose_full_name("  Alice ", None, " Sharma"), "Alice Sharma")


class PendingApplicationTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BEX")
        self.program = Program.objects.create(program_name="BE2", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="bob", roll_number="075BEX010",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="55555", name="Dr Rai", email="rai@example.com",
            department=self.dept,
        )

    def test_false_when_no_application(self):
        from home.intake import has_pending_application
        self.assertFalse(has_pending_application(self.student, self.prof))

    def test_true_when_pending_exists(self):
        from home.intake import has_pending_application
        Application.objects.create(std=self.student, professor=self.prof, is_generated=False)
        self.assertTrue(has_pending_application(self.student, self.prof))

    def test_false_when_only_generated_exists(self):
        from home.intake import has_pending_application
        Application.objects.create(std=self.student, professor=self.prof, is_generated=True)
        self.assertFalse(has_pending_application(self.student, self.prof))


class ParseUniversitiesTests(SimpleTestCase):
    def test_zips_parallel_lists(self):
        from home.intake import parse_universities
        rows = parse_universities(
            names=["MIT", "TU Delft"],
            countries=["USA", "Netherlands"],
            deadlines=["2026-12-15", "2027-01-10"],
            programs=["MS CS", "MS EE"],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {
            "uni_name": "MIT", "country": "USA",
            "uni_deadline": "2026-12-15", "program_applied": "MS CS",
        })

    def test_skips_rows_with_blank_name(self):
        from home.intake import parse_universities
        rows = parse_universities(
            names=["MIT", "  "], countries=["USA", "UK"],
            deadlines=["2026-12-15", ""], programs=["MS", ""],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["uni_name"], "MIT")

    def test_blank_deadline_becomes_none(self):
        from home.intake import parse_universities
        rows = parse_universities(
            names=["MIT"], countries=["USA"], deadlines=[""], programs=[""],
        )
        self.assertIsNone(rows[0]["uni_deadline"])

    def test_ragged_lists_do_not_crash(self):
        from home.intake import parse_universities
        rows = parse_universities(names=["MIT"], countries=[], deadlines=[], programs=[])
        self.assertEqual(rows[0]["country"], "")
        self.assertIsNone(rows[0]["uni_deadline"])


class SaveUniversitiesTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BME")
        self.program = Program.objects.create(program_name="BE3", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="cara", roll_number="075BME002",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="77777", name="Dr Koirala", email="k@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(std=self.student, professor=self.prof)

    def test_creates_rows(self):
        from home.intake import save_universities
        rows = [
            {"uni_name": "MIT", "country": "USA", "uni_deadline": None, "program_applied": "MS"},
            {"uni_name": "ETH", "country": "Switzerland", "uni_deadline": None, "program_applied": "PhD"},
        ]
        count = save_universities(self.app, rows)
        self.assertEqual(count, 2)
        self.assertEqual(University.objects.filter(application=self.app).count(), 2)
        self.assertTrue(
            University.objects.filter(application=self.app, uni_name="ETH", country="Switzerland").exists()
        )

    def test_replaces_existing_rows(self):
        from home.intake import save_universities
        University.objects.create(uni_name="OLD", application=self.app)
        save_universities(self.app, [
            {"uni_name": "NEW", "country": "UK", "uni_deadline": None, "program_applied": ""},
        ])
        names = list(University.objects.filter(application=self.app).values_list("uni_name", flat=True))
        self.assertEqual(names, ["NEW"])


class Studentform1PostTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCE")
        self.program = Program.objects.create(program_name="BE4", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="dan", roll_number="075BCE003",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="88888", name="Dr Thapa", email="t@example.com",
            department=self.dept,
        )

    def _post_data(self):
        return {
            "naam": "dan", "roll": "075BCE003",
            "email": "dan@example.com",
            "prof": "Dr Thapa|88888",
            "first_name": "Dan", "middle_name": "", "last_name": "Gurung",
            "contact_number": "9811111111",
            "applied_level": "PhD",
            "known_roles": ["instructor", "thesis supervisor"],
            "yrs": "4",
            "enrollment_batch": "075",
            "passed_year": "2079",
            "professional_experience": "TA for 2 years",
            "strong_points": "Curious", "weak_points": "Impatient",
        }

    def test_saves_new_fields_on_application(self):
        resp = self.client.post("/studentform1", data=self._post_data())
        self.assertEqual(resp.status_code, 200)
        app = Application.objects.get(std=self.student, professor=self.prof)
        self.assertEqual(app.first_name, "Dan")
        self.assertEqual(app.last_name, "Gurung")
        self.assertEqual(app.contact_number, "9811111111")
        self.assertEqual(app.applied_level, "PhD")
        self.assertEqual(app.known_roles, "instructor,thesis supervisor")
        self.assertEqual(app.enrollment_batch, "075")
        self.assertEqual(app.passed_year, "2079")
        self.assertEqual(app.strong_points, "Curious")
        self.assertEqual(app.name, "Dan Gurung")
        self.assertFalse(app.is_generated)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class Studentform2PostTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BAR")
        self.program = Program.objects.create(program_name="BE5", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="eve", roll_number="075BAR004",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="99999", name="Dr Basnet", email="b@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Eve", is_generated=False,
        )

    def _post_data(self):
        return {
            "roll": "075BAR004", "naam": "eve", "prof_name": "Dr Basnet",
            "uni_name": ["MIT", "ETH"],
            "uni_country": ["USA", "Switzerland"],
            "uni_deadline": ["2026-12-15", ""],
            "uni_program": ["MS CS", "PhD"],
            "gpa": "3.9", "final_percentage": "88", "tentative_ranking": "Top 5%",
            "eca": "Robotics club",
        }

    def test_saves_repeatable_universities_and_percentage(self):
        resp = self.client.post("/studentform2", data=self._post_data())
        self.assertEqual(resp.status_code, 200)
        unis = University.objects.filter(application=self.app).order_by("uni_name")
        self.assertEqual(unis.count(), 2)
        self.assertEqual(unis[0].uni_name, "ETH")
        self.assertEqual(unis[0].country, "Switzerland")
        aca = Academics.objects.get(application=self.app)
        self.assertEqual(aca.final_percentage, "88")

    def test_duplicate_pending_is_rejected(self):
        self.client.post("/studentform2", data=self._post_data())
        self.assertEqual(
            Application.objects.filter(
                std=self.student, professor=self.prof, is_generated=False
            ).count(),
            1,
        )
