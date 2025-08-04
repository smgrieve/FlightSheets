from flask import Flask, request, render_template, redirect, url_for, flash
import MySQLdb
from datetime import datetime, timedelta
import csv
from io import StringIO
from flask import Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
from flask import abort
import logging
from contextlib import contextmanager
import mysql.connector
from flask import make_response
import string
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = '123442523523'
app.config['MAIL_DEBUG'] = True

airport_elevation = 1300

# MySQL configurations
db = MySQLdb.connect(
    host="localhost",
    user="hscprod",
    passwd="g1212MNZ!",
    db="hscflightprod"
)

@contextmanager
def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="hscprod",
        password="g1212MNZ!",
        database="hscflightprod"
    )
    try:
        yield conn
    finally:
        conn.close()  # Ensures it closes


db.ping(True)


#def get_connection():
#    return MySQLdb.connect(
#       host="localhost",
#        user="hscprod",
#        passwd="g1212MNZ!",
#        db="hscflightprod"
#    )


logging.basicConfig(level=logging.DEBUG)
app.logger.debug("Debugging message")

from flask_mail import Mail, Message
import smtplib

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'hamiltonsoaring@gmail.com'  # Replace with your Gmail address
app.config['MAIL_PASSWORD'] = 'bzpg jeds bvtt owgk'  # Replace with your Gmail app password
app.config['MAIL_DEFAULT_SENDER'] = 'hamiltonsoaring@gmail.com'

mail = Mail(app)

from datetime import datetime

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, username, password FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if user:
                    return User(id=user[0], username=user[1], password=user[2])
                return None
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database error in load_user: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Unexpected error in load_user: {e}")
        return None


class User(UserMixin):
    def __init__(self, id, username, password, is_adult=False):
        self.id = id
        self.username = username
        self.password = password
        self.is_adult = is_adult

def sync_youth_members_to_volunteers():
    """Ensures that youth members from `members` and adult approvers from `users` exist in `volunteers`."""
    cursor = db.cursor()

    # Insert youth members into `volunteers`
    cursor.execute("""
        INSERT IGNORE INTO volunteers (id, name, email)
        SELECT member_id, CONCAT(FirstName, ' ', LastName), MainEmail 
        FROM members 
        WHERE youth_member = 1
    """)

    # Insert adult users (approvers) into `volunteers`
    cursor.execute("""
        INSERT IGNORE INTO volunteers (id, name, email)
        SELECT id, username, '' FROM users WHERE is_adult = 1
    """)

    db.commit()
    cursor.close()


@app.template_filter('datetime')
def format_datetime(value, format='%Y-%m-%dT%H:%M'):
    """Format a datetime object for use in a datetime-local input."""
    if isinstance(value, datetime):
        return value.strftime(format)
    return value

def execute_query(query, params=None):
    """Helper function to execute a query with retries."""
    for _ in range(2):  # Retry twice
        try:
            cursor = db.cursor()
            cursor.execute(query, params or [])
            result = cursor.fetchall()
            cursor.close()
            return result
        except MySQLdb.OperationalError as e:
            app.logger.error(f"MySQL OperationalError: {e}. Retrying...")
            db.ping(reconnect=True)
        except Exception as e:
            app.logger.error(f"Query failed: {e}")
            raise
    raise MySQLdb.OperationalError("Failed to execute query after retries.")


