import datetime
import os
from django.db import transaction
from django.db.models.fields import DateTimeField
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sessions.models import Session
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify

# check old password and new password
from django.contrib.auth.hashers import make_password, check_password

from django.contrib.auth.models import User
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from .models import *
from .forms import TeacherInfoForm
from home.identity import current_teacher, current_student, set_student_cookie
from django.contrib import messages
import random
import uuid
import json
from collections import OrderedDict


# imports from xhtml
from django.http import HttpResponse, FileResponse, Http404
from django.template.loader import get_template
#from xhtml2pdf import pisa


# serializers helps to convert queryset into json strings
from django.core import serializers

# sending email
from django.core.mail import send_mail

# to send mail to admin
from django.core.mail import mail_admins


# to create random number for OTP
from random import randint
# Create your views here.
#import os
#os.environ["SSL_CERT_FILE"] = r"C:\\Users\\lovel\\Desktop\\Recommendation-Letter-Generator\\venv\\Lib\\site-packages\\certifi\\cacert.pem"




def index(request):

    #if the user is logged in then index will not be their respective home page after login
    
    #check if the user is logged in or not
    if request.method == "GET":                                                     #if logged in 
        student = current_student(request)
        if student is not None:
            naam = student.username

            teachers = TeacherInfo.objects.filter(department=student.department)
            if Application.objects.filter(std__username=naam).exists():                 #std is foreign key for StudentLoginInfo
                appli = Application.objects.filter(std__username=naam)
            else:
                appli = {}
            response = render(
                        request,
                        "student_success.html",
                        {
                            "naam": student.username,
                            "roll": student.roll_number,
                            "letter": True,
                            'applications': appli
                        },
                    )
                    
            return response
                                         #if exist
        # if StudentLoginInfo.objects.filter(username__exact=naam).exists():
        #     student = StudentLoginInfo.objects.get(username__exact=naam)
        #     teachers = TeacherInfo.objects.filter(department=student.department)
        #     response =  render(                                                     #render student home page
        #             request,
        #             "Studentform1.html",
        #             {
        #                 "naam": student.username,
        #                 "teachers": teachers,
        #                 "roll": student.roll_number,
        #             },
        #         )
            # return response
        teacher = current_teacher(request)                   #if not student then might be teacher
        if teacher is not None:
                unique = teacher.unique_id                                          #teacher's unique id (see schema diagram)


                # generate teachers home page
                context = build_teacher_dashboard_context(unique, request.GET)
                return render(request, "Teacher.html", context)
        
    # if the request is not a GET request or user is not logged in , render index page
    return render(request, "index.html")
#now check studentLogin and teacherLogin


def gallery(request):
    return render(request, "gallery.html")


from io import BytesIO as bio
#import fs
from home.forms import StudentForm
from home.dashboard import build_teacher_dashboard_context
from home.letters import (
    available_templates, build_docx_bytes, build_pdf_bytes,
    render_letter, select_template, system_templates, visible_to,
)



import re
import logging

logger = logging.getLogger(__name__)


def send_mail_safely(subject, message, from_email, recipients, fail_message=None):
    """Send mail without letting an SMTP failure break the request.

    Mail is a side effect of registration, recovery and letter generation --
    never the point of them. A misconfigured mail server should not 500 a
    request that has already written to the database. Failures are logged so a
    broken configuration is discoverable rather than silent.
    """
    try:
        send_mail(subject, message, from_email, recipients, fail_silently=False)
        return True
    except Exception:
        logger.error(
            "%s (subject=%r, recipients=%r)",
            fail_message or "Failed to send mail",
            subject,
            recipients,
            exc_info=True,
        )
        return False


def mail_admins_safely(subject, message, fail_message=None):
    """``mail_admins`` counterpart to :func:`send_mail_safely`.

    ``mail_admins`` takes no recipient list -- it targets ``settings.ADMINS`` --
    so it cannot go through the helper above, but the failure policy is the same.
    """
    try:
        mail_admins(subject, message, fail_silently=False)
        return True
    except Exception:
        logger.error(
            "%s (subject=%r, recipients=ADMINS)",
            fail_message or "Failed to send mail to admins",
            subject,
            exc_info=True,
        )
        return False


def studentfinal(request, *args, **kwargs):
    """Serve a generated letter as PDF or DOCX for the professor who owns it.

    The dashboard's PDF/DOCX buttons used to redirect to legacy on-disk paths
    (``media/letter/<roll>_<prof>.pdf`` / ``media/docs/...``) that the current
    pipeline never writes -- ``download_letter`` stores letters in the
    ``generated_letter`` FileField instead -- so every click 404'd. We now render
    the letter from the application's template with the same helpers as
    ``download_letter`` and stream the bytes, scoped to the signed-in professor.
    """
    if request.method != "POST":
        return redirect("/teacher")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    # Own applications only: a roll that is not this professor's is a 404, never
    # another professor's letter.
    application = get_object_or_404(
        Application,
        std__roll_number=request.POST.get("roll"),
        professor__unique_id=teacher.unique_id,
    )

    template_obj = application.generated_template or select_template(application.professor)
    letter_text = render_letter(application, template_obj)
    if not letter_text.strip():
        # ``render_letter`` returns "" when the template fails to compile; refuse
        # rather than streaming a blank file.
        messages.error(request, "That letter could not be rendered. Check the template for errors.")
        return redirect("/teacher")

    safe_name = slugify(application.name) or "letter"
    if request.POST.get("id") == "docs":
        payload = build_docx_bytes(letter_text)
        content_type = (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )
        filename = f"Recommendation_{safe_name}.docx"
        disposition = "attachment"
    else:
        payload = build_pdf_bytes(letter_text)
        content_type = "application/pdf"
        filename = f"Recommendation_{safe_name}.pdf"
        disposition = "inline"

    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response

