# Phase B — Full Student Details on the Generation Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Show the professor every detail the student submitted, in a polished read-only panel on the letter-generation page, and stop the page from 500-ing on incomplete/multi-entry applications.

**Architecture:** `make_letter` (`home/views.py`) gains resilient satellite lookups and passes the full universities/papers/projects collections; `formTeacher.html` gets a new card-based "Student's submitted application" panel above the professor's (unchanged) generate form. No schema change.

**Tech Stack:** Django 5.1, Bootstrap 5 + bootstrap-icons (already loaded via `base2.html`), Django test framework.

---

## File Structure
- Modify `home/views.py` — `make_letter` (`:468`): `.get()` → `.filter().first()`; add `universities`/`papers`/`projects`.
- Rewrite `templates/formTeacher.html` — new details panel + kept form + fixed modal ids.
- Modify `home/tests.py` — new `StudentDetailsPanelTests`.

Run one class with `python manage.py test home.tests.<ClassName> -v 2` (activate venv first: `source venv/bin/activate`). Repo rules: no AI attribution in commits; never stage `db.sqlite3`, `CLAUDE.md`, `docs/mockups/`, `media/`.

---

## Task 1: Make `make_letter` resilient and expose collections

**Files:** Modify `home/views.py` (`make_letter`, lines ~478-520). Test: `home/tests.py` (`StudentDetailsPanelTests.test_generation_page_survives_a_bare_application`).

- [ ] **Step 1: Write the failing test** — add this class to `home/tests.py`:

```python
class StudentDetailsPanelTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.teacher = TeacherInfo.objects.create(
            name="Prof R", unique_id="T-R", email="r@example.com", department=self.dept,
        )
        self.student = StudentLoginInfo.objects.create(
            username="Mina Rai", roll_number="080BCT900", department=self.dept,
            program=self.program, password="x", dob="2000-01-01", gender="Female",
        )
        login_as_teacher(self.client, self.teacher)

    def test_generation_page_survives_a_bare_application(self):
        # No Paper/Project/University/Qualities/Academics/Files rows at all.
        Application.objects.create(
            name="Mina Rai", std=self.student, professor=self.teacher, subjects="Maths",
        )
        resp = self.client.post("/makeLetter", {"roll": "080BCT900"})
        self.assertEqual(resp.status_code, 200)

    def test_panel_shows_the_newly_exposed_fields(self):
        app = Application.objects.create(
            name="Mina Rai", std=self.student, professor=self.teacher, subjects="Maths",
            intern_company="Acme Labs", scholarships="Dean's List 2024",
        )
        Qualities.objects.create(application=app, leadership=True)
        University.objects.create(application=app, uni_name="MIT", country="USA")
        University.objects.create(application=app, uni_name="ETH", country="Switzerland")
        resp = self.client.post("/makeLetter", {"roll": "080BCT900"})
        self.assertContains(resp, "Acme Labs")
        self.assertContains(resp, "Dean's List 2024")
        self.assertContains(resp, "Leadership")
        self.assertContains(resp, "MIT")
        self.assertContains(resp, "ETH")

    def test_the_two_file_modals_have_distinct_ids(self):
        app = Application.objects.create(
            name="Mina Rai", std=self.student, professor=self.teacher,
        )
        files = Files.objects.create(application=app)
        for field in ("transcript", "CV"):
            getattr(files, field).save(f"{field}.png", ContentFile(b"x"), save=False)
        files.save()
        resp = self.client.post("/makeLetter", {"roll": "080BCT900"})
        self.assertContains(resp, 'id="modalTranscript"')
        self.assertContains(resp, 'id="modalCV"')
```

(`ContentFile` is already imported at the top of `home/tests.py`; if not, add `from django.core.files.base import ContentFile`.)

- [ ] **Step 2: Run** `python manage.py test home.tests.StudentDetailsPanelTests.test_generation_page_survives_a_bare_application -v 2` — confirm it FAILS with a 500 (`Paper.DoesNotExist` from the `.get()`).

- [ ] **Step 3: Replace the satellite lookups and context in `make_letter`.** Replace the block from `stu = StudentLoginInfo.objects.get(...)` down through the `return render(... "formTeacher.html", {...})` with:

```python
        stu = StudentLoginInfo.objects.get(roll_number=roll)
        appli = Application.objects.get(name=stu.username, professor__unique_id=teacher_id)

        # Satellites may be absent (student skipped a section) or plural (several
        # universities/papers/projects). ``.first()`` keeps the single-value
        # template refs working without a 500; the querysets feed the full panel.
        paper = Paper.objects.filter(application=appli).first()
        project = Project.objects.filter(application=appli).first()
        university = University.objects.filter(application=appli).first()
        quality = Qualities.objects.filter(application=appli).first()
        academics = Academics.objects.filter(application=appli).first()
        files = Files.objects.filter(application=appli).first()

        universities = University.objects.filter(application=appli)
        papers = Paper.objects.filter(application=appli)
        projects = Project.objects.filter(application=appli)

        linkedin = appli.linkedIn
        personal_statement = appli.personal_statement
        recommendation_purpose = appli.recommendation_purpose

        templates = available_templates(appli.professor)
        default_template = templates.filter(is_default=True).first()
        teacher_name = appli.professor.name

        return render(
            request,
            "formTeacher.html",
            {
                "student": appli,
                "roll": roll,
                "paper": paper,
                "project": project,
                "university": university,
                "quality": quality,
                "academics": academics,
                "files": files,
                "universities": universities,
                "papers": papers,
                "projects": projects,
                "teacher": teacher_name,
                "teacher_model": teacher_model,
                "templates": templates,
                "default_template": default_template,
                "linkedin": linkedin,
                "personal_statement": personal_statement,
                "recommendation_purpose": recommendation_purpose,
            },
        )
```

- [ ] **Step 4: Run** `python manage.py test home.tests.StudentDetailsPanelTests.test_generation_page_survives_a_bare_application -v 2` — PASS. (The other two panel tests will pass after Task 2; they need the new template.)

- [ ] **Step 5: Commit**
```bash
git add home/views.py home/tests.py
git commit -m "fix(letter): make generation page resilient and expose all student collections"
```

---

## Task 2: Rewrite `formTeacher.html` with the details panel

**Files:** Rewrite `templates/formTeacher.html`. Tests: the remaining two `StudentDetailsPanelTests` methods + existing `MakeLetterTemplateListTests`.

- [ ] **Step 1: Confirm the two panel tests currently fail** (template not updated yet):
`python manage.py test home.tests.StudentDetailsPanelTests.test_panel_shows_the_newly_exposed_fields home.tests.StudentDetailsPanelTests.test_the_two_file_modals_have_distinct_ids -v 2` — expect FAIL.

- [ ] **Step 2: Replace the ENTIRE contents of `templates/formTeacher.html` with:**

