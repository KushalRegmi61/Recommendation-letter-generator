from django.db import models
from django.db.models.deletion import CASCADE

class Department(models.Model):
    dept_name = models.CharField(max_length=100,blank=True, unique=True)

    def __str__(self):
        return str(self.dept_name)

    class Meta:
        db_table = 'department'

class Program(models.Model):
    program_name = models.CharField(max_length=100,blank=True, unique=True)
    department = models.ForeignKey(Department, on_delete=CASCADE)

    def __str__(self):
        return str(self.program_name)
    
    class Meta:
        db_table = 'program'


class StudentLoginInfo(models.Model):
    username = models.CharField(max_length=120,null=True,blank=False)
    roll_number = models.CharField(primary_key=True,max_length=9)
    department = models.ForeignKey(Department,on_delete=CASCADE)
    program = models.ForeignKey(Program,on_delete=CASCADE)
    password = models.CharField(max_length=100, null=True,blank=False)
    dob = models.DateField()
    gender = models.CharField(max_length=10 , default="null",null=True,blank=True)
    photo =models.ImageField(upload_to='student_photos/', blank=True, null=True)

    def __str__(self):
        return str(self.username)
    
    class Meta:
        db_table = 'StudentLoginInfo'


class Subject(models.Model):
    sub_name= models.CharField(max_length=150, blank=True,null=True)

    def __str__(self):
        return str(self.sub_name)

    class Meta:
        db_table = 'subject'


class TeacherInfo(models.Model):
    unique_id = models.CharField(max_length=10, null=True)
    name = models.CharField(max_length=40,null=True,blank=True)
    title = models.CharField(max_length=30,null=True,blank=True)
    designation = models.CharField(max_length=50, blank=True, null=True)
    phone = models.CharField(max_length=15,null=True,blank=True)
    email = models.EmailField()
    department = models.ForeignKey(Department,on_delete=CASCADE)
    office_address = models.CharField(max_length=200, blank=True, null=True)
    images = models.ImageField(upload_to='images/', blank=True, default="cute_baby.gif")
    subjects = models.ManyToManyField(Subject)

    def __str__(self):
        return str(self.name)
    
    class Meta:
        db_table = 'TeacherInfo'

class Application(models.Model): 
    name = models.CharField(max_length=122,null=True,blank=True)
    email = models.EmailField(null=True,blank=True)
    professor = models.ForeignKey(TeacherInfo, on_delete= CASCADE)
    std = models.ForeignKey(StudentLoginInfo, on_delete= CASCADE)
    is_generated = models.BooleanField(default=False) 
    years_taught= models.CharField(max_length=10, null=True, blank=True)
    is_pro = models.CharField(max_length=3,default="null")
    subjects= models.CharField(max_length=500, null=True, blank=True)
    is_paper = models.CharField(max_length=500, null=True, blank=True)
    intern = models.BooleanField(default=False)
    
    #added here some more
    personal_statement = models.CharField(max_length=500,null=True,blank=True)
    recommendation_purpose = models.CharField(max_length=500,null=True,blank=True)
    linkedIn = models.CharField(max_length=200,null=True,blank=True)

    # relationship and ranking context
    relationship_type = models.CharField(max_length=50,null=True,blank=True)
    class_size = models.IntegerField(null=True,blank=True)
    ranking_percentile = models.CharField(max_length=20,null=True,blank=True)
    language_instruction = models.CharField(max_length=50,null=True,blank=True)

    # internship details
    intern_company = models.CharField(max_length=200,null=True,blank=True)
    intern_role = models.CharField(max_length=100,null=True,blank=True)
    intern_duration = models.CharField(max_length=50,null=True,blank=True)
    intern_outcome = models.CharField(max_length=200,null=True,blank=True)

    # awards/honors
    scholarships = models.TextField(null=True,blank=True)
    competitions_won = models.TextField(null=True,blank=True)

    prof_anecdote = models.TextField(null=True,blank=True)  # could be filled later by professor

    # --- FR-2 intake fields (Google Form parity) ---
    first_name = models.CharField(max_length=100, null=True, blank=True)
    middle_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    applied_level = models.CharField(
        max_length=20, null=True, blank=True,
        choices=[
            ('Masters', 'Masters'), ('PhD', 'PhD'),
            ('Both', 'Both'), ('Other', 'Other'),
        ],
    )
    known_roles = models.TextField(null=True, blank=True)   # CSV of selected roles
    years_known = models.CharField(max_length=10, null=True, blank=True)
    enrollment_batch = models.CharField(max_length=20, null=True, blank=True)
    passed_year = models.CharField(max_length=20, null=True, blank=True)
    professional_experience = models.TextField(null=True, blank=True)
    strong_points = models.TextField(null=True, blank=True)
    weak_points = models.TextField(null=True, blank=True)

    # --- FR-5 generated-letter tracking (populated in Phase 3) ---
    generated_at = models.DateTimeField(null=True, blank=True)
    generated_template = models.ForeignKey(
        'CustomTemplates', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='generated_applications',
    )
    generated_letter = models.FileField(
        upload_to='generated_letters/', blank=True,
    )

    def __str__(self):
        return str(self.name) + " " + str(self.professor)
    
    class Meta:
        db_table = 'Application'