def registerStudent(request):
    departments = Department.objects.all().values()
    programs = Program.objects.all().values()
    context_dict = { "departments": departments , "programs": programs}
    
    if request.method == "GET":
        student = current_student(request)
        if student is not None:
            naam = student.username

            teachers = TeacherInfo.objects.filter(department=student.department)
            if Application.objects.filter(std__username=naam).exists():                 #std is foreign key for StudentLoginInfo
                appli = Application.objects.filter(std__username=naam)
            else:
                appli = {}
            response = render(
                        request,
                        "student_success.html",
                        {
                            "naam": student.username,
                            "roll": student.roll_number,
                            "letter": True,
                            'applications': appli
                        },
                    )
                    
            return response
       
        # if StudentLoginInfo.objects.filter(username__exact=naam).exists():
        #     student = StudentLoginInfo.objects.get(username__exact=naam)
        #     teachers = TeacherInfo.objects.filter(department=student.department)
        #     response =  render(
        #             request,
        #             "Studentform1.html",
        #             {
        #                 "naam": student.username,
        #                 "teachers": teachers,
        #                 "roll": student.roll_number,
        #             },
        #         )
        #     return response
        teacher = current_teacher(request)
        if teacher is not None:
                unique = teacher.unique_id
                context = build_teacher_dashboard_context(unique, request.GET)
                return render(request, "Teacher.html", context)
        
    if request.method == "POST":
        usern = request.POST.get("name")
        roll = request.POST.get("roll")
        dob = request.POST.get("dob")
        gender = request.POST.get("gender")
        Pass = request.POST.get("pass")
        confirmPass = request.POST.get("confirmPass")
        depart = request.POST.get("department")
        prog = request.POST.get("program")
        department = Department.objects.get(dept_name=depart)
        program = Program.objects.get(program_name=prog)
        
        if Pass != confirmPass:
            messages.error(request, "Passwords donot match")
            return render(request, "registerStudent.html", context=context_dict )
            
        try:
            if StudentLoginInfo.objects.filter(roll_number__exact=roll):
                messages.error(request, "Student Already Exists")
                return render(request, "registerStudent.html", context=context_dict )
            else:
                Student = StudentLoginInfo.objects.create(username=usern, 
                roll_number=roll, dob=dob, department=department, program=program, gender=gender, password=make_password(Pass))
                Student.save()
                messages.error(request, "Account Sucessfully Created")
                return render(request, "loginStudent.html")
        except Exception as e:
            messages.error(request, e)
            return render(request, "registerStudent.html", context=context_dict )
    return render(request, "registerStudent.html", context=context_dict )

def loginStudent(request):
    # after login /loginstudent url will also be a homepage

    #handles just after student is logged in
    if request.method == "GET":
        student = current_student(request)
        if student is not None:
            naam = student.username

            teachers = TeacherInfo.objects.filter(department=student.department)
            if Application.objects.filter(std__username=naam).exists():                 #std is foreign key for StudentLoginInfo
                appli = Application.objects.filter(std__username=naam)
            else:
                appli = {}
            response = render(
                        request,
                        "student_success.html",
                        {
                            "naam": student.username,
                            "roll": student.roll_number,
                            "letter": True,
                            'applications': appli
                        },
                    )
                    
            return response
        teacher = current_teacher(request)
        if teacher is not None:
                unique = teacher.unique_id
                context = build_teacher_dashboard_context(unique, request.GET)
                return render(request, "Teacher.html", context)
    
    # post request from loginStudent.html
    if request.method == "POST":
        naam = request.POST.get("username")
        Pass = request.POST.get("pass")
             # check if user is real
        if StudentLoginInfo.objects.filter(username__exact=naam).exists():
            student = StudentLoginInfo.objects.get(username__exact=naam)
            if not check_password(Pass, student.password):
                messages.error(request, "Sorry!  The Credentials doesn't match.")
                return render(request, "loginStudent.html")
            teachers = TeacherInfo.objects.filter(department=student.department)


            if Application.objects.filter(std__username=naam).exists():                 #std is foreign key for StudentLoginInfo
                appli = Application.objects.filter(std__username=naam)
            else:
                appli = {}
            response = render(
                        request,
                        "student_success.html",
                        {
                            "naam": student.username,
                            "roll": student.roll_number,
                            "letter": True,
                            'applications': appli
                        },
                    )

            set_student_cookie(response, student)
            return response

        else:
            messages.error(request, "Sorry!  The Credentials doesn't match.")
            return render(request, "loginStudent.html")
        
    
    return render(request, "loginStudent.html")
            # if Application.objects.filter(std__username=naam).exists():                 #std is foreign key for StudentLoginInfo
            #     appli = Application.objects.filter(std__username=naam)
            #     if appli[0].is_generated: 
            #         response = render(
            #             request,
            #             "student_success.html",
            #             {
            #                 "naam": student.username,
            #                 "roll": student.roll_number,
            #                 "letter": appli[0].is_generated,
            #                 'applications': appli
            #             },
            #         )
                    
            #     else:
            #         messages.error(request, "You are succesfully logged in.")
            #         response =  render(
            #             request,
            #             "Studentform1.html",
            #             {
            #                 "naam": student.username,
            #                 "teachers": teachers,
            #                 "roll": student.roll_number,
            #             },
            #         )

            # else:
            #     messages.error(request, "You are succesfully logged in.")
            #     response =  render(
            #         request,
            #         "Studentform1.html",
            #         {
            #             "naam": student.username,
            #             "teachers": teachers,
            #             "roll": student.roll_number,
            #         },
            #     )
                
    #         response.set_cookie('student', student)
    #         return response

    #     else:
    #         messages.error(request, "Sorry!  The Credentials doesn't match.")
    #         return render(request, "loginStudent.html")
        
    
    # return render(request, "loginStudent.html")
#now check studentform1.html 


@login_required(login_url="/loginTeacher")
def make_letter(request):
    if request.method == "POST":
        roll = request.POST.get("roll")
        # ``@login_required`` proves someone is signed in; this proves *which*
        # professor, so the letter is built from their own applications only.
        teacher_model = current_teacher(request)
        if teacher_model is None:
            return redirect("/loginTeacher")
        teacher_id = teacher_model.unique_id

        # Join through the ``std`` FK, not ``Application.name``: that field is
        # the free-text name typed on the application form and routinely differs
        # from the student's login username, which made this lookup miss rows
        # that were plainly there. The roll number is the student's PK.
        appli = Application.objects.get(
            std__roll_number=roll, professor__unique_id=teacher_id
        )

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


def _render_student_form(request, student, error=None):
    """Render the single-page student application form for ``student``."""
    teachers = TeacherInfo.objects.filter(department=student.department)
    return render(request, "Studentform1.html", {
        "naam": student.username,
        "roll": student.roll_number,
        "teachers": teachers,
        "error": error,
    })


