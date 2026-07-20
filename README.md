# Recommendation Letter Generator

A Django web application that lets students request Letters of Recommendation (LOR)
from their professors, and lets professors review those requests and generate
personalized recommendation letters (PDF/DOCX) from customizable templates.

Built for Tribhuvan University, IOE (BCT).

---

## Tech stack

- **Python** 3.10+ (developed/tested on 3.12)
- **Django** 5.1
- **Database:** SQLite (`db.sqlite3`, committed — no external DB to provision)
- **Letter generation:** Jinja2 templates → PDF (`fpdf`) / DOCX (`python-docx`)
- **Email:** Gmail SMTP (OTP + notifications)

---

## Prerequisites

- Python 3.10 or newer with `venv`
- `git`

There is **no Node/npm build step**. The old instructions mentioned `npm install`, but
there is no `package.json`; the `node_modules/` folder only vendors `bootstrap-icons`.

---

## Setup & run

### 1. Clone

```bash
git clone https://github.com/KushalRegmi61/Recommendation-letter-generator.git
cd Recommendation-letter-generator
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows (PowerShell)
./venv/Scripts/Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> **Heads-up — `requirements.txt` encoding.** This file is saved as **UTF-16**. On most
> systems `pip` reads it fine, but if you get an encoding error (garbled characters, or
> `UnicodeDecodeError`), convert it to UTF-8 first:
>
> ```bash
> python -c "open('requirements.utf8.txt','w',encoding='utf-8').write(open('requirements.txt',encoding='utf-16').read())"
> python -m pip install -r requirements.utf8.txt
> rm requirements.utf8.txt
> ```

### 4. Apply migrations

```bash
python manage.py migrate
```

(The repo ships a populated `db.sqlite3`; migrations are already applied, but run this to
be safe and after pulling changes.)

### 5. Create an admin (superuser)

```bash
python manage.py createsuperuser
```

> **Important — teacher/superuser naming.** Teachers log in through Django's `User` model,
> and the app recovers a teacher's ID from the user's full name. When you create a superuser
> that is also a teacher, set the **full name** to `Full Name/<unique_id>`, where `<unique_id>`
> matches the `TeacherInfo.unique_id` you create in the admin panel. Without the `/<unique_id>`
> suffix, the teacher views will not resolve.

### 6. Run the development server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser. The Django admin is at
http://127.0.0.1:8000/admin/.

---

## First-time data setup (admin)

Log in to the admin panel (`/admin/`) and create the reference data the app needs:

1. **Programs** — e.g. `BE`
2. **Departments** — e.g. `BCT`
3. **Teacher info** — each professor's profile (name, `unique_id`, email, department, etc.)
4. Create the professor's Django user with full name `Name/<unique_id>` (see step 5 above).

---

## Using the app

### Student
1. **Register**, then **log in**.
2. Fill the **LOR request form** — personal details, program(s) applied for, target
   **universities (repeatable: name + country + deadline)**, relationship with the professor,
   academics (percentage, ranking), strong/weak points, and upload transcript / CV / photo.
3. Submit the request to a professor. This creates a **pending application**; duplicate
   pending requests to the same professor are prevented.

### Teacher / Professor
1. Ask the admin to create your `TeacherInfo` profile and matching superuser.
2. **Log in** and view incoming requests and the students you have already recommended.
3. **Find a student** with the search box — it matches name, roll number, or email. Multiple
   words all have to match, so `ramesh 080bct` narrows to one person.
4. **Filter** by Department / Country / College. Each box suggests the values that appear in your
   own applications, but you can also type a partial value (`us` matches USA). Search and filters
   combine, and both apply to the pending list *and* the recommended list — so you can answer
   "whom have I recommended who applied to the USA". **Clear** resets everything.
5. The recommended-students table shows **when** each letter was generated, **which template**
   produced it, and a **Re-download** link for the stored file.
6. **Templates.** Open **Create / Edit Templates**. Three starter templates ship with the app
   (*Formal / Academic*, *Research / Graduate School*, *General Purpose*) — press **Duplicate**
   on one to get your own editable copy, then edit and save it. Tick *default* to make a
   template the one pre-selected for every new letter.
7. **Generate.** Pick a template on the letter form, preview it, edit the text inline if you
   want, then download as PDF or DOCX. The download is what gets stored and listed on your
   dashboard.

### Admin
- Manage programs, departments, teachers, templates, and all application data via `/admin/`.

> **Note on PDF export.** Letters are rendered with an embedded DejaVu Sans subset
> (`static/fonts/dejavu/DejaVuSans.ttf`), so accented Latin, Greek and Cyrillic text — along with
> em dashes and curly quotes — exports correctly. **Devanagari is not covered by this font**, and
> a Devanagari name will come out as blank/tofu boxes rather than readable text. Supporting it
> needs both a Devanagari-capable TTF added to `static/fonts/` with `_UNICODE_FONT_PATH` in
> `home/letters.py` pointed at it, *and* a PDF engine that performs complex text shaping — `fpdf`
> 1.7.2 does not reorder matras or form conjuncts, so a Devanagari font alone is not sufficient.
> If the font file is missing entirely the exporter falls back to Latin-1 and replaces
> unsupported characters with `?`. The DOCX export has never had this limitation and renders
> any script correctly.

---

## Running tests

```bash
python manage.py test home                          # run the app's test suite (228 tests)
python manage.py test home.tests.ModelFieldTests    # a single test class
```

Some tests deliberately exercise 404 paths, so `[WARNING] Not Found: /download_generated/` lines
in the output are expected, not failures. Look at the final `OK`.

---

## Email / SMTP

Email (OTP and notifications) uses Gmail SMTP configured in `auth/settings.py`. If you hit an
SMTP authentication error, generate a Gmail **App Password** for a valid account and set
`EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` in `auth/settings.py`.

> **Security note:** `auth/settings.py` currently contains a committed `SECRET_KEY`,
> `DEBUG = True`, `ALLOWED_HOSTS = ['*']`, and email credentials. Rotate these and move them
> to environment variables before deploying anywhere public.

---

## Project layout

```
auth/            Django project (settings, root urls, wsgi/asgi)
home/            Main app: models, views, urls, forms, migrations, tests
  intake.py      Student LOR-request form helpers (name composition, universities)
  filters.py     Professor dashboard filtering and student search
  dashboard.py   Single source of truth for the Teacher.html render context
  letters.py     Letter context, template selection, rendering, PDF/DOCX export
templates/       HTML templates (student/teacher/admin pages, letter templates)
static/          CSS, fonts, images
media/           Uploaded files (transcripts, CVs, photos, generated letters)
db.sqlite3       SQLite database (committed)
manage.py        Django management entry point
```
