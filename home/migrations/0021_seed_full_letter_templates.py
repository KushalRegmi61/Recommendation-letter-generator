from django.db import migrations

# Two richer starter templates that pull in as many of the intake fields as
# possible, so a generated letter reads like a real, fully-argued reference.
# Constraints (enforced by SeededSystemTemplateTests): ASCII only, one prose
# paragraph per source line, every optional field guarded (no "None" / no
# doubled spaces on a sparse application), and only past-tense / noun-phrase
# constructions after {{ pronoun }} so unset-gender "They" stays grammatical.

COMPREHENSIVE = """LETTER OF RECOMMENDATION

Institute of Engineering, Tribhuvan University
Pulchowk Campus, Lalitpur, Nepal

Date: {{ today }}

To Whom It May Concern,

I am pleased to recommend {{ app.name }}{% if app.std.program.program_name %}, a student of {{ app.std.program.program_name }}{% endif %}{% if app.std.department.dept_name %} in the Department of {{ app.std.department.dept_name }}{% endif %} at the Institute of Engineering, Pulchowk Campus, Tribhuvan University{% if university and university.program_applied %}, for admission to the {{ university.program_applied }} program{% elif app.applied_level %}, for admission to {{ app.applied_level }}-level study{% endif %}{% if university and university.uni_name %} at {{ university.uni_name }}{% endif %}.

I have known {{ app.name }}{% if app.years_known %} for {{ app.years_known }}{% endif %} in my capacity as {{ pronoun_pos|lower }} {{ rel_desc }}{% if subjects_sentence %}, having taught {{ pronoun_obj|lower }} in {{ subjects_sentence }}{% endif %}. Over this period I closely observed {{ pronoun_pos|lower }} academic performance, technical ability, and overall growth as a student.
{%- if academics and (academics.gpa or academics.final_percentage) %}

{{ pronoun }} maintained {% if academics.gpa %}a cumulative GPA of {{ academics.gpa }}{% else %}a final score of {{ academics.final_percentage }} percent{% endif %}{% if academics.tentative_ranking %}, with a tentative standing of {{ academics.tentative_ranking }} in {{ pronoun_pos|lower }} cohort{% endif %}{% if app.ranking_percentile %} (placing {{ pronoun_obj|lower }} within the {{ app.ranking_percentile }} of the class){% endif %}.
{%- endif %}
{%- if subjects_sentence %}

{{ pronoun }} showed particular competence in {{ subjects_sentence }}, and applied fundamental concepts to practical problems with confidence.
{%- endif %}
{%- if project and project.supervised_project %}

As {{ pronoun_pos|lower }} {{ rel_desc }}, I observed {{ pronoun_pos|lower }} research and project work firsthand. {{ pronoun_pos }} major work, titled "{{ project.supervised_project }}", required {{ pronoun_obj|lower }} to define a problem, review the literature, design a methodology, implement a solution, and evaluate the results critically.
{%- endif %}
{%- if project and project.final_project %}

{{ pronoun }} also carried out further project work on {{ project.final_project }}.
{%- endif %}
{%- if app.is_paper and paper and paper.paper_title %}

{{ pronoun }} contributed to research through the paper titled "{{ paper.paper_title }}"{% if paper.paper_link %}, available at {{ paper.paper_link }}{% endif %}, which reflects {{ pronoun_pos|lower }} ability to communicate technical findings.
{%- endif %}
{%- if app.strong_points %}

Among {{ pronoun_pos|lower }} notable strengths are the following: {{ app.strong_points }}
{%- endif %}
{%- if quality and quality.quality %}

In my assessment, {{ app.name }} is {{ quality.quality }}.
{%- endif %}
{%- if quality and quality.presentation %}

{{ pronoun_pos }} presentation and communication skills are {{ quality.presentation }}.
{%- endif %}
{%- if quality and (quality.leadership or quality.hardworking or quality.teamwork or quality.social or quality.friendly) %}

These experiences reflect {{ pronoun_pos|lower }} qualities as a student, including{% if quality.leadership %} leadership,{% endif %}{% if quality.hardworking %} a strong work ethic,{% endif %}{% if quality.teamwork %} an ability to work in a team,{% endif %}{% if quality.social %} a collaborative nature,{% endif %}{% if quality.friendly %} and an approachable manner,{% endif %} developed over {{ pronoun_pos|lower }} time at the campus.
{%- endif %}
{%- if app.professional_experience %}

Beyond coursework, {{ pronoun|lower }} gained practical experience, including the following: {{ app.professional_experience }}
{%- endif %}
{%- if quality and quality.extracirricular %}

{{ pronoun }} remained active beyond academics, including the following: {{ quality.extracirricular }}
{%- endif %}
{%- if app.weak_points %}

Like any developing student, {{ app.name }} has an area to strengthen further, noted as follows: {{ app.weak_points }}

I have found {{ pronoun_obj|lower }} receptive to feedback and steady in working toward improvement.
{%- endif %}
{%- if app.prof_anecdote %}

{{ app.prof_anecdote }}
{%- endif %}

Based on my experience {% if rel_desc == 'thesis supervisor' %}supervising{% else %}working with{% endif %} {{ app.name }}, I consider {{ pronoun_obj|lower }} to be {% if quality and quality.recommendation_strength == 'top5' %}an outstanding{% elif quality and quality.recommendation_strength == 'top10' %}a very strong{% elif quality and quality.recommendation_strength == 'outstanding' %}an outstanding{% else %}a strong{% endif %} candidate{% if university and university.program_applied %} for the {{ university.program_applied }} program{% endif %}. I {% if quality and quality.recommend %}{{ quality.recommend }}{% else %}strongly{% endif %} recommend {{ app.name }} for admission to your program, and I am confident {{ pronoun|lower }} will contribute meaningfully to your academic community.
{%- if deadline %}

I understand the application deadline is {{ deadline }}.
{%- endif %}

Please feel free to contact me should you require any further information regarding {{ pronoun_pos|lower }} qualifications.

Sincerely,

{{ teacher.name or '' }}
{%- if teacher.designation %}
{{ teacher.designation }}
{%- elif teacher.title %}
{{ teacher.title }}
{%- endif %}
{%- if teacher.department and teacher.department.dept_name %}
Department of {{ teacher.department.dept_name }}
{%- endif %}
Institute of Engineering, Tribhuvan University
Pulchowk Campus, Lalitpur, Nepal
{%- if teacher.email %}
Email: {{ teacher.email }}
{%- endif %}
{%- if teacher.phone %}
Contact: {{ teacher.phone }}
{%- endif %}
"""