def studentform1(request):
    """Single-page student recommendation-letter application.

    Personal details, universities, academics, files and qualities are all
    submitted together and written in one ``transaction.atomic()`` block, so
    there is no cross-page state and no Back button to lose data to.

    Identity is resolved from the signed session via ``current_student`` — any
    ``naam``/``roll`` in the request body is ignored, closing the impersonation
    gap the two-page intake had (a logged-in student could submit under another
    student's name).
    """
    student = current_student(request)
    if student is None:
        messages.error(request, "Please login first")
        return render(request, "loginStudent.html")

    if request.method != "POST":
        return _render_student_form(request, student)

    from home.intake import (
        parse_universities, save_universities, academics_present, compose_full_name,
    )

    # --- professor (must be one of the student's department) ---
    prof_id = (request.POST.get("prof") or "").split("|")[-1]
    prof = TeacherInfo.objects.filter(unique_id=prof_id).first()
    if prof is None:
        return _render_student_form(request, student, "Please select a professor.")

    # --- universities: every row needs a deadline ---
    uni_rows = parse_universities(
        names=request.POST.getlist("uni_name"),
        countries=request.POST.getlist("uni_country"),
        deadlines=request.POST.getlist("uni_deadline"),
        programs=request.POST.getlist("uni_program"),
    )
    if not uni_rows or any(r["uni_deadline"] is None for r in uni_rows):
        return _render_student_form(request, student, "Each university needs a deadline.")

    # --- academics: GPA or percentage, at least one ---
    gpa = request.POST.get("gpa")
    final_percentage = request.POST.get("final_percentage")
    if not academics_present(gpa, final_percentage):
        return _render_student_form(
            request, student,
            "Enter a GPA or a final percentage — at least one is required.",
        )

    # --- files + size limits ---
    MAX_FILE = 5 * 1024 * 1024   # 5MB
    MAX_PHOTO = 3 * 1024 * 1024  # 3MB
    file_transcript = request.FILES.get("transcript")
    file_cv = request.FILES.get("cv")
    file_photo = request.FILES.get("photo")
    if file_transcript and file_transcript.size > MAX_FILE:
        return _render_student_form(request, student, "Transcript exceeds the 5MB limit.")
    if file_cv and file_cv.size > MAX_FILE:
        return _render_student_form(request, student, "CV exceeds the 5MB limit.")
    if file_photo and file_photo.size > MAX_PHOTO:
        return _render_student_form(request, student, "Photo exceeds the 3MB limit.")

    # --- subjects (checkbox names subject0..N, one per Subject row) ---
    chosen_subjects = []
    for i in range(Subject.objects.count()):
        value = request.POST.get("subject" + str(i))
        if value is not None:
            chosen_subjects.append(value)
    subjects_csv = ",".join(str(s) for s in chosen_subjects)

    full_name = compose_full_name(
        request.POST.get("first_name"),
        request.POST.get("middle_name"),
        request.POST.get("last_name"),
    ) or student.username

    with transaction.atomic():
        # One application per (student, professor): resubmitting updates the
        # in-progress row rather than creating a duplicate pending request.
        info, _ = Application.objects.get_or_create(std=student, professor=prof)
        info.name = full_name
        info.email = request.POST.get("email")
        info.professor = prof
        info.std = student
        info.is_generated = False
        info.years_taught = request.POST.get("yrs")
        info.years_known = request.POST.get("yrs")
        info.subjects = subjects_csv
        info.is_paper = request.POST.get("has_paper")
        info.relationship_type = request.POST.get("relationship_type")
        info.first_name = request.POST.get("first_name")
        info.middle_name = request.POST.get("middle_name")
        info.last_name = request.POST.get("last_name")
        info.gender = request.POST.get("gender")
        info.contact_number = request.POST.get("contact_number")
        info.applied_level = request.POST.get("applied_level")
        info.program = request.POST.get("program")
        info.known_roles = ",".join(request.POST.getlist("known_roles"))
        info.enrollment_batch = request.POST.get("enrollment_batch")
        info.passed_year = request.POST.get("passed_year")
        info.professional_experience = request.POST.get("professional_experience")
        info.strong_points = request.POST.get("strong_points")
        info.weak_points = request.POST.get("weak_points")
        info.save()

        Project.objects.filter(application=info).delete()
        if request.POST.get("sproject") or request.POST.get("pro1"):
            Project.objects.create(
                application=info,
                supervised_project=request.POST.get("sproject"),
                final_project=request.POST.get("pro1"),
            )

        Paper.objects.filter(application=info).delete()
        if request.POST.get("paper_title") or request.POST.get("paper_link"):
            Paper.objects.create(
                application=info,
                paper_title=request.POST.get("paper_title"),
                paper_link=request.POST.get("paper_link"),
            )

        save_universities(info, uni_rows)

        Academics.objects.filter(application=info).delete()
        Academics.objects.create(
            application=info,
            gpa=gpa,
            tentative_ranking=request.POST.get("tentative_ranking"),
            final_percentage=final_percentage,
        )

        Files.objects.filter(application=info).delete()
        Files.objects.create(
            application=info,
            transcript=file_transcript,
            CV=file_cv,
            Photo=file_photo,
        )

        Qualities.objects.filter(application=info).delete()
        Qualities.objects.create(
            application=info,
            extracirricular=request.POST.get("eca"),
        )

    nearest_deadline = min(
        (r["uni_deadline"] for r in uni_rows if r["uni_deadline"]), default=None
    )
    send_mail(
        "Application for recommendation letter",
        f"Dear sir,\n {student.username} has sent an application in Recommendation "
        f"Letter Generator. Nearest Deadline is {nearest_deadline}. Please log in to "
        f"generate the letter.\n Link: http://recommendation-generator.bct.itclub.pp.ua/"
        f"\n\nBest Regards,\nIoe Recommendation Letter Generator",
        "ioerecoletter@gmail.com",
        [prof.email],
        fail_silently=True,
    )

    return render(request, "student_success.html", {
        "roll": student.roll_number, "letter": False, "naam": student.username,
    })


def studentform2(request):
    """The application is now a single page; keep this path working for any
    stale links/bookmarks by sending them to the one form."""
    return redirect("/studentform1")


def loginTeacher(request):
    if request.method == "GET":
        student = current_student(request)
        if student is not None:
            naam = student.username

            teachers = TeacherInfo.objects.filter(department=student.department)
            if Application.objects.filter(std__username=naam).exists():                 #std is foreign key for StudentLoginInfo
                appli = Application.objects.filter(std__username=naam)
            else:
                appli = {}
            response = render(
                        request,
                        "student_success.html",
                        {
                            "naam": student.username,
                            "roll": student.roll_number,
                            "letter": True,
                            'applications': appli
                        },
                    )
                    
            return response
        teacher = current_teacher(request)
        if teacher is not None:
                unique = teacher.unique_id
                context = build_teacher_dashboard_context(unique, request.GET)
                return render(request, "Teacher.html", context)
        return render(request, "loginTeacher.html")
            
    if request.method == "POST":
        email = request.POST.get("username")   
        passwo = request.POST.get("password")
        # check if user is real
        tempUsers = User.objects.filter(email__exact=email)
        if tempUsers.count() > 1:
            messages.error(request, "Multiple accounts found with this email. Please contact admin.")
            return render(request, "loginTeacher.html")
        elif not tempUsers.exists():
            messages.error(request, "You are not registered as a professor.")
            return render(request, "loginTeacher.html")
        else:
            tempUser = tempUsers.first()
            usern = tempUser.username
            user = authenticate(username=usern, password=passwo)
            if user is not None:
                print("user authenticated")
                login(request, user)
                # Resolves via the ``TeacherInfo.user`` link, falling back to the
                # legacy "Full Name/<unique_id>" convention for unlinked rows.
                teacher_model = current_teacher(request)
                if teacher_model is None:
                    messages.error(request, "No teacher record is linked to this account.")
                    return render(request, "loginTeacher.html")
                unique = teacher_model.unique_id

                context = build_teacher_dashboard_context(unique, request.GET)
                response = render(request, "Teacher.html", context)
                # Neither the "unique" nor the "username" cookie is issued any
                # more: identity resolves from the session via current_teacher().
                return response
            else:
                messages.error(request, "Sorry!  The Password doesnot match.")
                return render(request, "loginTeacher.html")
    



