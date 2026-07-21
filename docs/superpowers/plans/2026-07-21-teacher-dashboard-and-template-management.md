# Teacher Dashboard & Template Management (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the professor's template editor and dashboard discoverable and complete — a visible template list with Edit/Rename/Delete/Set-default, a rename that no longer silently duplicates, and a cleanly sectioned dashboard with template management moved to its own button.

**Architecture:** Django function-based views in `home/views.py`, URL names in `home/urls.py`, templates in `templates/`. No schema change — `CustomTemplates` already carries `template_name`, `professor`, `is_default`, `is_system`. New actions are POST + CSRF, identity via `current_teacher()`, own-templates-only (`get_object_or_404(..., professor=teacher)`). TinyMCE stays as the editor (Phase A); the chip editor is Phase C.

**Tech Stack:** Django 5.1, SQLite, Django test framework (`python manage.py test home`), `login_as_teacher` test helper.

---

## File Structure

- Modify `home/views.py` — fix `getTemplate` (edit-by-id); add `delete_template`, `set_default_template`.
- Modify `home/urls.py` — add `deleteTemplate`, `setDefaultTemplate` routes.
- Modify `templates/customTemplate.html` — visible template list with actions; accurate insert-field palette. (TinyMCE key already swapped to `8mp7ivw6…`.)
- Modify `templates/Teacher.html` — clean Pending/Recommended sections; Manage-Templates button on top; remove inline template block (lines ~135-145).
- Create `home/management/__init__.py`, `home/management/commands/__init__.py`, `home/management/commands/prune_template_copies.py` — one-off junk cleanup as a testable, idempotent command.
- Modify `home/tests.py` — new tests for every behavior.

Conventions: tests are Django `TestCase` classes using `self.client` and `login_as_teacher(self.client, teacher)`; run a single class with `python manage.py test home.tests.<ClassName>`.

---

## Task 0: Branch and baseline

- [ ] **Step 1: Create a working branch** (currently on `main`)

```bash
git checkout -b phase-a-template-management
```

- [ ] **Step 2: Commit the spec and the already-made TinyMCE key swap**

```bash
git add docs/superpowers/specs/2026-07-21-teacher-dashboard-and-template-management-design.md templates/customTemplate.html
git commit -m "docs: add Phase A spec; update TinyMCE cloud key"
```

Note: Do NOT `git add db.sqlite3`, `CLAUDE.md`, or `docs/mockups/`.

---

## Task 1: Edit templates by id (fix rename-duplicates bug)

**Files:**
- Modify: `home/views.py` (function `getTemplate`, currently `home/views.py:1620-1633`)
- Test: `home/tests.py` (new class `TemplateEditByIdTests`)

- [ ] **Step 1: Write the failing test**

Add to `home/tests.py`:

```python
class TemplateEditByIdTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            name="Prof E", unique_id="T-E", email="e@example.com", department=self.dept,
        )
        login_as_teacher(self.client, self.teacher)

    def test_editing_by_id_renames_in_place_without_duplicating(self):
        tpl = CustomTemplates.objects.create(
            template_name="Old Name", template="body", professor=self.teacher,
        )
        resp = self.client.post("/getTemplate", {
            "template_id": tpl.pk,
            "templateName": "New Name",
            "content": "updated body",
        })
        self.assertEqual(resp.status_code, 200)
        tpl.refresh_from_db()
        self.assertEqual(tpl.template_name, "New Name")
        self.assertEqual(
            CustomTemplates.objects.filter(professor=self.teacher).count(), 1
        )

    def test_saving_without_id_creates_new_template(self):
        resp = self.client.post("/getTemplate", {
            "templateName": "Brand New",
            "content": "hello",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            CustomTemplates.objects.filter(
                professor=self.teacher, template_name="Brand New"
            ).exists()
        )

    def test_cannot_edit_another_teachers_template_by_id(self):
        other = TeacherInfo.objects.create(
            name="Prof F", unique_id="T-F", email="f@example.com", department=self.dept,
        )
        theirs = CustomTemplates.objects.create(
            template_name="Theirs", template="x", professor=other,
        )
        self.client.post("/getTemplate", {
            "template_id": theirs.pk,
            "templateName": "Hijacked",
            "content": "y",
        })
        theirs.refresh_from_db()
        self.assertEqual(theirs.template_name, "Theirs")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.TemplateEditByIdTests -v 2`
