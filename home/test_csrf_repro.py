"""Browser-faithful CSRF round-trip: GET page, scrape token, POST it back."""
import re
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from home.models import *

TOKEN_RE = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')


def tokens(html):
    return TOKEN_RE.findall(html.decode() if isinstance(html, bytes) else html)


class CsrfRoundTripTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.user = User.objects.create_user(username="prof1", password="pw", email="p@x.com")
        self.user.first_name = "Prof One/T1"
        self.user.save()
        self.teacher = TeacherInfo.objects.create(
            name="Prof One", unique_id="T1", email="p@x.com", user=self.user, department=self.dept,
        )
        self.student = StudentLoginInfo.objects.create(
            username="Stu", roll_number="080BCT001", department=self.dept,
            program=self.program, password=make_password("pw"), dob="2000-01-01",
        )

    def _get(self, c, url):
        r = c.get(url, follow=True)
        return r

    def test_teacher_login_round_trip(self):
        c = Client(enforce_csrf_checks=True)
        r = self._get(c, "/loginTeacher")
        tk = tokens(r.content)
        print("GET /loginTeacher ->", r.status_code, "tokens:", len(tk),
              "cookie:", c.cookies.get("csrftoken") and c.cookies["csrftoken"].value[:8])
        r2 = c.post("/loginTeacher", {"username": "p@x.com", "password": "pw",
                                      "csrfmiddlewaretoken": tk[0]})
        print("POST /loginTeacher ->", r2.status_code)
        self.assertNotEqual(r2.status_code, 403)

        # tokens embedded in the dashboard rendered straight off the login POST
        tk2 = tokens(r2.content)
        print("dashboard tokens:", len(tk2),
              "cookie now:", c.cookies["csrftoken"].value[:8])
        if tk2:
            r3 = c.post("/getdetails", {"csrfmiddlewaretoken": tk2[0]})
            print("POST /getdetails with dashboard token ->", r3.status_code)
            self.assertNotEqual(r3.status_code, 403,
                                "token from the page rendered by the login POST is rejected")

    def test_logout_then_login_again(self):
        c = Client(enforce_csrf_checks=True)
        tk = tokens(self._get(c, "/loginTeacher").content)
        c.post("/loginTeacher", {"username": "p@x.com", "password": "pw",
                                 "csrfmiddlewaretoken": tk[0]})
        c.get("/logout", follow=True)
        print("after logout, csrftoken cookie =", repr(c.cookies.get("csrftoken") and c.cookies["csrftoken"].value))
        r = self._get(c, "/loginTeacher")
        tk2 = tokens(r.content)
        print("re-GET login tokens:", len(tk2), "cookie:", repr(c.cookies["csrftoken"].value[:8]))
        r2 = c.post("/loginTeacher", {"username": "p@x.com", "password": "pw",
                                      "csrfmiddlewaretoken": tk2[0]})
        print("re-POST /loginTeacher ->", r2.status_code)
        self.assertNotEqual(r2.status_code, 403, "login after logout fails CSRF")

    def test_student_login_round_trip(self):
        c = Client(enforce_csrf_checks=True)
        r = self._get(c, "/loginStudent")
        tk = tokens(r.content)
        print("GET /loginStudent tokens:", len(tk))
        r2 = c.post("/loginStudent", {"username": "080BCT001", "password": "pw",
                                      "csrfmiddlewaretoken": tk[0]})
        print("POST /loginStudent ->", r2.status_code)
        self.assertNotEqual(r2.status_code, 403)

    def test_public_form_pages_round_trip(self):
        for url in ["/contact", "/forgotPassword", "/forgotUsername",
                    "/registerProfessor/", "/loginAdmin", "/registerStudent"]:
            c = Client(enforce_csrf_checks=True)
            r = self._get(c, url)
            tk = tokens(r.content)
            print(f"GET {url} -> {r.status_code} tokens={len(tk)}")
            if not tk:
                continue
            r2 = c.post(url, {"csrfmiddlewaretoken": tk[0]})
            print(f"  POST {url} -> {r2.status_code}")
            self.assertNotEqual(r2.status_code, 403, f"{url} rejects its own token")