class Paper(models.Model):
    paper_title = models.CharField(max_length=100,null=True,blank=True)
    paper_link = models.CharField(max_length=200,null=True,blank=True)
    application = models.ForeignKey(Application, on_delete= CASCADE)

    def __str__(self):
        return str(self.application) + str(self.paper_title)

    class Meta:
        db_table = 'Paper'


class Project(models.Model):
    supervised_project = models.CharField(max_length=100,null=True,blank=True)
    final_project= models.CharField(max_length=200,null=True,blank=True)
    deployed = models.BooleanField(default=False)
    application = models.ForeignKey(Application, on_delete= CASCADE)

    def __str__(self):
        return str(self.application) + str(self.supervised_project)

    class Meta:
        db_table = 'Project'


class University(models.Model):
    uni_name = models.CharField(max_length=100,null=True,blank=True)
    uni_deadline = models.DateField(null=True,blank=True)
    program_applied = models.CharField(max_length=100,null=True,blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    application = models.ForeignKey(Application, on_delete= CASCADE)

    def __str__(self):
        return str(self.application) + str(self.uni_name)

    class Meta:
        db_table = 'University'

class Qualities(models.Model):
    application = models.ForeignKey(Application, on_delete= CASCADE)

    leadership = models.BooleanField(default=False) 
    hardworking = models.BooleanField(default=False) 
    social = models.BooleanField(default=False) 
    teamwork = models.BooleanField(default=False) 
    friendly = models.BooleanField(default=False) 
    
    quality= models.CharField(max_length=50,null=True,blank=True)
    presentation= models.CharField(max_length=50,null=True,blank=True)
    extracirricular= models.CharField(max_length=500,null=True,blank=True)

    recommend = models.CharField(max_length=50,null=True,blank=True)
    recommendation_strength = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=[
            ('top5','Top 5%'),
            ('top10','Top 10%'),
            ('outstanding','Outstanding'),
            ('strong','Strong')
        ]
    )

    def __str__(self):
        return str(self.application) + " Qualities"
    class Meta:
        db_table = 'Qualities'
        
        





class Academics(models.Model):
    application = models.ForeignKey(Application, on_delete= CASCADE)
    gpa= models.CharField(max_length=50,null=True,blank=True)
    tentative_ranking= models.CharField(max_length=50,null=True,blank=True)
    final_percentage = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return str(self.application) + " Academics"

    class Meta:
        db_table = 'Academics'

class Files(models.Model):
    transcript = models.FileField(upload_to='transcript/', blank=True)
    CV = models.FileField(upload_to='cv/', blank=True)
    Photo = models.ImageField(upload_to='student_photo/', blank=True)
    application = models.ForeignKey(Application, on_delete= CASCADE)
    def __str__(self):
        return str(self.application) + " Files"
    class Meta:
        db_table = 'Files'


class CustomTemplates(models.Model):
    template_name = models.CharField(max_length=100, null=True, blank=True)
    template = models.TextField(null=True, blank=True)
    # System templates are shared by every professor and have no owner.
    professor = models.ForeignKey(
        TeacherInfo, on_delete=CASCADE, null=True, blank=True
    )
    is_default = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)

    def __str__(self):
        owner = self.professor or "System"
        return f"{owner} - {self.template_name or 'Untitled'} Template"

    class Meta:
        db_table = 'Template'