def logoutUser(request):
    logout(request)
    response = redirect("/")
    # Kept even though login no longer sets it, so browsers still holding the
    # retired cookie from an earlier release get it cleared on logout.
    response.delete_cookie('unique')
    response.delete_cookie('csrftoken')
    response.delete_cookie('username')
    # The reset flow no longer issues these identity cookies (the OTP lives in
    # the session now), but clear any stale ones a browser still holds from an
    # earlier release so they cannot linger.
    response.delete_cookie('OTP_value')
    response.delete_cookie('teacher_ko_user')
    response.delete_cookie('teacher_ko_naam')
    return response

def logoutStudent(request):
    response = redirect("/")
    response.delete_cookie('student')
    return response

def forgotPassword(request):
    # The OTP is now generated and stored server-side in the ``otp`` view, not
    # handed to the client in a cookie the attacker could read or forge.
    return render(request, "forgotPassword.html")


def forgotUsername(request):
    # No OTP cookie: this username-recovery flow finishes in ``checkEmail``,
    # which never consulted the OTP, so the cookie was dead weight and a
    # client-writable value that the reset flow used to trust.
    return render(request, "forgotUsername.html")


# check email of username is valid or not
def checkEmail(request):
    if request.method == "POST":

        email = request.POST.get("user_email")
        if User.objects.filter(email__exact=email).exists():
            user = User.objects.get(email__exact=email)
            send_mail_safely(
                "UserName ",
                "Your username  is " + user.username,
                "christronaldo9090909@gmail.com",
                [email],
                fail_message="Username recovery mail failed",
            )
            messages.success(request, "Username has been sent to your gmail.")
            return redirect("loginTeacher")
        else:
            messages.error(request, "Email is not registered.")
            return redirect("loginTeacher")
    return redirect("loginTeacher")


# OTP
def otp(request):
    """Start a password reset: generate an OTP, keep it server-side, email it.

    The secret and the target username live in the Django session (server-side
    and signed), never in a client cookie. The response is identical whether or
    not the submitted username exists, so this cannot be used to enumerate
    accounts.
    """
    if request.method != "POST":
        return redirect("forgotPassword")

    username = request.POST.get("username")
    user = User.objects.filter(username=username).first()

    # Generate and store the OTP regardless, so timing/branching does not leak
    # whether the account exists. Only a real account gets the email, so an
    # attacker guessing a username can never learn the OTP.
    otp_value = str(OTP_generator(5))
    request.session["pw_reset_otp"] = otp_value
    request.session["pw_reset_user"] = username or ""
    request.session.pop("pw_reset_verified", None)

    master = None
    if user is not None:
        master = TeacherInfo.objects.filter(user=user).first()
        send_mail(
            "OTP ",
            "Your OTP for Recoomendation Letter is " + otp_value,
            "recoioe@gmail.com",
            [user.email],
            fail_silently=True,
        )

    # Same page either way; ``master`` may be None for an unknown username.
    return render(request, "otp.html", {"teacherkonam": master})


# Otp check
def OTP_check(request):
    """Verify the submitted OTP against the server-side session value.

    One-shot: the stored OTP is popped on the first attempt, so it cannot be
    brute-forced across requests. Only a correct guess sets the short-lived
    ``pw_reset_verified`` flag that ``changePassword`` requires.
    """
    if request.method != "POST":
        return redirect("loginTeacher")

    user_OTP_value = request.POST.get("user_typed_OTP_value")
    real_OTP_value = request.session.pop("pw_reset_otp", None)

    if real_OTP_value is not None and user_OTP_value == real_OTP_value:
        request.session["pw_reset_verified"] = True
        return render(
            request,
            "validatePassword.html",
            {"teacher_ko_naam": request.session.get("pw_reset_user")},
        )

    messages.error(request, "Wrong OTP_value")
    return render(request, "loginTeacher.html")


# #to pass the username and to validate the user

# def validatePassword(request):
#     teacher_ko_naam=request.COOKIES.get('teacher_ko_naam')
#     OTP_value=request.COOKIES.get('OTP_value')
#     return render(request, 'validatePassword.html',{'teacher_ko_naam':teacher_ko_naam, 'OTP_value':OTP_value})


# pwd is changed of corresponding user passed from validatePassword
def changePassword(request):
    """Reset the password for the account that completed the OTP flow.

    Gated on the server-side ``pw_reset_verified`` flag and the target username
    stored in the session by ``otp`` - never a client cookie. The three reset
    keys are cleared afterward so the flow cannot be replayed.
    """
    if request.method != "POST":
        return redirect("loginTeacher")

    if not request.session.get("pw_reset_verified"):
        messages.error(
            request,
            "Your password reset could not be verified. Please start again.",
        )
        return redirect("loginTeacher")

    password1 = request.POST.get("password1")
    password2 = request.POST.get("password2")

    if not password1 or password1 != password2:
        messages.error(request, "Passwords do not match.")
        return render(
            request,
            "validatePassword.html",
            {"teacher_ko_naam": request.session.get("pw_reset_user")},
        )

    username = request.session.get("pw_reset_user")
    usr = User.objects.filter(username=username).first()
    if usr is not None:
        usr.set_password(password1)
        usr.save()

    # One-time: tear the whole flow down so it cannot be replayed.
    for key in ("pw_reset_otp", "pw_reset_user", "pw_reset_verified"):
        request.session.pop(key, None)

    messages.success(request, "Password has been changed successfully.")
    return render(request, "loginTeacher.html")


def OTP_generator(n):
    range_start = 10 ** (n - 1)
    range_end = (10 ** n) - 1
    return randint(range_start, range_end)


# to pass message to admin user
def contact(request):

    return render(request, "contact.html")


def about(request):

    return render(request, "about.html")