Expected: FAIL — `test_editing_by_id_renames_in_place_without_duplicating` finds 2 rows (rename created a duplicate), and the hijack test alters the other teacher's row.

- [ ] **Step 3: Replace the name-matched update block with an id-matched update**

In `home/views.py`, replace the block currently at lines 1620-1633:

```python
    # try to update existing template with same name
    template_obj = CustomTemplates.objects.filter(template_name=name, professor=teacher).first()
    if template_obj:
        template_obj.template = content
        if make_default:
            template_obj.is_default = True
        template_obj.save()
    else:
        template_obj = CustomTemplates.objects.create(
            template_name=name,
            template=content,
            professor=teacher,
            is_default=make_default,
        )
```

with:

```python
    # Edit is keyed by primary key, not by name: matching on name meant that
    # renaming a template created a second row instead of renaming the first.
    template_id = (request.POST.get("template_id") or "").strip()
    template_obj = None
    if template_id:
        # Own templates only. A pk that is not this teacher's (including any
        # system row) resolves to nothing and falls through to create-new.
        template_obj = CustomTemplates.objects.filter(
            pk=template_id, professor=teacher
        ).first()

    if template_obj:
        template_obj.template_name = name
        template_obj.template = content
        if make_default:
            template_obj.is_default = True
        template_obj.save()
    else:
        # No id (a genuinely new save). Fall back to updating a same-named row
        # so re-saving "Default" keeps updating the one default.
        template_obj = CustomTemplates.objects.filter(
            template_name=name, professor=teacher
        ).first()
        if template_obj:
            template_obj.template = content
            if make_default:
                template_obj.is_default = True
            template_obj.save()
        else:
            template_obj = CustomTemplates.objects.create(
                template_name=name,
                template=content,
                professor=teacher,
                is_default=make_default,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.TemplateEditByIdTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "fix(templates): edit by id so renaming updates in place"
```

---

## Task 2: Delete a template

**Files:**
- Modify: `home/views.py` (add `delete_template` near `duplicate_template`, ~line 1700)
- Modify: `home/urls.py` (add route after the `duplicateTemplate` line)
- Test: `home/tests.py` (new class `DeleteTemplateTests`)

- [ ] **Step 1: Write the failing test**

```python
class DeleteTemplateTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            name="Prof G", unique_id="T-G", email="g@example.com", department=self.dept,
        )
        self.other = TeacherInfo.objects.create(
            name="Prof H", unique_id="T-H", email="h@example.com", department=self.dept,
        )
        login_as_teacher(self.client, self.teacher)

    def test_deletes_own_template(self):
        tpl = CustomTemplates.objects.create(
            template_name="Junk (copy) 3", template="x", professor=self.teacher,
        )
        resp = self.client.post("/deleteTemplate", {"template_id": tpl.pk})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(CustomTemplates.objects.filter(pk=tpl.pk).exists())

    def test_cannot_delete_another_teachers_template(self):
        theirs = CustomTemplates.objects.create(
            template_name="Theirs", template="x", professor=self.other,
        )
        resp = self.client.post("/deleteTemplate", {"template_id": theirs.pk})
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(CustomTemplates.objects.filter(pk=theirs.pk).exists())

    def test_cannot_delete_system_template(self):
        system = CustomTemplates.objects.filter(is_system=True).first()
        resp = self.client.post("/deleteTemplate", {"template_id": system.pk})
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(CustomTemplates.objects.filter(pk=system.pk).exists())

    def test_get_is_rejected(self):
        resp = self.client.get("/deleteTemplate")
        self.assertEqual(resp.status_code, 302)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.DeleteTemplateTests -v 2`
