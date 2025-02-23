import os
from nicegui import ui, app
from pony.orm import Database, Required, Set, db_session, commit, select
import hashlib

# -------------------------------
# Database Setup with PonyORM
# -------------------------------

app.add_static_files('/static', 'static')

db = Database()

class User(db.Entity):
    username = Required(str, unique=True)
    password_hash = Required(str)
    role = Required(str)  # 'teacher' or 'student'
    completions = Set('Completion')

class Lesson(db.Entity):
    title = Required(str)
    description = Required(str)
    code = Required(str)
    type = Required(str)  # 'lesson' or 'exercise'
    completions = Set('Completion')

class Completion(db.Entity):
    user = Required(User)
    lesson = Required(Lesson)

db.bind(provider='sqlite', filename='database.sqlite', create_db=True)
db.generate_mapping(create_tables=True)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Pre-create a teacher account (username: teacher, password: teacherpass)
with db_session:
    if not User.get(username='teacher'):
        User(username='teacher',
             password_hash=hash_password('teacherpass'),
             role='teacher')

TEACHER_COMPLETION_PASSWORD = "666M@giic666"  # Shared password for marking completion

# -------------------------------
# Authentication Functions
# -------------------------------

def login_user(username: str, password: str) -> bool:
    with db_session:
        user = User.get(username=username)
        if user and user.password_hash == hash_password(password):
            # Store only serializable user data
            app.storage.user['user_data'] = {
                'id': user.id,
                'username': user.username,
                'role': user.role
            }
            return True
    return False

def logout_user():
    if 'user_data' in app.storage.user:
        del app.storage.user['user_data']

def get_current_user():
    """Get the current user's data from storage"""
    user_data = app.storage.user.get('user_data')
    if user_data:
        with db_session:
            return User.get(id=user_data['id'])
    return None

# -------------------------------
# UI Pages using @ui.page
# -------------------------------

@ui.page('/login')
def login_page():
    with ui.card().classes('w-1/2 items-center self-center'):
        ui.markdown("## Login")
        username_field = ui.input(label='Username').classes('w-full').props('outlined')
        password_field = ui.input(label='Password', password=True).classes('w-full').props('outlined')
        with ui.row().classes('w-full'):
            ui.button('Login', on_click=lambda: handle_login(username_field.value, password_field.value))
            ui.space()
            ui.button('Sign Up', on_click=lambda: ui.run_javascript("window.location.href='/signup'"))

def handle_login(username, password):
    if login_user(username, password):
        user_data = app.storage.user.get('user_data')
        if user_data['role'] == 'teacher':
            ui.run_javascript("window.location.href='/teacher'")
        else:
            ui.run_javascript("window.location.href='/student'")
    else:
        ui.notify('Invalid username or password')

@ui.page('/signup')
def signup_page():
    with ui.card().classes('w-1/2 items-center self-center'):
        ui.markdown("## Sign Up")
        username_field = ui.input(label='Username').props('outlined').classes('w-full')
        password_field = ui.input(label='Password', password=True).props('outlined').classes('w-full')
        with ui.row().classes('w-full'):
            ui.button('Create Account', on_click=lambda: handle_signup(username_field.value, password_field.value))
            ui.space()
            ui.button('Back to Login', on_click=lambda: ui.run_javascript("window.location.href='/login'"))
        

def handle_signup(username, password):
    with db_session:
        if User.get(username=username):
            ui.notify('Username already exists')
            return
        User(username=username, password_hash=hash_password(password), role='student')
        commit()
    ui.notify('Account created, please log in')
    ui.run_javascript("window.location.href='/login'")