def feedback(request):

    if request.method == "POST":
        First_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")
        feedback = request.POST.get("feedback")

        message = (
            str(First_name)+" " 
            + str(last_name)
            + "\n"
            + str(email)
            + "\n"
            + str(feedback)
        )

        mail_admins_safely(
            "Feedback", message, fail_message="Contact-form admin notification failed"
        )
        send_mail_safely(
            "Reply From Recoomendation Letter Team",
            "Thank you for your feedback. We will get back to you soon.",
            " christronaldo9090909@gmail.com",
            [email],
            fail_message="Contact-form reply mail failed",
        )
        messages.success(request, "Your message has been sent.")
        return render(request, "contact.html")


def userDetails(request):
    subject=[]
    naya_subjects=[]
    teacherkonam = current_teacher(request)
    if teacherkonam is None:
        return redirect("/loginTeacher")

    email = teacherkonam.email
    username = User.objects.get(email=email)
    subjects=teacherkonam.subjects.all()
    length = len(subjects)
    bisaya=Subject.objects.all()
    
    for i in bisaya:
        if i not in subjects:
            naya_subjects.append(i)
        else:
            subject.append(i)
    
    return render(
        request,
        "userDetails.html",
        {"teacher_username": username, "teacher": teacherkonam,'subjects':subject,'bisaya':bisaya, 'length':length},
    )
    
def studentDetails(request):
    student = current_student(request)
    if student is not None:
        return render(
            request,
            "studentDetails.html",
            {"username": student.username,'roll':student.roll_number, 'department': student.department,'program': student.program,'gender': student.gender,
            'dob': student.dob},
        )
    # No identity: send them to log in rather than rendering an empty profile.
    # A student whose browser still holds a pre-Phase-4b unsigned cookie lands here.
    return redirect("/loginStudent")


def profileUpdate(request):
    teacherkonam = current_teacher(request)
    if teacherkonam is None:
        return redirect("/loginTeacher")

    return render(request, "profileUpdate.html", {"teacher": teacherkonam})


def profileUpdateRequest(request):

    teacherkonam = current_teacher(request)
    if teacherkonam is None:
        return redirect("/loginTeacher")

    email = teacherkonam.email
    username = User.objects.get(email=email)

    if request.method == "POST":
        photo = request.FILES["file"]

        teacherkonam.images = photo
        teacherkonam.save()

    return render(request, "userDetails.html", {"teacher_username": username, "teacher": teacherkonam})


def changeUsername(request):
    # Editing a professor's own login account. Identity comes from the session
    # via current_teacher(); the caller can only rename themselves, not an
    # arbitrary account named in a client-supplied "old_username".
    if request.method == "POST":
        teacher = current_teacher(request)
        if teacher is None:
            return redirect("/loginTeacher")
        user = teacher.user
        if user is None:
            messages.error(request, "No login account is linked to this professor.")
            return redirect(userDetails)

        new_username = request.POST.get("new_username")
        if not new_username:
            messages.error(request, "Please provide a new username.")
            return redirect(userDetails)
        if User.objects.filter(username=new_username).exclude(pk=user.pk).exists():
            messages.error(request, "Username already exists.")
            return redirect(userDetails)

        user.username = new_username
        user.save()
        messages.success(request, "Username has been changed successfully.")
        return redirect(loginTeacher)
    return redirect(userDetails)

def changeStudentName(request):
    # Editing a student's own account. Identity comes from the signed student
    # cookie via current_student(); the caller cannot rename another student by
    # supplying their name.
    if request.method == "POST":
        student = current_student(request)
        if student is None:
            return redirect("/loginStudent")

        new_username = request.POST.get("new_username")
        if not new_username:
            messages.error(request, "Please provide a new username.")
            return redirect(studentDetails)
        if StudentLoginInfo.objects.filter(username=new_username).exclude(
            pk=student.pk
        ).exists():
            messages.error(request, "Student already exists.")
            return redirect(studentDetails)

        student.username = new_username
        student.save()
        messages.success(request, "Your username has been changed successfully.")
        # The signed cookie still carries the old name, so drop it and make the
        # student log in again under the new one.
        response = redirect(loginStudent)
        response.delete_cookie('student')
        return response
    return redirect(studentDetails)


# to change the password of the corresponding user within website
@login_required(login_url="/loginTeacher")
def userPasswordChange(request):
    if request.method == "POST":
        typed_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        # The account being changed is the session's account. It used to be
        # looked up from the client-set "username" cookie, which let anyone
        # forge another professor's username and reset their password.
        user = request.user
        current_password = user.password

        # confirming typed old password is true or not
        old_new_check = check_password(typed_password, current_password)
        if old_new_check:
            if new_password == confirm_password:
                user.set_password(new_password)
                user.save()
                messages.success(request, "Password has been changed successfully.")
                return redirect(loginTeacher)
            else:
                messages.error(request, "Password does not match.")
                return redirect(userDetails)
        else:
            messages.error(request, "Old Password didnt match")
            return redirect(userDetails)

# to change the password of the corresponding student within website.
# Not @login_required: that checks the teacher/admin session, which a student
# never has. Identity comes from the signed student cookie instead.
def studentPasswordChange(request):
    student = current_student(request)
    if student is None:
        return redirect("/loginStudent")

    if request.method == "POST":
        typed_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        # to obtain old password,
        current_password = student.password

        # confirming typed old password is true or not
        old_new_check = check_password(typed_password, current_password)
        if old_new_check:
            if new_password == confirm_password:
                student.password = make_password(new_password)
                student.save()
                response = redirect(loginStudent)
                messages.success(request, "Password has been changed successfully.")
                response.delete_cookie('student')
                return response
            else:
                messages.error(request, "Passwords do not match.")
                return redirect(studentDetails)
        else:
            messages.error(request, "Old Password didn't match")
            return redirect(studentDetails)


def changeTitle(request):
    if request.method == "POST":
        new_title = request.POST.get("new_title")
        # Identity comes from the session, not from a client-set cookie.
        teacher = current_teacher(request)
        if teacher is not None:
            teacher.title = new_title
            teacher.save()

            messages.success(request, "Title has been changed successfully.")
            return redirect(userDetails)
        else:
            messages.error(request, "You are not signed in as a professor.")
            return redirect("/loginTeacher")

    return redirect(userDetails)


def changePhone(request):
    if request.method == "POST":
        new_phone = request.POST.get("new_phone")
        # Identity comes from the session, not from a client-set cookie.
        teacher = current_teacher(request)
        if teacher is not None:
            teacher.phone = new_phone
            teacher.save()

            messages.success(request, "Phone Number has been changed successfully.")
            return redirect(userDetails)
        else:
            messages.error(request, "You are not signed in as a professor.")
            return redirect("/loginTeacher")

    return redirect(userDetails)


