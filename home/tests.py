from datetime import date, datetime

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from home.models import (
    Application, University, Academics, Department, Program,
    StudentLoginInfo, TeacherInfo, CustomTemplates, Qualities,
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


class TeacherDashboardViewTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(dept_name="BCT")
        prog = Program.objects.create(program_name="BE-BCT", department=dept)
        self.prof = TeacherInfo.objects.create(
            unique_id="T400", name="Prof Four", email="p4@example.com", department=dept,
        )
        stu = StudentLoginInfo.objects.create(
            username="dan", roll_number="080BCT030", department=dept,
            program=prog, password="x", dob="2000-01-01",
        )
        self.usa_app = Application.objects.create(
            name="dan usa", email="d@example.com", professor=self.prof,
            std=stu, is_generated=False,
        )
        self.fin_app = Application.objects.create(
            name="dan finland", email="d@example.com", professor=self.prof,
            std=stu, is_generated=False,
        )
        University.objects.create(
            uni_name="MIT", country="USA", application=self.usa_app,
        )
        University.objects.create(
            uni_name="Aalto", country="Finland", application=self.fin_app,
        )
        self.client.cookies["unique"] = "T400"
        self.client.cookies["username"] = "Prof Four"

    def test_teacher_view_renders_all_applications_by_default(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dan usa")
        self.assertContains(response, "dan finland")

    def test_teacher_view_applies_country_filter(self):
        response = self.client.get("/teacher", {"country": "USA"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dan usa")
        self.assertNotContains(response, "dan finland")

    def test_teacher_view_exposes_filter_options(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.context["filter_options"]["countries"],
                         ["Finland", "USA"])

    def test_login_teacher_get_does_not_crash_without_generated_letters(self):
        # Regression: loginTeacher used Application.objects.get(is_generated=True),
        # which raised DoesNotExist for a professor with no generated letters.
        response = self.client.get("/loginTeacher")
        self.assertEqual(response.status_code, 200)

    def test_login_teacher_get_does_not_crash_with_two_generated_letters(self):
        # Regression: the same .get() raised MultipleObjectsReturned.
        Application.objects.filter(professor=self.prof).update(is_generated=True)
        response = self.client.get("/loginTeacher")
        self.assertEqual(response.status_code, 200)

    def test_all_teacher_dashboard_entry_points_supply_filter_options(self):
        # Teacher.html is rendered from several views; every one of them must
        # provide the filter context or the filter bar renders empty.
        for path in ("/", "/loginStudent", "/registerStudent"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["filter_options"]["countries"],
                    ["Finland", "USA"],
                )
                self.assertEqual(response.context["generated_count"], 0)

    def test_login_teacher_post_supplies_filter_options(self):
        user = User.objects.create_user(
            username="prof4", email="p4@example.com", password="secret",
        )
        user.first_name = "Prof Four/T400"
        user.save()
        response = self.client.post(
            "/loginTeacher", {"username": "p4@example.com", "password": "secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["filter_options"]["countries"], ["Finland", "USA"]
        )

    def test_filter_bar_is_rendered_with_typeable_comboboxes(self):
        response = self.client.get("/teacher")
        self.assertContains(response, 'name="department"')
        self.assertContains(response, 'name="country"')
        self.assertContains(response, 'name="college"')
        # Each field is an <input list=...> backed by a <datalist> of suggestions,
        # so the professor can either pick a value or type a partial one.
        self.assertContains(response, 'list="country-options"')
        self.assertContains(response, '<datalist id="country-options">')
        self.assertContains(response, '<option value="Finland">')
        self.assertContains(response, '<option value="MIT">')

    def test_active_filter_value_is_kept_in_the_box(self):
        response = self.client.get("/teacher", {"country": "USA"})
        self.assertContains(response, 'value="USA"')

    def test_partially_typed_filter_value_still_matches(self):
        response = self.client.get("/teacher", {"country": "us"})
        self.assertContains(response, "dan usa")
        self.assertNotContains(response, "dan finland")

    def test_search_box_is_rendered_and_keeps_its_value(self):
        response = self.client.get("/teacher", {"q": "dan usa"})
        self.assertContains(response, 'name="q"')
        self.assertContains(response, 'value="dan usa"')
        self.assertContains(response, "dan usa")
        self.assertNotContains(response, "dan finland")

    def test_generated_table_has_tracking_columns(self):
        response = self.client.get("/teacher")
        self.assertContains(response, "Generated on")
        self.assertContains(response, "Template")

    def test_empty_state_distinguishes_no_requests_from_no_matches(self):
        # No filter and nothing pending -> the cheerful global message.
        Application.objects.filter(professor=self.prof).update(is_generated=True)
        response = self.client.get("/teacher")
        self.assertContains(response, "You have no request for now")

        # A filter that matches nothing must NOT claim there are no requests at all.
        Application.objects.filter(professor=self.prof).update(is_generated=False)
        response = self.client.get("/teacher", {"country": "Antarctica"})
        self.assertContains(response, "No pending requests match")
        self.assertNotContains(response, "You have no request for now")

    def test_generated_count_is_shown(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.context["generated_count"], 0)

    def test_dashboard_never_shows_another_professors_students(self):
        other_dept = Department.objects.create(dept_name="BEX")
        other_prog = Program.objects.create(
            program_name="BE-BEX", department=other_dept,
        )
        other_prof = TeacherInfo.objects.create(
            unique_id="T999", name="Prof Nine", email="p9@example.com",
            department=other_dept,
        )
        other_stu = StudentLoginInfo.objects.create(
            username="zoe", roll_number="080BEX099", department=other_dept,
            program=other_prog, password="x", dob="2000-01-01",
        )
        secret = Application.objects.create(
            name="zoe secret", email="z@example.com", professor=other_prof,
            std=other_stu, is_generated=False,
        )
        University.objects.create(
            uni_name="SecretU", country="Japan", application=secret,
        )

        response = self.client.get("/teacher")
        self.assertNotContains(response, "zoe secret")
        # Nor may the other professor's values leak into the filter suggestions.
        self.assertNotIn("Japan", response.context["filter_options"]["countries"])
        self.assertNotIn("SecretU", response.context["filter_options"]["colleges"])
        self.assertNotIn("BEX", response.context["filter_options"]["departments"])

    def test_teacher_view_redirects_when_cookie_is_missing(self):
        del self.client.cookies["unique"]
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/loginTeacher")

    def test_teacher_view_redirects_when_cookie_is_stale(self):
        # A professor whose TeacherInfo was removed, or a hand-edited cookie.
        self.client.cookies["unique"] = "T000-does-not-exist"
        response = self.client.get("/teacher", {"country": "USA"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/loginTeacher")

    def test_redownload_link_shown_only_when_a_letter_is_stored(self):
        from django.core.files.base import ContentFile

        stored = Application.objects.create(
            name="dan stored", email="d@example.com", professor=self.prof,
            std=self.usa_app.std, is_generated=True,
        )
        response = self.client.get("/teacher")
        self.assertNotContains(response, f"/download_generated/?id={stored.pk}")

        stored.generated_letter.save(
            "dan.pdf", ContentFile(b"%PDF-1.4 x"), save=True,
        )
        try:
            response = self.client.get("/teacher")
            self.assertContains(response, f"/download_generated/?id={stored.pk}")
        finally:
            stored.generated_letter.delete(save=False)


class DownloadGeneratedTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(dept_name="BCT")
        prog = Program.objects.create(program_name="BE-BCT", department=dept)
        self.prof = TeacherInfo.objects.create(
            unique_id="T500", name="Prof Five", email="p5@example.com", department=dept,
        )
        self.other = TeacherInfo.objects.create(
            unique_id="T501", name="Prof Six", email="p6@example.com", department=dept,
        )
        stu = StudentLoginInfo.objects.create(
            username="eve", roll_number="080BCT040", department=dept,
            program=prog, password="x", dob="2000-01-01",
        )
        self.stored = Application.objects.create(
            name="eve stored", email="e@example.com", professor=self.prof,
            std=stu, is_generated=True,
        )
        self.stored.generated_letter.save(
            "eve.pdf", ContentFile(b"%PDF-1.4 fake letter"), save=True,
        )
        self.legacy = Application.objects.create(
            name="eve legacy", email="e@example.com", professor=self.prof,
            std=stu, is_generated=True,
        )
        self.client.cookies["unique"] = "T500"

    def tearDown(self):
        self.stored.generated_letter.delete(save=False)

    def test_returns_stored_file(self):
        response = self.client.get(f"/download_generated/?id={self.stored.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 fake letter")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_missing_stored_file_redirects_with_message(self):
        response = self.client.get(f"/download_generated/?id={self.legacy.pk}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/teacher")

    def test_other_professors_letter_is_not_served(self):
        self.client.cookies["unique"] = "T501"
        response = self.client.get(f"/download_generated/?id={self.stored.pk}")
        self.assertEqual(response.status_code, 404)

    def test_anonymous_request_is_not_served(self):
        del self.client.cookies["unique"]
        response = self.client.get(f"/download_generated/?id={self.stored.pk}")
        self.assertEqual(response.status_code, 404)

    def test_missing_id_parameter_is_not_served(self):
        response = self.client.get("/download_generated/")
        self.assertEqual(response.status_code, 404)

    def test_malformed_id_is_not_served(self):
        for bad in ("abc", "1 OR 1=1", "5.0", ""):
            with self.subTest(bad=bad):
                response = self.client.get(f"/download_generated/?id={bad}")
                self.assertEqual(response.status_code, 404)


class SystemTemplateModelTests(TestCase):
    """CustomTemplates must support shared system templates (FR-1)."""

    def test_a_system_template_needs_no_professor(self):
        tpl = CustomTemplates.objects.create(
            template_name="Formal / Academic",
            template="Dear Committee,",
            professor=None,
            is_system=True,
        )
        self.assertIsNone(tpl.professor)
        self.assertTrue(tpl.is_system)

    def test_professor_templates_are_not_system_by_default(self):
        dept = Department.objects.create(dept_name="BCT")
        teacher = TeacherInfo.objects.create(
            name="Prof A", unique_id="T-A", department=dept
        )
        tpl = CustomTemplates.objects.create(
            template_name="Mine", template="Hello", professor=teacher
        )
        self.assertFalse(tpl.is_system)

    def test_str_does_not_crash_without_a_professor(self):
        tpl = CustomTemplates.objects.create(
            template_name="Formal", template="x", professor=None, is_system=True
        )
        self.assertIn("Formal", str(tpl))


class SeededSystemTemplateTests(TestCase):
    """The data migration must ship a usable starter library (FR-1)."""

    def test_three_system_templates_are_seeded(self):
        seeded = CustomTemplates.objects.filter(is_system=True)
        self.assertEqual(seeded.count(), 3)

    def test_seeded_templates_have_names_and_bodies(self):
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                self.assertTrue(tpl.template_name)
                self.assertGreater(len(tpl.template), 100)
                self.assertIsNone(tpl.professor)
                self.assertFalse(tpl.is_default)

    def test_seeded_templates_are_ascii_only(self):
        # The PDF export encodes latin-1; a stray em dash crashes the download.
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                tpl.template.encode("ascii")

    def test_seeded_templates_are_valid_jinja(self):
        from jinja2 import Template
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                Template(tpl.template)  # raises TemplateSyntaxError if malformed

    def test_seeded_templates_render_without_leaking_none(self):
        """A sparse application must not put the literal word None in the prose."""
        from jinja2 import Template
        dept = Department.objects.create(dept_name="BCT")
        program = Program.objects.create(program_name="BE-BCT", department=dept)
        teacher = TeacherInfo.objects.create(
            name="Prof Q", unique_id="T-Q", email="q@example.com", department=dept,
        )
        student = StudentLoginInfo.objects.create(
            username="Sparse Student", roll_number="080BCT500", department=dept,
            program=program, password="x", dob="2000-01-01",
        )
        application = Application.objects.create(
            name="Sparse Student", std=student, professor=teacher,
        )
        # Every satellite object is absent, as it is for a barely-filled request.
        context = {
            "app": application, "teacher": teacher, "academics": None,
            "paper": None, "project": None, "university": None, "quality": None,
            "pronoun": "They", "pronoun_obj": "them", "pronoun_pos": "Their",
            "rel_desc": "teacher", "strength_phrase": "with great enthusiasm",
            "deadline": "", "today": "July 20, 2026",
        }
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                letter = Template(tpl.template).render(context)
                self.assertNotIn("None", letter)
                self.assertIn("Sparse Student", letter)
                # No paragraph may be bare punctuation left by an empty branch.
                for line in letter.splitlines():
                    self.assertNotIn(line.strip(), (".", ",", "-"))

    def test_seeded_paragraphs_are_single_source_lines(self):
        """The PDF exporter does not reflow across newlines, so a sentence
        split over two source lines becomes two ragged lines in the export."""
        for tpl in CustomTemplates.objects.filter(is_system=True):
            for line in tpl.template.splitlines():
                stripped = line.strip()
                # A line that ends mid-sentence has broken a paragraph in two.
                if stripped and not stripped.startswith("{%") and len(stripped) > 60:
                    with self.subTest(name=tpl.template_name, line=stripped[:40]):
                        self.assertTrue(
                            stripped.endswith((".", "}", "%}", '"', "!")),
                            f"paragraph broken mid-sentence: {stripped!r}",
                        )

    def _render_seeded(self, context):
        from jinja2 import Template
        return [
            (tpl.template_name, Template(tpl.template).render(context))
            for tpl in CustomTemplates.objects.filter(is_system=True)
        ]

    def test_blank_related_rows_do_not_leave_holes_in_the_prose(self):
        """Guards must fire for rows that EXIST but whose fields are blank.

        The sparse case above passes None for every satellite object, so the
        guards on dept_name/program_name/gpa are never actually exercised. Here
        the rows exist and the fields are empty, which is the realistic shape:
        Department.dept_name and Program.program_name are NOT NULL but
        blank=True, so the empty value is "" and dropping a guard leaves a
        doubled space ("studies in  at the Institute"), not the word "None".
        """
        dept = Department.objects.create(dept_name="")
        program = Program.objects.create(program_name="", department=dept)
        teacher = TeacherInfo.objects.create(
            name="Prof B", unique_id="T-B", email="b@example.com", department=dept,
        )
        student = StudentLoginInfo.objects.create(
            username="Blank Student", roll_number="080BCT501", department=dept,
            program=program, password="x", dob="2000-01-01",
        )
        application = Application.objects.create(
            name="Blank Student", std=student, professor=teacher,
        )
        # The row exists but carries no grade, so the GPA sentence must not run.
        academics = Academics.objects.create(
            application=application, gpa="", tentative_ranking="",
        )
        context = {
            "app": application, "teacher": teacher, "academics": academics,
            "paper": None, "project": None, "university": None, "quality": None,
            "pronoun": "They", "pronoun_obj": "them", "pronoun_pos": "Their",
            "rel_desc": "teacher", "strength_phrase": "with great enthusiasm",
            "deadline": "", "today": "July 20, 2026",
        }
        for name, letter in self._render_seeded(context):
            with self.subTest(name=name):
                self.assertIn("Blank Student", letter)
                self.assertNotIn("None", letter)
                # An unguarded blank field collapses to "" and doubles a space.
                self.assertNotIn("  ", letter)
                # academics is truthy but has no gpa: the whole sentence goes.
                self.assertNotIn("GPA", letter)

    def test_seeded_templates_are_grammatical_for_plural_pronouns(self):
        """Students with unset gender get They/them/Their, which must not
        collide with third-person-singular verbs ("They has maintained")."""
        from jinja2 import Template
        dept = Department.objects.create(dept_name="BEI")
        program = Program.objects.create(program_name="BE-BEI", department=dept)
        teacher = TeacherInfo.objects.create(
            name="Prof Z", unique_id="T-Z", email="z@example.com", department=dept,
        )
        student = StudentLoginInfo.objects.create(
            username="Plural Student", roll_number="080BEI777", department=dept,
            program=program, password="x", dob="2000-01-01",
        )
        application = Application.objects.create(
            name="Plural Student", std=student, professor=teacher,
            subjects="Control Systems", is_paper=True,
        )
        academics = Academics.objects.create(application=application, gpa="3.75")
        quality = Qualities.objects.create(
            application=application, leadership=True, hardworking=True,
            teamwork=True, friendly=True, quality="unfailingly curious",
        )
        context = {
            "app": application, "teacher": teacher, "academics": academics,
            "paper": None, "project": None, "university": None, "quality": quality,
            "pronoun": "They", "pronoun_obj": "them", "pronoun_pos": "Their",
            "rel_desc": "teacher", "strength_phrase": "with great enthusiasm",
            "deadline": "", "today": "July 20, 2026",
        }
        singular_verbs = (
            "They has", "they has", "They is", "they is", "They shows",
            "they shows", "They works", "they works", "They holds", "they holds",
        )
        for tpl in CustomTemplates.objects.filter(is_system=True):
            letter = Template(tpl.template).render(context)
            for bad in singular_verbs:
                with self.subTest(name=tpl.template_name, phrase=bad):
                    self.assertNotIn(bad, letter)


class LetterContextTests(TestCase):
    """build_letter_context assembles everything the Jinja templates read."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.teacher = TeacherInfo.objects.create(
            name="Prof B", unique_id="T-B", email="b@example.com", department=self.dept,
        )
        self.student = StudentLoginInfo.objects.create(
            username="Ramesh Shrestha", roll_number="080BCT042", department=self.dept,
            program=self.program, password="x", dob="2000-01-01", gender="Male",
        )
        self.application = Application.objects.create(
            name="Ramesh Shrestha", std=self.student, professor=self.teacher,
            subjects="Data Structures,Algorithms",
        )

    def test_pronouns_follow_the_student_gender(self):
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["pronoun"], "He")
        self.assertEqual(ctx["pronoun_obj"], "him")
        self.assertEqual(ctx["pronoun_pos"], "His")

    def test_female_gender_maps_correctly(self):
        from home.letters import build_letter_context
        self.student.gender = "Female"
        self.student.save()
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["pronoun"], "She")
        self.assertEqual(ctx["pronoun_obj"], "her")
        self.assertEqual(ctx["pronoun_pos"], "Her")

    def test_unknown_gender_falls_back_to_they(self):
        from home.letters import build_letter_context
        self.student.gender = ""
        self.student.save()
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["pronoun"], "They")
        self.assertEqual(ctx["pronoun_obj"], "them")
        self.assertEqual(ctx["pronoun_pos"], "Their")

    def test_null_gender_falls_back_to_they(self):
        from home.letters import build_letter_context
        self.student.gender = None
        self.student.save()
        self.assertEqual(build_letter_context(self.application)["pronoun"], "They")

    def test_gender_matching_is_case_insensitive(self):
        from home.letters import build_letter_context
        self.student.gender = "MALE"
        self.student.save()
        self.assertEqual(build_letter_context(self.application)["pronoun"], "He")

    def test_no_context_value_is_none_for_the_pronoun_words(self):
        # Jinja's ``|lower`` filter raises on an explicit None, and every
        # seeded template pipes these through it.
        from home.letters import build_letter_context
        self.student.gender = None
        self.student.save()
        ctx = build_letter_context(self.application)
        for key in ("pronoun", "pronoun_obj", "pronoun_pos", "rel_desc", "strength_phrase"):
            with self.subTest(key=key):
                self.assertIsInstance(ctx[key], str)

    def test_subjects_are_split_into_list_and_last(self):
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["subjects"], ["Data Structures"])
        self.assertEqual(ctx["subject"], "Algorithms")

    def test_single_subject_sets_value_true(self):
        from home.letters import build_letter_context
        self.application.subjects = "Algorithms"
        self.application.save()
        ctx = build_letter_context(self.application)
        self.assertTrue(ctx["value"])

    def test_empty_subjects_do_not_crash(self):
        from home.letters import build_letter_context
        self.application.subjects = ""
        self.application.save()
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["subjects"], [])
        self.assertFalse(ctx["value"])

    def test_firstname_is_the_first_word(self):
        from home.letters import build_letter_context
        self.assertEqual(build_letter_context(self.application)["firstname"], "Ramesh")

    def test_missing_satellite_rows_do_not_raise(self):
        # No Paper/Project/University/Qualities/Academics/Files rows exist.
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        for key in ("paper", "project", "university", "quality", "academics", "files"):
            with self.subTest(key=key):
                self.assertIsNone(ctx[key])
        self.assertEqual(ctx["deadline"], "")

    def test_satellite_rows_are_returned_when_present(self):
        from home.letters import build_letter_context
        academics = Academics.objects.create(application=self.application, gpa="3.9")
        university = University.objects.create(
            application=self.application, uni_name="MIT", country="USA",
        )
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["academics"], academics)
        self.assertEqual(ctx["university"], university)

    def test_deadline_is_formatted_when_present(self):
        from home.letters import build_letter_context
        University.objects.create(
            application=self.application, uni_name="MIT", country="USA",
            uni_deadline=date(2026, 12, 15),
        )
        self.assertEqual(build_letter_context(self.application)["deadline"], "December 15, 2026")

    def test_teacher_and_app_aliases_are_present(self):
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["teacher"], self.teacher)
        self.assertEqual(ctx["app"], self.application)
        self.assertEqual(ctx["student"], self.application)
        self.assertTrue(ctx["today"])

    def test_every_seeded_system_template_renders_against_this_context(self):
        # The real integration check: the three shipped templates must render
        # against exactly what this function produces.
        from jinja2 import Template
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                letter = Template(tpl.template).render(ctx)
                self.assertIn("Ramesh Shrestha", letter)
                self.assertNotIn("None", letter)

    def test_rel_desc_comes_from_the_application(self):
        from home.letters import build_letter_context
        self.application.relationship_type = "project supervisor"
        self.application.save()
        self.assertEqual(build_letter_context(self.application)["rel_desc"], "project supervisor")

    def test_rel_desc_falls_back_when_unset(self):
        from home.letters import build_letter_context
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.application.relationship_type = value
                self.application.save()
                self.assertEqual(build_letter_context(self.application)["rel_desc"], "teacher")

    def test_strength_phrase_follows_the_recommendation_strength(self):
        from home.letters import build_letter_context
        quality = Qualities.objects.create(application=self.application)
        expected = {
            "top5": "as one of the very best students I have taught",
            "top10": "as one of the strongest students I have taught",
            "outstanding": "in the strongest possible terms",
            "strong": "with great enthusiasm",
        }
        for value, phrase in expected.items():
            with self.subTest(value=value):
                quality.recommendation_strength = value
                quality.save()
                self.assertEqual(build_letter_context(self.application)["strength_phrase"], phrase)

    def test_strength_phrase_falls_back_without_a_qualities_row(self):
        from home.letters import build_letter_context
        self.assertEqual(
            build_letter_context(self.application)["strength_phrase"],
            "with great enthusiasm",
        )

    def test_strength_phrase_falls_back_on_an_unrecognised_value(self):
        from home.letters import build_letter_context
        Qualities.objects.create(application=self.application, recommendation_strength="")
        self.assertEqual(
            build_letter_context(self.application)["strength_phrase"],
            "with great enthusiasm",
        )

    def test_recommendation_reads_correctly_for_every_strength(self):
        """Each phrase must slot grammatically into every seeded template."""
        from jinja2 import Template
        from home.letters import build_letter_context
        quality = Qualities.objects.create(application=self.application)
        for value in ("top5", "top10", "outstanding", "strong"):
            quality.recommendation_strength = value
            quality.save()
            ctx = build_letter_context(self.application)
            for tpl in CustomTemplates.objects.filter(is_system=True):
                with self.subTest(strength=value, name=tpl.template_name):
                    letter = Template(tpl.template).render(ctx)
                    self.assertNotIn("and without reservation", letter)
                    self.assertNotIn("  ", letter)
                    # A trailing prepositional phrase must not attach itself
                    # to the end of a ranked strength phrase.
                    self.assertNotIn("I have taught for", letter)

    def _subjects(self, raw):
        from home.letters import build_letter_context
        self.application.subjects = raw
        self.application.save()
        return build_letter_context(self.application)

    def test_subject_keys_agree_on_empty_segments(self):
        # subjects/subject/value were derived separately in the legacy views
        # and disagreed; one normalisation now backs all three.
        cases = {
            "A,B,C": (["A", "B"], "C", False),
            "A": ([], "A", True),
            "A,": ([], "A", True),       # trailing comma must not blank the subject
            ",A": ([], "A", True),
            "A, B": (["A"], "B", False),  # inner whitespace is stripped
            "": ([], "", False),
            None: ([], "", False),
        }
        for raw, (subjects, subject, value) in cases.items():
            with self.subTest(raw=raw):
                ctx = self._subjects(raw)
                self.assertEqual(ctx["subjects"], subjects)
                self.assertEqual(ctx["subject"], subject)
                self.assertEqual(ctx["value"], value)

    def test_a_trailing_comma_does_not_drop_the_only_subject(self):
        # Legacy gave value=True with subject="", rendering "I taught him .".
        ctx = self._subjects("Algorithms,")
        self.assertTrue(ctx["value"])
        self.assertEqual(ctx["subject"], "Algorithms")

    def test_subjects_sentence_reads_as_prose(self):
        for raw, expected in (
            ("", ""),
            ("Algorithms", "Algorithms"),
            ("Algorithms,Compilers", "Algorithms and Compilers"),
            ("Algorithms,Compilers,Networks", "Algorithms, Compilers and Networks"),
            ("Algorithms, Compilers , Networks", "Algorithms, Compilers and Networks"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self._subjects(raw)["subjects_sentence"], expected)

    def test_firstname_handles_awkward_whitespace(self):
        from home.letters import build_letter_context
        for raw, expected in (
            ("  Ram Thapa", "Ram"),      # leading space returned "" before
            ("Ram  Thapa", "Ram"),
            ("Sita", "Sita"),
            ("", ""),
            (None, ""),
        ):
            with self.subTest(raw=raw):
                self.application.name = raw
                self.application.save()
                self.assertEqual(build_letter_context(self.application)["firstname"], expected)

    def test_seeded_templates_list_subjects_as_prose(self):
        from jinja2 import Template
        ctx = self._subjects("Algorithms,Compilers,Networks")
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                letter = Template(tpl.template).render(ctx)
                self.assertNotIn("Algorithms,Compilers", letter)
                if "Algorithms" in letter:
                    self.assertIn("Algorithms, Compilers and Networks", letter)

    def test_seeded_templates_omit_the_subject_clause_when_unset(self):
        from jinja2 import Template
        ctx = self._subjects("")
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                letter = Template(tpl.template).render(ctx)
                self.assertNotIn("having taught", letter)
                self.assertNotIn("I taught", letter)
                self.assertNotIn(" in .", letter)