Expected: FAIL — `/deleteTemplate` does not resolve (404 from URL resolver / NoReverseMatch), tests error out.

- [ ] **Step 3: Add the view**

In `home/views.py`, after `duplicate_template` (ends ~line 1699), add:

```python
def delete_template(request):
    """Delete one of the professor's own templates (never a system template)."""
    if request.method != "POST":
        return redirect("/makeTemplate")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    # Own templates only: a pk that is not this teacher's (including any shared
    # system row) is a 404, not a silent no-op.
    template_obj = get_object_or_404(
        CustomTemplates, pk=request.POST.get("template_id") or 0, professor=teacher
    )
    name = template_obj.template_name or "Untitled"
    template_obj.delete()
    messages.success(request, f'Deleted "{name}".')
    return redirect("/makeTemplate")
```

- [ ] **Step 4: Add the URL**

In `home/urls.py`, after the `duplicateTemplate` line (line 52), add:

```python
    path('deleteTemplate', views.delete_template, name='deleteTemplate'),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test home.tests.DeleteTemplateTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/urls.py home/tests.py
git commit -m "feat(templates): delete own templates"
```

---

## Task 3: Set default template

**Files:**
- Modify: `home/views.py` (add `set_default_template` after `delete_template`)
- Modify: `home/urls.py` (add route)
- Test: `home/tests.py` (new class `SetDefaultTemplateTests`)

- [ ] **Step 1: Write the failing test**

```python
class SetDefaultTemplateTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            name="Prof I", unique_id="T-I", email="i@example.com", department=self.dept,
        )
        self.other = TeacherInfo.objects.create(
            name="Prof J", unique_id="T-J", email="j@example.com", department=self.dept,
        )
        login_as_teacher(self.client, self.teacher)

    def test_setting_default_clears_the_previous_default(self):
        a = CustomTemplates.objects.create(
            template_name="A", professor=self.teacher, is_default=True,
        )
        b = CustomTemplates.objects.create(
            template_name="B", professor=self.teacher, is_default=False,
        )
        resp = self.client.post("/setDefaultTemplate", {"template_id": b.pk})
        self.assertEqual(resp.status_code, 302)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertFalse(a.is_default)
        self.assertTrue(b.is_default)

    def test_cannot_set_another_teachers_template_as_default(self):
        theirs = CustomTemplates.objects.create(
            template_name="Theirs", professor=self.other,
        )
        resp = self.client.post("/setDefaultTemplate", {"template_id": theirs.pk})
        self.assertEqual(resp.status_code, 404)
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_default)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.SetDefaultTemplateTests -v 2`
Expected: FAIL — `/setDefaultTemplate` does not resolve.

- [ ] **Step 3: Add the view**

In `home/views.py`, after `delete_template`, add:

```python
def set_default_template(request):
    """Mark one of the professor's own templates as their default."""
    if request.method != "POST":
        return redirect("/makeTemplate")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    template_obj = get_object_or_404(
        CustomTemplates, pk=request.POST.get("template_id") or 0, professor=teacher
    )
    # Exactly one default per professor: clear the others, then set this one.
    CustomTemplates.objects.filter(professor=teacher, is_default=True).update(
        is_default=False
    )
    template_obj.is_default = True
    template_obj.save(update_fields=["is_default"])
    messages.success(
        request, f'"{template_obj.template_name}" is now your default template.'
    )
    return redirect("/makeTemplate")
```

- [ ] **Step 4: Add the URL**

In `home/urls.py`, after the `deleteTemplate` line, add:

```python
    path('setDefaultTemplate', views.set_default_template, name='setDefaultTemplate'),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test home.tests.SetDefaultTemplateTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/urls.py home/tests.py
git commit -m "feat(templates): set a default template"
```

---

## Task 4: Visible template list + accurate palette (customTemplate.html)

