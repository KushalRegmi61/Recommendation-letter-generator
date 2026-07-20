from datetime import datetime

from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from home.models import (
    Application, University, Academics, Department, Program,
    StudentLoginInfo, TeacherInfo,
)
from home.filters import apply_application_filters, filter_options
from home.dashboard import build_teacher_dashboard_context


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
        # studentform2 fetches-and-updates the existing pending application (via
        # Application.objects.get(std__username=..., professor__name=...)), so the
        # count stays at 1 — i.e. this asserts no duplicate pending row is created.
        self.client.post("/studentform2", data=self._post_data())
        self.assertEqual(
            Application.objects.filter(
                std=self.student, professor=self.prof, is_generated=False
            ).count(),
            1,
        )


class Studentform1RenderTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BEL")
        self.program = Program.objects.create(program_name="BE6", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="fay", roll_number="075BEL005",
            department=self.dept, program=self.program, dob="2000-01-01",
        )

    def test_form_has_new_fr2_inputs(self):
        self.client.cookies["student"] = "fay"
        resp = self.client.get("/studentform1")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        for field in [
            'name="first_name"', 'name="middle_name"', 'name="last_name"',
            'name="contact_number"', 'name="applied_level"', 'name="known_roles"',
            'name="enrollment_batch"', 'name="passed_year"',
            'name="professional_experience"', 'name="strong_points"',
            'name="weak_points"',
        ]:
            self.assertIn(field, html, f"missing input: {field}")


