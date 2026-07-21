from django.contrib import admin
from django.urls import path ,include
from home import views
from .views import registerProfessor
from .views import download_letter
urlpatterns = [
    path('', views.index, name='home'),
    path('loginStudent', views.loginStudent, name='loginStudent'),
    path('registerStudent', views.registerStudent, name='registerStudent'),
    path('loginTeacher', views.loginTeacher, name='loginTeacher'),
    path('logout', views.logoutUser, name='logout'),
    path('studentLogout', views.logoutStudent, name='studentLogout'),
    path('studentform1', views.studentform1, name='Studentform1'),
    path('studentform2', views.studentform2, name='Studentform2'),
    path('makeLetter', views.make_letter, name='MakeLetter'),
    path('final', views.final, name='Final'),
    path('gallery', views.gallery, name='Gallery'),
    path('studentfinal', views.studentfinal, name='StudentFinal'),
    path('forgotPassword', views.forgotPassword, name='forgotPassword'),
    # path('validatePassword', views.validatePassword, name='validatePassword'),
    path('changePassword', views.changePassword, name='changePassword'),
    path('otp', views.otp, name='otp'),
    path('OTP_check', views.OTP_check, name='OTP_check'),
    path('contact', views.contact, name='contact'),
    path('feedback', views.feedback, name='feedback'),
    path('about', views.about, name='about'),
    # path('teacher', views.teacher, name='teacher'),
    path('userDetails', views.userDetails, name='userDetails'),
    path('studentDetails', views.studentDetails, name='studentDetails'),
    path('profileUpdate', views.profileUpdate, name='profileUpdate'),
    path('profileUpdateRequest', views.profileUpdateRequest, name='profileUpdateRequest'),
    path('changeUsername', views.changeUsername, name='changeUsername'),
    path('changeStudentName', views.changeStudentName, name='changeStudentName'),
    path('userPasswordChange', views.userPasswordChange, name='userPasswordChange'),
    path('studentPasswordChange', views.studentPasswordChange, name='studentPasswordChange'),
    path('forgotUsername', views.forgotUsername, name='forgotUsername'),
    path('checkEmail', views.checkEmail, name='checkEmail'),
    path('changeTitle', views.changeTitle, name='changeTitle'),
    path('changePhone', views.changePhone, name='changePhone'),
    path('changeEmail', views.changeEmail, name='changeEmail'),
    path('getdetails', views.getdetails, name='getdetails'),
    path('addSubjects', views.addSubjects, name='addSubjects'),
    path('deleteSubjects', views.deleteSubjects, name='deleteSubjects'),
    path('teacher', views.teacher, name='teacher'),
    path('download_letter/', download_letter, name='download_letter'),
    path('download_generated/', views.download_generated, name='download_generated'),

    ## Added by 78 batch
    path('renderCustom', views.renderCustom, name='renderCustom'),
    path('makeTemplate', views.template, name='templateTest'),
    path('getTemplate', views.getTemplate, name='getTemplate'),
    path('duplicateTemplate', views.duplicate_template, name='duplicateTemplate'),
    path('deleteTemplate', views.delete_template, name='deleteTemplate'),
    path('loginAdmin', views.admin_login, name='admin_login'),
    path('adminDashboard', views.adminDashboard, name='adminDashboard'),
    
    ##Added by 79 batch
    path('registerProfessor/', registerProfessor, name='registerProfessor'),























]