**Files:**
- Modify: `templates/customTemplate.html`
- Test: `home/tests.py` (new class `MakeTemplatePageTests`)

- [ ] **Step 1: Write the failing test**

```python
class MakeTemplatePageTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            name="Prof K", unique_id="T-K", email="k@example.com", department=self.dept,
        )
        login_as_teacher(self.client, self.teacher)

    def test_own_templates_listed_with_actions(self):
        CustomTemplates.objects.create(
            template_name="My Letter", template="x", professor=self.teacher,
        )
        resp = self.client.get("/makeTemplate")
        self.assertContains(resp, "My Letter")
        self.assertContains(resp, "/deleteTemplate")
        self.assertContains(resp, "/setDefaultTemplate")

    def test_palette_uses_real_context_variable(self):
        resp = self.client.get("/makeTemplate")
        # The real render context exposes app.name; the old stale palette did not.
        self.assertContains(resp, "app.name")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.MakeTemplatePageTests -v 2`
Expected: FAIL — page has no `/deleteTemplate` / `/setDefaultTemplate` forms and no `app.name` in the palette.

- [ ] **Step 3: Add a visible template list**

In `templates/customTemplate.html`, replace the "Existing Templates" dropdown block (the `{% if templates and templates.count > 0 %}` … `{% endif %}` at lines 238-256) with a visible list **and** keep a hidden `template_id` on the save form. Insert this list block, and add a hidden input inside the existing `<form action="/getTemplate" ...>`:

```html
      {% if templates and templates.count > 0 %}
      <div class="my-templates" style="text-align:left; margin: 12px 0 20px;">
        <span class="details">Your templates:</span>
        <ul style="list-style:none; padding:0; margin:8px 0;">
          {% for tmp in templates %}
          <li style="display:flex; align-items:center; gap:10px; padding:8px 10px; border:1px solid #e4e3dc; border-radius:8px; margin-bottom:6px;">
            <strong style="flex:1">{{ tmp.template_name }}{% if tmp.is_default %} <em style="color:#2f9e44">(default)</em>{% endif %}</strong>
            <button type="submit" class="btn btn-secondary"
                    formaction="/getTemplate" formmethod="get"
                    name="edit" value="{{ tmp.pk }}"
                    onclick="loadTemplateIntoEditor({{ tmp.pk }}); return false;">Edit</button>
            <form action="/setDefaultTemplate" method="post" style="display:inline">
              {% csrf_token %}
              <input type="hidden" name="template_id" value="{{ tmp.pk }}">
              <button type="submit" class="btn btn-secondary">Set default</button>
            </form>
            <form action="/deleteTemplate" method="post" style="display:inline"
                  onsubmit="return confirm('Delete &quot;{{ tmp.template_name|escapejs }}&quot;?');">
              {% csrf_token %}
              <input type="hidden" name="template_id" value="{{ tmp.pk }}">
              <button type="submit" class="btn btn-secondary">Delete</button>
            </form>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% endif %}
```

Inside the `<form action="/getTemplate" method="post">` (after `{% csrf_token %}`, near line 235), add the hidden id the edit flow needs:

```html
      <input type="hidden" name="template_id" id="templateId" value="{{ template.pk|default:'' }}">
```

- [ ] **Step 4: Wire the Edit button to load a template into the editor**

Replace the old dropdown `change` handler (the `DOMContentLoaded` block at lines 195-213 that referenced `existing_templates`) with a hidden data store and a loader. Store each template's name/content in `data-` attributes on hidden inputs — Django autoescaping encodes attributes correctly, matching the approach this file already documents for the old dropdown at lines 244-249. Add near the other scripts:

```html
<div id="tpl-store" style="display:none">
  {% for tmp in templates %}
  <input type="hidden" class="tpl-row"
         data-id="{{ tmp.pk }}"
         data-name="{{ tmp.template_name }}"
         data-content="{{ tmp.template }}"
         data-default="{{ tmp.is_default }}">
  {% endfor %}
</div>
<script>
  function loadTemplateIntoEditor(pk) {
    var row = document.querySelector('#tpl-store .tpl-row[data-id="' + pk + '"]');
    if (!row) { return; }
    document.getElementById('templateName').value = row.getAttribute('data-name');
    document.getElementById('templateId').value = pk;
    document.getElementById('is_default').checked =
      row.getAttribute('data-default') === 'True';
    var body = row.getAttribute('data-content');
    var ed = tinymce.get('editor');
    if (ed) { ed.setContent(body); }
    document.getElementById('templateName').scrollIntoView({behavior: 'smooth'});
  }
</script>
```

Then simplify the Edit button (remove the invalid `formaction`/`name` attributes) to just:

```html
            <button type="button" class="btn btn-secondary"
                    onclick="loadTemplateIntoEditor({{ tmp.pk }})">Edit</button>
```

- [ ] **Step 5: Fix the stale insert-field palette**

In the `placeholderItems` array (lines 34-62), replace the entries with the real context variables from `home/letters.py:build_letter_context`:

```javascript
      const placeholderItems = [
        { text: "Student Name", value: "{{ '{{' }} app.name }}" },
        { text: "First Name", value: "{{ '{{' }} firstname }}" },
        { text: "Program", value: "{{ '{{' }} app.std.program.program_name }}" },
        { text: "Department", value: "{{ '{{' }} app.std.department.dept_name }}" },
        { text: "Ranking Percentile", value: "{{ '{{' }} app.ranking_percentile }}" },
        { text: "Relationship", value: "{{ '{{' }} rel_desc }}" },
        { text: "Subjects Sentence", value: "{{ '{{' }} subjects_sentence }}" },
        { text: "Subject", value: "{{ '{{' }} subject }}" },
        { text: "GPA", value: "{{ '{{' }} academics.gpa }}" },
        { text: "Standout Quality", value: "{{ '{{' }} quality.quality }}" },
        { text: "Recommendation Strength", value: "{{ '{{' }} strength_phrase }}" },
        { text: "Teacher Name", value: "{{ '{{' }} teacher.name }}" },
        { text: "Teacher Email", value: "{{ '{{' }} teacher.email }}" },
        { text: "Teacher Title", value: "{{ '{{' }} teacher.title }}" },
        { text: "Teacher Phone", value: "{{ '{{' }} teacher.phone }}" },
        { text: "Pronoun (he/she)", value: "{{ '{{' }} pronoun }}" },
        { text: "Pronoun (him/her)", value: "{{ '{{' }} pronoun_obj }}" },
        { text: "Pronoun (his/her)", value: "{{ '{{' }} pronoun_pos }}" },
        { text: "Today's Date", value: "{{ '{{' }} today }}" },
        { text: "Deadline", value: "{{ '{{' }} deadline }}" },
      ];
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python manage.py test home.tests.MakeTemplatePageTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the CSRF scanner to confirm the new forms are safe**

Run: `python manage.py test home.tests.CsrfProtectionTests -v 2`
Expected: PASS — the new `/deleteTemplate` and `/setDefaultTemplate` forms each contain `{% csrf_token %}`.

- [ ] **Step 8: Commit**

```bash
git add templates/customTemplate.html home/tests.py
git commit -m "feat(templates): visible template list with edit/delete/set-default and accurate palette"
```

---

## Task 5: Dashboard cleanup (Teacher.html)

**Files:**
- Modify: `templates/Teacher.html` (Manage-Templates button on top; remove inline template block at lines ~135-145)
- Test: `home/tests.py` (new class `DashboardLayoutTests`)

- [ ] **Step 1: Write the failing test**

```python
class DashboardLayoutTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            name="Prof L", unique_id="T-L", email="l@example.com", department=self.dept,
        )
        login_as_teacher(self.client, self.teacher)

    def test_dashboard_links_to_template_page(self):
        resp = self.client.get("/teacher")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "/makeTemplate")

    def test_dashboard_drops_inline_default_template_heading(self):
        resp = self.client.get("/teacher")
        self.assertNotContains(resp, "Current default template:")

    def test_dashboard_shows_recommended_section(self):
        resp = self.client.get("/teacher")
        self.assertContains(resp, "Students You Have Recommended")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.DashboardLayoutTests -v 2`
Expected: FAIL — `test_dashboard_drops_inline_default_template_heading` fails because "Current default template:" is still rendered.

- [ ] **Step 3: Move the Manage-Templates button to the top**

In `templates/Teacher.html`, just after the `<h1 ...> Requests: ... Refresh</h1>` line (line 7), add:

```html
<div class="container-fluid" style="text-align:center; margin: 8px 0 20px;">
  <a href="/makeTemplate" class="btn btn-primary">Manage Templates</a>