```html
{% extends 'base2.html' %} {% block title %}Generate{% endblock title %}
{% block teacher %}{% if teacher_model.images %}<a href="teacher"><img src="{{ teacher_model.images.url }}" style="width:33px;height:33px; border-radius: 50%;"></a>{% endif %}{% endblock teacher %}
{% block body %}
<style>
  .gen { max-width: 1080px; margin: 0 auto; padding: 8px 16px 72px; }
  .gen-head { display: flex; align-items: center; gap: 16px; margin: 16px 0 8px; }
  .gen-head img { width: 72px; height: 72px; border-radius: 50%; object-fit: cover; border: 2px solid #e6e7ea; }
  .gen-head .who h1 { font-size: 1.5rem; font-weight: 650; margin: 0; }
  .gen-head .who p { margin: 0; color: #667085; font-size: .9rem; }
  .section-label { font-size: .8rem; letter-spacing: .05em; text-transform: uppercase; color: #98a2b3; font-weight: 600; margin: 28px 0 12px; }
  .surface { border: 1px solid #e6e7ea; border-radius: 12px; background: #fff; box-shadow: 0 1px 2px rgba(16,24,40,.04); }
  .detail-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
  .detail-card { padding: 16px 18px; }
  .detail-card h3 { font-size: .95rem; font-weight: 650; margin: 0 0 12px; display: flex; align-items: center; gap: 8px; }
  .detail-card h3 i { color: #33429e; }
  .kv { display: grid; grid-template-columns: 42% 58%; gap: 6px 10px; margin: 0; }
  .kv dt { color: #667085; font-size: .85rem; font-weight: 500; }
  .kv dd { margin: 0; font-size: .9rem; color: #1c2027; word-break: break-word; }
  .badges { display: flex; flex-wrap: wrap; gap: 6px; }
  .badge-q { background: #eef1fb; color: #33429e; border-radius: 999px; padding: 2px 10px; font-size: .8rem; font-weight: 600; }
  .doc-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .gen-form-card { padding: 22px; }
  .gen-form-card .input-box { margin-bottom: 16px; display: flex; flex-direction: column; max-width: 460px; }
  .gen-form-card .details { font-weight: 500; margin-bottom: 6px; display: block; }
  .gen-form-card select, .gen-form-card textarea { width: 100%; padding: 8px 10px; border: 1px solid #d0d5dd; border-radius: 8px; }
  .gen-form-card .gender-title { font-weight: 600; display: block; margin: 8px 0; }
</style>

<div class="gen">
  <div class="gen-head">
    {% if files.Photo %}<img src="{{ files.Photo.url }}" alt="{{ student.name }}">{% endif %}
    <div class="who">
      <h1>{{ student.name }}</h1>
      <p>Submitted application — review before generating the letter</p>
    </div>
  </div>

  <div class="section-label">Student's submitted application</div>
  <div class="detail-grid">

    <div class="surface detail-card">
      <h3><i class="bi bi-person"></i> Student</h3>
      <dl class="kv">
        <dt>Full name</dt><dd>{{ student.name|default:"—" }}</dd>
        <dt>Email</dt><dd>{{ student.email|default:"—" }}</dd>
        <dt>Contact</dt><dd>{{ student.contact_number|default:"—" }}</dd>
        <dt>Applied level</dt><dd>{{ student.applied_level|default:"—" }}</dd>
        <dt>LinkedIn</dt><dd>{% if linkedin %}<a href="{{ linkedin }}" target="_blank">{{ linkedin }}</a>{% else %}—{% endif %}</dd>
      </dl>
    </div>

    <div class="surface detail-card">
      <h3><i class="bi bi-mortarboard"></i> Academic</h3>
      <dl class="kv">
        <dt>GPA</dt><dd>{{ academics.gpa|default:"—" }}</dd>
        <dt>Tentative ranking</dt><dd>{{ academics.tentative_ranking|default:"—" }}</dd>
        <dt>Final %</dt><dd>{{ academics.final_percentage|default:"—" }}</dd>
        <dt>Class size</dt><dd>{{ student.class_size|default:"—" }}</dd>
        <dt>Ranking percentile</dt><dd>{{ student.ranking_percentile|default:"—" }}</dd>
        <dt>Enrollment batch</dt><dd>{{ student.enrollment_batch|default:"—" }}</dd>
        <dt>Passed year</dt><dd>{{ student.passed_year|default:"—" }}</dd>
        <dt>Language</dt><dd>{{ student.language_instruction|default:"—" }}</dd>
      </dl>
    </div>

    <div class="surface detail-card">
      <h3><i class="bi bi-people"></i> Relationship with you</h3>
      <dl class="kv">
        <dt>Years known/taught</dt><dd>{{ student.years_taught|default:student.years_known|default:"—" }}</dd>
        <dt>Relationship</dt><dd>{{ student.relationship_type|default:"—" }}</dd>
        <dt>Known roles</dt><dd>{{ student.known_roles|default:"—" }}</dd>
        <dt>Subjects taught</dt><dd>{{ student.subjects|default:"—" }}</dd>
        <dt>Prof. experience</dt><dd>{{ student.professional_experience|default:"—" }}</dd>
      </dl>
    </div>

    <div class="surface detail-card">
      <h3><i class="bi bi-building"></i> Universities applied</h3>
      {% for u in universities %}
      <dl class="kv" {% if not forloop.first %}style="margin-top:10px;border-top:1px solid #eef0f3;padding-top:10px;"{% endif %}>
        <dt>Name</dt><dd>{{ u.uni_name|default:"—" }}</dd>
        <dt>Country</dt><dd>{{ u.country|default:"—" }}</dd>
        <dt>Program</dt><dd>{{ u.program_applied|default:"—" }}</dd>
        <dt>Deadline</dt><dd>{{ u.uni_deadline|default:"—" }}</dd>
      </dl>
      {% empty %}<p class="text-muted mb-0">—</p>{% endfor %}
    </div>

    <div class="surface detail-card">
      <h3><i class="bi bi-journal-text"></i> Research / Papers</h3>
      {% for p in papers %}{% if p.paper_title or p.paper_link %}
      <p class="mb-1">{% if p.paper_link %}<a href="{{ p.paper_link }}" target="_blank">{{ p.paper_title|default:"View paper" }}</a>{% else %}{{ p.paper_title }}{% endif %}</p>
      {% endif %}{% empty %}<p class="text-muted mb-0">—</p>{% endfor %}
    </div>

    <div class="surface detail-card">
      <h3><i class="bi bi-kanban"></i> Projects</h3>
      {% for pr in projects %}
      <dl class="kv" {% if not forloop.first %}style="margin-top:10px;border-top:1px solid #eef0f3;padding-top:10px;"{% endif %}>
        <dt>Supervised</dt><dd>{{ pr.supervised_project|default:"—" }}</dd>
        <dt>Other / final</dt><dd>{{ pr.final_project|default:"—" }}</dd>
        <dt>Deployed</dt><dd>{% if pr.deployed %}Yes{% else %}No{% endif %}</dd>
      </dl>
      {% empty %}<p class="text-muted mb-0">—</p>{% endfor %}
    </div>

    {% if student.intern or student.intern_company or student.intern_role %}
    <div class="surface detail-card">
      <h3><i class="bi bi-briefcase"></i> Internship</h3>
      <dl class="kv">
        <dt>Company</dt><dd>{{ student.intern_company|default:"—" }}</dd>
        <dt>Role</dt><dd>{{ student.intern_role|default:"—" }}</dd>
        <dt>Duration</dt><dd>{{ student.intern_duration|default:"—" }}</dd>
        <dt>Outcome</dt><dd>{{ student.intern_outcome|default:"—" }}</dd>
      </dl>
    </div>
    {% endif %}

    {% if student.scholarships or student.competitions_won %}
    <div class="surface detail-card">
      <h3><i class="bi bi-award"></i> Awards &amp; scholarships</h3>
      <dl class="kv">
        <dt>Scholarships</dt><dd>{{ student.scholarships|default:"—"|linebreaksbr }}</dd>
        <dt>Competitions</dt><dd>{{ student.competitions_won|default:"—"|linebreaksbr }}</dd>
      </dl>
    </div>
    {% endif %}

    <div class="surface detail-card">
      <h3><i class="bi bi-stars"></i> Personal qualities (self-reported)</h3>
      <div class="badges mb-2">
        {% if quality.leadership %}<span class="badge-q">Leadership</span>{% endif %}
        {% if quality.hardworking %}<span class="badge-q">Hardworking</span>{% endif %}
        {% if quality.social %}<span class="badge-q">Social</span>{% endif %}
        {% if quality.teamwork %}<span class="badge-q">Teamwork</span>{% endif %}
        {% if quality.friendly %}<span class="badge-q">Friendly</span>{% endif %}
      </div>
      <dl class="kv">
        <dt>Presentation</dt><dd>{{ quality.presentation|default:"—" }}</dd>
        <dt>Recommend</dt><dd>{{ quality.recommend|default:"—" }}</dd>
        <dt>Strength</dt><dd>{{ quality.recommendation_strength|default:"—" }}</dd>
        <dt>Extracurricular</dt><dd>{{ quality.extracirricular|default:"—" }}</dd>
      </dl>
    </div>

    <div class="surface detail-card">
      <h3><i class="bi bi-chat-quote"></i> Statements</h3>
      <dl class="kv">
        <dt>Personal statement</dt><dd>{{ personal_statement|default:"—"|linebreaksbr }}</dd>
        <dt>Recommendation purpose</dt><dd>{{ recommendation_purpose|default:"—"|linebreaksbr }}</dd>
        <dt>Strong points</dt><dd>{{ student.strong_points|default:"—"|linebreaksbr }}</dd>
        <dt>Weak points</dt><dd>{{ student.weak_points|default:"—"|linebreaksbr }}</dd>
      </dl>
    </div>

    <div class="surface detail-card">
      <h3><i class="bi bi-paperclip"></i> Documents</h3>
      <div class="doc-actions">
        {% if files.transcript %}
          {% if files.transcript.url|lower|slice:'-4:' == '.pdf' %}
          <a href="{{ files.transcript.url }}" class="btn btn-sm btn-outline-primary" target="_blank"><i class="bi bi-file-earmark-text"></i> Transcript</a>
          {% else %}
          <button type="button" class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#modalTranscript"><i class="bi bi-file-earmark-text"></i> Transcript</button>
          {% endif %}
        {% else %}<span class="text-muted">No transcript</span>{% endif %}

        {% if files.CV %}
          {% if files.CV.url|lower|slice:'-4:' == '.pdf' %}
          <a href="{{ files.CV.url }}" class="btn btn-sm btn-outline-primary" target="_blank"><i class="bi bi-file-earmark-person"></i> CV</a>
          {% else %}
          <button type="button" class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#modalCV"><i class="bi bi-file-earmark-person"></i> CV</button>
          {% endif %}
        {% else %}<span class="text-muted">No CV</span>{% endif %}
      </div>
    </div>

  </div>

  {% if files.transcript and files.transcript.url|lower|slice:'-4:' != '.pdf' %}
  <div class="modal fade" id="modalTranscript" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-lg"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title">Transcript</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
      <div class="modal-body"><img src="{{ files.transcript.url }}" style="width:100%"></div>
    </div></div>
  </div>
  {% endif %}
  {% if files.CV and files.CV.url|lower|slice:'-4:' != '.pdf' %}
  <div class="modal fade" id="modalCV" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-lg"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title">CV</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
      <div class="modal-body"><img src="{{ files.CV.url }}" style="width:100%"></div>
    </div></div>
  </div>
  {% endif %}

  <div class="section-label">Generate the letter</div>
  <div class="surface gen-form-card">
    <form method="POST" id="recommendationForm" action="/renderCustom">
      {% csrf_token %}
      <div class="input-box">
        <span class="details">Presentation skills:</span>
        <select name="presentation" required>
          <option></option><option>good</option><option>outstanding</option><option>excellent</option>
        </select>
      </div>
      <div class="input-box">
        <span class="details">Quality:</span>
        <select name="qual" required>
          <option></option><option>sincere and hardworking</option><option>confident and responsible</option><option>diligent and competitive</option>
        </select>
      </div>
      <div class="input-box">
        <span class="details">Recommend:</span>
        <select name="recommend" required>
          <option></option><option>strongly</option><option>firmly</option>
        </select>
      </div>
      <div class="input-box">
        <span class="details">Professor Anecdote</span>
        <textarea name="prof_anecdote" rows="4" placeholder="Enter any specific observation or story"></textarea>
      </div>
      <div class="gender-details">
        <span class="gender-title">Personal Qualities</span>
        <div class="form-check"><input class="form-check-input" type="checkbox" name="quality1" id="q1"><label class="form-check-label" for="q1">Leadership</label></div>
        <div class="form-check"><input class="form-check-input" type="checkbox" name="quality2" id="q2"><label class="form-check-label" for="q2">Hardworking</label></div>
        <div class="form-check"><input class="form-check-input" type="checkbox" name="quality3" id="q3"><label class="form-check-label" for="q3">Social</label></div>
        <div class="form-check"><input class="form-check-input" type="checkbox" name="quality4" id="q4"><label class="form-check-label" for="q4">Teamwork</label></div>
        <div class="form-check"><input class="form-check-input" type="checkbox" name="quality5" id="q5"><label class="form-check-label" for="q5">Friendly</label></div>
      </div>
      <div class="input-box">
        <span class="details">Choose Template</span>
        <select name="template_id" id="template" required>
          {% for template in templates %}
          <option value="{{ template.pk }}" {% if default_template and template.pk == default_template.pk %}selected{% endif %}>{{ template.template_name }}{% if template.is_system %} (system){% endif %}</option>
          {% endfor %}
        </select>
      </div>
      <input type="hidden" value="{{ roll }}" name="roll" readonly>
      <div class="button mt-3">
        <button class="btn btn-success btn-lg" type="submit"><i class="bi bi-file-earmark-text"></i> Generate letter</button>
      </div>
    </form>
  </div>
</div>
{% endblock body %}
```