def changeEmail(request):
    if request.method == "POST":
        new_email = request.POST.get("new_email")
        # Identity comes from the session, not from a client-set cookie.
        teacher = current_teacher(request)
        if teacher is not None:
            teacher.email = new_email
            teacher.save()

            user = teacher.user
            if user is None:
                messages.error(request, "No login account is linked to this professor.")
                return redirect("/loginTeacher")
            user.email = new_email
            user.save()

            messages.success(request, "Email has been changed successfully.")
            return redirect(userDetails)
        else:
            messages.error(request, "You are not signed in as a professor.")
            return redirect("/loginTeacher")

    return redirect(userDetails)

def addSubjects(request):
    if request.method == "POST":
        # Identity comes from the session, not from a client-set cookie.
        teacher = current_teacher(request)
        if teacher is None:
            messages.error(request, "You are not signed in as a professor.")
            return redirect(userDetails)

        name = (request.POST.get("subject") or "").strip()
        if not name:
            messages.error(request, "Enter a subject name.")
            return redirect(userDetails)

        # Free-text, shared pool: reuse an existing row case-insensitively to
        # curb near-duplicates ("DBMS" vs "dbms"), otherwise create it.
        subject_obj = Subject.objects.filter(sub_name__iexact=name).first()
        if subject_obj is None:
            subject_obj = Subject.objects.create(sub_name=name)

        if teacher.subjects.filter(pk=subject_obj.pk).exists():
            messages.error(request, "Subject already exists.")
        else:
            teacher.subjects.add(subject_obj)
            messages.success(request, "Subject has been added successfully.")
        return redirect(userDetails)

    return redirect(userDetails)

def deleteSubjects(request):

    if request.method == "POST":
        subject= request.POST.get("subject")
        teacher = current_teacher(request)
        if teacher is not None:
            try:
                naya_subject = Subject.objects.get(sub_name=subject)
            except Subject.DoesNotExist:
                messages.error(request, "Subject does not exists.")
                return redirect(userDetails)

            # to check if subject is in teacher model or not
            check=[]
            subjects=teacher.subjects.all()
            for i in subjects:
                check.append(i.sub_name)
            if subject not in check:

                messages.error(request, "Subject does not exists.")
                return redirect(userDetails)

            else:
                teacher.subjects.remove(naya_subject)
                messages.success(request, "Subject has been removed successfully.")
                return redirect(userDetails)
        else:
            messages.error(request, "No such Subject exists. ")
            return redirect(userDetails)

    return redirect(userDetails)

# for dynamic dropdown of subjects
def getdetails(request):
    teacher_id = json.loads(request.GET.get("d_name"))
    result_set = []

    teacher = TeacherInfo.objects.get(unique_id=teacher_id)
    subjects = teacher.subjects.all()
    print(subjects)
    for subject in subjects:
        result_set.append({"subject_name": subject})
    return HttpResponse(
        json.dumps(result_set, indent=4, sort_keys=True, default=str),
        content_type="application/json",
    )


def teacher(request):
    # Identity comes from the session, never from a cookie: a visitor with no
    # session is an ordinary logged-out visitor, not an error.
    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")
    unique = teacher.unique_id
    context = build_teacher_dashboard_context(unique, request.GET)
    return render(request, "Teacher.html", context)



def renderCustom(request):
    """Preview a letter for one student from the professor's chosen template."""
    if request.method != "POST":
        return redirect("/teacher")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")
    unique = teacher.unique_id

    roll = request.POST.get("roll")
    application = get_object_or_404(
        Application, std__roll_number=roll, professor__unique_id=unique
    )

    from home.intake import academics_present, apply_professor_edits

    # Only the professor edit form (formTeacher) carries ``prof_edit`` and the
    # full application payload. Other callers of this preview endpoint send a
    # minimal payload and must not be forced through the edit/validation path
    # (which would reject them for a missing GPA and wipe their satellites).
    if request.POST.get("prof_edit"):
        # Enforce the same "GPA or percentage" rule the student form uses, then
        # persist the professor's inline edits before previewing. Reject before
        # saving anything so a bad edit leaves the record untouched.
        if not academics_present(request.POST.get("gpa"), request.POST.get("final_percentage")):
            messages.error(request, "Enter a GPA or a final percentage — at least one is required.")
            return redirect("/teacher")
        apply_professor_edits(application, request.POST)

    anecdote = request.POST.get("prof_anecdote")
    if anecdote is not None:
        application.prof_anecdote = anecdote
        application.save()

    # ``update_or_create`` rather than ``filter().update()``: an application with
    # no Qualities row would silently discard everything the professor ticked.
    quality_defaults = {
        "leadership": request.POST.get("quality1") == "on",
        "hardworking": request.POST.get("quality2") == "on",
        "social": request.POST.get("quality3") == "on",
        "teamwork": request.POST.get("quality4") == "on",
        "friendly": request.POST.get("quality5") == "on",
        "quality": request.POST.get("qual"),
        "presentation": request.POST.get("presentation"),
        "recommend": request.POST.get("recommend"),
    }
    # ``eca`` only comes from the professor edit form. Don't wipe a stored value
    # on a minimal preview POST that never carried the field.
    if "eca" in request.POST:
        quality_defaults["extracirricular"] = request.POST.get("eca")
    Qualities.objects.update_or_create(
        application=application,
        defaults=quality_defaults,
    )

    template_obj = select_template(application.professor, request.POST.get("template_id"))
    return render(request, "test2.html", {
        "letter": render_letter(application, template_obj),
        "student": application,
        # Carried into the download form so the export uses the same template.
        "template_id": template_obj.pk if template_obj else "",
    })


def template(request):
    """The professor's template editor: their own templates plus the system library."""
    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    return render(request, "customTemplate.html", {
        "professor": teacher,
        "templates": CustomTemplates.objects.filter(professor=teacher),
        "system_templates": system_templates().order_by("template_name"),
    })