</div>
```

- [ ] **Step 4: Remove the inline template block**

Delete the block at lines ~135-145 (the `<!-- Create Template Button -->` container through the `<a href="/makeTemplate" ...>Create / Edit Templates</a>`):

```html
<!-- Create Template Button -->
<div class="container-fluid mt-4">
  {% comment %} display current default template if exists (provided by view) {% endcomment %}
  {% if default_template %}
  <h4>Current default template: <em>{{ default_template.template_name }}</em></h4>
  {% else %}
  <h4>No default template yet. Duplicate a starter template to get going.</h4>
  {% endif %}
  <h2>Manage Templates:</h2>
  <a href="/makeTemplate" class="btn btn-primary">Create / Edit Templates</a>
```

Leave the `<script>` that follows (starting at the `//table heading` comment) intact — only the template-management markup above it is removed. Ensure any now-unbalanced closing `</div>` is reconciled so the page's tags stay balanced.

- [ ] **Step 5: Give Pending and Recommended clear section headers**

The Recommended heading already exists (`<h1>Students You Have Recommended ({{ generated_count }}):</h1>`, line 84). Confirm the Pending heading reads clearly ("Requests:" at line 7). No context change is needed — `student_list` (pending) and `all_students` / `generated_count` (recommended) already come from `build_teacher_dashboard_context`, and filters already apply to both.

- [ ] **Step 6: Run test to verify it passes**

Run: `python manage.py test home.tests.DashboardLayoutTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add templates/Teacher.html home/tests.py
git commit -m "refactor(dashboard): move template management to its own button, drop inline block"
```

---

## Task 6: One-off junk cleanup command

**Files:**
- Create: `home/management/__init__.py` (empty)
- Create: `home/management/commands/__init__.py` (empty)
- Create: `home/management/commands/prune_template_copies.py`
- Test: `home/tests.py` (new class `PruneTemplateCopiesTests`)

- [ ] **Step 1: Write the failing test**

```python
class PruneTemplateCopiesTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            name="Prof M", unique_id="T-M", email="m@example.com", department=self.dept,
        )

    def test_commit_removes_copy_rows_keeps_originals(self):
        from django.core.management import call_command
        keep = CustomTemplates.objects.create(
            template_name="Default", professor=self.teacher, is_default=True,
        )
        j1 = CustomTemplates.objects.create(
            template_name="Formal / Academic (copy)", professor=self.teacher,
        )
        j2 = CustomTemplates.objects.create(
            template_name="Formal / Academic (copy) 3", professor=self.teacher,
        )
        call_command("prune_template_copies", "--commit")
        self.assertTrue(CustomTemplates.objects.filter(pk=keep.pk).exists())
        self.assertFalse(CustomTemplates.objects.filter(pk=j1.pk).exists())
        self.assertFalse(CustomTemplates.objects.filter(pk=j2.pk).exists())

    def test_dry_run_deletes_nothing(self):
        from django.core.management import call_command
        j1 = CustomTemplates.objects.create(
            template_name="General Purpose (copy) 5", professor=self.teacher,
        )
        call_command("prune_template_copies")
        self.assertTrue(CustomTemplates.objects.filter(pk=j1.pk).exists())

    def test_system_templates_are_never_touched(self):
        from django.core.management import call_command
        system_before = CustomTemplates.objects.filter(is_system=True).count()
        call_command("prune_template_copies", "--commit")
        self.assertEqual(
            CustomTemplates.objects.filter(is_system=True).count(), system_before
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.PruneTemplateCopiesTests -v 2`
Expected: FAIL — `Unknown command: 'prune_template_copies'`.