- [ ] **Step 3: Run the panel tests** — `python manage.py test home.tests.StudentDetailsPanelTests -v 2` — all 3 PASS.

- [ ] **Step 4: Run the existing generation tests** — `python manage.py test home.tests.MakeLetterTemplateListTests -v 2` — both PASS (picker still lists templates and posts `name="template_id"`).

- [ ] **Step 5: Template render sanity** — `python manage.py shell -c "from django.template.loader import get_template; get_template('formTeacher.html'); print('OK')"` → `OK`.

- [ ] **Step 6: Commit**
```bash
git add templates/formTeacher.html
git commit -m "feat(letter): show the student's full submitted application on the generation page"
```

---

## Task 3: Full-suite verification
- [ ] **Step 1:** `python manage.py test home` → `OK`, no regressions (full suite runs once, here).
- [ ] **Step 2:** Manual smoke: log in as a teacher, open a pending request's "Create letter", confirm the details panel shows all sections and the generate form still works.

---

## Self-Review Notes
- Spec coverage: resilience + collections (Task 1); full panel + duplicate-modal-id fix (Task 2); tests (Tasks 1-2); full suite (Task 3).
- Preserved for tests: `name="template_id"`, template names + "(system)", `{% csrf_token %}`, guarded file `.url`, `roll` hidden input, `action="/renderCustom"`.
- Names consistent: context keys `universities`/`papers`/`projects`; modal ids `modalTranscript`/`modalCV`.