def getTemplate(request):
    if request.method != "POST":
        return redirect("/makeTemplate")

    # Identity comes from the session, never from the posted ``uid`` field: a
    # hidden input is client-controlled and could name another professor.
    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    content = request.POST.get("content") or ""
    name = (request.POST.get("templateName") or "").strip()
    if not name:
        # Without this the field arrives as None and creates a nameless row that
        # no dropdown can offer back to the professor.
        messages.error(request, "A template needs a name.")
        return redirect("/makeTemplate")
    make_default = request.POST.get("is_default") == 'on'
    # legacy: if template is named "Default" treat as default
    if name and name.strip().lower() == 'default':
        make_default = True

    # cleanup editor artifacts
    content = content.replace('<p>&nbsp;</p>\n<p>&nbsp;</p>', '')
    content = content.replace('<p>&nbsp;</p>', '')
    content = content.replace('</p>\n<p>', '<br>')
    content = content.replace('</p>\r\n<p>', '<br>')
    content = content.replace('</p>\r<p>', '<br>')
    content = content.replace('<p>', '<p><br>')

    # if requested as default, clear previous defaults for this prof
    if make_default:
        CustomTemplates.objects.filter(professor=teacher, is_default=True).update(is_default=False)

    # Edit is keyed by primary key, not by name: matching on name meant that
    # renaming a template created a second row instead of renaming the first.
    template_id = (request.POST.get("template_id") or "").strip()
    template_obj = None
    if template_id.isdigit():
        # Own templates only. A pk that is not this teacher's (including any
        # system row) resolves to nothing and falls through to create-new. A
        # non-numeric id harmlessly falls through to the create/name path too.
        template_obj = CustomTemplates.objects.filter(
            pk=template_id, professor=teacher
        ).first()

    if template_obj:
        # Reject a rename that would collide with another of this teacher's
        # templates, otherwise editing by id could produce a duplicate name.
        clash = (
            CustomTemplates.objects.filter(professor=teacher, template_name=name)
            .exclude(pk=template_obj.pk)
            .exists()
        )
        if clash:
            messages.error(request, f'You already have a template named "{name}".')
            return render(request, "customTemplate.html", {
                "professor": teacher,
                "templates": CustomTemplates.objects.filter(professor=teacher),
                "system_templates": system_templates().order_by("template_name"),
                "template": template_obj,
            })
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

    return render(request, "customTemplate.html", {
        'professor': teacher,
        'templates': CustomTemplates.objects.filter(professor=teacher),
        'system_templates': system_templates().order_by("template_name"),
        'template': template_obj,
    })


def duplicate_template(request):
    """Copy a system (or own) template into this professor's editable library (FR-3)."""
    if request.method != "POST":
        return redirect("/makeTemplate")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    try:
        template_id = int(request.POST.get("template_id", ""))
    except (TypeError, ValueError):
        raise Http404("No valid template requested.")

    # Only shared system templates and the professor's own may be copied.
    source = get_object_or_404(
        CustomTemplates.objects.filter(visible_to(teacher)), pk=template_id
    )

    # Names are bounded by the column width. Duplicating a copy of a copy grows
    # the name by len(" (copy)") each time, so an unbounded f-string overflows
    # ``max_length`` after a dozen clicks - silently on SQLite, as a DataError
    # (and a DEBUG traceback) on PostgreSQL.
    max_len = CustomTemplates._meta.get_field("template_name").max_length
    marker = " (copy)"
    base_name = f"{(source.template_name or 'Template')[:max_len - len(marker)]}{marker}"

    def taken(candidate):
        return CustomTemplates.objects.filter(
            professor=teacher, template_name=candidate
        ).exists()

    name = base_name
    suffix = 2
    # The numeric tail is appended *after* trimming the base to make room for
    # it, never by truncating the finished candidate: truncating the candidate
    # would map every suffix onto the same 100-char string once the base is
    # already at the cap, and the loop would never terminate.
    while taken(name) and suffix <= 999:
        tail = f" {suffix}"
        name = f"{base_name[:max_len - len(tail)]}{tail}"
        suffix += 1
    if taken(name):
        # 999 collisions on one base name is not a real workflow; fall back to a
        # token rather than spinning or overwriting.
        tail = f" {uuid.uuid4().hex[:8]}"
        name = f"{base_name[:max_len - len(tail)]}{tail}"

    CustomTemplates.objects.create(
        template_name=name,
        template=source.template,
        professor=teacher,
        is_default=False,
        is_system=False,
    )
    messages.success(request, f'Copied "{source.template_name}" into your templates.')
    return redirect("/makeTemplate")


def delete_template(request):
    """Delete one of the professor's own templates (never a system template)."""
    if request.method != "POST":
        return redirect("/makeTemplate")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    # Own templates only: a pk that is not this teacher's (including any shared
    # system row) is a 404, not a silent no-op.
    try:
        pk = int(request.POST.get("template_id", ""))
    except (TypeError, ValueError):
        raise Http404("No valid template requested.")
    template_obj = get_object_or_404(CustomTemplates, pk=pk, professor=teacher)
    name = template_obj.template_name or "Untitled"
    template_obj.delete()
    messages.success(request, f'Deleted "{name}".')
    return redirect("/makeTemplate")


def set_default_template(request):
    """Mark one of the professor's own templates as their default."""
    if request.method != "POST":
        return redirect("/makeTemplate")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    try:
        pk = int(request.POST.get("template_id", ""))
    except (TypeError, ValueError):
        raise Http404("No valid template requested.")
    template_obj = get_object_or_404(CustomTemplates, pk=pk, professor=teacher)
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


def admin_login(request):
    try:
        if request.user.is_authenticated and request.user.is_superuser:
            return redirect("adminDashboard")
        
        if request.method == "POST":
            username = request.POST.get("username")
            password = request.POST.get("password")

            user_obj = User.objects.filter(username=username)

            if not user_obj.exists():
                messages.error(request, "User does not exist")
                return render(request, "adminLogin.html")
            
            print(f'username {username} password {password}')

            user_obj = authenticate(username=username, password=password)
            print(user_obj)


            if user_obj and user_obj.is_superuser:
                login(request, user_obj)
                messages.success(request, "Login successful")
                return redirect("adminDashboard")
            
            
            messages.info(request, "Invalid credentials")
            return redirect("loginAdmin")
        
        if request.method == "GET":
            return render (request, "adminLogin.html")
        
        return render(request, "adminLogin.html")
    
    except Exception as e:
        print(e)
        messages.error(request, "An error occured. Please try again.")
        return render(request, "adminLogin.html")
    

def generate_unique_id():
    return str(random.randint(10000, 99999))