- [ ] **Step 3: Create the package files**

```bash
mkdir -p home/management/commands
touch home/management/__init__.py home/management/commands/__init__.py
```

- [ ] **Step 4: Write the command**

Create `home/management/commands/prune_template_copies.py`:

```python
"""Delete auto-generated '(copy)' template rows left behind by repeated
Duplicate clicks. Owned templates only; system templates are never touched.

Dry run by default; pass --commit to actually delete.
"""
import re

from django.core.management.base import BaseCommand

from home.models import CustomTemplates

# Matches names ending in " (copy)" or " (copy) 7", the exact shapes
# duplicate_template produces.
COPY_RE = re.compile(r" \(copy\)( \d+)?$")


class Command(BaseCommand):
    help = "Prune owned '(copy)' template duplicates. Dry run unless --commit."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually delete the rows (default: dry run).",
        )

    def handle(self, *args, **options):
        owned = CustomTemplates.objects.filter(professor__isnull=False)
        victims = [
            t for t in owned
            if t.template_name and COPY_RE.search(t.template_name)
        ]
        for t in victims:
            verb = "DELETE" if options["commit"] else "would delete"
            self.stdout.write(f"{verb}: [prof {t.professor_id}] {t.template_name}")

        if options["commit"]:
            count = CustomTemplates.objects.filter(
                pk__in=[t.pk for t in victims]
            ).delete()[0]
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} copy templates."))
        else:
            self.stdout.write(
                f"Dry run: {len(victims)} rows would be deleted. Re-run with --commit."
            )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test home.tests.PruneTemplateCopiesTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 6: Preview against the real DB, then clean up (with the user watching)**

Run the dry run first and show the output:

```bash
python manage.py prune_template_copies
```

Expected: lists the ~20 `(copy) N` rows for professor 3. After the user confirms the list:

```bash
python manage.py prune_template_copies --commit
```

- [ ] **Step 7: Commit the command (not the DB change)**

```bash
git add home/management home/tests.py
git commit -m "chore(templates): add prune_template_copies cleanup command"
```

Note: `db.sqlite3` is committed in this repo. Committing the pruned DB is a separate, explicit decision — confirm with the user before `git add db.sqlite3`.

---

## Task 7: Full-suite verification

- [ ] **Step 1: Run the whole suite**

Run: `python manage.py test home -v 1`
Expected: `OK` — all ~342 existing tests plus the ~17 new ones pass, no regressions. (Per the project rule, the full suite runs once, here at the end.)

- [ ] **Step 2: Manual smoke test**

Run: `python manage.py runserver`, log in as a teacher, and confirm: template list shows with Edit/Delete/Set-default; renaming does not create a duplicate; Duplicate adds a visible row; the dashboard has a Manage-Templates button on top and no inline template block.

---

## Self-Review Notes

- **Spec coverage:** edit-by-id (Task 1), delete (Task 2), set-default (Task 3), visible list + accurate palette (Task 4), dashboard sections + button + remove inline block (Task 5), junk cleanup (Task 6). All spec sections mapped.
- **Non-goals respected:** TinyMCE stays; no chip editor, preview, upload, or schema change here.
- **Type/name consistency:** view names `delete_template` / `set_default_template`; URL names `deleteTemplate` / `setDefaultTemplate`; hidden field `template_id`; JS loader `loadTemplateIntoEditor`. Used consistently across tasks.