from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import InputRequired, Length, EqualTo

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired(), Length(min=4, max=25)])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=6, max=35)])
    confirm = PasswordField('Repeat Password', validators=[InputRequired(), EqualTo('password')])
    is_adult = BooleanField('Adult Member') 
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired(), Length(min=4, max=25)])
    password = PasswordField('Password', validators=[InputRequired()])
    submit = SubmitField('Login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fname = request.form['first_name'].strip()
        lname = request.form['last_name'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip().lower()
        is_adult = int(request.form['is_adult'])
        youth_member = int(request.form['youth_member'])
        password = generate_password_hash(request.form['password'])

        with get_connection() as conn:
            with conn.cursor() as cursor:
                # Prevent duplicates
                cursor.execute("SELECT 1 FROM users WHERE username = %s", (email,))
                if cursor.fetchone():
                    flash("That email is already registered.")
                    return redirect(url_for('register'))

                cursor.execute("SELECT 1 FROM pending_members WHERE MainEmail = %s", (email,))
                if cursor.fetchone():
                    flash("You already have a pending application.")
                    return redirect(url_for('register'))

                cursor.execute("""
                    INSERT INTO pending_members 
                    (FirstName, LastName, MainPhone, MainEmail, is_adult, youth_member, password)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (fname, lname, phone, email, is_adult, youth_member, password))
                conn.commit()

        flash("Your registration was submitted. An admin will review it.")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        cursor = db.cursor()
        cursor.execute("SELECT id, username, password, is_adult FROM users WHERE username = %s", (form.username.data,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user[2], form.password.data):
            user_obj = User(id=user[0], username=user[1], password=user[2], is_adult=user[3])  # Assuming you handle User object creation this way
            login_user(user_obj)
            session['is_adult'] = user[3]  # Store is_adult in session
            return redirect(url_for('index'))  # Redirect to the main page or dashboard
            
        flash('Invalid username or password')

    return render_template('login.html', form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

def send_member_flight_report(email, flights):
    try:
        subject = "Your Daily Flight Report"
        body = f"Hello,\n\nHere is your flight report for the last 24 hours:\n\n"

        for flight in flights:
            body += f"""
            - Aircraft: {flight['aircraft']}
              Takeoff Time: {flight['takeoff_time']}
              Landing Time: {flight['landing_time']}
              Rental Cost: ${flight['cost']}
              Tow Cost: ${flight['tow_cost']}
              Total Cost: ${flight['total_cost']}
            """

        body += "\n\nBest regards,\nHamilton Soaring Club Team"

        # Compose and send the email
        msg = Message(subject, recipients=[email])
        msg.body = body
        mail.send(msg)

        print(f"Email sent successfully to {email}")
    except Exception as e:
        print(f"Failed to send email to {email}: {e}")

def calculate_flight_time(takeoff_time, landing_time):
    # Handle datetime-local format (e.g., '2024-12-03T11:09:57')
    if isinstance(takeoff_time, str) and 'T' in takeoff_time:
        try:
            takeoff_time = datetime.strptime(takeoff_time, '%Y-%m-%dT%H:%M:%S')
        except ValueError as e:
            raise ValueError(f"Invalid takeoff_time format: {e}")
    elif isinstance(takeoff_time, str):
        try:
            takeoff_time = datetime.strptime(takeoff_time, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            raise ValueError(f"Invalid takeoff_time format: {e}")

    if isinstance(landing_time, str) and 'T' in landing_time:
        try:
            landing_time = datetime.strptime(landing_time, '%Y-%m-%dT%H:%M:%S')
        except ValueError as e:
            raise ValueError(f"Invalid landing_time format: {e}")
    elif isinstance(landing_time, str):
        try:
            landing_time = datetime.strptime(landing_time, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            raise ValueError(f"Invalid landing_time format: {e}")

    # Ensure both are datetime objects
    if not isinstance(takeoff_time, datetime) or not isinstance(landing_time, datetime):
        raise ValueError("takeoff_time and landing_time must be datetime objects or valid strings.")

    # Calculate flight duration
    duration = landing_time - takeoff_time
    if duration < timedelta(minutes=1):
        return str(duration), True  # Incomplete flight
    return str(duration), False  # Complete flight

@app.route('/', methods=['GET'])
@login_required
def index():
    filter_date = request.args.get('date')
    show_incomplete = request.args.get('incomplete') == 'on'

    with get_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM flights WHERE 1=1 and deleted = 0"
        query_conditions = []
        query_params = []

        if not filter_date:
            query_conditions.append("takeoff_time > NOW() - INTERVAL 48 HOUR")

        if filter_date:
            try:
                filter_date = datetime.strptime(filter_date, '%Y-%m-%d')
                start_date = filter_date.replace(hour=0, minute=0, second=0)
                end_date = filter_date.replace(hour=23, minute=59, second=59)
                query_conditions.append("takeoff_time BETWEEN %s AND %s")
                query_params.extend([start_date, end_date])
            except ValueError:
                flash('Invalid date format.', 'error')

        if show_incomplete:
            query_conditions.append("incomplete = 1")

        if query_conditions:
            query += " AND " + " AND ".join(query_conditions)

        query += " ORDER BY id ASC"

        cursor.execute(query, query_params)
        flights = cursor.fetchall()

    response = make_response(render_template('index.html', flights=flights, filter_date=filter_date))
    response.headers['Cache-Control'] = 'no-store'
    return response



import MySQLdb.cursors  # top of your file

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_flight():
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
    
        # GET grounded info for aircraft and towplanes!
        cursor.execute("SELECT name, grounded FROM aircraft")
        aircraft_list = cursor.fetchall()

        cursor.execute("SELECT name, grounded FROM towplanes")
        towplane_list = cursor.fetchall()
    
        cursor.execute("SELECT name FROM instructors")
        instructor_list = cursor.fetchall()
        
        cursor.execute("SELECT name FROM tow_pilots WHERE active = TRUE")
        tow_pilots = cursor.fetchall()
    
        cursor.execute("SELECT member_id, CONCAT(FirstName, ' ', LastName) AS member_name FROM members WHERE `Active Status` = 'Active'")
        members = cursor.fetchall()
        
        if request.method == 'POST':
            try:
                aircraft = request.form['aircraft']
                towplane = request.form['towplane']
                instructor = request.form['instructor']
                tow_pilot = request.form['tow_pilot']
                pilot = request.form['pilot']
                bill_to = request.form['bill_to']
                comments = request.form['comments']

                takeoff_datetime = datetime.strptime(request.form['takeoff_date'] + ' ' + request.form['takeoff_time'], "%Y-%m-%d %H:%M")
                landing_datetime = datetime.strptime(request.form['landing_date'] + ' ' + request.form['landing_time'], "%Y-%m-%d %H:%M")
                release_altitude = int(request.form['release_altitude'])

                flight_time, incomplete = calculate_flight_time(takeoff_datetime, landing_datetime)
                duration = datetime.strptime(flight_time, "%H:%M:%S")
                duration_in_hours = duration.hour + duration.minute / 60 + duration.second / 3600

                cursor.execute("SELECT rental_rate FROM aircraft WHERE name = %s", (aircraft,))
                rental_rate = float(cursor.fetchone()['rental_rate'])
                flight_cost = round(duration_in_hours * rental_rate, 2)

                cursor.execute("SELECT base_fee, rate_per_100ft FROM tow_rates LIMIT 1")
                tow_rate = cursor.fetchone()
                base_fee = float(tow_rate['base_fee'])
                rate_per_100ft = float(tow_rate['rate_per_100ft'])

                airport_elevation = 1300
                adjusted_altitude = max(0, release_altitude - airport_elevation)
                additional_fee = (adjusted_altitude - 1000) / 100.0 * rate_per_100ft if adjusted_altitude > 1000 else 0.0
                tow_cost = round(base_fee + additional_fee, 2)

                total_cost = round(flight_cost + tow_cost, 2)

                cursor.execute("""
                    INSERT INTO flights (
                        aircraft, towplane, instructor, pilot, charge_to, takeoff_time,
                        landing_time, flight_time, release_altitude, comments, incomplete,
                        tow_pilot, user_id, cost, tow_cost, total_cost
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    aircraft, towplane, instructor, pilot, bill_to, takeoff_datetime,
                    landing_datetime, flight_time, release_altitude, comments, incomplete,
                    tow_pilot, current_user.username, flight_cost, tow_cost, total_cost
                ))

                conn.commit()
                flash("Flight added successfully!", "success")
                return redirect(url_for('index'))

            except Exception as e:
                conn.rollback()
                flash(f"Error: {e}", "error")

        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M')

        aircraft_selected = request.args.get('aircraft_selected', '')
        towplane_selected = request.args.get('towplane_selected', '')
        instructor_selected = request.args.get('instructor_selected', '')
        tow_pilot_selected = request.args.get('tow_pilot_selected', '')
        pilot_selected = request.args.get('pilot_selected', '')
        bill_to_selected = request.args.get('bill_to_selected', '')
        comments_prefilled = request.args.get('comments_prefilled', '')

    return render_template(
        'add_flight.html',
        aircraft_list=aircraft_list,
        towplane_list=towplane_list,
        instructor_list=instructor_list,
        tow_pilots=tow_pilots,
        members=members,
        current_date=current_date,
        current_time=current_time,
        aircraft_selected=aircraft_selected,
        towplane_selected=towplane_selected,
        instructor_selected=instructor_selected,
        tow_pilot_selected=tow_pilot_selected,
        pilot_selected=pilot_selected,
        bill_to_selected=bill_to_selected,
        comments_prefilled=comments_prefilled
    )

@app.route('/update/<int:flight_id>', methods=['GET', 'POST'])
@login_required
def update_landing_time(flight_id):
    cursor = db.cursor()

    # Fetch the flight details
    cursor.execute("SELECT * FROM flights WHERE id = %s and deleted = 0", (flight_id,))
    flight = cursor.fetchone()

    if not flight:
        flash("Flight not found.", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            # Get landing time and release altitude from the form
            landing_time = request.form['landing_time']
            release_altitude = int(request.form['release_altitude'])  # Ensure it's an integer
            user_update = current_user.username

            # Parse landing_time into a datetime object
            if isinstance(landing_time, str):
                landing_time = datetime.strptime(landing_time, '%Y-%m-%dT%H:%M:%S')

            # Get takeoff_time from the fetched flight details
            takeoff_time = flight[5]  # Assuming takeoff_time is at index 5

            # Calculate flight time and incomplete status
            flight_time, incomplete = calculate_flight_time(takeoff_time, landing_time)

            # Fetch the aircraft rental rate
            aircraft = flight[1]  # Assuming aircraft name is at index 1
            cursor.execute("SELECT rental_rate FROM aircraft WHERE name = %s", (aircraft,))
            result = cursor.fetchone()
            rental_rate = float(result[0]) if result else 0.0  # Default to $0.0 if not found

            # Calculate flight cost
            duration = datetime.strptime(flight_time, "%H:%M:%S")  # Parse flight_time string
            duration_in_hours = duration.hour + duration.minute / 60 + duration.second / 3600
            flight_cost = round(duration_in_hours * rental_rate, 2)

            # Fetch tow rates and calculate tow cost
            cursor.execute("SELECT base_fee, rate_per_100ft FROM tow_rates LIMIT 1")
            tow_rate = cursor.fetchone()
            base_tow_fee = float(tow_rate[0]) if tow_rate else 0.0
            rate_per_100ft = float(tow_rate[1]) if tow_rate else 0.0

            # Calculate adjusted altitude and tow cost
            airport_elevation = 1300  # Assuming a static elevation
            adjusted_altitude = max(0, release_altitude - airport_elevation)
            additional_fee = max(0, (adjusted_altitude - 1000) / 100) * rate_per_100ft
            tow_cost = base_tow_fee + additional_fee

            # Calculate total cost
            total_cost = flight_cost + tow_cost

            # Update the database with the new values
            cursor.execute("""
                UPDATE flights 
                SET landing_time = %s, flight_time = %s, release_altitude = %s, user_update = %s, 
                    incomplete = %s, cost = %s, tow_cost = %s, total_cost = %s
                WHERE id = %s
            """, (landing_time, flight_time, release_altitude, user_update, incomplete, 
                  flight_cost, tow_cost, total_cost, flight_id))
            db.commit()

            flash(f"Flight updated successfully! Rental Cost: ${flight_cost:.2f}, Tow Cost: ${tow_cost:.2f}, Total Cost: ${total_cost:.2f}", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error updating flight: {str(e)}", "error")
        finally:
            cursor.close()

        return redirect(url_for('index'))

    # Pre-populate the form with current flight details
    current_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')  # Format for datetime-local input
    return render_template('update_landing_time.html', flight=flight, current_time=current_time)



@app.route('/update_altitude/<int:flight_id>', methods=['GET', 'POST'])
@login_required
def update_altitude(flight_id):
    cursor = db.cursor()
    
    if request.method == 'POST':
        new_altitude = request.form['release_altitude']
        user_update = current_user.username
        cursor.execute("UPDATE flights SET release_altitude=%s WHERE id=%s", (new_altitude, flight_id))
        db.commit()
        flash('Release altitude updated successfully!')
        return redirect(url_for('index'))

    # For GET request, fetch the current altitude to display in the form
    cursor.execute("SELECT release_altitude FROM flights WHERE id=%s and deleted = 0", (flight_id,))
    current_altitude = cursor.fetchone()[0]
    cursor.close()
    return render_template('update_altitude.html', flight_id=flight_id, current_altitude=current_altitude)

@app.route('/export')
@login_required
def export_to_csv():
    cursor = db.cursor()
    cursor.execute("SELECT * FROM flights and deleted = 0")
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
@login_required
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

@app.route('/add_tow_plane_usage', methods=['GET', 'POST'])
@login_required
def add_tow_plane_usage():
    cursor = db.cursor()

    if request.method == 'POST':
        # Extract data from form
        tow_plane_id = request.form['tow_plane_id']
        date_of_usage = request.form['date_of_usage']
        number_of_tows = request.form['number_of_tows']
        refuel_times = request.form['refuel_times']
        gallons_of_fuel = request.form['gallons_of_fuel']
        oil_added = request.form['oil_added']
        tach_start = request.form['tach_start']
        tach_end = request.form['tach_end']

        # Fetch the last oil change tach and compute the next due
        cursor.execute("SELECT next_oil_change_tach FROM tow_plane_usage WHERE tow_plane_id=%s ORDER BY date_of_usage DESC LIMIT 1", (tow_plane_id,))
        result = cursor.fetchone()

        # Insert data into the database
        cursor.execute("""
            INSERT INTO tow_plane_usage (
                tow_plane_id, date_of_usage, number_of_tows, refuel_times, 
                gallons_of_fuel, oil_added, tach_start, tach_end
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (tow_plane_id, date_of_usage, number_of_tows, refuel_times, gallons_of_fuel, oil_added, tach_start, tach_end)
        )
        db.commit()
        cursor.close()
        flash('Tow plane usage added successfully!')
        return redirect(url_for('view_tow_plane_usage'))

    cursor.execute("SELECT id, name FROM towplanes")
    towplanes = cursor.fetchall()
    cursor.close()
    return render_template('add_tow_plane_usage.html', towplanes=towplanes)

@app.route('/view_tow_plane_usage')
@login_required
def view_tow_plane_usage():
    current_date = datetime.now().date()
    current_month_start = datetime(current_date.year, current_date.month, 1).date()
    next_month_start = (current_month_start + timedelta(days=31)).replace(day=1)
    cursor = db.cursor()
    cursor.execute("""
    SELECT tp.id, tpu.date_of_usage, tpu.number_of_tows, tpu.refuel_times, tpu.gallons_of_fuel, tpu.oil_added, tpu.tach_start, tpu.tach_end, tp.name, tp.annual_due_date, tp.next_oil_change_due, tpu.tach_end
    FROM tow_plane_usage tpu
    INNER JOIN towplanes tp ON tpu.tow_plane_id = tp.id
""") 
    raw_usages = cursor.fetchall()
    
    usages = []
    for usage in raw_usages:
        tow_plane_id, date_of_usage, number_of_tows, refuel_times, gallons_of_fuel, oil_added, tach_start, tach_end, name, annual_due_date, next_oil_change_due, current_tach_end = usage
        is_annual_due_soon = annual_due_date >= current_month_start and annual_due_date < next_month_start
        is_oil_change_due_soon = (next_oil_change_due - current_tach_end) <= 5
        
        usages.append({
            'tow_plane_id': tow_plane_id,
            'date_of_usage': date_of_usage,
            'number_of_tows': number_of_tows,
            'refuel_times': refuel_times,
            'gallons_of_fuel': gallons_of_fuel,
            'oil_added': oil_added,
            'tach_start': tach_start,
            'tach_end': tach_end,
            'name': name,
            'annual_due_date': annual_due_date,
            'next_oil_change_due': next_oil_change_due,
            'is_annual_due_soon': is_annual_due_soon,
            'is_oil_change_due_soon': is_oil_change_due_soon
        })
    print (usages)
    cursor.close()
    return render_template('view_tow_plane_usage.html', usages=usages)

@app.route('/admin/towplanes', methods=['GET', 'POST'])
@login_required
def update_towplane():
    cursor = db.cursor()

    if request.method == 'POST':
        tow_plane_id = request.form['towplane_id']
        last_oil_change_tach = float(request.form['last_oil_change_tach'])
        annual_due_date = request.form['annual_due_date']

        # Calculate next oil change due based on last oil change tach
        next_oil_change_due = last_oil_change_tach + 50  # Increment by 50 tach hours

        try:
            cursor.execute("""
                UPDATE towplanes SET
                last_oil_change_tach = %s,
                next_oil_change_due = %s,
                annual_due_date = %s
                WHERE id = %s
            """, (last_oil_change_tach, next_oil_change_due, annual_due_date, tow_plane_id))
            db.commit()
            flash('Towplane details updated successfully!')
        except MySQLdb.Error as e:
            db.rollback()
            flash(f'Error updating towplane details: {e}')

    # Fetch towplane data for dropdown
    cursor.execute("SELECT id, name FROM towplanes")
    towplanes = cursor.fetchall()

    return render_template('admin_towplanes.html', towplanes=towplanes)

@app.route('/aircraft_status', methods=['GET', 'POST'])
@login_required
def aircraft_status():
    cursor = db.cursor()
    current_date = datetime.now().date()
    current_month_start = current_date.replace(day=1)
    next_month_start = (current_month_start + timedelta(days=32)).replace(day=1)

    if request.method == 'POST':
        aircraft_id = request.form.get('aircraft_id')
        aircraft_type = request.form.get('aircraft_type')  # Glider or towplane
        action = request.form.get('action')

        if aircraft_type == "glider":
            if action == "Ground":
                cursor.execute("UPDATE aircraft SET grounded = TRUE WHERE id = %s", (aircraft_id,))
                db.commit()
                flash('Glider grounded successfully!', 'warning')

            elif action == "Un-Ground":
                cursor.execute("UPDATE aircraft SET grounded = FALSE WHERE id = %s", (aircraft_id,))
                db.commit()
                flash('Glider restored to active status!', 'success')

        elif aircraft_type == "towplane":
            if action == "Ground":
                cursor.execute("UPDATE towplanes SET grounded = TRUE WHERE id = %s", (aircraft_id,))
                db.commit()
                flash('Towplane grounded successfully!', 'warning')

            elif action == "Un-Ground":
                cursor.execute("UPDATE towplanes SET grounded = FALSE WHERE id = %s", (aircraft_id,))
                db.commit()
                flash('Towplane restored to active status!', 'success')

    # Fetching gliders data
    cursor.execute("""
        SELECT 
            a.id, 
            a.name, 
            a.total_flights, 
            a.annual_due_date, 
            COALESCE(SEC_TO_TIME(SUM(f.flight_time)), '00:00:00') AS total_flight_time, 
            COALESCE(SEC_TO_TIME(SUM(CASE 
                WHEN f.takeoff_time > DATE_SUB(a.annual_due_date, INTERVAL 12 MONTH) THEN f.flight_time 
                ELSE 0 
            END)), '00:00:00') AS hours_since_last_annual,
            a.grounded,
            'glider' AS aircraft_type,
            (a.annual_due_date >= %s AND a.annual_due_date < %s) AS is_due_this_month
        FROM 
            aircraft a
        LEFT JOIN flights f 
            ON a.name = f.aircraft
        GROUP BY 
            a.id
    """, (current_month_start, next_month_start))
    
    gliders = cursor.fetchall()

    # Fetching towplanes data
    cursor.execute("""
        SELECT 
            t.id, 
            t.name, 
            NULL AS total_flights,  -- Towplanes don't track flights the same way
            t.annual_due_date, 
            NULL AS total_flight_time,
            NULL AS hours_since_last_annual,
            t.grounded,
            'towplane' AS aircraft_type,
            (t.annual_due_date >= %s AND t.annual_due_date < %s) AS is_due_this_month,
            (t.next_oil_change_due - t.last_oil_change_tach) <= 5 AS is_oil_due
        FROM 
            towplanes t
    """, (current_month_start, next_month_start))
    
    towplanes = cursor.fetchall()
    cursor.close()

    # Combine gliders and towplanes into one list
    aircrafts = gliders + towplanes

    return render_template('aircraft_status.html', aircrafts=aircrafts, current_date=current_date)


@app.route('/admin/maint', methods=['GET', 'POST'])
@login_required
def update_aircraft():
    cursor = db.cursor()

    if request.method == 'POST':
        aircraft_id = request.form['aircraft_id']
        annual_due_date = request.form['annual_due_date']

        try:
            cursor.execute("""
                UPDATE aircraft SET
                annual_due_date = %s
                WHERE id = %s
            """, (annual_due_date, aircraft_id))
            db.commit()
            flash('Aircrat details updated successfully!')
        except MySQLdb.Error as e:
            db.rollback()
            flash(f'Error updating Aircraft details: {e}')

    # Fetch towplane data for dropdown
    cursor.execute("SELECT id, name FROM aircraft")
    aircrafts = cursor.fetchall()

    return render_template('admin_maint.html', aircrafts=aircrafts)

# Admin route to manage instructors
@app.route('/admin/instructors', methods=['GET', 'POST'])
@login_required
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

def update_flight_counts():
    cursor = db.cursor()

    cursor.execute("""
        SELECT name FROM aircraft
    """)
    aircrafts = cursor.fetchall()

    for aircraft in aircrafts:
        cursor.execute("""
            SELECT COUNT(*)
            FROM flights
            WHERE aircraft = %s and deleted = 0
        """, (aircraft[0],))
        total_flights = cursor.fetchone()[0]

        cursor.execute("""
            UPDATE aircraft
            SET total_flights = %s
            WHERE name = %s 
        """, (total_flights, aircraft[0]))

    db.commit()
    cursor.close()

    return 'Flight counts updated successfully.'

@app.route('/add_time', methods=['GET', 'POST'])
@login_required
def add_time():
    cursor = db.cursor()
    #Sync youth members before showing the form
    sync_youth_members_to_volunteers()

    if request.method == 'POST':
        volunteer_id = request.form['volunteer_id']
        date_worked = request.form['date_worked']
        hours = request.form['hours']
        work_type_id = request.form['work_type_id']
        comments = request.form['comments']  

        cursor.execute("""
            INSERT INTO volunteer_hours (volunteer_id, date_worked, hours, work_type_id, comments)
            VALUES (%s, %s, %s, %s, %s)
        """, (volunteer_id, date_worked, hours, work_type_id, comments))
        db.commit()
        cursor.close()
        flash('Volunteer time added successfully!')
        return redirect(url_for('add_time'))

    # **Fetch Youth Members Instead of Volunteers**
    cursor.execute("SELECT member_id, CONCAT(FirstName, ' ', LastName) FROM members WHERE youth_member = TRUE ORDER BY FirstName")
    volunteers = cursor.fetchall()

    cursor.execute("SELECT id, description FROM work_types ORDER BY description")
    work_types = cursor.fetchall()
    cursor.close()

    return render_template('add_time.html', volunteers=volunteers, work_types=work_types)

@app.route('/manage_volunteers', methods=['GET', 'POST'])
@login_required
def manage_volunteers():
    cursor = db.cursor()

    if request.method == 'POST':
        action = request.form['action']

        if action == 'add':
            member_id = request.form['member_id']
            cursor.execute("UPDATE members SET youth_member = TRUE WHERE member_id = %s", (member_id,))
            db.commit()
            flash(f'Member ID {member_id} is now a youth volunteer!', 'success')

        elif action == 'remove':
            member_id = request.form['member_id']
            cursor.execute("UPDATE members SET youth_member = FALSE WHERE member_id = %s", (member_id,))
            db.commit()
            flash(f'Member ID {member_id} is no longer a youth volunteer!', 'success')

        return redirect(url_for('manage_volunteers'))

    # **Fetch Only Youth Members as Volunteers**
    cursor.execute("SELECT member_id, CONCAT(FirstName, ' ', LastName) FROM members WHERE youth_member = TRUE ORDER BY FirstName")
    volunteers = cursor.fetchall()

    cursor.close()
    return render_template('manage_volunteers.html', volunteers=volunteers)

@app.route('/approve_hours', methods=['GET', 'POST'])
@login_required
def approve_hours():
    if not session.get('is_adult'):
        abort(403)  # Only adults can approve hours
    
    cursor = db.cursor()
    # Sync youth members first
    sync_youth_members_to_volunteers()

    if request.method == 'POST':
        if 'approve' in request.form:
            hour_ids = request.form.getlist('approve_ids')
            approver_id = current_user.id

            for hour_id in hour_ids:
                cursor.execute("""
                    UPDATE volunteer_hours
                    SET approved = TRUE, approver_id = %s
                    WHERE id = %s
                """, (approver_id, hour_id))
            db.commit()
            flash('Selected hours have been approved successfully!')

    # Fetch unapproved volunteer hours
    cursor.execute("""
        SELECT vh.id, CONCAT(m.FirstName, ' ', m.LastName) AS name, vh.date_worked, vh.hours, vh.comments
        FROM volunteer_hours vh
        JOIN members m ON vh.volunteer_id = m.member_id
        WHERE m.youth_member = TRUE AND vh.approved = FALSE
        ORDER BY vh.date_worked DESC
    """)
    unapproved_hours = cursor.fetchall()
    cursor.close()

    return render_template('approve_hours.html', unapproved_hours=unapproved_hours)

@app.route('/display_hours')
@login_required
def display_hours():
    cursor = db.cursor()

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    query = """
        SELECT CONCAT(m.FirstName, ' ', m.LastName) AS volunteer_name, 
               wt.description AS work_type, wt.value as rate, 
               vh.hours, vh.date_worked, 
               (wt.value * vh.hours) AS value, 
               a.username AS approver_name, 
               SUM(vh.hours) OVER(PARTITION BY vh.volunteer_id) AS total_hours, 
               SUM(vh.hours * wt.value) OVER(PARTITION BY vh.volunteer_id) AS total_value, 
               vh.comments
        FROM volunteer_hours vh
        JOIN members m ON vh.volunteer_id = m.member_id
        JOIN users a ON vh.approver_id = a.id
        JOIN work_types wt ON vh.work_type_id = wt.id
        WHERE m.youth_member = TRUE AND vh.approved = TRUE
        ORDER BY m.FirstName
    """

    if start_date and end_date:
        query += " AND vh.date_worked BETWEEN %s AND %s"
        cursor.execute(query, (start_date, end_date))
    else:
        cursor.execute(query)

    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    volunteer_hours = [dict(zip(columns, row)) for row in rows]

    cursor.close()

    return render_template('display_hours.html', volunteer_hours=volunteer_hours, start_date=start_date, end_date=end_date)

@app.route('/volunteer_dashboard')
@login_required
def volunteer_dashboard():
    return render_template('volunteer_dashboard.html')

@app.route('/manage_work_types', methods=['GET', 'POST'])
@login_required
def manage_work_types():
    if not session.get('is_adult'):
        abort(403)  # Forbidden access if not an adult
    cursor = db.cursor()

    if request.method == 'POST':
        if 'add' in request.form:
            # Adding a new work type
            new_description = request.form['new_description']
            new_value = request.form['new_value']
            if new_description and new_value:  # Ensure non-empty submission
                cursor.execute("INSERT INTO work_types (description, value) VALUES (%s, %s)", (new_description, new_value))
                db.commit()
                flash('New work type added successfully!')
        elif 'update' in request.form:
            # Updating an existing work type
            description = request.form['description']
            value = request.form['value']
            cursor.execute("UPDATE work_types SET value = %s WHERE description = %s", (value, description))
            db.commit()
            flash('Work type updated successfully!')
        elif 'delete' in request.form:
            # Deleting an existing work type
            description = request.form['description']
            cursor.execute("DELETE FROM work_types WHERE description = %s", (description,))
            db.commit()
            flash('Work type deleted successfully!')

    cursor.execute("SELECT description, value FROM work_types ORDER BY description")
    work_types = cursor.fetchall()
    cursor.close()

    return render_template('manage_work_types.html', work_types=work_types)

@app.route('/export_volunteer_hours')
def export_volunteer_hours():
    cursor = db.cursor()
    cursor.execute("""
        SELECT v.name, vh.date_worked, vh.hours, vh.comments, vh.approved
        FROM volunteer_hours vh
        JOIN volunteers v ON vh.volunteer_id = v.id
        ORDER BY vh.date_worked DESC
    """)
    volunteer_hours = cursor.fetchall()
    cursor.close()

    # Creating a CSV response
    def generate():
        # Create an in-memory output file
        import io
        output = io.StringIO()
        data = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        data.writerow(['Name', 'Date Worked', 'Hours', 'Comments', 'Approved'])
        for hour in volunteer_hours:
            # Map boolean to a more readable format if needed
            approved_status = 'Yes' if hour[4] else 'No'
            data.writerow([hour[0], hour[1], hour[2], hour[3], approved_status])
        output.seek(0)  # rewind the buffer
        return output.read()

    response = Response(generate(), mimetype='text/csv')
    response.headers.set('Content-Disposition', 'attachment', filename='volunteer_hours.csv')
    return response

@app.route('/admin/tow_pilots', methods=['GET', 'POST'])
@login_required
def admin_tow_pilots():
    cursor = db.cursor()

    if request.method == 'POST':
        name = request.form['name']
        active = request.form.get('active', 'off') == 'on'

        if request.form['submit'] == 'Add':
            cursor.execute("INSERT INTO tow_pilots (name, active) VALUES (%s, %s)", (name, active))
            db.commit()
            flash('Tow pilot added successfully!')
        elif request.form['submit'] == 'Update':
            pilot_id = request.form['pilot_id']
            cursor.execute("UPDATE tow_pilots SET name=%s, active=%s WHERE id=%s", (name, active, pilot_id))
            db.commit()
            flash('Tow pilot updated successfully!')

    # Always fetch and display the current list of tow pilots
    cursor.execute("SELECT id, name, active FROM tow_pilots ORDER BY name")
    tow_pilots = cursor.fetchall()
    cursor.close()

    return render_template('admin_tow_pilots.html', tow_pilots=tow_pilots)

from flask_login import current_user

@app.route('/admin/flights/<int:flight_id>/edit', methods=['GET', 'POST'])
def edit_flight(flight_id):
    cursor = db.cursor()

    if request.method == 'POST':
        # Fetch form data
        aircraft = request.form['aircraft']
        towplane = request.form['towplane']
        tow_pilot = request.form['tow_pilot']
        instructor = request.form['instructor']
        pilot = request.form['pilot']
        charge_to = request.form['charge_to']
        takeoff_time = request.form['takeoff_time']
        landing_time = request.form['landing_time']
        release_altitude = int(request.form['release_altitude'])
        comments = request.form['comments']

        try:
            # Convert times to datetime objects
            takeoff_time = datetime.strptime(takeoff_time, '%Y-%m-%dT%H:%M')
            landing_time = datetime.strptime(landing_time, '%Y-%m-%dT%H:%M')

            # Calculate flight duration
            flight_time = landing_time - takeoff_time

            # Recalculate costs
            rental_cost, tow_cost, total_cost = calculate_costs(aircraft, release_altitude, flight_time)

            # Update the flight in the database
            cursor.execute("""
                UPDATE flights
                SET aircraft = %s, towplane = %s, tow_pilot = %s, instructor = %s, pilot = %s, charge_to = %s,
                    takeoff_time = %s, landing_time = %s, flight_time = %s, release_altitude = %s, comments = %s,
                    user_update = %s, cost = %s, tow_cost = %s, total_cost = %s
                WHERE id = %s
            """, (aircraft, towplane, tow_pilot, instructor, pilot, charge_to, takeoff_time, landing_time,
                  str(flight_time), release_altitude, comments, current_user.username, rental_cost, tow_cost, total_cost, flight_id))
            db.commit()

            flash(f"Flight ID {flight_id} updated successfully! Total Cost: ${total_cost:.2f}", 'success')
        except Exception as e:
            db.rollback()
            flash(f"Error updating flight: {str(e)}", 'error')
        finally:
            cursor.close()

        return redirect(url_for('manage_flights'))

    # Fetch the flight details
    cursor.execute("SELECT * FROM flights WHERE id = %s and deleted = 0", (flight_id,))
    flight = cursor.fetchone()
    if not flight:
        flash(f"Flight ID {flight_id} not found.", "error")
        return redirect(url_for('manage_flights'))

    # Fetch dropdown options
    cursor.execute("SELECT name FROM aircraft")
    aircraft_list = cursor.fetchall()
    cursor.execute("SELECT name FROM towplane")
    towplane_list = cursor.fetchall()
    cursor.execute("SELECT name FROM instructors")
    instructor_list = cursor.fetchall()
    cursor.execute("SELECT name FROM tow_pilots")
    tow_pilot_list = cursor.fetchall()
    cursor.execute("SELECT member_id, CONCAT(FirstName, ' ', LastName) AS member_name FROM members")
    members_list = cursor.fetchall()
    cursor.close()

    # Format datetime fields for datetime-local inputs
    flight = list(flight)
    if isinstance(flight[5], datetime):  # takeoff_time
        flight[5] = flight[5].strftime('%Y-%m-%dT%H:%M')
    if isinstance(flight[6], datetime):  # landing_time
        flight[6] = flight[6].strftime('%Y-%m-%dT%H:%M')

    return render_template(
        'edit_flight.html',
        flight=flight,
        aircraft_list=aircraft_list,
        towplane_list=towplane_list,
        instructor_list=instructor_list,
        tow_pilot_list=tow_pilot_list,
        members_list=members_list
    )


@app.route('/edit_flight_details', methods=['GET', 'POST'])
@login_required
def enter_flight_id():
    if request.method == 'POST':
        flight_id = request.form['flight_id']
        # Redirect the user to the flight edit page for the entered flight ID
        return redirect(url_for('edit_flight', flight_id=flight_id))
    
    return render_template('enter_flight_id.html')

@app.route('/admin/flights/<int:flight_id>/delete', methods=['POST'])
@login_required
def delete_flight(flight_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Soft delete: mark the flight as deleted
            cursor.execute("""
                UPDATE flights
                SET deleted = 1
                WHERE id = %s
            """, (flight_id,))
            print(f"Delete query rowcount: {cursor.rowcount}")  # <-- Add this!

            # Write to audit log
            cursor.execute("""
                INSERT INTO audit_log (table_name, record_id, action, user, timestamp, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                'flights',
                flight_id,
                'soft_delete',
                current_user.username,
                datetime.now(),
                'Flight soft deleted via admin panel'
            ))

        conn.commit()

    flash("Flight has been marked as deleted.")
    return redirect(url_for('manage_flights'))

@app.route('/manage_flights/delete/<int:flight_id>', methods=['POST'])
@login_required
def delete_flight_manage(flight_id):
    cursor = db.cursor()

    try:
        # Check if flight exists and is not already deleted
        cursor.execute("SELECT id FROM flights WHERE id = %s AND deleted = 0", (flight_id,))
        flight = cursor.fetchone()
        if not flight:
            flash(f'Flight with ID {flight_id} does not exist or is already deleted.', 'error')
            return redirect(url_for('manage_flights'))

        # Soft delete
        cursor.execute("UPDATE flights SET deleted = 1 WHERE id = %s", (flight_id,))

        # Audit log
        cursor.execute("""
            INSERT INTO audit_log (table_name, record_id, action, user, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, ('flights', flight_id, 'soft_delete', current_user.username, 'Deleted via manage_flights'))

        db.commit()
        flash('Flight marked as deleted successfully!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error deleting flight: {str(e)}', 'error')
    finally:
        cursor.close()

    return redirect(url_for('manage_flights'))


@app.route('/admin/flights', methods=['GET'])
@login_required
def manage_flights():
    page = request.args.get('page', default=1, type=int)
    per_page = 25
    offset = (page - 1) * per_page

    aircraft = request.args.get('aircraft', '').strip()
    pilot = request.args.get('pilot', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    filters = []
    params = []

    if aircraft:
        filters.append("aircraft = %s")
        params.append(aircraft)
    if pilot:
        filters.append("pilot = %s")
        params.append(pilot)
    if start_date:
        filters.append("takeoff_time >= %s")
        params.append(f"{start_date} 00:00:00")
    if end_date:
        filters.append("takeoff_time <= %s")
        params.append(f"{end_date} 23:59:59")

    where_clause = "WHERE " + " AND ".join(filters + ["deleted = 0"]) if filters else "WHERE deleted = 0"

    cursor = db.cursor()

    # Count total with filters
    cursor.execute(f"SELECT COUNT(*) FROM flights {where_clause}", params)
    total_flights = cursor.fetchone()[0]
    total_pages = (total_flights + per_page - 1) // per_page

    # Fetch paginated results
    query = f"""
        SELECT id, aircraft, pilot, takeoff_time, landing_time, release_altitude, cost, tow_cost, total_cost
        FROM flights 
        {where_clause}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(query, params + [per_page, offset])
    flights = cursor.fetchall()

    # Populate filter dropdowns
    cursor.execute("SELECT DISTINCT aircraft FROM flights WHERE deleted = 0 ORDER BY aircraft")
    aircraft_options = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT pilot FROM flights WHERE deleted = 0 ORDER BY pilot")
    pilot_options = [row[0] for row in cursor.fetchall()]

    cursor.close()

    return render_template(
        'manage_flights.html',
        flights=flights,
        page=page,
        total_pages=total_pages,
        aircraft_options=aircraft_options,
        pilot_options=pilot_options,
        selected_aircraft=aircraft,
        selected_pilot=pilot,
        start_date=start_date,
        end_date=end_date
    )

@app.route('/admin/update_tow_rates', methods=['GET', 'POST'])
@login_required
def update_tow_rates():

    cursor = db.cursor()
    if request.method == 'POST':
        base_fee = request.form['base_fee']
        rate_per_100ft = request.form['rate_per_100ft']

        try:
            cursor.execute("""
                UPDATE tow_rates
                SET base_fee = %s, rate_per_100ft = %s
                LIMIT 1
            """, (base_fee, rate_per_100ft))
            db.commit()
            flash('Tow rates updated successfully!', 'success')
        except Exception as e:
            db.rollback()
            flash(f"Error updating tow rates: {str(e)}", 'error')

    cursor.execute("SELECT base_fee, rate_per_100ft FROM tow_rates LIMIT 1")
    tow_rate = cursor.fetchone()
    cursor.close()

    return render_template('update_tow_rates.html', tow_rate=tow_rate)

@app.route('/daily_flight_report', methods=['GET'])
@login_required
def daily_flight_report():
    cursor = db.cursor()
    
    # Calculate the time range for the last 24 hours
    now = datetime.now()
    yesterday = now - timedelta(hours=24)

    try:
        # Query to fetch flight details within the last 24 hours
        query = """
            SELECT 
                pilot, 
                COUNT(id) AS total_flights,
                SUM(cost) AS total_rental_cost,
                SUM(tow_cost) AS total_tow_cost,
                SUM(total_cost) AS grand_total_cost
            FROM flights
            WHERE takeoff_time BETWEEN %s AND %s and deleted = 0
            GROUP BY pilot
        """
        cursor.execute(query, (yesterday, now))
        results = cursor.fetchall()

        # Format the results into a structured report
        report = []
        for row in results:
            report.append({
                'pilot': row[0],
                'total_flights': row[1],
                'total_rental_cost': round(float(row[2] or 0), 2),
                'total_tow_cost': round(float(row[3] or 0), 2),
                'grand_total_cost': round(float(row[4] or 0), 2)
            })

        cursor.close()

        # Render the report as a template
        return render_template('daily_flight_report.html', report=report, now=now, yesterday=yesterday)

    except Exception as e:
                    flash(f"Error generating report: {str(e)}", "error")
                    return redirect(url_for('index'))
@app.route('/detailed_flight_report', methods=['GET'])
@login_required
def detailed_flight_report():
    cursor = db.cursor()
    
    # Calculate the time range for the last 24 hours
    now = datetime.now()
    yesterday = now - timedelta(hours=24)

    try:
        # Query to fetch flight details within the last 24 hours
        flight_query = """
            SELECT 
                pilot, 
                aircraft, 
                takeoff_time, 
                landing_time, 
                cost, 
                tow_cost, 
                total_cost 
            FROM flights
            WHERE takeoff_time BETWEEN %s AND %s and deleted = 0
            ORDER BY pilot, takeoff_time
        """
        cursor.execute(flight_query, (yesterday, now))
        flight_details = cursor.fetchall()

        # Query to fetch aggregated summary for each pilot
        summary_query = """
            SELECT 
                pilot, 
                COUNT(id) AS total_flights,
                SUM(cost) AS total_rental_cost,
                SUM(tow_cost) AS total_tow_cost,
                SUM(total_cost) AS grand_total_cost
            FROM flights
            WHERE takeoff_time BETWEEN %s AND %s and deleted = 0
            GROUP BY pilot
        """
        cursor.execute(summary_query, (yesterday, now))
        summary_details = cursor.fetchall()

        # Organize data by pilot
        report = {}
        for row in summary_details:
            pilot = row[0]
            report[pilot] = {
                'summary': {
                    'total_flights': row[1],
                    'total_rental_cost': round(float(row[2] or 0), 2),
                    'total_tow_cost': round(float(row[3] or 0), 2),
                    'grand_total_cost': round(float(row[4] or 0), 2)
                },
                'flights': []
            }

        for flight in flight_details:
            pilot = flight[0]
            if pilot in report:
                report[pilot]['flights'].append({
                    'aircraft': flight[1],
                    'takeoff_time': flight[2],
                    'landing_time': flight[3],
                    'cost': round(float(flight[4] or 0), 2),
                    'tow_cost': round(float(flight[5] or 0), 2),
                    'total_cost': round(float(flight[6] or 0), 2)
                })

        cursor.close()

        # Render the report as a template
        return render_template('detailed_flight_report.html', report=report, now=now, yesterday=yesterday)
    
    except Exception as e:
        flash(f"Error generating report: {str(e)}", "error")
        return redirect(url_for('index'))
    finally:
        cursor.close()  # Ensure the cursor is always closed

@app.route('/send_daily_flight_report', methods=['GET'])
def send_daily_flight_report():
    cursor = db.cursor()

    try:
        # Calculate date range (last 24 hours)
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)

        # Query flights from the last 24 hours
        query = """
            SELECT f.id, f.aircraft, f.instructor, f.pilot, f.charge_to, 
                   f.takeoff_time, f.landing_time, f.flight_time, 
                   f.release_altitude, f.cost, f.tow_cost, f.total_cost, 
                   m.member_id, m.FirstName, m.LastName, m.MainEmail,
                   a.rental_rate, tr.rate_per_100ft
            FROM flights f
            LEFT JOIN members m ON f.charge_to = m.member_id
            LEFT JOIN aircraft a ON f.aircraft = a.name
            LEFT JOIN tow_rates tr ON tr.id = 1
            WHERE f.takeoff_time BETWEEN %s AND %s AND deleted = 0
            ORDER BY f.charge_to, f.takeoff_time ASC
        """
        cursor.execute(query, (start_time, end_time))
        flights = cursor.fetchall()

        if not flights:
            flash("No flights in the last 24 hours to report.", "info")
            return redirect(url_for('index'))

        # Group flights by member
        flights_by_member = {}
        for flight in flights:
            member_id = flight[12]
            if member_id not in flights_by_member:
                flights_by_member[member_id] = {
                    "member_name": f"{flight[13]} {flight[14]}",
                    "email": flight[15],
                    "flights": []
                }
            flights_by_member[member_id]["flights"].append(flight)

        # Generate and send emails
        for member_id, data in flights_by_member.items():
            recipient = data["email"]
            subject = "Daily Flight Report"
            flights_details = data["flights"]

            # Generate the email body
            email_body = f"Dear {data['member_name']},\n\nHere is your flight report for the past 24 hours:\n\n"
            email_body += "Flight Details:\n"
            email_body += "{:<10} {:<10} {:<20} {:<20} {:<10} {:<10} {:<10} {:<10} {:<10} {:<10} {:<10}\n".format(
                "Flight ID", "Aircraft", "Takeoff", "Landing", "Flight Time", "Release", "Rate", "Tow Rate", "Cost", "Tow", "Total"
            )

            for flight in flights_details:
                # Format times and flight duration
                takeoff_time = flight[5].strftime("%Y-%m-%d %H:%M:%S")
                landing_time = flight[6].strftime("%Y-%m-%d %H:%M:%S")
                flight_time = str(flight[7])  # Already a timedelta, converted to HH:MM:SS

                email_body += "{:<10} {:<10} {:<20} {:<20} {:<10} {:<10} ${:<10} ${:<10} ${:<10} ${:<10} ${:<10}\n".format(
                    flight[0],  # Flight ID
                    flight[1],  # Aircraft
                    takeoff_time,  # Formatted Takeoff Time
                    landing_time,  # Formatted Landing Time
                    flight_time,  # Flight Time (formatted)
                    flight[8],  # Release Altitude
                    flight[16],  # Aircraft Rate
                    flight[17],  # Tow Rate
                    flight[9],  # Cost
                    flight[10],  # Tow Cost
                    flight[11],  # Total Cost
                )

            email_body += "\nThank you for flying with us!\n\nBest regards,\nHamilton Soaring Club"

            # Debug logs
            print(f"Sending email to: {recipient}")
            print(email_body)

            # Send the email
            send_email(recipient, subject, email_body)

        flash("Daily flight reports sent successfully!", "success")
    except Exception as e:
        flash(f"Error sending daily flight reports: {str(e)}", "error")
        print("Error:", e)  # Debugging
    finally:
        cursor.close()

    return redirect(url_for('index'))


@app.route('/billing_report', methods=['GET', 'POST'])
@login_required
def billing_report():
    cursor = db.cursor()
    flights_data = []
    total_data = {}

    # Default date range to the last 7 days
    today = datetime.now().date()
    start_date = request.form.get('start_date', (today - timedelta(days=7)).strftime('%Y-%m-%d'))
    end_date = request.form.get('end_date', today.strftime('%Y-%m-%d'))

    if request.method == 'POST':
        try:
            # Query to fetch flights within the date range grouped by member_id
            query = """
                SELECT 
                    f.charge_to AS member_id,
                    m.mainemail,
                    f.pilot,
                    f.aircraft,
                    f.takeoff_time,
                    f.landing_time,
                    f.flight_time,
                    f.release_altitude,
                    f.cost,
                    f.tow_cost,
                    f.total_cost
                FROM flights f
                JOIN members m ON f.charge_to = m.member_id
                WHERE DATE(f.takeoff_time) BETWEEN %s AND %s and deleted = 0
                ORDER BY member_id, f.takeoff_time
            """
            cursor.execute(query, (start_date, end_date))
            flights_data = cursor.fetchall()

            # Summarize the total cost by member_id
            summary_query = """
                SELECT 
                    f.charge_to AS member_id,
                    m.mainemail,
                    SUM(f.total_cost) AS grand_total_cost
                FROM flights f
                JOIN members m ON f.charge_to = m.member_id
                WHERE DATE(f.takeoff_time) BETWEEN %s AND %s and deleted = 0
                GROUP BY member_id, m.mainemail
            """
            cursor.execute(summary_query, (start_date, end_date))
            total_data = {row[0]: row for row in cursor.fetchall()}  # Map by member_id

        except Exception as e:
            flash(f"Error generating billing report: {str(e)}", "error")
        finally:
            cursor.close()

    # Render the report
    return render_template(
        'billing_report.html',
        flights_data=flights_data,
        total_data=total_data,
        start_date=start_date,
        end_date=end_date
    )

import random

@app.route('/admin/members', methods=['GET', 'POST'])
@login_required
def manage_members():
    cursor = db.cursor()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'Add':
            # Generate a unique 3-digit random member ID
            while True:
                member_id = random.randint(100, 999)
                cursor.execute("SELECT COUNT(*) FROM members WHERE member_id = %s", (member_id,))
                if cursor.fetchone()[0] == 0:
                    break  # Ensure the ID is unique

            active_status = request.form['active_status']
            customer = request.form['customer']
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            main_phone = request.form['main_phone']
            main_email = request.form['main_email']
            bill_to_1 = request.form['bill_to_1']
            bill_to_2 = request.form['bill_to_2']
            bill_to_3 = request.form['bill_to_3']
            youth_member = 'youth_member' in request.form  # Boolean from checkbox

            cursor.execute("""
                INSERT INTO members (
                    `Active Status`, Customer, FirstName, LastName, MainPhone, MainEmail,
                    `Bill to 1`, `Bill to 2`, `Bill to 3`, youth_member, member_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (active_status, customer, first_name, last_name, main_phone, main_email,
                  bill_to_1, bill_to_2, bill_to_3, youth_member, member_id))
            db.commit()
            flash(f'Member {first_name} {last_name} added successfully!', 'success')

        elif action == 'Edit':
            member_id = request.form['member_id']
            youth_member = 'youth_member' in request.form  # Boolean from checkbox

            cursor.execute("""
                UPDATE members SET youth_member = %s WHERE member_id = %s
            """, (youth_member, member_id))
            db.commit()
            flash(f'Member ID {member_id} updated successfully!', 'success')

        elif action == 'Delete':
            member_id = request.form['member_id']
            cursor.execute("DELETE FROM members WHERE member_id = %s", (member_id,))
            db.commit()
            flash(f'Member ID {member_id} deleted successfully!', 'success')

        return redirect(url_for('manage_members'))

    cursor.execute("SELECT `Active Status`, Customer, FirstName, LastName, MainPhone, MainEmail, `Bill to 1`, `Bill to 2`, `Bill to 3`, youth_member, member_id FROM members ORDER BY member_id")
    members = cursor.fetchall()
    cursor.close()

    return render_template('manage_members.html', members=members)


def calculate_costs(aircraft, release_altitude, flight_time):
    """
    Calculate rental cost, tow cost, and total cost based on flight details.
    """
    cursor = db.cursor()

    try:
        # Fetch rental rate for the aircraft
        cursor.execute("SELECT rental_rate FROM aircraft WHERE name = %s", (aircraft,))
        rental_rate = cursor.fetchone()
        rental_rate = float(rental_rate[0]) if rental_rate else 0.0

        # Fetch tow rates
        cursor.execute("SELECT base_fee, rate_per_100ft FROM tow_rates LIMIT 1")
        tow_rates = cursor.fetchone()
        base_tow_fee = float(tow_rates[0]) if tow_rates else 0.0
        rate_per_100ft = float(tow_rates[1]) if tow_rates else 0.0

        # Fetch airport elevation (assuming single airport or modify for multiple airports)
        #cursor.execute("SELECT elevation FROM airport LIMIT 1")
        airport_elevation = 1300 
        #airport_elevation = xxxcursor.fetchone()
        #airport_elevation = int(airport_elevation[0]) if airport_elevation else 0

        # Adjust release altitude to AGL
        adjusted_altitude = max(0, release_altitude - airport_elevation)

        # Calculate tow cost
        if adjusted_altitude > 1000:
            additional_fee = ((adjusted_altitude - 1000) / 100) * rate_per_100ft
        else:
            additional_fee = 0
        tow_cost = base_tow_fee + additional_fee

        # Calculate rental cost
        flight_time_hours = flight_time.total_seconds() / 3600  # Convert flight time to hours
        rental_cost = flight_time_hours * rental_rate

        # Calculate total cost
        total_cost = rental_cost + tow_cost

        return rental_cost, tow_cost, total_cost
    except Exception as e:
        print(f"Error in calculate_costs: {e}")
        return 0.0, 0.0, 0.0
    finally:
        cursor.close()

from io import StringIO
import csv
from flask import Response

@app.route('/flight_report/export', methods=['POST'])
@login_required
def export_flight_report():
    cursor = db.cursor()

    # Get date range from form
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    try:
        # Fetch flights within the specified date range
        query = """
            SELECT f.id, f.aircraft, f.instructor, f.pilot, f.charge_to, 
                   f.takeoff_time, f.landing_time, f.flight_time, 
                   f.release_altitude, f.cost, f.tow_cost, f.total_cost, 
                   m.member_id, m.FirstName, m.LastName, m.MainEmail
            FROM flights f
            LEFT JOIN members m ON f.charge_to = m.member_id
            WHERE DATE(f.takeoff_time) BETWEEN %s AND %s and deleted = 0
            ORDER BY f.takeoff_time ASC
        """
        cursor.execute(query, (start_date, end_date))
        flights = cursor.fetchall()

        # Create in-memory CSV file
        output = StringIO()
        writer = csv.writer(output)

        # Write header row
        writer.writerow([
            "Flight ID", "Aircraft", "Instructor", "Pilot", "Charge To", 
            "Takeoff Time", "Landing Time", "Flight Time", "Release Altitude", 
            "Rental Cost", "Tow Cost", "Total Cost", "Member ID", "Member Name", "Email"
        ])

        # Write data rows
        for flight in flights:
            writer.writerow([
                flight[0], flight[1], flight[2], flight[3], flight[4],
                flight[5], flight[6], flight[7], flight[8],
                f"{flight[9]:.2f}", f"{flight[10]:.2f}", f"{flight[11]:.2f}",
                flight[12], f"{flight[13]} {flight[14]}", flight[15]
            ])

        # Reset buffer to start
        output.seek(0)

        # Prepare response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=flight_report_{start_date}_to_{end_date}.csv"}
        )
    except Exception as e:
        flash(f"Error exporting report: {str(e)}", 'error')
        return redirect(url_for('flight_report'))
    finally:
        cursor.close()

@app.route('/flight_report', methods=['GET', 'POST'])
@login_required
def flight_report():
    cursor = db.cursor()

    # Initialize default date range (e.g., last 7 days)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    flights = []
    if request.method == 'POST':
        # Get user-provided date range
        start_date = request.form.get('start_date', start_date)
        end_date = request.form.get('end_date', end_date)

        try:
            # Fetch flights within the specified date range
            query = """
                SELECT f.id, f.aircraft, f.instructor, f.pilot, f.charge_to, 
                       f.takeoff_time, f.landing_time, f.flight_time, 
                       f.release_altitude, f.cost, f.tow_cost, f.total_cost, 
                       m.member_id, m.FirstName, m.LastName, m.MainEmail
                FROM flights f
                LEFT JOIN members m ON f.charge_to = m.member_id
                WHERE DATE(f.takeoff_time) BETWEEN %s AND %s and deleted = 0
                ORDER BY f.takeoff_time ASC
            """
            cursor.execute(query, (start_date, end_date))
            flights = cursor.fetchall()
        except Exception as e:
            flash(f"Error fetching report: {str(e)}", 'error')

    cursor.close()

    return render_template('flight_report.html', flights=flights, start_date=start_date, end_date=end_date)

import smtplib
from email.mime.text import MIMEText

def send_email(recipient, subject, body):
    """Send an email using Office365's SMTP server."""
    try:
        sender_email = "smgrieve@hamiltonsoaringclub.org"  # Replace with your Office365 email address
        sender_password = "hzbbnfylnplrvsdq"          # Replace with your Office365 password

        # Configure the SMTP server for Office365
        server = smtplib.SMTP("smtp.office365.com", 587)
        server.starttls()  # Start TLS encryption
        server.login(sender_email, sender_password)

        # Create the email
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = "flights@hamiltonsoaringclub.org"
        msg["To"] = recipient

        # Send the email
        server.sendmail(sender_email, recipient, msg.as_string())
        server.quit()

        print(f"Email sent to {recipient}")
    except Exception as e:
        print(f"Error sending email to {recipient}: {e}")


@app.route('/email_member_ids', methods=['GET'])
@login_required
def email_member_ids():
    cursor = db.cursor()

    try:
        # Query all active members
        query = """
            SELECT member_id, FirstName, LastName, MainEmail
            FROM members
            WHERE `Active Status` = 'Active'
        """
        cursor.execute(query)
        members = cursor.fetchall()

        if not members:
            flash("No active members found to email.", "info")
            return redirect(url_for('index'))

        # Send emails to each member
        for member in members:
            member_id = member[0]
            first_name = member[1]
            last_name = member[2]
            email = member[3]

            # Construct email content
            subject = "Hamilton Soaring Member ID"
            body = f"""
            Dear {first_name} {last_name},

            Here is your Member ID:

            Member ID: {member_id}

            Please keep this information for your records. If you have any questions, feel free to contact us.

            Best regards,
            Hamilton Soaring Club 
            """

            # Send the email
            send_email(email, subject, body)

            # Debug log
            print(f"Email sent to {email} with Member ID {member_id}")

        flash("Member ID emails sent successfully!", "success")
    except Exception as e:
        flash(f"Error sending Member ID emails: {str(e)}", "error")
        print("Error:", e)  # Debugging
    finally:
        cursor.close()

    return redirect(url_for('index'))


@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
        return render_template('admin_dashboard.html')

@app.route('/api/dashboard/flight_stats', methods=['GET'])
@login_required
def flight_stats():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    aircraft = request.args.get('aircraft')
    pilot = request.args.get('pilot')

    cursor = db.cursor()

    try:
        # Build the query dynamically based on filters
        query = "SELECT COUNT(*), AVG(TIMESTAMPDIFF(SECOND, takeoff_time, landing_time) / 3600) FROM flights WHERE 1=1 and deleted = 0"
        params = []

        if start_date:
            query += " AND takeoff_time >= %s"
            params.append(start_date)
        if end_date:
            query += " AND takeoff_time <= %s"
            params.append(end_date)
        if aircraft:
            query += " AND aircraft = %s"
            params.append(aircraft)
        if pilot:
            query += " AND pilot = %s"
            params.append(pilot)

        cursor.execute(query, params)
        result = cursor.fetchone()

        # Ensure result contains data
        if not result or len(result) < 2:
            return {"total_flights": 0, "avg_duration_hours": 0.0}, 200

        return {
            "total_flights": result[0],
            "avg_duration_hours": round(result[1] or 0, 2)
        }, 200

    except Exception as e:
        app.logger.error(f"Error in flight_stats: {e}")
        return {"error": str(e)}, 500

    finally:
        cursor.close()


from flask import jsonify

@app.route('/api/filters/aircraft', methods=['GET'])
@login_required
def get_aircraft_filter():
    try:
        conn = get_connection()  # Ensure this is defined
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT aircraft FROM flights WHERE deleted = 0")
        aircrafts = cursor.fetchall()
        return jsonify([row[0] for row in aircrafts])
    except Exception as e:
        app.logger.error(f"Error in get_aircraft_filter: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        # Close cursor and connection if they exist
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/filters/pilot', methods=['GET'])
@login_required
def get_pilot_filter():
    try:
        conn = get_connection()  # Ensure get_connection is defined as described earlier
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT pilot FROM flights")
        pilots = [row[0] for row in cursor.fetchall()]
        return jsonify(pilots)
    except Exception as e:
        app.logger.error(f"Error in get_pilot_filter: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

@app.route('/api/dashboard/revenue', methods=['GET'])
@login_required
def revenue():
    start_date = request.args.get('start_date', None)
    end_date = request.args.get('end_date', None)

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT 
                        SUM(cost) AS total_rental_revenue,
                        SUM(tow_cost) AS total_tow_revenue,
                        SUM(total_cost) AS total_revenue
                    FROM flights
                """
                params = []
                if start_date and end_date:
                    query += " WHERE takeoff_time BETWEEN %s AND %s and deleted = 0"
                    params = [start_date, end_date]

                cursor.execute(query, params)
                result = cursor.fetchone()

                return jsonify({
                    "total_rental_revenue": round(result[0] or 0, 2),
                    "total_tow_revenue": round(result[1] or 0, 2),
                    "total_revenue": round(result[2] or 0, 2),
                })
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in revenue: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in revenue: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500


@app.route('/api/dashboard/flights_by_aircraft', methods=['GET'])
@login_required
def flights_by_aircraft():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        cursor = db.cursor()

        query = """
            SELECT aircraft, COUNT(*) AS flight_count
            FROM flights FORCE INDEX (idx_takeoff_time_aircraft_composite)
            WHERE deleted = 0
        """

        conditions = []
        params = []

        if start_date:
            conditions.append("takeoff_time >= %s")
            params.append(f"{start_date} 00:00:00")
        if end_date:
            conditions.append("takeoff_time <= %s")
            params.append(f"{end_date} 23:59:59")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " GROUP BY aircraft"

        app.logger.info(f"Query: {query}, Params: {params}")  # Log the query for debugging

        cursor.execute(query, params)
        results = cursor.fetchall()

        if not results:
            app.logger.info("No flights found for the given date range.")

        response = [{"aircraft": row[0], "flight_count": row[1]} for row in results]
        return jsonify(response)

    except MySQLdb.Error as e:
        app.logger.error(f"Error in flights_by_aircraft: {e}")
        return jsonify({"error": "Failed to fetch flights by aircraft"}), 500
    finally:
        cursor.close()

@app.route('/api/dashboard/flights_by_pilot', methods=['GET'])
@login_required
def flights_by_pilot():
    start_date = request.args.get("start_date") or "1900-01-01 00:00:00"
    end_date = request.args.get("end_date") or "9999-12-31 23:59:59"

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT pilot, COUNT(*) AS flight_count
                    FROM flights
                    WHERE takeoff_time BETWEEN %s AND %s and deleted = 0
                    GROUP BY pilot
                """
                cursor.execute(query, (start_date, end_date))
                result = cursor.fetchall()
                flights = [{"pilot": row[0], "flight_count": row[1]} for row in result]
                return jsonify(flights)
    except Exception as e:
        app.logger.error(f"Error in flights_by_pilot: {e}")
        # Return an empty array to ensure frontend doesn't fail
        return jsonify([])


@app.route('/api/dashboard/flights_by_member', methods=['GET'])
@login_required
def flights_by_member():
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        # Assign default date range if none provided
        if not start_date:
            start_date = '1900-01-01'  # Earliest possible date
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        # Ensure time components are added to create valid DATETIME values
        start_date += ' 00:00:00'
        end_date += ' 23:59:59'

        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT charge_to AS member_id, COUNT(*) AS flight_count
                    FROM flights
                    WHERE takeoff_time >= %s AND takeoff_time <= %s and deleted = 0
                    GROUP BY charge_to
                """
                cursor.execute(query, (start_date, end_date))
                results = cursor.fetchall()

                # Transform results into JSON format
                return jsonify([
                    {"member_id": row[0], "flight_count": row[1]}
                    for row in results
                ])
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in flights_by_member: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in flights_by_member: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/dashboard/release_altitude', methods=['GET'])
@login_required
def release_altitude():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Ensure valid defaults if no dates are provided
        if not start_date or start_date.strip() == "":
            start_date = "1970-01-01"  # Default earliest date
        if not end_date or end_date.strip() == "":
            end_date = "2099-12-31"  # Default farthest date

        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT release_altitude
                    FROM flights
                    WHERE takeoff_time >= %s AND takeoff_time <= %s and deleted = 0
                """
                cursor.execute(query, (start_date + " 00:00:00", end_date + " 23:59:59"))
                result = cursor.fetchall()

                altitudes = [row[0] for row in result if row[0] is not None]
                return jsonify(altitudes)
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in release_altitude: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in release_altitude: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/dashboard/towplane', methods=['GET'])
@login_required
def towplane():
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        # Validate and format the dates
        if start_date:
            start_date = f"{start_date} 00:00:00"
        else:
            start_date = None

        if end_date:
            end_date = f"{end_date} 23:59:59"
        else:
            end_date = None

        query = """
            SELECT towplane, COUNT(*) AS flight_count
            FROM flights
            WHERE (%s IS NULL OR takeoff_time >= %s)
              AND (%s IS NULL OR takeoff_time <= %s) and deleted = 0
            GROUP BY towplane
        """

        params = [start_date, start_date, end_date, end_date]

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

        return jsonify([
            {"towplane": row[0], "flight_count": row[1]} for row in results
        ])
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in towplane: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in towplane: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500


@app.route('/api/dashboard/instructor', methods=['GET'])
@login_required
def flights_by_instructor():
    try:
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        # Default date range to avoid errors
        if not start_date:
            start_date = "1900-01-01 00:00:00"  # Replace with an appropriate default
        else:
            start_date += " 00:00:00"

        if not end_date:
            end_date = "2100-12-31 23:59:59"  # Replace with an appropriate default
        else:
            end_date += " 23:59:59"

        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT instructor, COUNT(*) AS flight_count
                    FROM flights
                    WHERE takeoff_time >= %s AND takeoff_time <= %s and deleted = 0
                    GROUP BY instructor
                """
                cursor.execute(query, (start_date, end_date))
                results = cursor.fetchall()

                data = [{"instructor": row[0], "flight_count": row[1]} for row in results]
                return jsonify(data)
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in flights_by_instructor: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in flights_by_instructor: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/dashboard/towpilot', methods=['GET'])
@login_required
def flights_by_tow_pilot():
    try:
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        # Default date range to handle empty inputs
        if not start_date:
            start_date = "1900-01-01 00:00:00"
        else:
            start_date += " 00:00:00"

        if not end_date:
            end_date = "2100-12-31 23:59:59"
        else:
            end_date += " 23:59:59"

        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT tow_pilot, COUNT(*) AS flight_count
                    FROM flights
                    WHERE takeoff_time >= %s AND takeoff_time <= %s and deleted = 0
                    GROUP BY tow_pilot
                """
                cursor.execute(query, (start_date, end_date))
                results = cursor.fetchall()

                data = [{"tow_pilot": row[0], "flight_count": row[1]} for row in results]
                return jsonify(data)
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in flights_by_tow_pilot: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in flights_by_tow_pilot: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/dashboard/flight_time_by_aircraft', methods=['GET'])
@login_required
def flight_time_per_glider():
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        # Validate and format the dates
        if start_date:
            start_date = f"{start_date} 00:00:00"
        else:
            start_date = None

        if end_date:
            end_date = f"{end_date} 23:59:59"
        else:
            end_date = None

        query = """
            SELECT aircraft, SUM(TIMESTAMPDIFF(MINUTE, takeoff_time, landing_time)) AS total_flight_time
            FROM flights
            WHERE (%s IS NULL OR takeoff_time >= %s)
              AND (%s IS NULL OR takeoff_time <= %s) and deleted = 0
            GROUP BY aircraft
        """
        params = [start_date, start_date, end_date, end_date]

        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

        return jsonify([
            {"aircraft": row[0], "flight_time": row[1]} for row in results
        ])
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in flight_time_per_glider: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in flight_time_per_glider: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/dashboard/flight_time_by_member', methods=['GET'])
@login_required
def flight_time_per_member():
    try:
        start_date = request.args.get("start_date", "")
        end_date = request.args.get("end_date", "")
        
        # Provide default values if the dates are empty
        if not start_date:
            start_date = "1900-01-01"  # A very early date
        if not end_date:
            end_date = "2100-12-31"  # A far future date

        with get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT charge_to AS member_id, SUM(flight_time) AS total_flight_time
                    FROM flights
                    WHERE takeoff_time >= %s AND takeoff_time <= %s and deleted = 0
                    GROUP BY charge_to
                """
                cursor.execute(query, (f"{start_date} 00:00:00", f"{end_date} 23:59:59"))
                result = cursor.fetchall()
                data = [{"member_id": row[0], "total_flight_time": row[1]} for row in result]
                return jsonify(data)
    except MySQLdb.OperationalError as e:
        app.logger.error(f"Database operation failed in flight_time_per_member: {e}")
        return jsonify({"error": "Database operation failed"}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in flight_time_per_member: {e}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/dashboard/glider_status', methods=['GET'])
@login_required
def get_glider_status():
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # Query for gliders (aircraft table)
                cursor.execute("""
                    SELECT id, name, annual_due_date, total_flight_time, total_flights, rental_rate
                    FROM aircraft
                """)
                gliders = cursor.fetchall()

                gliders_status = []
                for glider in gliders:
                    annual_due_date = glider[2]
                    status = {
                        'id': glider[0],
                        'name': glider[1],
                        'annual_due_date': annual_due_date,
                        'total_flight_time': glider[3],
                        'total_flights': glider[4],
                        'rental_rate': glider[5],
                        'status': 'red' if annual_due_date and datetime.now().date() > annual_due_date else 'green'
                    }
                    gliders_status.append(status)

                return jsonify(gliders_status)
    except Exception as e:
        app.logger.error(f"Error retrieving glider status: {e}")
        return jsonify({'error': 'Failed to retrieve glider status'}), 500


@app.route('/api/dashboard/towplane_status', methods=['GET'])
@login_required
def get_towplane_status():
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # Query for towplanes (towplanes table)
                cursor.execute("""
                    SELECT id, name, annual_due_date, last_oil_change_tach, next_oil_change_due
                    FROM towplanes
                """)
                towplanes = cursor.fetchall()

                towplanes_status = []
                for towplane in towplanes:
                    annual_due_date = towplane[2]
                    next_oil_change_due = towplane[4]
                    status = {
                        'id': towplane[0],
                        'name': towplane[1],
                        'annual_due_date': annual_due_date,
                        'last_oil_change_tach': towplane[3],
                        'next_oil_change_due': next_oil_change_due,
                        'status': 'red' if (annual_due_date and datetime.now().date() > annual_due_date) or \
                                                 (next_oil_change_due and next_oil_change_due <= towplane[3]) else 'green'
                    }
                    towplanes_status.append(status)

                return jsonify(towplanes_status)
    except Exception as e:
        app.logger.error(f"Error retrieving towplane status: {e}")
        return jsonify({'error': 'Failed to retrieve towplane status'}), 500
        return jsonify({'error': 'Failed to retrieve aircraft status'}), 500
        return jsonify({'error': 'Failed to retrieve aircraft status'}), 500
        return jsonify({'error': 'Failed to retrieve aircraft status'}), 500

@app.route('/copy_flight/<int:flight_id>')
@login_required
def copy_flight(flight_id):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        # Fetch the flight record to be copied
        cursor.execute("SELECT * FROM flights WHERE id = %s and deleted = 0", (flight_id,))
        flight = cursor.fetchone()
        cursor.close()

        if not flight:
            flash("Flight not found", "error")
            return redirect(url_for('index'))

        # Redirect to add_flight with pre-filled query parameters
        return redirect(url_for(
            'add_flight',
            aircraft_selected=flight['aircraft'],
            towplane_selected=flight['towplane'],
            instructor_selected=flight['instructor'],
            tow_pilot_selected=flight['tow_pilot'],
            pilot_selected=flight['pilot'],
            bill_to_selected=flight['charge_to'],
            comments_prefilled=flight['comments']
        ))
@app.route('/profile')
@login_required
def profile():
    member_id = current_user.id  # Assumes user.id == member_id

    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:

            # Get flight history
            cursor.execute("""
                SELECT id, aircraft, takeoff_time, landing_time, flight_time, cost, tow_cost, total_cost
                FROM flights
                WHERE charge_to = %s and deleted = 0
                ORDER BY takeoff_time DESC
            """, (member_id,))
            flights = cursor.fetchall()

            # Summarize totals
            cursor.execute("""
                SELECT 
                    SEC_TO_TIME(SUM(TIME_TO_SEC(flight_time))) AS total_flight_time,
                    SUM(cost) AS total_rental,
                    SUM(tow_cost) AS total_tow,
                    SUM(total_cost) AS grand_total
                FROM flights
                WHERE charge_to = %s and deleted = 0
            """, (member_id,))
            totals = cursor.fetchone()

            # Volunteer hours (if youth_member)
            cursor.execute("SELECT youth_member FROM members WHERE member_id = %s", (member_id,))
            is_youth = cursor.fetchone()['youth_member']

            volunteer_hours = []
            if is_youth:
                cursor.execute("""
                    SELECT date_worked, hours, comments
                    FROM volunteer_hours
                    WHERE volunteer_id = %s AND approved = TRUE
                    ORDER BY date_worked DESC
                """, (member_id,))
                volunteer_hours = cursor.fetchall()

    return render_template('profile.html', 
                           flights=flights,
                           totals=totals,
                           volunteer_hours=volunteer_hours,
                           is_youth=is_youth)

@app.route('/admin/approve_registration/<int:pending_id>', methods=['POST'])
@login_required
def approve_registration(pending_id):
    if not session.get('is_adult'):
        abort(403)  # Only adults can approve hours

    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM pending_members WHERE id = %s", (pending_id,))
            p = cursor.fetchone()
            if not p:
                flash("Not found.")
                return redirect(url_for('pending_registrations'))

            # Insert into members
            cursor.execute("""
                INSERT INTO members 
                (FirstName, LastName, MainPhone, MainEmail, youth_member, member_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (p['FirstName'], p['LastName'], p['MainPhone'], p['MainEmail'], p['youth_member'], p['id']))

            # Insert into users (id = member_id)
            cursor.execute("""
                INSERT INTO users (id, username, password, is_adult)
                VALUES (%s, %s, %s, %s)
            """, (p['id'], p['MainEmail'], p['password'], p['is_adult']))

            # Remove from pending
            cursor.execute("DELETE FROM pending_members WHERE id = %s", (pending_id,))
            conn.commit()

    flash("Member approved and activated.")
    return redirect(url_for('pending_registrations'))


@app.route('/admin/reject_registration/<int:pending_id>', methods=['POST'])
@login_required
def reject_registration(pending_id):
    if not session.get('is_adult'):
        abort(403)  # Only adults can approve hours

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM pending_members WHERE id = %s", (pending_id,))
            conn.commit()

    flash("Member rejected and removed.")
    return redirect(url_for('pending_registrations'))

@app.route('/admin/pending_registrations')
@login_required
def pending_registrations():
    if not session.get('is_adult'):
        abort(403)  # Only adults can approve hours

    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM pending_members ORDER BY submitted_at DESC")
            pending = cursor.fetchall()
    return render_template("admin/pending_registrations.html", pending=pending)

@app.route('/member/logbook/download')
@login_required
def download_logbook():
    username = current_user.username  # or use member_id if preferred

    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT 
                    takeoff_time, aircraft, instructor, pilot, release_altitude, flight_time, comments 
                FROM flights 
                WHERE (pilot = %s OR charge_to = %s) AND deleted = 0
                ORDER BY takeoff_time DESC
            """, (username, current_user.id))  # Or use member ID as charge_to

            flights = cursor.fetchall()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Aircraft', 'Instructor', 'Pilot', 'Altitude', 'Flight Time', 'Comments'])

    for f in flights:
        writer.writerow([
            f['takeoff_time'].strftime('%Y-%m-%d'),
            f['aircraft'],
            f['instructor'],
            f['pilot'],
            f['release_altitude'],
            str(f['flight_time']),
            f['comments'].replace('\n', ' ') if f['comments'] else ''
        ])

    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=flight_logbook.csv"}
    )

@app.route('/admin/flights/<int:flight_id>/edit_cost', methods=['GET', 'POST'])
@login_required
def edit_flight_cost(flight_id):
    if not current_user.is_authenticated:
        abort(403)

    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:
            if request.method == 'POST':
                new_rental = request.form.get('rental_cost', type=float)
                new_tow = request.form.get('tow_cost', type=float)
                new_total = new_rental + new_tow

                cursor.execute("""
                    UPDATE flights
                    SET cost = %s, tow_cost = %s, total_cost = %s
                    WHERE id = %s
                """, (new_rental, new_tow, new_total, flight_id))

                cursor.execute("""
                    INSERT INTO audit_log (table_name, record_id, action, user, notes)
                    VALUES (%s, %s, %s, %s, %s)
                """, ('flights', flight_id, 'edit_cost', current_user.username,
                      f"Updated costs: rental={new_rental}, tow={new_tow}"))

                conn.commit()
                flash("Flight costs updated.", "success")
                return redirect(url_for('manage_flights'))

            # GET: fetch existing cost
            cursor.execute("SELECT id, cost, tow_cost, total_cost FROM flights WHERE id = %s", (flight_id,))
            flight = cursor.fetchone()
            if not flight:
                flash("Flight not found.", "error")
                return redirect(url_for('manage_flights'))

    return render_template('admin/edit_flight_cost.html', flight=flight)


from flask import render_template, request
from datetime import timedelta
from typing import List, Dict

def sanitize_point(p: dict) -> dict:
    return {
        "latitude": float(p["latitude"]),
        "longitude": float(p["longitude"]),
        "vertical_speed": float(p["vertical_speed"] or 0),
        "position_time": p["position_time"].strftime("%H:%M:%S")
    }

def detect_thermals(track: List[Dict]) -> List[List[Dict]]:
    thermals = []
    current = []
    for pt in track:
        vs = pt.get("vertical_speed") or 0
        if vs > 1.5:
            current.append(pt)
        else:
            if len(current) >= 3:
                thermals.append(current)
            current = []
    if len(current) >= 3:
        thermals.append(current)
    return thermals

@app.route("/ogn/flight/<int:flight_id>")
def ogn_flight(flight_id):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT flarm_id, takeoff_time, landing_time
            FROM ogn_flights WHERE id = %s
        """, (flight_id,))
        flight = cursor.fetchone()
        if not flight:
            return f"Flight ID {flight_id} not found", 404

        flarm_id = flight["flarm_id"]
        takeoff = flight["takeoff_time"]
        landing = flight["landing_time"]

        start = takeoff - timedelta(seconds=10)
        end = landing + timedelta(seconds=10)

        cursor.execute("""
            SELECT * FROM ogn_positions
            WHERE flarm_id = %s
              AND position_time BETWEEN %s AND %s
            ORDER BY position_time
        """, (flarm_id, start, end))
        track = cursor.fetchall()

    if not track:
        return f"No position data found for flight {flight_id}", 404

    # Compute vertical speed
    vspd = [0]
    times = [track[0]["position_time"].strftime("%H:%M:%S")]
    for i in range(1, len(track)):
        alt1 = track[i - 1]["altitude"]
        alt2 = track[i]["altitude"]
        t1 = track[i - 1]["position_time"]
        t2 = track[i]["position_time"]
        dt = (t2 - t1).total_seconds()
        vs = (alt2 - alt1) / dt if dt > 0 and alt1 is not None and alt2 is not None else 0
        vspd.append(round(vs, 2))
        times.append(t2.strftime("%H:%M:%S"))
        track[i]["vertical_speed"] = vs

    track[0]["vertical_speed"] = vspd[0]

    thermals = detect_thermals(track)
    best_thermal = max(thermals, key=lambda t: max(p["vertical_speed"] or 0 for p in t), default=[])
    best_thermal_clean = [sanitize_point(p) for p in best_thermal]

    return render_template("ogn_flight.html",
        flight_id=flight_id,
        track=track,
        vspd=vspd,
        times=times,
        thermals=thermals,
        best_thermal=best_thermal_clean
    )


@app.route("/ogn/flights")
def ogn_flights():
    date = request.args.get("date")
    flarm_id = request.args.get("flarm_id")
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT f.*, a.name AS aircraft
            FROM ogn_flights f
            LEFT JOIN aircraft a ON f.flarm_id COLLATE utf8mb4_unicode_ci = a.flarm_id COLLATE utf8mb4_unicode_ci
            WHERE 1=1
        """
        params = []

        if date:
            query += " AND DATE(f.takeoff_time) = %s"
            params.append(date)
        if flarm_id:
            query += " AND f.flarm_id = %s"
            params.append(flarm_id)

        query += " ORDER BY f.takeoff_time DESC"

        cursor.execute(query, params)
        flights = cursor.fetchall()

        # Get distinct aircraft for dropdown
        cursor.execute("SELECT flarm_id, name FROM aircraft WHERE flarm_id IS NOT NULL ORDER BY name IS NULL, name")
        aircraft_ids = cursor.fetchall()

    return render_template("ogn_flights.html", flights=flights, aircraft_ids=aircraft_ids, selected_date=date, selected_id=flarm_id)


@app.route("/api/ogn")
def ogn_api():
    with get_connection() as conn:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT
                    p.flarm_id,
                    /*  Use aircraft.name if present; otherwise fall back to the FLARM ID  */
                    COALESCE(a.name, p.flarm_id)            AS aircraft,
                    p.latitude  AS lat,
                    p.longitude AS lng,
                    COALESCE(p.altitude,0)                  AS alt,
                    COALESCE(p.speed,0)                     AS speed,
                    p.course,
                    p.position_time
                FROM ogn_positions AS p
                LEFT JOIN aircraft AS a ON a.flarm_id = p.flarm_id
                WHERE p.position_time >= UTC_TIMESTAMP() - INTERVAL 15 MINUTE
                  AND p.latitude  IS NOT NULL
                  AND p.longitude IS NOT NULL
                  AND (a.grounded IS NULL OR a.grounded = 0)
                  AND p.id IN (
                      SELECT MAX(id)
                      FROM ogn_positions
                      WHERE position_time >= UTC_TIMESTAMP() - INTERVAL 15 MINUTE
                      GROUP BY flarm_id
                  )
                ORDER BY p.position_time DESC
            """)
            rows = cur.fetchall()
    return jsonify(rows)


@app.route("/ogn/map")
def ogn_map():
    return render_template("ogn_map.html")

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form['email']
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for('reset_password'))

        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT id, password FROM users WHERE username = %s", (email,))
                user = cursor.fetchone()

                if not user or not check_password_hash(user['password'], old_password):
                    flash("Old password is incorrect.", "error")
                    return redirect(url_for('reset_password'))

                hashed = generate_password_hash(new_password)
                cursor.execute("UPDATE users SET password = %s, must_reset_password = 0 WHERE username = %s", (hashed, email))

                cursor.execute("""
                    INSERT INTO audit_log (event_type, user_id, description, timestamp)
                    VALUES (%s, %s, %s, NOW())
                """, ('password_reset', user['id'], 'Password was reset by user'))

                try:
                    send_email(email, "Your Password Was Changed", "Your flight account password was successfully changed.")
                except Exception as e:
                    print(f"Failed to send confirmation email to {email}: {e}")

                conn.commit()

        flash("Password reset successfully.", "success")
        return redirect(url_for('login'))

    return render_template('reset_password.html')

@app.route('/reset_password_code', methods=['GET', 'POST'])
def reset_password_code():
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form['email']
        reset_code = request.form.get('reset_code')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT m.member_id, u.reset_code, u.reset_code_sent_at
                    FROM members m
                    JOIN users u ON m.member_id = u.id
                    WHERE m.MainEmail = %s
                """, (email,))
                user = cursor.fetchone()

                if not user:
                    flash("Email not found.", "error")
                    return render_template("reset_password_code.html", email=email)

                now = datetime.now()

                if action == "send_code":
                    if user['reset_code_sent_at']:
                        elapsed = now - user['reset_code_sent_at']
                        if elapsed < timedelta(minutes=5):
                            flash("Please wait 5 minutes before requesting again.", "error")
                            return render_template("reset_password_code.html", email=email)

                    code = ''.join(random.choices(string.digits, k=6))
                    cursor.execute("""
                        UPDATE users SET reset_code = %s, reset_code_sent_at = %s WHERE id = %s
                    """, (code, now, user['member_id']))
                    conn.commit()

                    send_email(email, "Your Reset Code", f"Your reset code is: {code}")
                    flash("Reset code sent to your email.", "info")
                    return render_template("reset_password_code.html", email=email)

                elif action == "reset_password":
                    if user['reset_code'] != reset_code:
                        flash("Invalid reset code.", "error")
                        return render_template("reset_password_code.html", email=email)

                    if now - user['reset_code_sent_at'] > timedelta(minutes=15):
                        flash("Reset code expired. Please request again.", "error")
                        return render_template("reset_password_code.html", email=email)

                    if new_password != confirm_password:
                        flash("Passwords do not match.", "error")
                        return render_template("reset_password_code.html", email=email)

                    hashed = generate_password_hash(new_password)
                    cursor.execute("""
                        UPDATE users 
                        SET password = %s, reset_code = NULL, reset_code_sent_at = NULL, must_reset_password = 0
                        WHERE id = %s
                    """, (hashed, user['member_id']))

                    cursor.execute("""
                        INSERT INTO audit_log (event_type, user_id, description, timestamp)
                        VALUES (%s, %s, %s, NOW())
                    """, ('password_reset', user['member_id'], 'Password reset via code'))

                    conn.commit()
                    send_email(email, "Password Changed", "Your password has been updated.")
                    flash("Password updated. You may now log in.", "success")
                    return redirect(url_for('login'))

    return render_template("reset_password_code.html")

@app.route('/guest_flight_report', methods=['GET', 'POST'])
@login_required
def guest_flight_report():
    cursor = db.cursor()

    # Default date range: last 7 days
    today = datetime.now().date()
    default_start = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    default_end = today.strftime('%Y-%m-%d')

    start_date = request.form.get('start_date', default_start)
    end_date = request.form.get('end_date', default_end)

    flights = []
    if request.method == 'POST':
        try:
            cursor.execute("""
                SELECT 
                    f.id,
                    f.pilot,
                    f.takeoff_time,
                    f.landing_time,
                    f.flight_time,
                    f.cost,
                    f.tow_cost,
                    f.total_cost,
                    f.charge_to,
                    CONCAT(m.FirstName, ' ', m.LastName) AS member_name
                FROM flights f
                LEFT JOIN members m ON f.charge_to = m.member_id
                WHERE f.charge_to = 1 AND DATE(f.takeoff_time) BETWEEN %s AND %s AND f.deleted = 0
                ORDER BY f.takeoff_time DESC
            """, (start_date, end_date))
            flights = cursor.fetchall()
        except Exception as e:
            flash(f"Error loading report: {e}", "error")

    cursor.close()
    return render_template('guest_flight_report.html', flights=flights, start_date=start_date, end_date=end_date)

from flask import render_template, request, jsonify

@app.route("/tracks")
def track_page():
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT DISTINCT a.name, a.flarm_id
            FROM aircraft a
            JOIN ogn_positions o ON o.flarm_id = a.flarm_id
            ORDER BY a.name
        """)
        aircraft = cur.fetchall()
    return render_template("tracks.html", aircraft=aircraft)

@app.route("/api/track_data")
def track_data():
    flarm_id = request.args.get("flarm_id")
    date = request.args.get("date")
    if not date:
        return jsonify([])

    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        if flarm_id:
            cur.execute("""
                SELECT flarm_id, position_time, latitude, longitude, altitude
                FROM ogn_positions
                WHERE flarm_id = %s AND DATE(position_time) = %s
                ORDER BY position_time
            """, (flarm_id, date))
        else:
            cur.execute("""
                SELECT flarm_id, position_time, latitude, longitude, altitude
                FROM ogn_positions
                WHERE DATE(position_time) = %s
                ORDER BY flarm_id, position_time
            """, (date,))
        return jsonify(cur.fetchall())

from flask import request, Response
from datetime import datetime
import math

@app.route("/export_igc")
def export_igc():
    flarm_id = request.args.get("flarm_id")
    date = request.args.get("date")

    if not flarm_id or not date:
        return "Missing flarm_id or date", 400

    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT position_time, latitude, longitude, altitude
            FROM ogn_positions
            WHERE flarm_id = %s AND DATE(position_time) = %s
            ORDER BY position_time
        """, (flarm_id, date))
        rows = cur.fetchall()

    if not rows:
        return "No data", 404

    def igc_time(dtobj):
        return dtobj.strftime("%H%M%S")

    def igc_lat(lat):
        deg = int(abs(lat))
        min = (abs(lat) - deg) * 60
        hemi = 'N' if lat >= 0 else 'S'
        return f"{deg:02d}{min:05.2f}".replace('.', '')[:7] + hemi

    def igc_lng(lon):
        deg = int(abs(lon))
        min = (abs(lon) - deg) * 60
        hemi = 'E' if lon >= 0 else 'W'
        return f"{deg:03d}{min:05.2f}".replace('.', '')[:8] + hemi

    first_time = rows[0]["position_time"]
    igc_date = first_time.strftime("%d%m%y")

    lines = []
    lines.append("AXXXIGC_GENERATOR")
    lines.append(f"HFDTE{igc_date}")
    lines.append(f"HFPLTPILOTIN:{flarm_id}")
    lines.append("HFGTYGLIDERTYPE:UNKNOWN")
    lines.append("HFGIDGLIDERID:UNKNOWN")
    lines.append("HFDTM100GPSDATUM:WGS-84")
    lines.append("")

    for row in rows:
        t = igc_time(row["position_time"])
        lat = igc_lat(row["latitude"])
        lon = igc_lng(row["longitude"])
        alt = int(round(row["altitude"] or 0))
        lines.append(f"B{t}{lat}{lon}A{alt:05d}{alt:05d}")

    igc_text = "\n".join(lines) + "\n"
    filename = f"{flarm_id}_{date}.igc"
    return Response(
        igc_text,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

from flask import jsonify
from datetime import datetime, timedelta

@app.route("/ogn/aircraft_status.json")
def aircraft_status_json():
    today = datetime.utcnow().date()
    due_soon_cutoff = today + timedelta(days=30)

    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        # Gliders
        cursor.execute("""
            SELECT
                a.id,
                a.name,
                a.annual_due_date,
                a.grounded,
                'glider' AS aircraft_type
            FROM aircraft a
        """)
        gliders = cursor.fetchall()
        for g in gliders:
            g["icon"] = "🪂"
            g["due_soon"] = g["annual_due_date"] is not None and g["annual_due_date"] <= due_soon_cutoff
            g["oil_due"] = False  # Not tracked for gliders

        # Towplanes
        cursor.execute("""
            SELECT
                t.id,
                t.name,
                t.annual_due_date,
                t.grounded,
                t.last_oil_change_tach,
                t.next_oil_change_due,
                'towplane' AS aircraft_type
            FROM towplanes t
        """)
        towplanes = cursor.fetchall()
        for t in towplanes:
            t["icon"] = "🛩"
            t["due_soon"] = t["annual_due_date"] is not None and t["annual_due_date"] <= due_soon_cutoff
            t["oil_due"] = (
                t["last_oil_change_tach"] is not None and
                t["next_oil_change_due"] is not None and
                (t["next_oil_change_due"] - t["last_oil_change_tach"]) <= 5
            )

        return jsonify(gliders + towplanes)



@app.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    return render_template('dashboard.html')  # Include your visualizations in this template.

@app.route("/ogn/slideshow")
def ogn_slideshow():
    photo_filenames = ["photo1.jpg", "photo2.jpg"]  # from /static/photos/
    return render_template("ogn_slideshow.html", photos=photo_filenames)

from flask import render_template

@app.route("/ogn/weather_briefing")
def ogn_weather_briefing():
    return render_template("ogn_weather_briefing.html")

import requests
from flask import request, Response, abort

@app.route("/proxy/noaa")
def proxy_noaa():
    url = request.args.get("url")
    allowed_domains = ["aviationweather.gov", "radar.weather.gov", "spc.noaa.gov"]

    # Safety check
    if not url or not any(domain in url for domain in allowed_domains):
        return abort(403, "Blocked")

    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            return Response(resp.content, content_type=resp.headers.get("Content-Type", "image/png"))
        return f"Error fetching remote resource: {resp.status_code}", resp.status_code
    except Exception as e:
        return f"Error: {e}", 500


@app.context_processor
def inject_now():
        return {'now': datetime.now}

if __name__ == '__main__':
    app.run(host='0.0.0.0' , port=5001, debug=True) 