@ui.page('/teacher')
def teacher_dashboard():
    user_data = app.storage.user.get('user_data')
    if not user_data or user_data['role'] != 'teacher':
        ui.notify("Not authorized")
        ui.run_javascript("window.location.href='/login'")
        return

    with ui.row():
        ui.button('Logout', on_click=lambda: [logout_user(), ui.run_javascript("window.location.href='/login'")])
    ui.markdown(f"## Welcome, {user_data['username']} (Teacher)")
    
    # Section: Create New Lesson/Exercise
    with ui.card().classes('q-pa-md'):
        ui.markdown("### Create New Lesson / Exercise")
        title_input = ui.input(label='Lesson Title')
        description_input = ui.input(label='Lesson Description')
        code_input = ui.textarea(label='Lesson Code').style('height: 200px;')
        type_select = ui.select(['lesson', 'exercise'], label='Type')
        ui.button('Create', on_click=lambda: handle_create_lesson(
            title_input.value,
            description_input.value,
            code_input.value,
            type_select.value
        ))

    # Section: Overview of Lessons and Completions
    ui.markdown("## Lessons Overview")
    with db_session:
        lessons = select(l for l in Lesson)[:]
    for lesson in lessons:
        with ui.card().classes('q-pa-md q-mb-md'):
            ui.markdown(f"### {lesson.title} ({lesson.type})")
            ui.label(lesson.description)
            with db_session:
                completions = lesson.completions.select()[:]
                student_names = [comp.user.username for comp in completions]
            if student_names:
                ui.label("Completed by: " + ", ".join(student_names))
            else:
                ui.label("Not completed by anyone yet")
            
            # Add Edit and Delete Buttons
            with ui.row():
                ui.button('Edit', on_click=lambda lesson_id=lesson.id: handle_edit_lesson(lesson_id))
                ui.button('Delete', on_click=lambda lesson_id=lesson.id: handle_delete_lesson(lesson_id))

    def handle_edit_lesson(lesson_id):
        with db_session:
            lesson = Lesson.get(id=lesson_id)
            if not lesson:
                ui.notify("Lesson not found")
                return
            dialog = ui.dialog()
            with dialog, ui.card().classes('q-pa-md'):
                ui.markdown("### Edit Lesson")
                title_input = ui.input(label='Title', value=lesson.title)
                description_input = ui.input(label='Description', value=lesson.description)
                code_input = ui.textarea(label='Code',value=lesson.code).style('height: 200px;')
                type_select = ui.select(['lesson', 'exercise'], value=lesson.type, label='Type')
                
                def save_changes():
                    new_title = title_input.value.strip()
                    new_description = description_input.value.strip()
                    new_code = code_input.value.strip()
                    new_type = type_select.value
                    
                    if not new_title or not new_code:
                        ui.notify("Title and code are required.")
                        return
                    
                    with db_session:
                        lesson_to_update = Lesson.get(id=lesson_id)
                        if lesson_to_update:
                            lesson_to_update.title = new_title
                            lesson_to_update.description = new_description
                            lesson_to_update.code = new_code
                            lesson_to_update.type = new_type
                            commit()
                            ui.notify("Lesson updated successfully.")
                            dialog.close()
                            ui.run_javascript("window.location.reload()")
                        else:
                            ui.notify("Lesson not found.")
                
                with ui.row():
                    ui.button('Save', on_click=save_changes)
                    ui.button('Cancel', on_click=dialog.close)
            
            dialog.open()

    def handle_delete_lesson(lesson_id):
        """Handle the deletion of a lesson."""
        confirm_dialog = ui.dialog()
        with confirm_dialog, ui.card().classes('q-pa-md'):
            ui.markdown("### Are you sure you want to delete this lesson?")
            ui.label("This action cannot be undone.")
            
            def confirm_delete():
                with db_session:
                    lesson = Lesson.get(id=lesson_id)
                    if lesson:
                        lesson.delete()
                        commit()
                        ui.notify("Lesson deleted successfully.")
                        confirm_dialog.close()
                        ui.run_javascript("window.location.reload()")
                    else:
                        ui.notify("Lesson not found.")
            
            with ui.row():
                ui.button('Delete', on_click=confirm_delete, color='red')
                ui.button('Cancel', on_click=confirm_dialog.close)
        
        confirm_dialog.open()

def handle_create_lesson(title, description, code, lesson_type):
    if not title or not code:
        ui.notify('Please enter at least a title and code for the lesson')
        return
    with db_session:
        Lesson(title=title, description=description, code=code, type=lesson_type)
        commit()
    ui.notify('Lesson created')
    ui.run_javascript("window.location.reload()")

def handle_create_lesson(title, description, code, lesson_type):
    if not title or not code:
        ui.notify('Please enter at least a title and code for the lesson')
        return
    with db_session:
        Lesson(title=title, description=description, code=code, type=lesson_type)
        commit()
    ui.notify('Lesson created')
    ui.run_javascript("window.location.reload()")

