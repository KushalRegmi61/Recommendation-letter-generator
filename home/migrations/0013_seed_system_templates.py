from django.db import migrations

FORMAL = """{{ today }}

To Whom It May Concern

Re: Letter of Recommendation for {{ app.name }}

It is my pleasure to recommend {{ app.name }}{% if app.std.program.program_name %}, a student of the {{ app.std.program.program_name }} program{% endif %}{% if app.std.department.dept_name %} in the Department of {{ app.std.department.dept_name }}{% endif %} at the Institute of Engineering, Pulchowk Campus, Tribhuvan University.

I have known {{ app.name }} as {{ pronoun_pos|lower }} {{ rel_desc }}{% if subjects_sentence %}, having taught {{ pronoun_obj|lower }} in {{ subjects_sentence }}{% endif %}.
{%- if academics and academics.gpa %}

{{ pronoun_pos }} cumulative GPA is {{ academics.gpa }}{% if app.ranking_percentile %}, placing {{ pronoun_obj|lower }} within the top {{ app.ranking_percentile }} percent of the cohort{% endif %}.
{%- endif %}
{%- if quality and quality.quality %}

Above all, I regard {{ pronoun_obj|lower }} as {{ quality.quality }}.
{%- endif %}
{%- if app.prof_anecdote %}

{{ app.prof_anecdote }}
{%- endif %}

I recommend {{ pronoun_obj|lower }} {{ strength_phrase }}.

Sincerely,
{{ teacher.name or '' }}
{{ teacher.email or '' }}
Institute of Engineering, Pulchowk Campus
"""

RESEARCH = """{{ today }}

{% if university and university.uni_name %}Admissions Committee
{% if university.program_applied %}{{ university.program_applied }} Program
{% endif %}{{ university.uni_name }}
{% else %}To Whom It May Concern
{% endif %}
Re: Graduate Application of {{ app.name }}

I write in strong support of {{ app.name }}'s application{% if university and university.program_applied %} to the {{ university.program_applied }} program{% endif %}{% if university and university.uni_name %} at {{ university.uni_name }}{% endif %}.

{{ pronoun }} completed {{ pronoun_pos|lower }} undergraduate studies{% if app.std.department.dept_name %} in {{ app.std.department.dept_name }}{% endif %} at the Institute of Engineering, Pulchowk Campus, where I served as {{ pronoun_pos|lower }} {{ rel_desc }}.
{%- if app.is_paper and paper and paper.paper_title %}

{{ pronoun }} authored "{{ paper.paper_title }}", which speaks directly to {{ pronoun_pos|lower }} readiness for independent research.
{%- endif %}
{%- if project and (project.final_project or project.supervised_project) %}

{{ pronoun }} also completed {% if project.final_project %}a final-year project on {{ project.final_project }}{% else %}project work under my supervision on {{ project.supervised_project }}{% endif %}.
{%- endif %}
{%- if academics and academics.gpa %}

Academically, {{ pronoun_pos|lower }} GPA stands at {{ academics.gpa }}{% if academics.tentative_ranking %}, ranked {{ academics.tentative_ranking }}{% if app.class_size %} of {{ app.class_size }}{% endif %}{% endif %}.
{%- endif %}
{%- if deadline %}

I understand the application deadline is {{ deadline }}.
{%- endif %}

I recommend {{ pronoun_obj|lower }} for admission {{ strength_phrase }}.

Sincerely,
{{ teacher.name or '' }}
{{ teacher.email or '' }}
"""

GENERAL = """{{ today }}

To Whom It May Concern

I am glad to recommend {{ app.name }}, whom I have known as {{ pronoun_pos|lower }} {{ rel_desc }} at the Institute of Engineering, Pulchowk Campus, Tribhuvan University.
{%- if subjects_sentence %}

I taught {{ pronoun_obj|lower }} in {{ subjects_sentence }}.
{%- endif %}
{%- if academics and academics.gpa %}

{{ pronoun_pos }} cumulative GPA is {{ academics.gpa }}.
{%- endif %}
{%- if quality and (quality.leadership or quality.hardworking or quality.teamwork or quality.friendly) %}

{% if quality.leadership %}{{ pronoun }} demonstrated genuine leadership. {% endif %}{% if quality.hardworking %}{{ pronoun }} worked consistently hard. {% endif %}{% if quality.teamwork %}{{ pronoun }} collaborated well within a team. {% endif %}{% if quality.friendly %}{{ pronoun }} remained approachable and well liked by peers.{% endif %}
{%- endif %}
{%- if quality and quality.recommend %}

{{ quality.recommend }}
{%- endif %}

I recommend {{ pronoun_obj|lower }} {{ strength_phrase }}.

Sincerely,
{{ teacher.name or '' }}
{{ teacher.email or '' }}
"""

SEEDS = (
    ("Formal / Academic", FORMAL),
    ("Research / Graduate School", RESEARCH),
    ("General Purpose", GENERAL),
)


def seed(apps, schema_editor):
    CustomTemplates = apps.get_model("home", "CustomTemplates")
    for name, body in SEEDS:
        CustomTemplates.objects.update_or_create(
            template_name=name,
            is_system=True,
            defaults={"template": body, "professor": None, "is_default": False},
        )


def unseed(apps, schema_editor):
    CustomTemplates = apps.get_model("home", "CustomTemplates")
    CustomTemplates.objects.filter(
        is_system=True, template_name__in=[name for name, _ in SEEDS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0012_system_templates"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
