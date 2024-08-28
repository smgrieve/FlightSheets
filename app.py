from flask import Flask, request, render_template, redirect, url_for, flash
import MySQLdb
from datetime import datetime, timedelta
import csv
from io import StringIO
from flask import Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = '123442523523'

# MySQL configurations
db = MySQLdb.connect(
    host="localhost",
    user="hsc",
    passwd="hsc",
    db="flightclub"
)

from datetime import datetime

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if user:
        return User(id=user[0], username=user[1], password=user[2])
    return None

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, EqualTo

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired(), Length(min=4, max=25)])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=6, max=35)])
    confirm = PasswordField('Repeat Password', validators=[InputRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired(), Length(min=4, max=25)])
    password = PasswordField('Password', validators=[InputRequired()])
    submit = SubmitField('Login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        cursor = db.cursor()
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (form.username.data, hashed_password))
        db.commit()
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (form.username.data,))
        user = cursor.fetchone()
        if user and check_password_hash(user[2], form.password.data):
            user_obj = User(id=user[0], username=user[1], password=user[2])
            login_user(user_obj)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html', form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


def calculate_flight_time(takeoff_time, landing_time):
    # Convert both takeoff_time and landing_time to datetime if they are strings
    if isinstance(takeoff_time, str):
        try:
            takeoff = datetime.strptime(takeoff_time, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            raise ValueError(f"Invalid takeoff_time format: {e}")
    elif isinstance(takeoff_time, datetime):
        takeoff = takeoff_time
    else:
        raise ValueError("takeoff_time must be either str or datetime object.")
    
    if isinstance(landing_time, str):
        try:
            landing = datetime.strptime(landing_time, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            raise ValueError(f"Invalid landing_time format: {e}")
    elif isinstance(landing_time, datetime):
        landing = landing_time
    else:
        raise ValueError("landing_time must be either str or datetime object.")
    
    # Calculate the flight duration
    duration = landing - takeoff
    if duration < timedelta(minutes=1):
        return str(duration), True  # Return incomplete status as True
    return str(duration), False  # Return incomplete status as False

@app.route('/', methods=['GET'])
def index():
    filter_date = request.args.get('date')
    show_incomplete = request.args.get('incomplete') == 'on'
    cursor = db.cursor()
    
    query = "SELECT * FROM flights"
    query_conditions = []
    query_params = []  # List to hold parameters for the query

    # Handling the date filter
    if filter_date:
        try:
            filter_date = datetime.strptime(filter_date, '%Y-%m-%d')
            start_date = filter_date.replace(hour=0, minute=0, second=0)
            end_date = filter_date.replace(hour=23, minute=59, second=59)
            query_conditions.append("takeoff_time BETWEEN %s AND %s")
            query_params.extend([start_date, end_date])  # Append start and end dates to the parameters list
        except ValueError:
            flash('Invalid date format. Please enter a valid date.', 'error')
    
    # Handling the incomplete flights filter
    if show_incomplete:
        query_conditions.append("incomplete = 1")
    
    # Building the final query based on the conditions
    if query_conditions:
        query += " WHERE " + " AND ".join(query_conditions)

    # Execute the query with the parameters list
    cursor.execute(query, query_params)
    flights = cursor.fetchall()
    cursor.close()
    
    return render_template('index.html', flights=flights, filter_date=filter_date)


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_flight():
    cursor = db.cursor()

    cursor.execute("SELECT name FROM aircraft")
    aircraft_list = cursor.fetchall()
    
    cursor.execute("SELECT name FROM towplane")
    towplane_list = cursor.fetchall()

    cursor.execute("SELECT name FROM instructors")
    instructor_list = cursor.fetchall()


    if request.method == 'POST':
        aircraft = request.form['aircraft']
        towplane = request.form['towplane']
        instructor = request.form['instructor']
        pilot = request.form['pilot']
        user_id = current_user.username
        charge_to = request.form['charge_to']
        takeoff_time = request.form['takeoff_time']
        landing_time = request.form['landing_time']
        release_altitude = request.form['release_altitude']
        comments = request.form['comments']
        
        flight_time, incomplete = calculate_flight_time(takeoff_time, landing_time)
        
        cursor.execute("""INSERT INTO flights (aircraft, towplane, instructor, pilot, user_id, charge_to, takeoff_time, landing_time, flight_time, release_altitude, comments, incomplete) 
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                       (aircraft, towplane, instructor, pilot, user_id, charge_to, takeoff_time, landing_time, flight_time, release_altitude, comments, incomplete))
        db.commit()         
        
        return redirect(url_for('index'))
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template('add_flight.html', aircraft_list=aircraft_list, towplane_list=towplane_list,  instructor_list=instructor_list, current_time=current_time)

@app.route('/update/<int:flight_id>', methods=['GET', 'POST'])
def update_landing_time(flight_id):
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM flights WHERE id = %s", (flight_id,))
    flight = cursor.fetchone()
    
    if request.method == 'POST':
        landing_time = request.form['landing_time']
        release_altitude = request.form['release_altitude']
        user_update = current_user.username
        
        flight_time, incomplete = calculate_flight_time(flight[5], landing_time)
        
        cursor.execute("UPDATE flights SET landing_time = %s, flight_time = %s, release_altitude = %s, user_update = %s, incomplete = %s WHERE id = %s", 
                       (landing_time, flight_time, release_altitude, user_update, incomplete, flight_id))
        db.commit()
        
        return redirect(url_for('index'))
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template('update_landing_time.html', flight=flight, current_time=current_time)

@app.route('/export')
def export_to_csv():
    cursor = db.cursor()
    cursor.execute("SELECT * FROM flights")
    data = cursor.fetchall()

    # Create an in-memory string buffer to hold CSV data
    output = StringIO()
    writer = csv.writer(output)

    # Write the header row
    writer.writerow(['ID', 'Aircraft', 'Instructor', 'Pilot', 'Charge To', 'Takeoff Time', 'Landing Time', 'Flight Time', 'Release Altitude', 'Status', 'Comments', 'Create User', 'Update User'] )

    # Write data rows
    for row in data:
        writer.writerow(row)

    # Get CSV content from the buffer
    output.seek(0)
    csv_content = output.getvalue()
    output.close()

    # Serve the CSV file
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=flights.csv"}
    )

# Admin route to manage aircraft
@app.route('/admin/aircraft', methods=['GET', 'POST'])
def admin_aircraft():
    if request.method == 'POST':
        action = request.form.get('action')
        aircraft_name = request.form.get('name')

        if action == 'Add':
            cursor = db.cursor()
            cursor.execute("INSERT INTO aircraft (name) VALUES (%s)", (aircraft_name,))
            db.commit()
            flash('Aircraft added successfully!', 'success')
        elif action == 'Delete':
            cursor = db.cursor()
            cursor.execute("DELETE FROM aircraft WHERE name = %s", (aircraft_name,))
            db.commit()
            flash('Aircraft deleted successfully!', 'success')

        return redirect(url_for('admin_aircraft'))

    # Get list of aircraft
    cursor = db.cursor()
    cursor.execute("SELECT name FROM aircraft")
    aircraft_list = cursor.fetchall()

    return render_template('admin_aircraft.html', aircraft_list=aircraft_list)

# Admin route to manage instructors
@app.route('/admin/instructors', methods=['GET', 'POST'])
def admin_instructors():
    if request.method == 'POST':
        action = request.form.get('action')
        instructor_name = request.form.get('name')

        if action == 'Add':
            cursor = db.cursor()
            cursor.execute("INSERT INTO instructors (name) VALUES (%s)", (instructor_name,))
            db.commit()
            flash('Instructor added successfully!', 'success')
        elif action == 'Delete':
            cursor = db.cursor()
            cursor.execute("DELETE FROM instructors WHERE name = %s", (instructor_name,))
            db.commit()
            flash('Instructor deleted successfully!', 'success')

        return redirect(url_for('admin_instructors'))

    # Get list of instructors
    cursor = db.cursor()
    cursor.execute("SELECT name FROM instructors")
    instructor_list = cursor.fetchall()

    return render_template('admin_instructors.html', instructor_list=instructor_list)


if __name__ == '__main__':
    app.run(host='0.0.0.0' , port=5000) 