@ui.page('/student')
def student_dashboard():
    user_data = app.storage.user.get('user_data')
    if not user_data or user_data['role'] != 'student':
        ui.notify("Not authorized")
        ui.run_javascript("window.location.href='/login'")
        return

    with ui.header().classes('w-full bg-black'):
        ui.label('ECIG - Prof Youss').classes('text-h5 text-white')
        ui.space()
        ui.button('Logout',color='green', on_click=lambda: [logout_user(), ui.run_javascript("window.location.href='/login'")])
    ui.markdown(f"## Welcome, {user_data['username']} (Student)").classes('self-center')
    
    with ui.tabs().classes('w-full') as tabs:
        one = ui.tab('Lessons')
        two = ui.tab('Exercises')
    with ui.tab_panels(tabs=tabs,value=one).classes('w-full'):
        with ui.tab_panel('Lessons').classes('w-full'):
            show_lessons_panel('lesson', user_data)
        with ui.tab_panel('Exercises').classes('w-full'):
            show_lessons_panel('exercise', user_data)

def show_lessons_panel(lesson_type, user_data):
    with db_session:
        lessons = select(l for l in Lesson if l.type == lesson_type)[:]
    for lesson in lessons:
        with ui.card().classes('w-full'):
            ui.markdown(f"### {lesson.title}")
            ui.label(lesson.description)
            with ui.row().classes('bg-white w-full'):
                if lesson.type == 'exercise':
                    xcode = ui.code(''' Do The Exercise First ''', language='python').style('width: 65%')
                else:
                    xcode = ui.code(lesson.code, language='python').style('width: 65%')
                with ui.card().style('width: 30%').classes('rounded-borders'):
                    tb = ui.button('Run Code').classes('w-full')
                    tb.on('click',lambda lesson_code=lesson.code, tb=tb: run_code(lesson_code, tb))
            with ui.row().classes('bg-white'):
                dialog = ui.dialog()
                def mark_complete(lesson_id=lesson.id):
                    def confirm_completion():
                        entered_password = password_field.value
                        if entered_password == TEACHER_COMPLETION_PASSWORD:
                            chb.value = True
                            if lesson.type == 'exercise':
                                xcode.content = lesson.code
                            with db_session:
                                lesson_obj = Lesson.get(id=lesson_id)
                                student = User.get(id=user_data['id'])
                                if not any(completion.user == student for completion in lesson_obj.completions):
                                    Completion(user=student, lesson=lesson_obj)
                                    commit()
                                    ui.notify('Marked as complete')
                                    #ui.run_javascript("window.location.reload()")
                                else:
                                    ui.notify('Already marked complete')
                        else:
                            chb.value = False
                            ui.notify('Incorrect teacher password')
                    dialog.clear()
                    with dialog, ui.card():
                        ui.markdown("### Enter Completion Password")
                        password_field = ui.input(label="Teacher Password", password=True)
                        with ui.row():
                            ui.button("OK", on_click=lambda: [confirm_completion(), dialog.close()])
                            ui.button("Cancel", on_click=dialog.close)
                    dialog.open()
                lesson_id=lesson.id
                chb = ui.checkbox("Mark as complete")
                chb.on('click', lambda chb=chb, lesson_id=lesson_id: mark_complete(lesson_id) if chb.value else None)
                with db_session:
                    lesson_obj = Lesson.get(id=lesson.id)
                    student = User.get(id=user_data['id'])
                    if any(completion.user == student for completion in lesson_obj.completions):
                        chb.value = True
                        chb.enabled = False
                        xcode.content = lesson.code
                        dialog.close()

def run_code(lesson_code, button):
    button.visible = False
    try:
        namespace = {'ui': ui}  # Make 'ui' available inside exec()
        #exec(lesson_code, {}, local_vars)
        exec(lesson_code, globals(), namespace)
        for k in namespace:
            globals()[k] = namespace[k]
        ui.notify("Code executed successfully")
    except Exception as e:
        ui.notify(f"Error executing code: {e}")
    button.visible = False

# -------------------------------
# Redirect Root to Login
# -------------------------------

@ui.page('/')
def index_page():
    ui.run_javascript("window.location.href='/login'")

# -------------------------------
# Start the Application
# -------------------------------

ui.run(storage_secret=os.environ['STORAGE_SECRET'])