GRADUATE = """{{ today }}

{% if university and university.uni_name %}Admissions Committee
{% if university.program_applied %}{{ university.program_applied }} Program
{% endif %}{{ university.uni_name }}{% if university.country %}
{{ university.country }}{% endif %}
{% else %}Admissions Committee
{% endif %}
Re: Recommendation for {{ app.name }}

Dear Members of the Admissions Committee,

I am writing to offer my strong support for {{ app.name }}'s application{% if university and university.program_applied %} to the {{ university.program_applied }} program{% endif %}{% if university and university.uni_name %} at {{ university.uni_name }}{% endif %}{% if app.applied_level %} for {{ app.applied_level }}-level study{% endif %}. {{ pronoun }} completed {{ pronoun_pos|lower }} undergraduate studies{% if app.std.program.program_name %} in {{ app.std.program.program_name }}{% endif %}{% if app.std.department.dept_name %}, Department of {{ app.std.department.dept_name }},{% endif %} at the Institute of Engineering, Pulchowk Campus, Tribhuvan University, where I served as {{ pronoun_pos|lower }} {{ rel_desc }}.
{%- if app.years_known %}

I have known {{ app.name }} for {{ app.years_known }}{% if subjects_sentence %}, including through the courses {{ subjects_sentence }}{% endif %}, and can speak to {{ pronoun_pos|lower }} preparation for graduate study with confidence.
{%- endif %}
{%- if academics and (academics.gpa or academics.final_percentage) %}

Academically, {{ pronoun|lower }} performed strongly, with {% if academics.gpa %}a GPA of {{ academics.gpa }}{% else %}a final score of {{ academics.final_percentage }} percent{% endif %}{% if academics.tentative_ranking %} and a standing of {{ academics.tentative_ranking }}{% if app.class_size %} out of {{ app.class_size }}{% endif %}{% endif %}.
{%- endif %}
{%- if project and project.supervised_project %}

For {{ pronoun_pos|lower }} thesis, titled "{{ project.supervised_project }}", {{ pronoun|lower }} formulated the problem, surveyed prior work, developed a methodology, and evaluated the outcomes with rigour.
{%- endif %}
{%- if project and project.final_project %}

{{ pronoun }} undertook additional project work on {{ project.final_project }}.
{%- endif %}
{%- if app.is_paper and paper and paper.paper_title %}

{{ pronoun }} authored the paper "{{ paper.paper_title }}"{% if paper.paper_link %} ({{ paper.paper_link }}){% endif %}, which demonstrates {{ pronoun_pos|lower }} readiness for independent research.
{%- endif %}
{%- if app.strong_points %}

I would especially highlight the following strengths: {{ app.strong_points }}
{%- endif %}
{%- if app.professional_experience %}

{{ pronoun }} broadened {{ pronoun_pos|lower }} practical exposure through the following: {{ app.professional_experience }}
{%- endif %}
{%- if quality and quality.extracirricular %}

Outside the curriculum, {{ pronoun|lower }} took part in the following: {{ quality.extracirricular }}
{%- endif %}
{%- if app.weak_points %}

In the interest of a balanced assessment, an area {{ app.name }} continues to develop is noted as follows: {{ app.weak_points }}
{%- endif %}

On the strength of {{ pronoun_pos|lower }} record, I consider {{ app.name }} {% if quality and quality.recommendation_strength == 'top5' %}an outstanding{% elif quality and quality.recommendation_strength == 'top10' %}a very strong{% elif quality and quality.recommendation_strength == 'outstanding' %}an outstanding{% else %}a strong{% endif %} candidate for graduate study, and I recommend {{ pronoun_obj|lower }} {{ strength_phrase }}.
{%- if deadline %}

I note that the application deadline is {{ deadline }}, and I am glad to provide any further information the committee may require.
{%- endif %}

Sincerely,

{{ teacher.name or '' }}
{%- if teacher.designation %}
{{ teacher.designation }}
{%- elif teacher.title %}
{{ teacher.title }}
{%- endif %}
{%- if teacher.department and teacher.department.dept_name %}
Department of {{ teacher.department.dept_name }}
{%- endif %}
Institute of Engineering, Tribhuvan University
Pulchowk Campus, Lalitpur, Nepal
{%- if teacher.email %}
Email: {{ teacher.email }}
{%- endif %}
{%- if teacher.phone %}
Contact: {{ teacher.phone }}
{%- endif %}
"""

SEEDS = (
    ("Comprehensive Reference (Pulchowk)", COMPREHENSIVE),
    ("Graduate Admission (Detailed)", GRADUATE),
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
        ("home", "0020_seed_pulchowk_departments"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