@user_passes_test(lambda u: u.is_authenticated and u.is_superuser, login_url="/loginAdmin")
def adminDashboard(request):
    if request.method == 'POST':
        form = TeacherInfoForm(request.POST, request.FILES)
        if form.is_valid():
            email = request.POST.get('email')
            if TeacherInfo.objects.filter(email=email).exists():
                messages.warning(request, 'Another teacher with the same email already exists.')
                return redirect('adminDashboard')
            
            unique_id = generate_unique_id()
            while TeacherInfo.objects.filter(unique_id=unique_id).exists():
                unique_id = generate_unique_id()
            
            teacher_info = form.save(commit=False)
            teacher_info.unique_id = unique_id
            teacher_info.save()


            # Check if other teacher has same email

            uname = teacher_info.name.lower().replace('dr. ', '').replace(' ', '') + "_" + unique_id
            # Create corresponding User with a password
            user = User.objects.create_user(
                username=uname,
                password=form.cleaned_data['password'],  # Password is taken from the cleaned data
                first_name=teacher_info.name,
                last_name= '/' + unique_id             # 78batch: seniors had made to input last name as /unique id
                                                        # so, we had to continue with this( lazy us). You guys can change it. 
                                                        # we leave this for you. Otherwise works completely fine. Better not touch it.
            )
            user.email = teacher_info.email
            user.save()

            # Link the record to its login account, so identity resolves from
            # the session rather than the legacy name convention.
            teacher_info.user = user
            teacher_info.save(update_fields=["user"])

            # Save many-to-many relationships
            form.save_m2m()
            
            messages.success(request, 'Teacher added successfully!')
            send_mail_safely('Account Created Successfully', f'Dear sir,\n  Your account has been created in Recommendation Letter Generator. Your username is {uname}. Please login to verify. If you get any problem please contact us.  \n Link: http://recommendation-generator.bct.itclub.pp.ua/  \n \nBest Regards, \nIoe Recommendation Letter Generator', 'ioerecoletter@gmail.com', [teacher_info.email], fail_message="Teacher account-creation mail failed")


            return redirect('adminDashboard')
        else:
            messages.error(request, 'An error occurred while adding the teacher. Please try again.')
            return redirect('adminDashboard')
    else:
        form = TeacherInfoForm()

    # Query departments and subjects for the form
    departments = Department.objects.all()
    subjects = Subject.objects.all()
    teachers = TeacherInfo.objects.all()
    
    # make username dic of all teachers
    teacher_usernames = {}
    for teacher in teachers:
        teacher_usernames[teacher.name] = f"{teacher.name.lower().replace('dr. ', '').replace(' ', '')}_{teacher.unique_id}"
    

#reverse the order of elements in the dict 
    reversed_teacher_usernames = OrderedDict(reversed(list(teacher_usernames.items())))

    return render(request, 'adminDashboard.html', {
        'form': form,
        'departments': departments,
        'subjects': subjects,
        'professors': reversed_teacher_usernames
    })
from .forms import TeacherInfoForm
from django.contrib.auth.models import User
from docx import Document
from jinja2 import Template
import datetime

def download_generated(request):
    """Re-serve the letter stored on an Application (FR-5).

    Scoped to the professor holding the session so one professor cannot
    fetch another's letters by guessing an id. Rows generated before Phase 3
    started stamping ``generated_letter`` have no stored file, so we redirect
    back to the dashboard with an explanation instead of 500-ing.
    """
    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")
    unique = teacher.unique_id

    # A missing or non-numeric id would otherwise reach the ORM and raise
    # ValueError, which surfaces as a 500 (and a debug traceback when
    # DEBUG is on) rather than an ordinary not-found.
    try:
        application_id = int(request.GET.get("id", ""))
    except (TypeError, ValueError):
        raise Http404("No valid letter requested.")

    application = get_object_or_404(
        Application, pk=application_id, professor__unique_id=unique
    )

    if not application.generated_letter:
        messages.error(
            request,
            "No stored copy of this letter is available. Generate it again to save a copy.",
        )
        return redirect("/teacher")

    return FileResponse(
        application.generated_letter.open("rb"),
        as_attachment=True,
        filename=os.path.basename(application.generated_letter.name),
    )


def download_letter(request):
    """Export a letter as PDF/DOCX, store a copy, and record the FR-5 tracking fields."""
    if request.method != "POST":
        return redirect("/teacher")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")
    unique = teacher.unique_id

    file_format = request.POST.get("format")
    if file_format not in ("pdf", "docx"):
        # Reject before touching the database so a bad request stamps nothing.
        return HttpResponse("Invalid format", status=400)

    application = get_object_or_404(
        Application,
        std__roll_number=request.POST.get("roll"),
        professor__unique_id=unique,
    )
    template_obj = select_template(application.professor, request.POST.get("template_id"))

    # A professor may hand-edit the preview; their text wins over the template.
    edited_text = request.POST.get("edited_letter")
    letter_text = edited_text if edited_text else render_letter(application, template_obj)
    # ``render_letter`` returns "" when the template fails to compile. Refuse
    # rather than storing a blank file and stamping the row as generated: the
    # dashboard would otherwise assert success for a letter that does not exist.
    if not letter_text.strip():
        messages.error(
            request, "That template could not be rendered. Check it for errors."
        )
        return redirect("/teacher")

    if file_format == "docx":
        payload = build_docx_bytes(letter_text)
        content_type = (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )
    else:
        payload = build_pdf_bytes(letter_text)
        content_type = "application/pdf"

    safe_name = slugify(application.name) or "letter"
    filename = f"Recommendation_{safe_name}.{file_format}"

    # FR-5: record what was generated so the dashboard can list and re-serve it.
    # ``save=False`` defers the FileField write into the single UPDATE below, so
    # a failure cannot leave a stored file on a row with no timestamp.
    previous = application.generated_letter.name
    storage = application.generated_letter.storage
    application.generated_letter.save(filename, ContentFile(payload), save=False)

    # Re-exporting otherwise orphans the superseded file forever. Only once the
    # replacement is safely written, and never at the cost of the export: the
    # old file may already be gone, or be shared by a row we are not looking at.
    if previous and previous != application.generated_letter.name:
        try:
            storage.delete(previous)
        except OSError:
            pass

    application.generated_template = template_obj
    application.generated_at = timezone.now()
    application.is_generated = True
    application.save()

    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response



def registerProfessor(request):
    if request.method == 'POST':
        form = TeacherInfoForm(request.POST, request.FILES)
        if form.is_valid():
            teacher_info = form.save(commit=False)
            # Generate unique_id
            unique_id = str(random.randint(10000, 99999))
            while TeacherInfo.objects.filter(unique_id=unique_id).exists():
                unique_id = str(random.randint(10000, 99999))
            teacher_info.unique_id = unique_id
            teacher_info.save()
            form.save_m2m()
            # Create corresponding User
            uname = teacher_info.name.lower().replace('dr. ', '').replace(' ', '') + "_" + unique_id
            user = User.objects.create_user(
                username=uname,
                password=form.cleaned_data['password'],
                first_name=teacher_info.name,
                last_name='/' + unique_id,
                email=teacher_info.email
            )
            # Registration is open: professors self-register and log in
            # immediately. Vetting a requesting student's authenticity is the
            # professor's responsibility, not an admin gate on the account.

            # Link the record to its login account, so identity resolves from
            # the session rather than the legacy name convention.
            teacher_info.user = user
            teacher_info.save(update_fields=["user"])

            messages.success(request, 'Professor registered successfully! You can now log in.')
            return redirect('loginTeacher')
    else:
        form = TeacherInfoForm()
    return render(request, 'registerProfessor.html', {'form': form})