class ApplicationFilterTests(TestCase):
    def setUp(self):
        self.dept_bct = Department.objects.create(dept_name="BCT")
        self.dept_bce = Department.objects.create(dept_name="BCE")
        prog_bct = Program.objects.create(program_name="BE-BCT", department=self.dept_bct)
        prog_bce = Program.objects.create(program_name="BE-BCE", department=self.dept_bce)
        self.prof = TeacherInfo.objects.create(
            unique_id="T100", name="Prof One", email="p1@example.com",
            department=self.dept_bct,
        )
        self.stu_bct = StudentLoginInfo.objects.create(
            username="alice", roll_number="080BCT001", department=self.dept_bct,
            program=prog_bct, password="x", dob="2000-01-01",
        )
        self.stu_bce = StudentLoginInfo.objects.create(
            username="bob", roll_number="080BCE002", department=self.dept_bce,
            program=prog_bce, password="x", dob="2000-01-01",
        )
        self.app_bct = Application.objects.create(
            name="alice", email="a@example.com", professor=self.prof, std=self.stu_bct,
        )
        self.app_bce = Application.objects.create(
            name="bob", email="b@example.com", professor=self.prof, std=self.stu_bce,
        )
        University.objects.create(
            uni_name="MIT", country="USA", application=self.app_bct,
        )
        University.objects.create(
            uni_name="TU Delft", country="Netherlands", application=self.app_bce,
        )

    def base_qs(self):
        return Application.objects.filter(professor__unique_id="T100")

    def test_empty_params_returns_everything(self):
        result = apply_application_filters(self.base_qs(), {})
        self.assertEqual(result.count(), 2)

    def test_blank_values_are_ignored(self):
        result = apply_application_filters(
            self.base_qs(), {"department": "", "country": "", "college": ""}
        )
        self.assertEqual(result.count(), 2)

    def test_filter_by_department(self):
        result = apply_application_filters(self.base_qs(), {"department": "BCT"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_filter_by_country(self):
        result = apply_application_filters(self.base_qs(), {"country": "USA"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_filter_by_college(self):
        result = apply_application_filters(self.base_qs(), {"college": "TU Delft"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_filters_combine_with_and(self):
        # BCT department but a Netherlands university -> no match
        result = apply_application_filters(
            self.base_qs(), {"department": "BCT", "country": "Netherlands"}
        )
        self.assertEqual(result.count(), 0)

        result = apply_application_filters(
            self.base_qs(), {"department": "BCT", "country": "USA"}
        )
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_partial_and_case_insensitive_dropdown_values_match(self):
        # The dropdowns are typeable comboboxes, so a half-typed value must work.
        result = apply_application_filters(self.base_qs(), {"country": "us"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

        result = apply_application_filters(self.base_qs(), {"college": "delft"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

        result = apply_application_filters(self.base_qs(), {"department": "bct"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_no_duplicate_rows_when_application_has_many_universities(self):
        # A second USA university on the same application must not duplicate it.
        University.objects.create(
            uni_name="Stanford", country="USA", application=self.app_bct,
        )
        result = apply_application_filters(self.base_qs(), {"country": "USA"})
        self.assertEqual(result.count(), 1)

    def test_search_matches_application_name(self):
        result = apply_application_filters(self.base_qs(), {"q": "alice"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_search_is_case_insensitive_and_partial(self):
        result = apply_application_filters(self.base_qs(), {"q": "AL"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_search_matches_roll_number(self):
        result = apply_application_filters(self.base_qs(), {"q": "080bce"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_search_matches_email(self):
        result = apply_application_filters(self.base_qs(), {"q": "b@example.com"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_search_matches_first_or_last_name_fields(self):
        self.app_bce.first_name = "Bobby"
        self.app_bce.last_name = "Tables"
        self.app_bce.save()
        result = apply_application_filters(self.base_qs(), {"q": "tables"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_blank_search_is_ignored(self):
        result = apply_application_filters(self.base_qs(), {"q": "   "})
        self.assertEqual(result.count(), 2)

    def test_search_combines_with_dropdown_filters(self):
        # alice matches the text, but her university is in the USA, not Finland.
        result = apply_application_filters(
            self.base_qs(), {"q": "alice", "country": "Netherlands"}
        )
        self.assertEqual(result.count(), 0)

        result = apply_application_filters(
            self.base_qs(), {"q": "alice", "country": "USA"}
        )
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_search_terms_are_anded_regardless_of_word_order(self):
        self.app_bce.first_name = "Ramesh"
        self.app_bce.last_name = "Shrestha"
        self.app_bce.save()
        result = apply_application_filters(self.base_qs(), {"q": "shrestha ramesh"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_search_terms_may_match_different_fields(self):
        result = apply_application_filters(self.base_qs(), {"q": "bob 080bce"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_every_term_must_match(self):
        result = apply_application_filters(self.base_qs(), {"q": "bob 080bct"})
        self.assertEqual(result.count(), 0)

    def test_search_does_not_match_university_name(self):
        # University search is the dropdowns' job; matching it here would
        # surprise a professor searching for a person.
        result = apply_application_filters(self.base_qs(), {"q": "MIT"})
        self.assertEqual(result.count(), 0)


class FilterOptionTests(TestCase):
    def setUp(self):
        dept_bct = Department.objects.create(dept_name="BCT")
        dept_bex = Department.objects.create(dept_name="BEX")
        prog_bct = Program.objects.create(program_name="BE-BCT", department=dept_bct)
        prog_bex = Program.objects.create(program_name="BE-BEX", department=dept_bex)
        self.mine = TeacherInfo.objects.create(
            unique_id="T200", name="Mine", email="mine@example.com", department=dept_bct,
        )
        other = TeacherInfo.objects.create(
            unique_id="T201", name="Other", email="other@example.com", department=dept_bct,
        )
        stu_a = StudentLoginInfo.objects.create(
            username="ann", roll_number="080BCT010", department=dept_bct,
            program=prog_bct, password="x", dob="2000-01-01",
        )
        stu_b = StudentLoginInfo.objects.create(
            username="ben", roll_number="080BEX011", department=dept_bex,
            program=prog_bex, password="x", dob="2000-01-01",
        )
        app_a = Application.objects.create(
            name="ann", email="ann@example.com", professor=self.mine, std=stu_a,
        )
        app_b = Application.objects.create(
            name="ben", email="ben@example.com", professor=self.mine, std=stu_b,
        )
        app_other = Application.objects.create(
            name="zed", email="zed@example.com", professor=other, std=stu_a,
        )
        University.objects.create(uni_name="MIT", country="USA", application=app_a)
        University.objects.create(uni_name="MIT", country="USA", application=app_b)
        University.objects.create(uni_name="Aalto", country="Finland", application=app_b)
        University.objects.create(
            uni_name="SecretU", country="Japan", application=app_other,
        )

    def base_qs(self):
        return Application.objects.filter(professor__unique_id="T200")

    def test_options_are_sorted_and_deduplicated(self):
        options = filter_options(self.base_qs())
        self.assertEqual(options["departments"], ["BCT", "BEX"])
        self.assertEqual(options["countries"], ["Finland", "USA"])
        self.assertEqual(options["colleges"], ["Aalto", "MIT"])

    def test_options_exclude_other_professors_values(self):
        options = filter_options(self.base_qs())
        self.assertNotIn("Japan", options["countries"])
        self.assertNotIn("SecretU", options["colleges"])

    def test_blank_and_null_values_are_omitted(self):
        app = Application.objects.get(name="ann")
        University.objects.create(uni_name="", country=None, application=app)
        options = filter_options(self.base_qs())
        self.assertNotIn("", options["colleges"])
        self.assertNotIn(None, options["countries"])


class DashboardContextTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(dept_name="BCT")
        prog = Program.objects.create(program_name="BE-BCT", department=dept)
        self.prof = TeacherInfo.objects.create(
            unique_id="T300", name="Prof Three", email="p3@example.com", department=dept,
        )
        self.stu = StudentLoginInfo.objects.create(
            username="cara", roll_number="080BCT020", department=dept,
            program=prog, password="x", dob="2000-01-01",
        )
        self.pending = Application.objects.create(
            name="cara pending", email="c@example.com", professor=self.prof,
            std=self.stu, is_generated=False,
        )
        self.older = Application.objects.create(
            name="cara older", email="c@example.com", professor=self.prof,
            std=self.stu, is_generated=True,
            generated_at=timezone.make_aware(datetime(2026, 1, 1, 9, 0)),
        )
        self.newer = Application.objects.create(
            name="cara newer", email="c@example.com", professor=self.prof,
            std=self.stu, is_generated=True,
            generated_at=timezone.make_aware(datetime(2026, 5, 1, 9, 0)),
        )
        University.objects.create(uni_name="MIT", country="USA", application=self.newer)
        University.objects.create(
            uni_name="Aalto", country="Finland", application=self.older,
        )

    def test_splits_pending_and_generated(self):
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertEqual([a.pk for a in ctx["student_list"]], [self.pending.pk])
        self.assertEqual(len(ctx["all_students"]), 2)

    def test_generated_list_is_newest_first(self):
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertEqual(
            [a.pk for a in ctx["all_students"]], [self.newer.pk, self.older.pk]
        )

    def test_filters_apply_to_both_lists(self):
        ctx = build_teacher_dashboard_context("T300", {"country": "USA"})
        self.assertEqual([a.pk for a in ctx["all_students"]], [self.newer.pk])
        # The pending application has no USA university, so it drops out too.
        self.assertEqual(list(ctx["student_list"]), [])

    def test_context_exposes_options_and_active_filters(self):
        ctx = build_teacher_dashboard_context("T300", {"country": "USA"})
        self.assertEqual(ctx["filter_options"]["countries"], ["Finland", "USA"])
        self.assertEqual(ctx["active_filters"]["country"], "USA")
        self.assertEqual(ctx["active_filters"]["department"], "")
        self.assertTrue(ctx["filters_active"])

    def test_no_filters_means_filters_inactive(self):
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertFalse(ctx["filters_active"])

    def test_search_narrows_both_lists_and_counts_as_active(self):
        ctx = build_teacher_dashboard_context("T300", {"q": "newer"})
        self.assertEqual([a.pk for a in ctx["all_students"]], [self.newer.pk])
        self.assertEqual(list(ctx["student_list"]), [])
        self.assertEqual(ctx["active_filters"]["q"], "newer")
        self.assertTrue(ctx["filters_active"])

    def test_teacher_with_no_generated_letters_does_not_crash(self):
        Application.objects.filter(is_generated=True).delete()
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertEqual(list(ctx["all_students"]), [])
        self.assertFalse(ctx["check_value"])

    def test_check_value_true_when_nothing_pending(self):
        self.pending.delete()
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertTrue(ctx["check_value"])
