import os
import time
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, jsonify, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta, date
import json
import secrets
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Configure application
app = Flask(__name__)
# Use a more secure secret key, ideally from environment variables
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(24).hex())
app.config["UPLOAD_FOLDER"] = "static/uploads"

# Ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Configure session to use filesystem   
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Initialize database
db = SQL("sqlite:///database.db")   

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Define User Model
class User(UserMixin):
    def __init__(self, user_id, username, role):
        self.id = user_id
        self.username = username
        self.role = role

    def get_id(self):
        return str(self.id)  # Flask-Login expects a string return

@login_manager.user_loader
def load_user(user_id):
    """Flask-Login callback to load user"""
    try:
        user = db.execute("SELECT * FROM users WHERE id = ?", int(user_id))
        if user:
            return User(user[0]["id"], user[0]["username"], user[0]["role"])
        return None  # Return None if no user found
    except (ValueError, TypeError):
        # Handle case where user_id can't be converted to int
        return None

# Add a custom filter for date formatting
@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    if fmt is None:
        fmt = '%Y-%m-%d'
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d')
    return date.strftime(fmt)

# Add a custom filter for JSON serialization
@app.template_filter('tojson')
def _tojson_filter(obj):
    return json.dumps(obj)

########################### Routes for all USERS ##################################

@app.route("/")
def index():
    """Show the home page or redirect to appropriate dashboard"""
    
    # If user is logged in, redirect to appropriate dashboard based on role
    if current_user.is_authenticated:
        if current_user.role == "owner" or current_user.role == "admin":
            return redirect("/admin/home")
        elif current_user.role == "instructor":
            return redirect("/instructor/calendar")
        elif current_user.role == "customer":
            return redirect("/customer/my_lessons")
    
    # If not logged in or role not recognized, show the public home page
    else:
        flash("Invalid role", "danger")
        return redirect("/logout")

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Allow users to edit their own profile information"""
    
    # Get the current user's information
    user_info = db.execute(
        """
        SELECT u.id, u.username, u.role, ui.* 
        FROM users u 
        JOIN user_info ui ON u.id = ui.id 
        WHERE u.id = ?
        """, 
        current_user.id
    )
    
    if not user_info:
        flash("Error retrieving user information", "danger")
        return redirect("/")
    
    user_info = user_info[0]
    
    # Handle form submission
    if request.method == "POST":
        email = request.form.get("email")
        phone = request.form.get("phone")
        birthday = request.form.get("birthday")
        ski_type = request.form.get("ski_type")
        
        # Handle empty email - convert empty string to None
        if email == "":
            email = None
        
        # If email is provided, check if it's already in use by another user
        if email is not None:
            existing_email = db.execute(
                "SELECT id FROM user_info WHERE email = ? AND id != ?", 
                email, current_user.id
            )
            
            if existing_email:
                flash("Email is already in use by another user", "danger")
                return redirect("/settings")
        
        # Handle profile picture upload
        profile_picture_path = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                # Check if the file is an allowed image type
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                
                if file_ext not in allowed_extensions:
                    flash("Only image files (PNG, JPG, JPEG, GIF) are allowed for profile pictures", "danger")
                    return redirect("/settings")
                
                # Create a unique filename to prevent overwriting
                filename = secure_filename(f"user_{current_user.id}_{int(time.time())}.{file_ext}")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                
                # Save the file
                file.save(filepath)
                
                # Store the relative path in the database
                profile_picture_path = f"/static/uploads/{filename}"
                
                # Delete old profile picture if it exists
                old_picture = user_info["profile_picture"]
                if old_picture and old_picture != profile_picture_path:
                    old_file_path = os.path.join(os.getcwd(), old_picture.lstrip('/'))
                    try:
                        if os.path.exists(old_file_path):
                            os.remove(old_file_path)
                    except Exception as e:
                        print(f"Error removing old profile picture: {e}")
        
        try:
            # Update user_info table
            if profile_picture_path:
                db.execute(
                    "UPDATE user_info SET email = ?, phone = ?, profile_picture = ?, birthday = ?, ski_type = ? WHERE id = ?",
                    email, phone, profile_picture_path, birthday, ski_type, current_user.id
                )
            else:
                db.execute(
                    "UPDATE user_info SET email = ?, phone = ?, birthday = ?, ski_type = ? WHERE id = ?",
                    email, phone, birthday, ski_type, current_user.id
                )
            
            flash("Your profile has been updated successfully!", "success")
        except Exception as e:
            flash(f"Error updating profile: {str(e)}", "danger")
        
        return redirect("/settings")
    
    # Determine which settings template to use based on user role
    if current_user.role == "owner":
        template = "owner/settings.html"
    elif current_user.role == "admin":
        template = "admin/settings.html"
    elif current_user.role == "instructor":
        template = "instructor/settings.html"
    elif current_user.role == "customer":
        template = "customer/settings.html"
    else:
        flash("Something went wrong", "danger")
        return redirect("/logout")
    
    return render_template(template, user=user_info)

@app.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Allow users to change their password"""
    
    # Get form data
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    # Validate input
    if not current_password or not new_password or not confirm_password:
        flash("All password fields are required", "danger")
        return redirect("/settings")
    
    # Check if new password and confirmation match
    if new_password != confirm_password:
        flash("New password and confirmation do not match", "danger")
        return redirect("/settings")
    
    # Check password length
    if len(new_password) < 8:
        flash("Password must be at least 8 characters long", "danger")
        return redirect("/settings")
    
    # Get the user's current password hash
    user = db.execute("SELECT hash FROM users WHERE id = ?", current_user.id)
    
    if not user:
        flash("User not found", "danger")
        return redirect("/settings")
    
    # Verify current password
    if not check_password_hash(user[0]["hash"], current_password):
        flash("Current password is incorrect", "danger")
        return redirect("/settings")
    
    # Generate hash for new password
    new_hash = generate_password_hash(new_password)
    
    try:
        # Update password in database
        db.execute("UPDATE users SET hash = ? WHERE id = ?", new_hash, current_user.id)
        flash("Your password has been updated successfully!", "success")
    except Exception as e:
        flash(f"Error updating password: {str(e)}", "danger")
    
    return redirect("/settings")

########################### Customer routes ##################################

@app.route("/customer/book_lesson", methods=["GET", "POST"])
@login_required
def customer_book_lesson():
    """Book a lesson with an instructor"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    if request.method == "POST":
        instructor_id = request.form.get("instructor_id")
        date = request.form.get("date")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        notes = request.form.get("notes", "")
        
        # Validate input
        if not instructor_id or not date or not start_time or not end_time:
            flash("Please fill in all required fields", "danger")
            return redirect("/customer/book_lesson")
        
        # Validate date format
        try:
            lesson_date = datetime.strptime(date, "%Y-%m-%d").date()
            if lesson_date < datetime.now().date():
                flash("Lesson date must be in the future", "danger")
                return redirect("/customer/book_lesson")
        except ValueError:
            flash("Invalid date format", "danger")
            return redirect("/customer/book_lesson")
        
        # Validate time format and logic
        try:
            start_time_obj = datetime.strptime(start_time, "%H:%M").time()
            end_time_obj = datetime.strptime(end_time, "%H:%M").time()
            
            if end_time_obj <= start_time_obj:
                flash("End time must be after start time", "danger")
                return redirect("/customer/book_lesson")
        except ValueError:
            flash("Invalid time format", "danger")
            return redirect("/customer/book_lesson")
        
        # Check if instructor exists and has instructor role
        instructor = db.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'instructor'", 
            instructor_id
        )
        
        if not instructor:
            flash("Invalid instructor selected", "danger")
            return redirect("/customer/book_lesson")
        
        # Check if the instructor has an approved open time slot for this date and time
        # This is complex because we need to consider both open and close requests
        
        # Get all approved time requests for this instructor on this date
        time_requests = db.execute(
            """
            SELECT 
                request_date, 
                start_time, 
                end_time,
                request_type,
                processed_at
            FROM time_requests 
            WHERE instructor_id = ? 
            AND status = 'approved'
            AND request_date = ?
            ORDER BY processed_at
            """,
            instructor_id, date
        )
        
        # Process time requests to determine if the requested time is available
        open_ranges = []
        
        # Process each request in chronological order
        for req in time_requests:
            # Convert times to datetime objects for easier comparison
            req_start = datetime.strptime(req["start_time"], "%H:%M").time()
            req_end = datetime.strptime(req["end_time"], "%H:%M").time()
            
            if req["request_type"] == "open":
                # Add this open time range
                new_range = {"start": req_start, "end": req_end}
                
                # Check for overlaps with existing open ranges and merge if needed
                i = 0
                while i < len(open_ranges):
                    existing = open_ranges[i]
                    
                    # If ranges overlap or are adjacent, merge them
                    if (new_range["start"] <= existing["end"] and 
                        new_range["end"] >= existing["start"]):
                        
                        new_range["start"] = min(new_range["start"], existing["start"])
                        new_range["end"] = max(new_range["end"], existing["end"])
                        
                        # Remove the existing range as it's now merged into new_range
                        open_ranges.pop(i)
                    else:
                        i += 1
                
                # Add the new (possibly merged) range
                open_ranges.append(new_range)
                
                # Sort ranges by start time
                open_ranges.sort(key=lambda x: x["start"])
                
            elif req["request_type"] == "close":
                # Handle close request
                close_start = req_start
                close_end = req_end
                
                # Create a new list for the updated open ranges
                updated_ranges = []
                
                for open_range in open_ranges:
                    # Case 1: Close range completely covers open range - skip this open range
                    if close_start <= open_range["start"] and close_end >= open_range["end"]:
                        continue
                    
                    # Case 2: Close range is completely within open range - split into two
                    elif close_start > open_range["start"] and close_end < open_range["end"]:
                        updated_ranges.append({"start": open_range["start"], "end": close_start})
                        updated_ranges.append({"start": close_end, "end": open_range["end"]})
                    
                    # Case 3: Close range overlaps with start of open range
                    elif close_start <= open_range["start"] and close_end > open_range["start"] and close_end < open_range["end"]:
                        updated_ranges.append({"start": close_end, "end": open_range["end"]})
                    
                    # Case 4: Close range overlaps with end of open range
                    elif close_start > open_range["start"] and close_start < open_range["end"] and close_end >= open_range["end"]:
                        updated_ranges.append({"start": open_range["start"], "end": close_start})
                    
                    # Case 5: No overlap - keep the open range as is
                    else:
                        updated_ranges.append(open_range)
                
                # Replace the open ranges with the updated ones
                open_ranges = updated_ranges
        
        # Check if the requested time slot is within an open range
        is_available = False
        for open_range in open_ranges:
            if start_time_obj >= open_range["start"] and end_time_obj <= open_range["end"]:
                is_available = True
                break
        
        if not is_available:
            flash("The selected instructor is not available at this time", "danger")
            return redirect("/customer/book_lesson")
        
        # Check if the instructor already has a lesson booked for this time
        existing_lessons = db.execute(
            """
            SELECT id FROM lessons
            WHERE instructor_id = ?
            AND lesson_date = ?
            AND status = 'booked'
            AND (
                (start_time <= ? AND end_time > ?) OR
                (start_time < ? AND end_time >= ?) OR
                (start_time >= ? AND end_time <= ?)
            )
            """,
            instructor_id, date,
            start_time, start_time,
            end_time, end_time,
            start_time, end_time
        )
        
        if existing_lessons:
            flash("The instructor already has a lesson booked for this time", "danger")
            return redirect("/customer/book_lesson")
        
        # Book the lesson
        db.execute(
            """
            INSERT INTO lessons
            (customer_id, instructor_id, lesson_date, start_time, end_time, notes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'booked', datetime('now'))
            """,
            current_user.id, instructor_id, date, start_time, end_time, notes
        )
        
        flash("Lesson booked successfully", "success")
        return redirect("/customer/my_lessons")
    
    # Get all instructors
    instructors = db.execute(
        """
        SELECT 
            users.id, 
            user_info.name, 
            user_info.surname, 
            users.username,
            user_info.profile_picture
        FROM users 
        JOIN user_info ON users.id = user_info.id
        WHERE users.role = 'instructor'
        ORDER BY user_info.name, user_info.surname
        """
    )
    
    return render_template(
        "customer/book_lesson.html",
        instructors=instructors
    )

@app.route("/customer/get_available_times_for_date", methods=["GET"])
@login_required
def get_available_times_for_date():
    """API endpoint to get available times for a specific date (any instructor)"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 403
    
    date = request.args.get("date")
    
    if not date:
        return jsonify({"error": "Missing date parameter"}), 400
    
    # Get all instructors with open time requests for this date
    instructors_with_open_times = db.execute(
        """
        SELECT DISTINCT instructor_id
        FROM time_requests
        WHERE request_date = ?
        AND status = 'approved'
        AND request_type = 'open'
        """,
        date
    )
    
    # For each instructor, get their available time slots
    all_available_times = []
    
    for instructor in instructors_with_open_times:
        instructor_id = instructor["instructor_id"]
        
        # Get all approved time requests for this instructor on this date
        time_requests = db.execute(
            """
            SELECT 
                start_time, 
                end_time,
                request_type,
                processed_at
            FROM time_requests 
            WHERE instructor_id = ? 
            AND status = 'approved'
            AND request_date = ?
            ORDER BY processed_at
            """,
            instructor_id, date
        )
        
        # Process time requests to determine open time ranges
        open_ranges = []
        
        # Process each request in chronological order
        for req in time_requests:
            # Convert times to datetime objects for easier comparison
            req_start = datetime.strptime(req["start_time"], "%H:%M").time()
            req_end = datetime.strptime(req["end_time"], "%H:%M").time()
            
            if req["request_type"] == "open":
                # Add this open time range
                new_range = {"start": req_start, "end": req_end}
                
                # Check for overlaps with existing open ranges and merge if needed
                i = 0
                while i < len(open_ranges):
                    existing = open_ranges[i]
                    
                    # If ranges overlap or are adjacent, merge them
                    if (new_range["start"] <= existing["end"] and 
                        new_range["end"] >= existing["start"]):
                        
                        new_range["start"] = min(new_range["start"], existing["start"])
                        new_range["end"] = max(new_range["end"], existing["end"])
                        
                        # Remove the existing range as it's now merged into new_range
                        open_ranges.pop(i)
                    else:
                        i += 1
                
                # Add the new (possibly merged) range
                open_ranges.append(new_range)
                
                # Sort ranges by start time
                open_ranges.sort(key=lambda x: x["start"])
                
            elif req["request_type"] == "close":
                # Handle close request
                close_start = req_start
                close_end = req_end
                
                # Create a new list for the updated open ranges
                updated_ranges = []
                
                for open_range in open_ranges:
                    # Case 1: Close range completely covers open range - skip this open range
                    if close_start <= open_range["start"] and close_end >= open_range["end"]:
                        continue
                    
                    # Case 2: Close range is completely within open range - split into two
                    elif close_start > open_range["start"] and close_end < open_range["end"]:
                        updated_ranges.append({"start": open_range["start"], "end": close_start})
                        updated_ranges.append({"start": close_end, "end": open_range["end"]})
                    
                    # Case 3: Close range overlaps with start of open range
                    elif close_start <= open_range["start"] and close_end > open_range["start"] and close_end < open_range["end"]:
                        updated_ranges.append({"start": close_end, "end": open_range["end"]})
                    
                    # Case 4: Close range overlaps with end of open range
                    elif close_start > open_range["start"] and close_start < open_range["end"] and close_end >= open_range["end"]:
                        updated_ranges.append({"start": open_range["start"], "end": close_start})
                    
                    # Case 5: No overlap - keep the open range as is
                    else:
                        updated_ranges.append(open_range)
                
                # Replace the open ranges with the updated ones
                open_ranges = updated_ranges
        
        # Get existing lessons for this instructor on this date
        existing_lessons = db.execute(
            """
            SELECT start_time, end_time
            FROM lessons
            WHERE instructor_id = ?
            AND lesson_date = ?
            AND status = 'booked'
            ORDER BY start_time
            """,
            instructor_id, date
        )
        
        # Remove times that are already booked
        for lesson in existing_lessons:
            lesson_start = datetime.strptime(lesson["start_time"], "%H:%M").time()
            lesson_end = datetime.strptime(lesson["end_time"], "%H:%M").time()
            
            updated_ranges = []
            
            for open_range in open_ranges:
                # Case 1: Lesson completely covers open range - skip this open range
                if lesson_start <= open_range["start"] and lesson_end >= open_range["end"]:
                    continue
                
                # Case 2: Lesson is completely within open range - split into two
                elif lesson_start > open_range["start"] and lesson_end < open_range["end"]:
                    updated_ranges.append({"start": open_range["start"], "end": lesson_start})
                    updated_ranges.append({"start": lesson_end, "end": open_range["end"]})
                
                # Case 3: Lesson overlaps with start of open range
                elif lesson_start <= open_range["start"] and lesson_end > open_range["start"] and lesson_end < open_range["end"]:
                    updated_ranges.append({"start": lesson_end, "end": open_range["end"]})
                
                # Case 4: Lesson overlaps with end of open range
                elif lesson_start > open_range["start"] and lesson_start < open_range["end"] and lesson_end >= open_range["end"]:
                    updated_ranges.append({"start": open_range["start"], "end": lesson_start})
                
                # Case 5: No overlap - keep the open range as is
                else:
                    updated_ranges.append(open_range)
            
            # Replace the open ranges with the updated ones
            open_ranges = updated_ranges
        
        # Create 1-hour slots within each open range
        for open_range in open_ranges:
            start = open_range["start"]
            end = open_range["end"]
            
            # Convert to datetime for easier arithmetic
            start_dt = datetime.combine(datetime.today(), start)
            end_dt = datetime.combine(datetime.today(), end)
            
            # Create 1-hour slots
            current = start_dt
            while current + timedelta(hours=1) <= end_dt:
                slot_start = current.time()
                slot_end = (current + timedelta(hours=1)).time()
                
                # Format times for display
                start_str = slot_start.strftime("%H:%M")
                end_str = slot_end.strftime("%H:%M")
                display = f"{slot_start.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
                
                # Check if this time slot is already in the list
                existing = next((t for t in all_available_times if t["start_time"] == start_str and t["end_time"] == end_str), None)
                
                if not existing:
                    all_available_times.append({
                        "start_time": start_str,
                        "end_time": end_str,
                        "display": display
                    })
                
                current += timedelta(minutes=30)  # 30-minute increments
    
    # Sort by start time
    all_available_times.sort(key=lambda x: x["start_time"])
    
    return jsonify({"available_times": all_available_times})

@app.route("/customer/get_available_instructors", methods=["GET"])
@login_required
def get_available_instructors():
    """API endpoint to get available instructors for a specific date and time"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 403
    
    date = request.args.get("date")
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")
    
    if not date or not start_time or not end_time:
        return jsonify({"error": "Missing parameters"}), 400
    
    # Get all instructors
    instructors = db.execute(
        """
        SELECT 
            users.id, 
            user_info.name, 
            user_info.surname, 
            users.username,
            user_info.profile_picture
        FROM users 
        JOIN user_info ON users.id = user_info.id
        WHERE users.role = 'instructor'
        ORDER BY user_info.name, user_info.surname
        """
    )
    
    available_instructors = []
    
    # Check each instructor's availability
    for instructor in instructors:
        # Get all approved time requests for this instructor on this date
        time_requests = db.execute(
            """
            SELECT 
                start_time, 
                end_time,
                request_type,
                processed_at
            FROM time_requests 
            WHERE instructor_id = ? 
            AND status = 'approved'
            AND request_date = ?
            ORDER BY processed_at
            """,
            instructor["id"], date
        )
        
        # Process time requests to determine open time ranges
        open_ranges = []
        
        # Process each request in chronological order
        for req in time_requests:
            # Convert times to datetime objects for easier comparison
            req_start = datetime.strptime(req["start_time"], "%H:%M").time()
            req_end = datetime.strptime(req["end_time"], "%H:%M").time()
            
            if req["request_type"] == "open":
                # Add this open time range
                new_range = {"start": req_start, "end": req_end}
                
                # Check for overlaps with existing open ranges and merge if needed
                i = 0
                while i < len(open_ranges):
                    existing = open_ranges[i]
                    
                    # If ranges overlap or are adjacent, merge them
                    if (new_range["start"] <= existing["end"] and 
                        new_range["end"] >= existing["start"]):
                        
                        new_range["start"] = min(new_range["start"], existing["start"])
                        new_range["end"] = max(new_range["end"], existing["end"])
                        
                        # Remove the existing range as it's now merged into new_range
                        open_ranges.pop(i)
                    else:
                        i += 1
                
                # Add the new (possibly merged) range
                open_ranges.append(new_range)
                
                # Sort ranges by start time
                open_ranges.sort(key=lambda x: x["start"])
                
            elif req["request_type"] == "close":
                # Handle close request
                close_start = req_start
                close_end = req_end
                
                # Create a new list for the updated open ranges
                updated_ranges = []
                
                for open_range in open_ranges:
                    # Case 1: Close range completely covers open range - skip this open range
                    if close_start <= open_range["start"] and close_end >= open_range["end"]:
                        continue
                    
                    # Case 2: Close range is completely within open range - split into two
                    elif close_start > open_range["start"] and close_end < open_range["end"]:
                        updated_ranges.append({"start": open_range["start"], "end": close_start})
                        updated_ranges.append({"start": close_end, "end": open_range["end"]})
                    
                    # Case 3: Close range overlaps with start of open range
                    elif close_start <= open_range["start"] and close_end > open_range["start"] and close_end < open_range["end"]:
                        updated_ranges.append({"start": close_end, "end": open_range["end"]})
                    
                    # Case 4: Close range overlaps with end of open range
                    elif close_start > open_range["start"] and close_start < open_range["end"] and close_end >= open_range["end"]:
                        updated_ranges.append({"start": open_range["start"], "end": close_start})
                    
                    # Case 5: No overlap - keep the open range as is
                    else:
                        updated_ranges.append(open_range)
                
                # Replace the open ranges with the updated ones
                open_ranges = updated_ranges
        
        # Get existing lessons for this instructor on this date
        existing_lessons = db.execute(
            """
            SELECT start_time, end_time
            FROM lessons
            WHERE instructor_id = ?
            AND lesson_date = ?
            AND status = 'booked'
            """,
            instructor["id"], date
        )
        
        # Check if the requested time slot is available
        start_time_obj = datetime.strptime(start_time, "%H:%M").time()
        end_time_obj = datetime.strptime(end_time, "%H:%M").time()
        
        # First check if the time is within an open range
        is_in_open_range = False
        for open_range in open_ranges:
            if start_time_obj >= open_range["start"] and end_time_obj <= open_range["end"]:
                is_in_open_range = True
                break
        
        if not is_in_open_range:
            continue  # Skip this instructor
        
        # Then check if there's no overlapping lesson
        has_overlapping_lesson = False
        for lesson in existing_lessons:
            lesson_start = datetime.strptime(lesson["start_time"], "%H:%M").time()
            lesson_end = datetime.strptime(lesson["end_time"], "%H:%M").time()
            
            # Check for overlap
            if ((start_time_obj < lesson_end and end_time_obj > lesson_start) or
                (start_time_obj >= lesson_start and end_time_obj <= lesson_end)):
                has_overlapping_lesson = True
                break
        
        if not has_overlapping_lesson:
            available_instructors.append(instructor)
    
    return jsonify({"available_instructors": available_instructors})

@app.route("/customer/get_instructor_available_dates", methods=["GET"])
@login_required
def get_instructor_available_dates():
    """API endpoint to get available dates for a specific instructor"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 403
    
    instructor_id = request.args.get("instructor_id")
    year = request.args.get("year", datetime.now().year)
    month = request.args.get("month", datetime.now().month)
    
    try:
        year = int(year)
        month = int(month)
    except ValueError:
        return jsonify({"error": "Invalid year or month"}), 400
    
    if not instructor_id:
        return jsonify({"error": "Missing instructor_id parameter"}), 400
    
    # Get the first and last day of the requested month
    first_day = datetime(year, month, 1).date()
    
    # Get the last day of the month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Format dates for SQL query
    first_day_str = first_day.strftime("%Y-%m-%d")
    last_day_str = last_day.strftime("%Y-%m-%d")
    
    # Get all dates with approved open time requests
    dates_with_open_times = db.execute(
        """
        SELECT DISTINCT request_date
        FROM time_requests
        WHERE instructor_id = ?
        AND status = 'approved'
        AND request_type = 'open'
        AND request_date BETWEEN ? AND ?
        ORDER BY request_date
        """,
        instructor_id, first_day_str, last_day_str
    )
    
    # Convert to list of date strings
    available_dates = []
    
    for date_row in dates_with_open_times:
        date_str = date_row["request_date"]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Format for display
        display_date = date_obj.strftime("%A, %b %d, %Y")
        
        available_dates.append({
            "date": date_str,
            "display": display_date,
            "available": True
        })
    
    return jsonify({"available_dates": available_dates})

@app.route("/customer/get_available_dates", methods=["GET"])
@login_required
def get_available_dates():
    """API endpoint to get dates with available instructors"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 403
    
    year = request.args.get("year", datetime.now().year)
    month = request.args.get("month", datetime.now().month)
    
    try:
        year = int(year)
        month = int(month)
    except ValueError:
        return jsonify({"error": "Invalid year or month"}), 400
    
    # Get the first and last day of the requested month
    first_day = datetime(year, month, 1).date()
    
    # Get the last day of the month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Format dates for SQL query
    first_day_str = first_day.strftime("%Y-%m-%d")
    last_day_str = last_day.strftime("%Y-%m-%d")
    
    # Get all dates with approved open time requests
    dates_with_open_times = db.execute(
        """
        SELECT DISTINCT request_date
        FROM time_requests
        WHERE status = 'approved'
        AND request_type = 'open'
        AND request_date BETWEEN ? AND ?
        ORDER BY request_date
        """,
        first_day_str, last_day_str
    )
    
    # Convert to list of date strings
    available_dates = []
    
    for date_row in dates_with_open_times:
        date_str = date_row["request_date"]
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Format for display
        display_date = date_obj.strftime("%A, %b %d, %Y")
        
        available_dates.append({
            "date": date_str,
            "display": display_date,
            "available": True
        })
    
    return jsonify({"available_dates": available_dates})

@app.route("/customer/get_instructor_available_times", methods=["GET"])
@login_required
def get_instructor_available_times():
    """API endpoint to get available times for a specific instructor on a date"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 403
    
    instructor_id = request.args.get("instructor_id")
    date = request.args.get("date")
    
    if not instructor_id or not date:
        return jsonify({"error": "Missing parameters"}), 400
    
    # Get all approved time requests for this instructor on this date
    time_requests = db.execute(
        """
        SELECT 
            start_time, 
            end_time,
            request_type,
            processed_at
        FROM time_requests 
        WHERE instructor_id = ? 
        AND status = 'approved'
        AND request_date = ?
        ORDER BY processed_at
        """,
        instructor_id, date
    )
    
    # Process time requests to determine open time ranges
    open_ranges = []
    
    # Process each request in chronological order
    for req in time_requests:
        # Convert times to datetime objects for easier comparison
        req_start = datetime.strptime(req["start_time"], "%H:%M").time()
        req_end = datetime.strptime(req["end_time"], "%H:%M").time()
        
        if req["request_type"] == "open":
            # Add this open time range
            new_range = {"start": req_start, "end": req_end}
            
            # Check for overlaps with existing open ranges and merge if needed
            i = 0
            while i < len(open_ranges):
                existing = open_ranges[i]
                
                # If ranges overlap or are adjacent, merge them
                if (new_range["start"] <= existing["end"] and 
                    new_range["end"] >= existing["start"]):
                    
                    new_range["start"] = min(new_range["start"], existing["start"])
                    new_range["end"] = max(new_range["end"], existing["end"])
                    
                    # Remove the existing range as it's now merged into new_range
                    open_ranges.pop(i)
                else:
                    i += 1
            
            # Add the new (possibly merged) range
            open_ranges.append(new_range)
            
            # Sort ranges by start time
            open_ranges.sort(key=lambda x: x["start"])
            
        elif req["request_type"] == "close":
            # Handle close request
            close_start = req_start
            close_end = req_end
            
            # Create a new list for the updated open ranges
            updated_ranges = []
            
            for open_range in open_ranges:
                # Case 1: Close range completely covers open range - skip this open range
                if close_start <= open_range["start"] and close_end >= open_range["end"]:
                    continue
                
                # Case 2: Close range is completely within open range - split into two
                elif close_start > open_range["start"] and close_end < open_range["end"]:
                    updated_ranges.append({"start": open_range["start"], "end": close_start})
                    updated_ranges.append({"start": close_end, "end": open_range["end"]})
                
                # Case 3: Close range overlaps with start of open range
                elif close_start <= open_range["start"] and close_end > open_range["start"] and close_end < open_range["end"]:
                    updated_ranges.append({"start": close_end, "end": open_range["end"]})
                
                # Case 4: Close range overlaps with end of open range
                elif close_start > open_range["start"] and close_start < open_range["end"] and close_end >= open_range["end"]:
                    updated_ranges.append({"start": open_range["start"], "end": close_start})
                
                # Case 5: No overlap - keep the open range as is
                else:
                    updated_ranges.append(open_range)
            
            # Replace the open ranges with the updated ones
            open_ranges = updated_ranges
    
    # Get existing lessons for this instructor on this date
    existing_lessons = db.execute(
        """
        SELECT start_time, end_time
        FROM lessons
        WHERE instructor_id = ?
        AND lesson_date = ?
        AND status = 'booked'
        ORDER BY start_time
        """,
        instructor_id, date
    )
    
    # Remove times that are already booked
    for lesson in existing_lessons:
        lesson_start = datetime.strptime(lesson["start_time"], "%H:%M").time()
        lesson_end = datetime.strptime(lesson["end_time"], "%H:%M").time()
        
        updated_ranges = []
        
        for open_range in open_ranges:
            # Case 1: Lesson completely covers open range - skip this open range
            if lesson_start <= open_range["start"] and lesson_end >= open_range["end"]:
                continue
            
            # Case 2: Lesson is completely within open range - split into two
            elif lesson_start > open_range["start"] and lesson_end < open_range["end"]:
                updated_ranges.append({"start": open_range["start"], "end": lesson_start})
                updated_ranges.append({"start": lesson_end, "end": open_range["end"]})
            
            # Case 3: Lesson overlaps with start of open range
            elif lesson_start <= open_range["start"] and lesson_end > open_range["start"] and lesson_end < open_range["end"]:
                updated_ranges.append({"start": lesson_end, "end": open_range["end"]})
            
            # Case 4: Lesson overlaps with end of open range
            elif lesson_start > open_range["start"] and lesson_start < open_range["end"] and lesson_end >= open_range["end"]:
                updated_ranges.append({"start": open_range["start"], "end": lesson_start})
            
            # Case 5: No overlap - keep the open range as is
            else:
                updated_ranges.append(open_range)
        
        # Replace the open ranges with the updated ones
        open_ranges = updated_ranges
    
    # Create 1-hour slots within each open range
    available_times = []
    
    for open_range in open_ranges:
        start = open_range["start"]
        end = open_range["end"]
        
        # Convert to datetime for easier arithmetic
        start_dt = datetime.combine(datetime.today(), start)
        end_dt = datetime.combine(datetime.today(), end)
        
        # Create 1-hour slots
        current = start_dt
        while current + timedelta(hours=1) <= end_dt:
            slot_start = current.time()
            slot_end = (current + timedelta(hours=1)).time()
            
            # Format times for display
            start_str = slot_start.strftime("%H:%M")
            end_str = slot_end.strftime("%H:%M")
            display = f"{slot_start.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
            
            available_times.append({
                "start_time": start_str,
                "end_time": end_str,
                "display": display
            })
            
            current += timedelta(minutes=30)  # 30-minute increments
    
    # Sort by start time
    available_times.sort(key=lambda x: x["start_time"])
    
    return jsonify({"available_times": available_times})

@app.route("/customer/cancel_lesson", methods=["POST"])
@login_required
def cancel_lesson():
    """Cancel a booked lesson"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    lesson_id = request.form.get("lesson_id")
    
    if not lesson_id:
        flash("Invalid request", "danger")
        return redirect("/customer/my_lessons")
    
    # Check if the lesson exists and belongs to the current user
    lesson = db.execute(
        """
        SELECT id, lesson_date, start_time 
        FROM lessons 
        WHERE id = ? AND customer_id = ? AND status = 'booked'
        """,
        lesson_id, current_user.id
    )
    
    if not lesson:
        flash("Lesson not found or already cancelled", "danger")
        return redirect("/customer/my_lessons")
    
    # Check if the lesson is in the future
    lesson_date = datetime.strptime(lesson[0]["lesson_date"], "%Y-%m-%d").date()
    lesson_time = datetime.strptime(lesson[0]["start_time"], "%H:%M").time()
    lesson_datetime = datetime.combine(lesson_date, lesson_time)
    
    # Calculate cancellation policy (e.g., 24 hours in advance)
    cancellation_deadline = datetime.now() + timedelta(hours=24)
    
    if lesson_datetime < cancellation_deadline:
        flash("Lessons must be cancelled at least 24 hours in advance", "danger")
        return redirect("/customer/my_lessons")
    
    # Update the lesson status to cancelled
    db.execute(
        "UPDATE lessons SET status = 'cancelled' WHERE id = ?",
        lesson_id
    )
    
    flash("Lesson cancelled successfully", "success")
    return redirect("/customer/my_lessons")


    """API endpoint to get available times for an instructor on a specific date"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 403
    
    instructor_id = request.args.get("instructor_id")
    date = request.args.get("date")
    
    if not instructor_id or not date:
        return jsonify({"error": "Missing parameters"}), 400
    
    # Get all approved time requests for this instructor on this date
    time_requests = db.execute(
        """
        SELECT 
            request_date, 
            start_time, 
            end_time,
            request_type,
            processed_at
        FROM time_requests 
        WHERE instructor_id = ? 
        AND status = 'approved'
        AND request_date = ?
        ORDER BY processed_at
        """,
        instructor_id, date
    )
    
    # Process time requests to determine open time slots
    open_ranges = []
    
    # Process each request in chronological order
    for req in time_requests:
        # Convert times to datetime objects for easier comparison
        req_start = datetime.strptime(req["start_time"], "%H:%M").time()
        req_end = datetime.strptime(req["end_time"], "%H:%M").time()
        
        if req["request_type"] == "open":
            # Add this open time range
            new_range = {"start": req_start, "end": req_end}
            
            # Check for overlaps with existing open ranges and merge if needed
            i = 0
            while i < len(open_ranges):
                existing = open_ranges[i]
                
                # If ranges overlap or are adjacent, merge them
                if (new_range["start"] <= existing["end"] and 
                    new_range["end"] >= existing["start"]):
                    
                    new_range["start"] = min(new_range["start"], existing["start"])
                    new_range["end"] = max(new_range["end"], existing["end"])
                    
                    # Remove the existing range as it's now merged into new_range
                    open_ranges.pop(i)
                else:
                    i += 1
            
            # Add the new (possibly merged) range
            open_ranges.append(new_range)
            
            # Sort ranges by start time
            open_ranges.sort(key=lambda x: x["start"])
            
        elif req["request_type"] == "close":
            # Handle close request
            close_start = req_start
            close_end = req_end
            
            # Create a new list for the updated open ranges
            updated_ranges = []
            
            for open_range in open_ranges:
                # Case 1: Close range completely covers open range - skip this open range
                if close_start <= open_range["start"] and close_end >= open_range["end"]:
                    continue
                
                # Case 2: Close range is completely within open range - split into two
                elif close_start > open_range["start"] and close_end < open_range["end"]:
                    updated_ranges.append({"start": open_range["start"], "end": close_start})
                    updated_ranges.append({"start": close_end, "end": open_range["end"]})
                
                # Case 3: Close range overlaps with start of open range
                elif close_start <= open_range["start"] and close_end > open_range["start"] and close_end < open_range["end"]:
                    updated_ranges.append({"start": close_end, "end": open_range["end"]})
                
                # Case 4: Close range overlaps with end of open range
                elif close_start > open_range["start"] and close_start < open_range["end"] and close_end >= open_range["end"]:
                    updated_ranges.append({"start": open_range["start"], "end": close_start})
                
                # Case 5: No overlap - keep the open range as is
                else:
                    updated_ranges.append(open_range)
            
            # Replace the open ranges with the updated ones
            open_ranges = updated_ranges
    
    # Get existing lessons for this instructor on this date
    existing_lessons = db.execute(
        """
        SELECT start_time, end_time
        FROM lessons
        WHERE instructor_id = ?
        AND lesson_date = ?
        AND status = 'booked'
        ORDER BY start_time
        """,
        instructor_id, date
    )
    
    # Remove times that are already booked
    for lesson in existing_lessons:
        lesson_start = datetime.strptime(lesson["start_time"], "%H:%M").time()
        lesson_end = datetime.strptime(lesson["end_time"], "%H:%M").time()
        
        updated_ranges = []
        
        for open_range in open_ranges:
            # Case 1: Lesson completely covers open range - skip this open range
            if lesson_start <= open_range["start"] and lesson_end >= open_range["end"]:
                continue
            
            # Case 2: Lesson is completely within open range - split into two
            elif lesson_start > open_range["start"] and lesson_end < open_range["end"]:
                updated_ranges.append({"start": open_range["start"], "end": lesson_start})
                updated_ranges.append({"start": lesson_end, "end": open_range["end"]})
            
            # Case 3: Lesson overlaps with start of open range
            elif lesson_start <= open_range["start"] and lesson_end > open_range["start"] and lesson_end < open_range["end"]:
                updated_ranges.append({"start": lesson_end, "end": open_range["end"]})
            
            # Case 4: Lesson overlaps with end of open range
            elif lesson_start > open_range["start"] and lesson_start < open_range["end"] and lesson_end >= open_range["end"]:
                updated_ranges.append({"start": open_range["start"], "end": lesson_start})
            
            # Case 5: No overlap - keep the open range as is
            else:
                updated_ranges.append(open_range)
        
        # Replace the open ranges with the updated ones
        open_ranges = updated_ranges
    
    # Format the available times for the response
    available_times = []
    
    for open_range in open_ranges:
        # Create 1-hour slots within each open range
        start = open_range["start"]
        end = open_range["end"]
        
        # Convert to datetime for easier arithmetic
        start_dt = datetime.combine(datetime.today(), start)
        end_dt = datetime.combine(datetime.today(), end)
        
        # Create 1-hour slots
        current = start_dt
        while current + timedelta(hours=1) <= end_dt:
            slot_start = current.time()
            slot_end = (current + timedelta(hours=1)).time()
            
            available_times.append({
                "start_time": slot_start.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "display": f"{slot_start.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
            })
            
            current += timedelta(minutes=30)  # 30-minute increments
    
    return jsonify({"available_times": available_times})

@app.route("/customer/my_lessons", methods=["GET"])
@login_required
def customer_my_lessons():
    """View customer's upcoming and past lessons"""
    
    # Ensure the current user is a customer
    if current_user.role != "customer":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    # Get upcoming lessons
    upcoming_lessons = db.execute(
        """
        SELECT 
            lessons.id,
            lessons.lesson_date,
            lessons.start_time,
            lessons.end_time,
            lessons.status,
            lessons.notes,
            instructor.username AS instructor_username,
            instructor_info.name AS instructor_name,
            instructor_info.surname AS instructor_surname,
            instructor_info.hourly_rate
        FROM lessons
        JOIN users AS instructor ON lessons.instructor_id = instructor.id
        JOIN user_info AS instructor_info ON instructor.id = instructor_info.id
        WHERE lessons.customer_id = ?
        AND (lessons.lesson_date > CURRENT_DATE OR 
             (lessons.lesson_date = CURRENT_DATE AND lessons.end_time >= strftime('%H:%M', 'now', 'localtime')))
        AND lessons.status = 'booked'
        ORDER BY lessons.lesson_date, lessons.start_time
        """,
        current_user.id
    )
    
    # Get past lessons
    past_lessons = db.execute(
        """
        SELECT 
            lessons.id,
            lessons.lesson_date,
            lessons.start_time,
            lessons.end_time,
            lessons.status,
            lessons.notes,
            instructor.username AS instructor_username,
            instructor_info.name AS instructor_name,
            instructor_info.surname AS instructor_surname,
            instructor_info.hourly_rate
        FROM lessons
        JOIN users AS instructor ON lessons.instructor_id = instructor.id
        JOIN user_info AS instructor_info ON instructor.id = instructor_info.id
        WHERE lessons.customer_id = ?
        AND (lessons.lesson_date < CURRENT_DATE OR 
             (lessons.lesson_date = CURRENT_DATE AND lessons.end_time < strftime('%H:%M', 'now', 'localtime'))
             OR lessons.status IN ('completed', 'cancelled', 'no-show'))
        ORDER BY lessons.lesson_date DESC, lessons.start_time DESC
        LIMIT 20
        """,
        current_user.id
    )
    
    return render_template(
        "customer/my_lessons.html",
        upcoming_lessons=upcoming_lessons,
        past_lessons=past_lessons
    )

########################### Instructor routes ##################################

@app.route("/instructor/request_time", methods=["POST"])
@login_required
def  request_time():
    """Request time off or additional availability"""
    
    # Ensure the current user is an instructor
    if current_user.role != "instructor":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    # Check for client-side validation errors
    validation_error = request.form.get("validation_error")
    validation_message = request.form.get("validation_message")
    
    if validation_error == "1" and validation_message:
        flash(validation_message, "danger")
        return redirect("/instructor/calendar")
    
    # Get form data
    request_date = request.form.get("request_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    request_type = request.form.get("request_type")
   
    # Validate form data
    if not request_date or not start_time or not end_time or not request_type:
        flash("All fields are required", "danger")
        return redirect("/instructor/calendar")
    
    # Check if request date is in the future
    if request_date < datetime.now().strftime("%Y-%m-%d"):
        flash("Request date must be in the future", "danger")
        return redirect("/instructor/calendar")
   
    # Check if end time is after start time
    if start_time >= end_time:
        flash("End time must be after start time", "danger")
        return redirect("/instructor/calendar")
    
    # Check if request type is valid
    if request_type not in ["open", "close"]:
        flash("Invalid request type", "danger")
        return redirect("/instructor/calendar")
    
    # Check if there are any existing lessons during this time
    existing_lessons = db.execute(
        """
        SELECT * FROM lessons
        WHERE instructor_id = ? AND lesson_date = ? AND status != 'cancelled'
        AND ((start_time <= ? AND end_time > ?) OR (start_time < ? AND end_time >= ?) OR (start_time >= ? AND end_time <= ?))
        """,
        current_user.id, request_date, start_time, start_time, end_time, end_time, start_time, end_time
    )
    
    if existing_lessons:
        flash("You have lessons scheduled during this time. Please choose a different time.", "danger")
        return redirect("/instructor/calendar")
    
    # Check if there's an existing time request for this date and time
    existing_request = db.execute(
        """
        SELECT * FROM time_requests
        WHERE instructor_id = ? AND request_date = ? AND status = 'pending'
        AND ((start_time <= ? AND end_time > ?) OR (start_time < ? AND end_time >= ?) OR (start_time >= ? AND end_time <= ?))
        """,
        current_user.id, request_date, start_time, start_time, end_time, end_time, start_time, end_time
    )
        
    if existing_request:
        flash("You already have a pending request for this time. Please wait for it to be processed.", "danger")
        return redirect("/instructor/calendar")
    
    # Add the time request
    db.execute(
        """
        INSERT INTO time_requests (instructor_id, request_date, start_time, end_time, request_type, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
        """,
        current_user.id, request_date, start_time, end_time, request_type
    )
            
    flash("Time request submitted successfully. An admin will review your request.", "success")
    return redirect("/instructor/calendar")

@app.route("/instructor/cancel_time_request", methods=["POST"])
@login_required
def cancel_time_request():
    """Cancel a pending time request"""
    
    # Ensure the current user is an instructor
    if current_user.role != "instructor":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    # Get request ID from form
    request_id = request.form.get("request_id")
    
    if not request_id:
        flash("Invalid request", "danger")
        return redirect("/instructor/calendar")
    
    # Check if the request exists and belongs to the current user
    time_request = db.execute(
        "SELECT * FROM time_requests WHERE id = ? AND instructor_id = ?",
        request_id, current_user.id
    )
    
    if not time_request:
        flash("Request not found or you don't have permission to cancel it", "danger")
        return redirect("/instructor/calendar")
    
    # Check if the request is still pending
    if time_request[0]["status"] != "pending":
        flash("Only pending requests can be cancelled", "danger")
        return redirect("/instructor/calendar")
    
    # Delete the request
    db.execute("DELETE FROM time_requests WHERE id = ?", request_id)
    
    flash("Time request cancelled successfully", "success")
    return redirect("/instructor/calendar")

@app.route("/instructor/calendar")
@login_required
def instructor_calendar():
    """Show instructor's calendar"""
    
    # Ensure the current user is an instructor
    if current_user.role != "instructor":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    # Get calendar data for the current month
    today = datetime.now()
    year = today.year
    month = today.month  # 1-based month (January = 1)
    
    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    
    # Get last day of month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Find the first upcoming day with lessons
    next_lesson_day = db.execute(
        """
        SELECT 
            lesson_date
        FROM lessons
        WHERE instructor_id = ? 
        AND lesson_date >= CURRENT_DATE
        AND status != 'cancelled'
        ORDER BY lesson_date
        LIMIT 1
        """,
        current_user.id
    )
    
    # If no upcoming lessons, default to today
    if next_lesson_day:
        next_day = datetime.strptime(next_lesson_day[0]["lesson_date"], "%Y-%m-%d").date()
    else:
        next_day = today.date()
    
    # Get instructor availabilities for the month (approved "open" time requests)
    availabilities = db.execute(
        """
        SELECT 
            id,
            request_date as availability_date,
            start_time,
            end_time
        FROM time_requests
        WHERE instructor_id = ? 
        AND request_date BETWEEN ? AND ?
        AND request_type = 'open'
        AND status = 'approved'
        ORDER BY request_date, start_time
        """,
        current_user.id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get instructor unavailabilities for the month (approved "close" time requests)
    unavailabilities = db.execute(
        """
        SELECT 
            id,
            request_date as unavailable_date,
            start_time,
            end_time
        FROM time_requests
        WHERE instructor_id = ? 
        AND request_date BETWEEN ? AND ?
        AND request_type = 'close'
        AND status = 'approved'
        ORDER BY request_date, start_time
        """,
        current_user.id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get detailed lessons for the next day with lessons
    detailed_lessons = db.execute(
        """
        SELECT 
            l.id,
            l.lesson_date,
            l.start_time,
            l.end_time,
            l.status,
            l.notes,
            u.username as customer_name,
            ui.email as customer_email,
            ui.phone as customer_phone,
            ui.name as customer_first_name,
            ui.surname as customer_last_name,
            ui.birthday as customer_birthday,
            ui.ski_type as customer_ski_type
        FROM lessons l
        JOIN users u ON l.customer_id = u.id
        LEFT JOIN user_info ui ON u.id = ui.id
        WHERE l.instructor_id = ? 
        AND l.lesson_date = ?
        AND l.status != 'cancelled'
        ORDER BY l.start_time
        """,
        current_user.id, next_day.strftime("%Y-%m-%d")
    )
    
    # Get all lessons for the month with detailed info (for monthly calendar view)
    lessons = db.execute(
        """
        SELECT 
            l.id,
            l.lesson_date,
            l.start_time,
            l.end_time,
            l.status,
            l.notes,
            u.username as customer_name,
            ui.email as customer_email,
            ui.phone as customer_phone,
            ui.name as customer_first_name,
            ui.surname as customer_last_name,
            ui.birthday as customer_birthday,
            ui.ski_type as customer_ski_type
        FROM lessons l
        JOIN users u ON l.customer_id = u.id
        LEFT JOIN user_info ui ON u.id = ui.id
        WHERE l.instructor_id = ? 
        AND l.lesson_date BETWEEN ? AND ?
        AND l.status != 'cancelled'
        ORDER BY l.lesson_date, l.start_time
        """,
        current_user.id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get pending time requests
    pending_requests = db.execute(
        """
        SELECT 
            id,
            request_date,
            start_time,
            end_time,
            request_type,
            status,
            created_at
        FROM time_requests
        WHERE instructor_id = ?
        ORDER BY request_date, start_time
        """,
        current_user.id
    )
    
    # Get time slots for dropdown
    time_slots = []
    start_time = datetime.strptime("08:00", "%H:%M")
    end_time = datetime.strptime("23:00", "%H:%M")
    interval = timedelta(minutes=30)
    
    current_time = start_time
    while current_time <= end_time:
        time_slots.append(current_time.strftime("%H:%M"))
        current_time += interval
    
    # Get working hours for each day of the week
    working_hours = db.execute("SELECT * FROM working_hours ORDER BY day_of_week")
    
    # Create a dictionary for easier access in template
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours_by_day = {}
    
    for day in range(7):
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": "09:00",
            "close_time": "17:00",
            "is_open": True
        }
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    # Get current month for calendar
    current_month = today.strftime("%B %Y")
    
    # Format the next day for display
    day_name = next_day.strftime("%A")  # Get day name (Monday, Tuesday, etc.)
    formatted_date = next_day.strftime("%B %d, %Y")  # Format like "January 1, 2023"
    next_day_info = {
        "date": next_day.strftime("%Y-%m-%d"),
        "day_name": day_name,
        "formatted_date": formatted_date,
        "has_lessons": len(detailed_lessons) > 0
    }
    
    return render_template(
        "instructor/calendar.html",
        availabilities=availabilities,
        unavailabilities=unavailabilities,
        lessons=lessons,
        detailed_lessons=detailed_lessons,
        next_day=next_day_info,
        pending_requests=pending_requests,
        time_slots=time_slots,
        today=today.strftime("%Y-%m-%d"),
        working_hours=hours_by_day,
        current_month=current_month,
        current_year=year,
        current_month_num=month
    )

@app.route("/instructor/get_calendar")
@login_required
def get_instructor_calendar():
    """API endpoint to get instructor's calendar data"""
    
    # Ensure the current user is an instructor
    if current_user.role != "instructor":
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get year and month from request
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    
    if not year or not month:
        # Default to current month
        today = datetime.now()
        year = today.year
        month = today.month
    
    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    
    # Get last day of month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Get instructor availabilities for the month (approved "open" time requests)
    availabilities = db.execute(
        """
        SELECT 
            id,
            request_date as availability_date,
            start_time,
            end_time
        FROM time_requests
        WHERE instructor_id = ? 
        AND request_date BETWEEN ? AND ?
        AND request_type = 'open'
        AND status = 'approved'
        ORDER BY request_date, start_time
        """,
        current_user.id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get instructor unavailabilities for the month (approved "close" time requests)
    unavailabilities = db.execute(
        """
        SELECT 
            id,
            request_date as unavailable_date,
            start_time,
            end_time
        FROM time_requests
        WHERE instructor_id = ? 
        AND request_date BETWEEN ? AND ?
        AND request_type = 'close'
        AND status = 'approved'
        ORDER BY request_date, start_time
        """,
        current_user.id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get lessons for the instructor for the month
    lessons = db.execute(
        """
        SELECT 
            l.id,
            l.lesson_date,
            l.start_time,
            l.end_time,
            l.status,
            u.username as customer_name,
            ui.name as customer_first_name,
            ui.surname as customer_last_name,
            ui.email as customer_email,
            ui.phone as customer_phone,
            ui.birthday as customer_birthday,
            ui.ski_type as customer_ski_type
        FROM lessons l
        JOIN users u ON l.customer_id = u.id
        LEFT JOIN user_info ui ON u.id = ui.id
        WHERE l.instructor_id = ? 
        AND l.lesson_date BETWEEN ? AND ?
        AND l.status != 'cancelled'
        ORDER BY l.lesson_date, l.start_time
        """,
        current_user.id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get working hours for each day of the week
    working_hours = db.execute("SELECT * FROM working_hours ORDER BY day_of_week")
    
    # Create a dictionary for easier access in the frontend
    hours_by_day = {}
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    # Return the data as JSON
    return jsonify({
        "availabilities": availabilities,
        "unavailabilities": unavailabilities,
        "lessons": lessons,
        "working_hours": hours_by_day,
        "year": year,
        "month": month
    })

@app.route("/instructor/history")
@login_required
def instructor_history():
    """Show history of all past lessons for the instructor"""
    
    # Ensure the current user is an instructor
    if current_user.role != "instructor":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    # Get current date for comparison
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Get all past lessons for this instructor
    past_lessons = db.execute(
        """
        SELECT 
            l.id, 
            l.lesson_date, 
            l.start_time, 
            l.end_time, 
            l.status,
            l.notes,
            l.created_at,
            u.id as customer_id,
            ui.name as customer_first_name,
            ui.surname as customer_last_name,
            ui.email as customer_email,
            ui.phone as customer_phone,
            ui.ski_type as customer_ski_type
        FROM lessons l
        JOIN users u ON l.customer_id = u.id
        JOIN user_info ui ON u.id = ui.id
        WHERE l.instructor_id = ?
        AND (l.lesson_date < ? OR (l.lesson_date = ? AND l.end_time < strftime('%H:%M', 'now')))
        ORDER BY l.lesson_date DESC, l.start_time DESC
        """,
        current_user.id, current_date, current_date
    )
    
    # Group lessons by month for better organization
    grouped_lessons = {}
    
    for lesson in past_lessons:
        # Convert date string to datetime object
        lesson_date = datetime.strptime(lesson["lesson_date"], "%Y-%m-%d")
        
        # Format month and year as a key
        month_year = lesson_date.strftime("%B %Y")
        
        # Add to grouped dictionary
        if month_year not in grouped_lessons:
            grouped_lessons[month_year] = []
        
        # Format date for display
        lesson["formatted_date"] = lesson_date.strftime("%A, %B %d, %Y")
        
        # Format time for display
        start_time = datetime.strptime(lesson["start_time"], "%H:%M").strftime("%I:%M %p")
        end_time = datetime.strptime(lesson["end_time"], "%H:%M").strftime("%I:%M %p")
        lesson["formatted_time"] = f"{start_time} - {end_time}"
        
        # Add to group
        grouped_lessons[month_year].append(lesson)
    
    # Get instructor info for the page header
    instructor_info = db.execute(
        """
        SELECT ui.name, ui.surname, ui.profile_picture
        FROM user_info ui
        WHERE ui.id = ?
        """,
        current_user.id
    )[0]
    
    return render_template(
        "instructor/history.html",
        grouped_lessons=grouped_lessons,
        instructor=instructor_info
    )

########################### Admin routes ##################################

@app.route("/admin/home")
@login_required
def admin_home():
    """Show admin dashboard"""
    
    # Ensure the current user is an admin or owner
    if current_user.role != "admin" and current_user.role != "owner":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    # Get all the data needed for the admin dashboard
    upcoming_lessons = db.execute(
        """
        SELECT 
            l.id,
            l.lesson_date,
            l.start_time,
            l.end_time,
            c.username as customer_name,
            i.username as instructor_name,
            l.status
        FROM lessons l
        JOIN users c ON l.customer_id = c.id
        JOIN users i ON l.instructor_id = i.id
        WHERE l.lesson_date >= CURRENT_DATE
        ORDER BY l.lesson_date, l.start_time
        LIMIT 10
        """
    )
    
    pending_time_requests = db.execute(
        """
        SELECT 
            tr.id,
            tr.request_date,
            tr.start_time,
            tr.end_time,
            tr.request_type,
            u.username as instructor_name,
            tr.created_at
        FROM time_requests tr
        JOIN users u ON tr.instructor_id = u.id
        WHERE tr.status = 'pending'
        ORDER BY tr.request_date, tr.start_time
        LIMIT 10
        """
    )
    
    # Get calendar data for the current month
    today = datetime.now()
    year = today.year
    month = today.month  # 1-based month (January = 1)
    
    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    
    # Get last day of month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Get all admins
    admins = db.execute(
        """
        SELECT 
            u.id, 
            u.username, 
            ui.name, 
            ui.surname
        FROM users u
        JOIN user_info ui ON u.id = ui.id
        WHERE u.role IN ('admin', 'owner')
        ORDER BY CASE WHEN u.id = ? THEN 0 ELSE 1 END, ui.name, ui.surname
        """,
        current_user.id
    )
    
    # Get schedules for all admins for the month
    all_admin_schedules = db.execute(
        """
        SELECT 
            a.id,
            a.admin_id,
            u.username as admin_name,
            ui.name as admin_first_name,
            ui.surname as admin_last_name,
            a.work_date,
            a.start_time,
            a.end_time
        FROM admin_schedules a
        JOIN users u ON a.admin_id = u.id
        JOIN user_info ui ON u.id = ui.id
        WHERE a.work_date BETWEEN ? AND ?
        ORDER BY a.work_date, a.start_time
        """,
        first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get lessons for the month
    lessons = db.execute(
        """
        SELECT 
            l.id,
            l.lesson_date,
            l.start_time,
            l.end_time,
            l.status,
            c.username as customer_name,
            i.username as instructor_name
        FROM lessons l
        JOIN users c ON l.customer_id = c.id
        JOIN users i ON l.instructor_id = i.id
        WHERE l.lesson_date BETWEEN ? AND ?
        AND l.status != 'cancelled'
        ORDER BY l.lesson_date, l.start_time
        """,
        first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get working hours for each day of the week
    working_hours = db.execute("SELECT * FROM working_hours ORDER BY day_of_week")
    
    # Create a dictionary for easier access in template
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours_by_day = {}
    
    for day in range(7):
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": "09:00",
            "close_time": "17:00",
            "is_open": True
        }
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    # Get current month for calendar
    current_month = today.strftime("%B %Y")
    
    return render_template(
        "admin/home.html",
        upcoming_lessons=upcoming_lessons,
        pending_time_requests=pending_time_requests,
        admins=admins,
        all_admin_schedules=all_admin_schedules,
        lessons=lessons,
        hours_by_day=hours_by_day,
        current_month=current_month,
        current_year=year,
        current_month_num=month  # This is 1-based (January = 1)
    )

@app.route("/admin/get_my_calendar")
@login_required
def get_my_calendar():
    """API endpoint to get admin's own calendar data for a specific month"""
    
    # Ensure the current user is an admin or owner
    if current_user.role != "admin" and current_user.role != "owner":
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get year and month from request
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    
    if not year or not month:
        # Default to current month
        today = datetime.now()
        year = today.year
        month = today.month
    
    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    
    # Get last day of month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Get admin schedules for the current admin for the month
    schedules = db.execute(
        """
        SELECT 
            id,
            work_date,
            start_time,
            end_time
        FROM admin_schedules
        WHERE admin_id = ? AND work_date BETWEEN ? AND ?
        ORDER BY work_date, start_time
        """,
        current_user.id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get schedules for all admins for the month (to show who else is working)
    all_admin_schedules = db.execute(
        """
        SELECT 
            a.id,
            a.admin_id,
            u.username as admin_name,
            a.work_date,
            a.start_time,
            a.end_time
        FROM admin_schedules a
        JOIN users u ON a.admin_id = u.id
        WHERE a.work_date BETWEEN ? AND ?
        ORDER BY a.work_date, a.start_time
        """,
        first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get lessons for the month
    lessons = db.execute(
        """
        SELECT 
            l.id,
            l.lesson_date,
            l.start_time,
            l.end_time,
            l.status,
            c.username as customer_name,
            i.username as instructor_name
        FROM lessons l
        JOIN users c ON l.customer_id = c.id
        JOIN users i ON l.instructor_id = i.id
        WHERE l.lesson_date BETWEEN ? AND ?
        AND l.status != 'cancelled'
        ORDER BY l.lesson_date, l.start_time
        """,
        first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get working hours for each day of the week
    working_hours = db.execute("SELECT * FROM working_hours ORDER BY day_of_week")
    
    # Create a dictionary for easier access in the frontend
    hours_by_day = {}
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    # Return the data as JSON
    return jsonify({
        "schedules": schedules,
        "all_admin_schedules": all_admin_schedules,
        "lessons": lessons,
        "working_hours": hours_by_day,
        "year": year,
        "month": month,
        "admin_name": current_user.username,
        "admin_id": current_user.id
    })

@app.route("/admin/manage_time_requests", methods=["GET", "POST"])
@login_required
def admin_time_requests():
    """Review and manage instructor time requests"""
    
    # Ensure the current user is an admin or owner
    if current_user.role not in ["admin", "owner"]:
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    if request.method == "POST":
        request_id = request.form.get("request_id")
        action = request.form.get("action")
        admin_note = request.form.get("admin_note", "")
        
        # Validate input
        if not request_id or not action:
            flash("Invalid request", "danger")
            return redirect("/admin/manage_time_requests")
        
        if action not in ["approve", "reject"]:
            flash("Invalid action", "danger")
            return redirect("/admin/manage_time_requests")
        
        # Update the request status
        status = "approved" if action == "approve" else "rejected"
        
        db.execute(
            """
            UPDATE time_requests
            SET status = ?, admin_id = ?, processed_at = CURRENT_TIMESTAMP, admin_note = ?
            WHERE id = ?
            """,
            status, current_user.id, admin_note, request_id
        )
        
        flash(f"Time request {status}", "success")
        return redirect("/admin/manage_time_requests")
    
    # Get all pending time requests
    pending_requests = db.execute(
        """
        SELECT 
            time_requests.id,
            time_requests.request_date,
            time_requests.start_time,
            time_requests.end_time,
            time_requests.request_type,
            time_requests.reason,
            time_requests.created_at,
            user_info.name,
            user_info.surname,
            users.username,
            users.id AS instructor_id
        FROM time_requests
        JOIN users ON time_requests.instructor_id = users.id
        JOIN user_info ON users.id = user_info.id
        WHERE time_requests.status = 'pending'
        ORDER BY time_requests.request_date, time_requests.start_time
        """
    )
    
    # Get recent processed requests
    processed_requests = db.execute(
        """
        SELECT 
            time_requests.id,
            time_requests.request_date,
            time_requests.start_time,
            time_requests.end_time,
            time_requests.request_type,
            time_requests.status,
            time_requests.reason,
            time_requests.admin_note,
            time_requests.processed_at,
            user_info.name,
            user_info.surname,
            users.username
        FROM time_requests
        JOIN users ON time_requests.instructor_id = users.id
        JOIN user_info ON users.id = user_info.id
        WHERE time_requests.status IN ('approved', 'rejected')
        ORDER BY time_requests.processed_at DESC
        LIMIT 20
        """
    )
    
    return render_template(
        "/admin/manage_time_requests.html",
        pending_requests=pending_requests,
        processed_requests=processed_requests
    )

@app.route("/admin/instructor_schedule", methods=["GET"])
@login_required
def admin_instructor_schedule():
    """Show instructor schedule for a specific date"""

    if current_user.role not in ["admin", "owner"]:
        flash("You don't have permission to access this page", "danger")
        return redirect("/logout")

    # Get the selected date (default to today)
    selected_date_str = request.args.get("date", None)
    
    # Parse the selected date or use today
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    # Format selected date for display
    formatted_date = selected_date.strftime("%A, %B %d, %Y")
    
    # Get working hours for the day of week
    day_of_week = selected_date.weekday()  # 0 = Monday, 6 = Sunday
    
    # Query the working hours for this day
    db_working_hours = db.execute(
        "SELECT * FROM working_hours WHERE day_of_week = ? AND is_open = 1", 
        day_of_week
    )
    
    if not db_working_hours:
        # Return a message that the school is closed
        return render_template("admin/instructor_schedule.html", 
            selected_date=selected_date.strftime("%Y-%m-%d"),
            formatted_date=formatted_date,
            is_open=False)
    
    working_hours = db_working_hours[0]
    
    # Generate time slots in 30-minute intervals
    start_hour, start_minute = map(int, working_hours["open_time"].split(":"))
    end_hour, end_minute = map(int, working_hours["close_time"].split(":"))
    
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute
    
    time_slots = []
    current_minutes = start_minutes
    
    while current_minutes < end_minutes:
        hour = current_minutes // 60
        minute = current_minutes % 60
        time_slot = f"{hour:02d}:{minute:02d}"
        time_slots.append(time_slot)
        current_minutes += 30
    
    # Get all instructors
    instructors = db.execute(
        "SELECT users.id, user_info.name, user_info.surname "
        "FROM users JOIN user_info ON users.id = user_info.id "
        "WHERE users.role = 'instructor' "
        "ORDER BY user_info.surname, user_info.name"
    )
    
    # Get all approved time requests (openings and closings) for the selected date
    time_requests = db.execute(
        "SELECT instructor_id, start_time, end_time, request_type "
        "FROM time_requests "
        "WHERE request_date = ? AND status = 'approved'",
        selected_date.strftime("%Y-%m-%d")
    )
    
    # Create a dictionary to track instructor availability
    instructor_availability = {}
    
    for instructor in instructors:
        instructor_id = instructor["id"]
        instructor_availability[instructor_id] = {}
        
        # Initialize all time slots as closed
        for time_slot in time_slots:
            instructor_availability[instructor_id][time_slot] = {
                "status": "closed",
                "lesson": None
            }
        
        # Process time requests to update availability
        for req in time_requests:
            if req["instructor_id"] == instructor_id:
                req_start = req["start_time"]
                req_end = req["end_time"]
                req_type = req["request_type"]
                
                # Update all time slots affected by this request
                for time_slot in time_slots:
                    if req_start <= time_slot < req_end:
                        if req_type == "open":
                            instructor_availability[instructor_id][time_slot]["status"] = "open"
                        elif req_type == "close":
                            instructor_availability[instructor_id][time_slot]["status"] = "closed"
    
    # Get all lessons for the selected date
    lessons = db.execute(
        """
        SELECT l.id, l.instructor_id, l.start_time, l.end_time, l.status, l.notes,
               u.id as customer_id, ui.name as customer_first_name, ui.surname as customer_last_name,
               ui.email as customer_email, ui.phone as customer_phone, ui.birthday as customer_birthday,
               ui.ski_type as customer_ski_type
        FROM lessons l
        JOIN users u ON l.customer_id = u.id
        JOIN user_info ui ON u.id = ui.id
        WHERE l.lesson_date = ? AND l.status = 'booked'
        """,
        selected_date.strftime("%Y-%m-%d")
    )
    
    # Update availability with lessons
    for lesson in lessons:
        instructor_id = lesson["instructor_id"]
        start_time = lesson["start_time"]
        end_time = lesson["end_time"]
        
        # Add lesson to all time slots it covers
        for time_slot in time_slots:
            if start_time <= time_slot < end_time:
                if instructor_id in instructor_availability:
                    instructor_availability[instructor_id][time_slot]["status"] = "booked"
                    instructor_availability[instructor_id][time_slot]["lesson"] = lesson
    
    # Format lessons for JSON serialization
    lessons_json = []
    for lesson in lessons:
        lesson_dict = dict(lesson)
        # Convert any non-serializable data types if needed
        lessons_json.append(lesson_dict)
    
    return render_template("admin/instructor_schedule.html",
        selected_date=selected_date.strftime("%Y-%m-%d"),
        formatted_date=formatted_date,
        time_slots=time_slots,
        instructors=instructors,
        instructor_availability=instructor_availability,
        lessons=lessons_json,
        is_open=True)

@app.route("/admin/search_customers", methods=["GET"])
@login_required
def search_customers():
    """Search for customers by name, surname, email, or phone"""
    
    if current_user.role not in ["admin", "owner"]:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    # Get search query
    query = request.args.get("q", "")
    
    if not query or len(query) < 2:
        return jsonify({"success": True, "customers": []})
    
    # Search for customers
    customers = db.execute(
        """
        SELECT u.id, ui.name, ui.surname, ui.email, ui.phone, ui.birthday, ui.ski_type
        FROM users u
        JOIN user_info ui ON u.id = ui.id
        WHERE u.role = 'customer' 
        AND (
            ui.name LIKE ? OR 
            ui.surname LIKE ? OR 
            ui.email LIKE ? OR 
            ui.phone LIKE ?
        )
        ORDER BY ui.surname, ui.name
        LIMIT 10
        """,
        f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"
    )
    
    return jsonify({"success": True, "customers": customers})

@app.route("/admin/add_lesson", methods=["POST"])
@login_required
def admin_add_lesson():
    """Add a new lesson manually by admin"""
    
    if current_user.role not in ["admin", "owner"]:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    # Get form data
    instructor_id = request.form.get("instructor_id")
    lesson_date = request.form.get("lesson_date")
    start_time = request.form.get("start_time")
    notes = request.form.get("notes", "")
    user_type = request.form.get("user_type")
    
    # Fixed duration of 60 minutes
    duration = 60
    
    # Calculate end time (start_time + duration)
    start_hour, start_minute = map(int, start_time.split(":"))
    start_minutes = start_hour * 60 + start_minute
    end_minutes = start_minutes + duration
    end_hour = end_minutes // 60
    end_minute = end_minutes % 60
    end_time = f"{end_hour:02d}:{end_minute:02d}"
    
    try:
        # Check if the instructor is available for this time slot
        # Get all approved time requests for this instructor on this date
        time_requests = db.execute(
            """
            SELECT start_time, end_time, request_type
            FROM time_requests
            WHERE instructor_id = ? AND request_date = ? AND status = 'approved'
            """,
            instructor_id, lesson_date
        )
        
        # Check if the instructor is available for the entire duration
        is_available = False
        for req in time_requests:
            if req["request_type"] == "open" and req["start_time"] <= start_time and end_time <= req["end_time"]:
                is_available = True
                break
        
        if not is_available:
            return jsonify({"success": False, "message": "Instructor is not available for this time slot"}), 400
        
        # Check if there are any overlapping lessons
        existing_lessons = db.execute(
            """
            SELECT id FROM lessons
            WHERE instructor_id = ? AND lesson_date = ? AND status = 'booked'
            AND ((start_time <= ? AND end_time > ?) OR (start_time < ? AND end_time >= ?) OR (start_time >= ? AND end_time <= ?))
            """,
            instructor_id, lesson_date, start_time, start_time, end_time, end_time, start_time, end_time
        )
        
        if existing_lessons:
            return jsonify({"success": False, "message": "There is already a lesson booked during this time"}), 400
        
        # Handle customer based on user_type
        customer_id = None
        
        if user_type == "existing":
            # Get existing customer ID
            customer_id = request.form.get("customer_id")
            if not customer_id:
                return jsonify({"success": False, "message": "Please select a customer"}), 400
        
        elif user_type == "new":
            # Create a new customer
            name = request.form.get("name")
            surname = request.form.get("surname")
            email = request.form.get("email")
            phone = request.form.get("phone")
            birthday = request.form.get("birthday", "")
            ski_type = request.form.get("ski_type", "")
            
            # Validate required fields
            if not name or not surname or not email:
                return jsonify({"success": False, "message": "Name, surname, and email are required"}), 400
            
            # Check if email already exists
            existing_email = db.execute("SELECT id FROM user_info WHERE email = ?", email)
            if existing_email:
                return jsonify({"success": False, "message": "Email already exists"}), 400
            
            # Generate a username (email or name+surname)
            username = email.split("@")[0].lower()
            
            # Check if username exists and append numbers if needed
            existing_username = db.execute("SELECT id FROM users WHERE username = ?", username)
            if existing_username:
                base_username = username
                counter = 1
                while existing_username:
                    username = f"{base_username}{counter}"
                    existing_username = db.execute("SELECT id FROM users WHERE username = ?", username)
                    counter += 1
            
            # Generate a random password (not needed for login, but required for the hash field)
            import secrets
            import string
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for i in range(12))
            
            # Hash the password
            hash_value = generate_password_hash(password)
            
            # Insert new user
            customer_id = db.execute(
                "INSERT INTO users (username, hash, role) VALUES (?, ?, 'customer')",
                username, hash_value)
            print(f"New customer ID: {customer_id}")
            # Insert user info
            db.execute(
                """
                UPDATE user_info SET role = "customer", name = ?, surname = ?, email = ?, phone = ?, birthday = ?, ski_type = ? WHERE id = ?
                """,
                name, surname, email, phone, birthday, ski_type, customer_id
            )
        else:
            return jsonify({"success": False, "message": "Invalid user type"}), 400
        
        # Insert the new lesson
        lesson_id = db.execute(
            """
            INSERT INTO lessons (instructor_id, customer_id, lesson_date, start_time, end_time, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, 'booked', ?, datetime('now'))
            """,
            instructor_id, customer_id, lesson_date, start_time, end_time, notes
        )
        
        # Get the newly created lesson details
        new_lesson = db.execute(
            """
            SELECT l.id, l.instructor_id, l.start_time, l.end_time, l.status, l.notes,
                   u.id as customer_id, ui.name as customer_first_name, ui.surname as customer_last_name,
                   ui.email as customer_email, ui.phone as customer_phone, ui.birthday as customer_birthday,
                   ui.ski_type as customer_ski_type
            FROM lessons l
            JOIN users u ON l.customer_id = u.id
            JOIN user_info ui ON u.id = ui.id
            WHERE l.id = ?
            """,
            lesson_id
        )[0]
        
        return jsonify({
            "success": True, 
            "message": "Lesson added successfully",
            "lesson": dict(new_lesson)
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

########################### Owner routes ##################################

@app.route("/owner/working_hours", methods=["GET", "POST"])
@login_required
def owner_working_hours():
    """Manage ski school working hours"""
    
    # Ensure the current user is an owner
    if current_user.role != "owner":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    if request.method == "POST":
        day = int(request.form.get("day"))
        open_time = request.form.get("open_time")
        close_time = request.form.get("close_time")
        is_open = "is_open" in request.form
        
        # Validate input
        if day is None or not open_time or not close_time:
            flash("Please fill in all required fields", "danger")
            return redirect("/owner/working_hours")
        
        # Check if entry already exists for this day
        existing = db.execute(
            "SELECT id FROM working_hours WHERE day_of_week = ?", 
            day
        )
        
        if existing:
            # Update existing entry
            db.execute(
                """
                UPDATE working_hours 
                SET open_time = ?, close_time = ?, is_open = ?, created_by = ?
                WHERE day_of_week = ?
                """,
                open_time, close_time, is_open, current_user.id, day
            )
            flash("Working hours updated successfully", "success")
        else:
            # Create new entry
            db.execute(
                """
                INSERT INTO working_hours 
                (day_of_week, open_time, close_time, is_open, created_by) 
                VALUES (?, ?, ?, ?, ?)
                """,
                day, open_time, close_time, is_open, current_user.id
            )
            flash("Working hours added successfully", "success")
        
        return redirect("/owner/working_hours")
    
    # Get current working hours
    working_hours = db.execute(
        "SELECT * FROM working_hours ORDER BY day_of_week"
    )
    
    # Create a dictionary for easier access in template
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours_by_day = {}
    
    for day in range(7):
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": "09:00",
            "close_time": "17:00",
            "is_open": True
        }
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    return render_template("owner/working_hours.html", hours_by_day=hours_by_day)

@app.route("/admin/get_admin_calendar")
@login_required
def get_admin_calendar():
    """API endpoint to get a specific admin's calendar data"""
    
    # Ensure the current user is an admin or owner
    if current_user.role != "admin" and current_user.role != "owner":
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get parameters from request
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    admin_id = request.args.get("admin_id", type=int)
    
    if not year or not month or not admin_id:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Get admin info
    admin = db.execute("SELECT username FROM users WHERE id = ?", admin_id)
    if not admin:
        return jsonify({"error": "Admin not found"}), 404
    
    admin_name = admin[0]["username"]
    
    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    
    # Get last day of month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Get admin schedules for the selected admin for the month
    schedules = db.execute(
        """
        SELECT 
            id,
            work_date,
            start_time,
            end_time
        FROM admin_schedules
        WHERE admin_id = ? AND work_date BETWEEN ? AND ?
        ORDER BY work_date, start_time
        """,
        admin_id, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get working hours for each day of the week
    working_hours = db.execute("SELECT * FROM working_hours ORDER BY day_of_week")
    
    # Create a dictionary for easier access in the frontend
    hours_by_day = {}
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    # Return the data as JSON
    return jsonify({
        "schedules": schedules,
        "working_hours": hours_by_day,
        "year": year,
        "month": month,
        "admin_name": admin_name,
        "admin_id": admin_id
    })

@app.route("/owner/get_all_admin_calendars")
@login_required
def get_all_admin_calendars():
    """API endpoint to get calendar data for all admins"""
    
    # Ensure the current user is an owner
    if current_user.role != "owner":
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get year and month from request
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    
    if not year or not month:
        # Default to current month
        today = datetime.now()
        year = today.year
        month = today.month
    
    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    
    # Get last day of month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Get schedules for all admins for the month
    schedules = db.execute(
        """
        SELECT 
            a.id,
            a.admin_id,
            a.work_date,
            a.start_time,
            a.end_time
        FROM admin_schedules a
        JOIN users u ON a.admin_id = u.id
        WHERE a.work_date BETWEEN ? AND ?
        ORDER BY a.work_date, a.start_time
        """,
        first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")
    )
    
    # Get only admins who have schedules in this month
    admin_ids_with_schedules = set()
    for schedule in schedules:
        admin_ids_with_schedules.add(schedule["admin_id"])
    
    # Get admin details for those who have schedules
    admins = []
    if admin_ids_with_schedules:
        # Convert set to comma-separated string for SQL IN clause
        admin_ids_str = ", ".join(str(id) for id in admin_ids_with_schedules)
        
        admins = db.execute(
            f"""
            SELECT id, name, surname, username
            FROM user_info 
            WHERE id IN ({admin_ids_str}) 
            ORDER BY username
            """
        )
    
    # Get working hours for each day of the week
    working_hours = db.execute("SELECT * FROM working_hours ORDER BY day_of_week")
    
    # Create a dictionary for easier access in the frontend
    hours_by_day = {}
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    # Return the data as JSON
    return jsonify({
        "admins": admins,
        "schedules": schedules,
        "working_hours": hours_by_day,
        "year": year,
        "month": month
    })

@app.route("/owner/delete_admin_schedule", methods=["POST"])
@login_required
def delete_admin_schedule():
    """Delete an admin schedule"""
    
    # Ensure the current user is an owner
    if current_user.role != "owner":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    schedule_id = request.form.get("schedule_id")
    
    if not schedule_id:
        flash("Invalid request", "danger")
        return redirect("/owner/admin_schedule")
    
    # Delete the schedule
    db.execute("DELETE FROM admin_schedules WHERE id = ?", schedule_id)
    
    flash("Admin schedule deleted successfully", "success")
    return redirect("/owner/admin_schedule")

@app.route("/owner/admin_schedule", methods=["GET", "POST"])
@login_required
def admin_schedule():
    """Manage admin work schedules"""
    
    # Ensure the current user is an owner
    if current_user.role != "owner":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    if request.method == "POST":
        # Get form data
        admin_id = request.form.get("admin_id")
        work_date = request.form.get("work_date")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        
        # Validate form data
        if not admin_id or not work_date or not start_time or not end_time:
            flash("All fields are required", "danger")
            return redirect("/owner/admin_schedule")
        
        # Check if admin exists and is an admin
        admin = db.execute("SELECT * FROM users WHERE id = ?", admin_id)
        if not admin or (admin[0]["role"] != "admin" and admin[0]["role"] != "owner"):
            flash("Invalid admin selected", "danger")
            return redirect("/owner/admin_schedule")
        
        # Check if end time is after start time
        if start_time >= end_time:
            flash("End time must be after start time", "danger")
            return redirect("/owner/admin_schedule")
        
        # Check if schedule already exists for this admin on this date
        existing_schedule = db.execute(
            "SELECT * FROM admin_schedules WHERE admin_id = ? AND work_date = ?",
            admin_id, work_date
        )
        
        if existing_schedule:
            # Update existing schedule
            db.execute(
                "UPDATE admin_schedules SET start_time = ?, end_time = ? WHERE id = ?",
                start_time, end_time, existing_schedule[0]["id"]
            )
            flash("Admin schedule updated successfully", "success")
        else:
            # Add new schedule
            db.execute(
                "INSERT INTO admin_schedules (admin_id, work_date, start_time, end_time) VALUES (?, ?, ?, ?)",
                admin_id, work_date, start_time, end_time
            )
            flash("Admin schedule added successfully", "success")
        
        return redirect("/owner/admin_schedule")
    
    # GET request - show form and schedules
    
    # Get all admins
    admins = db.execute(
        "SELECT id, name, surname FROM user_info WHERE role = 'admin' OR role = 'owner' ORDER BY username"
    )
    
    # Get upcoming admin schedules
    schedules = db.execute(
        """
        SELECT 
            a.id,
            a.admin_id,
            u.username as admin_name,
            a.work_date,
            a.start_time,
            a.end_time
        FROM admin_schedules a
        JOIN users u ON a.admin_id = u.id
        WHERE a.work_date >= CURRENT_DATE
        ORDER BY a.work_date, a.start_time
        LIMIT 50
        """
    )
    
    # Get time slots for dropdown
    time_slots = []
    start_time = datetime.strptime("08:00", "%H:%M")
    end_time = datetime.strptime("23:00", "%H:%M")
    interval = timedelta(minutes=30)
    
    current_time = start_time
    while current_time <= end_time:
        time_slots.append(current_time.strftime("%H:%M"))
        current_time += interval
    
    # Get working hours for each day of the week
    working_hours = db.execute("SELECT * FROM working_hours ORDER BY day_of_week")
    
    # Create a dictionary for easier access in template
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours_by_day = {}
    
    for day in range(7):
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": "09:00",
            "close_time": "17:00",
            "is_open": True
        }
    
    for hours in working_hours:
        day = hours["day_of_week"]
        hours_by_day[day] = {
            "name": days_of_week[day],
            "open_time": hours["open_time"],
            "close_time": hours["close_time"],
            "is_open": hours["is_open"]
        }
    
    # Get current month for calendar
    today = datetime.now()
    current_month = today.strftime("%B %Y")
    
    return render_template(
        "owner/admin_schedule.html",
        admins=admins,
        schedules=schedules,
        time_slots=time_slots,
        today=today.strftime("%Y-%m-%d"),
        working_hours=hours_by_day,
        current_month=current_month,
        current_year=today.year,
        current_month_num=today.month
    )

@app.route("/owner/edit_staff_info", methods=["GET", "POST"])
@login_required
def edit_staff_info():
    """Allow owners to view and edit staff information"""
    
    # Ensure the current user is an owner
    if current_user.role != "owner":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")
    
    # Handle search functionality
    search_query = request.args.get("search", "")
    
    # Handle edit form submission
    if request.method == "POST" and "edit_user" in request.form:
        user_id = request.form.get("user_id")
        name = request.form.get("name")
        surname = request.form.get("surname")
        email = request.form.get("email")
        phone = request.form.get("phone")
        hourly_rate = request.form.get("hourly_rate") or 0
        role = request.form.get("role")
        
        # Get ski types (could be multiple)
        ski_types = request.form.getlist("ski_type")
        ski_type = ",".join(ski_types) if ski_types else None
        
        # Validate input
        if not user_id:
            flash("Invalid user ID", "danger")
            return redirect("/owner/edit_staff_info")
        
        # Handle empty email - convert empty string to None
        if email == "":
            email = None
        
        # If email is provided, check if it's already in use by another user
        if email is not None:
            existing_email = db.execute(
                "SELECT id FROM user_info WHERE email = ? AND id != ?", 
                email, user_id
            )
            
            if existing_email:
                flash("Email is already in use by another user", "danger")
                return redirect(f"/owner/edit_staff_info?edit={user_id}")
        
        # Handle profile picture upload
        profile_picture_path = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                # Check if the file is an allowed image type
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                
                if file_ext not in allowed_extensions:
                    flash("Only image files (PNG, JPG, JPEG, GIF) are allowed for profile pictures", "danger")
                    return redirect(f"/owner/edit_staff_info?edit={user_id}")
                
                # Create a unique filename to prevent overwriting
                filename = secure_filename(f"user_{user_id}.{file_ext}")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                
                # Save the file
                file.save(filepath)
                
                # Store the relative path in the database
                profile_picture_path = f"/static/uploads/{filename}"
                
                # Delete old profile picture if it exists
                old_picture = db.execute("SELECT profile_picture FROM user_info WHERE id = ?", user_id)[0]["profile_picture"]
                if old_picture and old_picture != profile_picture_path:
                    old_file_path = os.path.join(os.getcwd(), old_picture.lstrip('/'))
                    try:
                        if os.path.exists(old_file_path):
                            os.remove(old_file_path)
                    except Exception as e:
                        print(f"Error removing old profile picture: {e}")
        
        # Update user_info table
        if profile_picture_path:
            db.execute(
                "UPDATE user_info SET name = ?, surname = ?, email = ?, phone = ?, hourly_rate = ?, profile_picture = ?, ski_type = ? WHERE id = ?",
                name, surname, email, phone, hourly_rate, profile_picture_path, ski_type, user_id
            )
        else:
            db.execute(
                "UPDATE user_info SET name = ?, surname = ?, email = ?, phone = ?, hourly_rate = ?, ski_type = ? WHERE id = ?",
                name, surname, email, phone, hourly_rate, ski_type, user_id
            )
        
        # Update role in both tables if it has changed
        current_role = db.execute("SELECT role FROM users WHERE id = ?", user_id)[0]["role"]
        if role != current_role:
            db.execute("UPDATE users SET role = ? WHERE id = ?", role, user_id)
            db.execute("UPDATE user_info SET role = ? WHERE id = ?", role, user_id)
        
        flash("Staff information updated successfully!", "success")
        return redirect("/owner/edit_staff_info")
    
    # Get all staff members (excluding customers)
    if search_query:
        # Search in multiple fields
        staff = db.execute(
            """
            SELECT u.id, u.username, ui.* 
            FROM users u 
            JOIN user_info ui ON u.id = ui.id 
            WHERE u.role != 'customer' 
            AND (u.username LIKE ? OR ui.name LIKE ? OR ui.surname LIKE ? OR ui.email LIKE ?)
            ORDER BY u.role, ui.surname, ui.name
            """, 
            f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"
        )
    else:
        staff = db.execute(
            """
            SELECT u.id, u.username, ui.* 
            FROM users u 
            JOIN user_info ui ON u.id = ui.id 
            WHERE u.role != 'customer'
            ORDER BY u.role, ui.surname, ui.name
            """
        )
    
    # Get user to edit if specified
    edit_id = request.args.get("edit")
    user_to_edit = None
    
    if edit_id:
        user_to_edit = db.execute(
            """
            SELECT u.id, u.username, u.role, ui.* 
            FROM users u 
            JOIN user_info ui ON u.id = ui.id 
            WHERE u.id = ?
            """, 
            edit_id
        )
        if user_to_edit:
            user_to_edit = user_to_edit[0]
            # Split ski_type into a list if it exists
            if user_to_edit["ski_type"]:
                user_to_edit["ski_types"] = user_to_edit["ski_type"].split(",")
            else:
                user_to_edit["ski_types"] = []
    
    return render_template(
        "owner/edit_staff_info.html", 
        staff=staff, 
        search_query=search_query,
        user_to_edit=user_to_edit
    )

@app.route("/owner/delete_user", methods=["GET", "POST"])
@login_required
def delete_user():
    """Allow owners to delete users by username"""

    # Ensure the current user is an owner
    if current_user.role != "owner":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username")

        # Ensure the username is provided
        if not username:
            flash("Must provide a username to delete.", "danger")
            return render_template("owner/delete_user.html")

        # Check if the user exists
        user_to_delete = db.execute("SELECT * FROM users WHERE username = ?", username)
        if not user_to_delete:
            flash("No user found with that username.", "danger")
            return render_template("owner/delete_user.html")

        # Ensure we don't delete the owner themselves
        if user_to_delete[0]["username"] == current_user.username:
            flash("You cannot delete your own account!", "danger")
            return render_template("owner/delete_user.html")

        # Delete the user from the database
        db.execute("DELETE FROM users WHERE username = ?", username)

        flash(f"User {username} has been deleted successfully.", "success")
        return render_template("owner/delete_user.html")

    return render_template("owner/delete_user.html")

@app.route("/owner/add_user", methods=["GET", "POST"])
@login_required
def add_user():
    """Allow only owners to register new users"""

    # Ensure the current user is an owner
    if current_user.role != "owner":
        flash("You don't have permission to access this page", "danger")
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        # Validate input fields
        if not username or not password or not role:
            flash("Must provide username, password, and role!", "danger")
            return render_template("/owner/add_user.html")

        # Check if username already exists
        existing_user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if existing_user:
            flash("Username already exists. Please choose a different one.", "danger")
            return render_template("/owner/add_user.html")

        # Insert new user into the users database
        db.execute(
            "INSERT INTO users (username, hash, role) VALUES (?, ?, ?)",
            username,
            generate_password_hash(password),
            role
        )

        flash("User successfully registered!", "success")
        return redirect("/owner/add_user")

    return render_template("/owner/add_user.html")

########################### Not logged-in routes ##################################

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Must provide username and password", "danger")
            return render_template("login.html")

        user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(user) != 1 or not check_password_hash(user[0]["hash"], password):
            flash("Invalid username or password", "danger")
            return render_template("login.html")

        # Create user object and log in
        user_obj = User(user[0]["id"], user[0]["username"], user[0]["role"])
        login_user(user_obj)
        return redirect("/")

    return render_template("login.html")

###password reset routes###

@app.route("/reset_password_request", methods=["GET", "POST"])
def reset_password_request():
    """Handle password reset requests"""
    if request.method == "POST":
        email = request.form.get("email")
        
        if not email:
            flash("Please enter your email address", "danger")
            return render_template("reset_password_request.html")
        
        # Find user by email
        user_info = db.execute("SELECT * FROM user_info WHERE email = ?", email)
        
        if not user_info:
            # Don't reveal that the email doesn't exist for security
            flash("If this email is registered, you will receive password reset instructions shortly", "info")
            return render_template("reset_password_request.html")
        
        # Get the user ID
        user_id = user_info[0]["id"]
        
        # Generate a token
        token = secrets.token_urlsafe(32)
        
        # Set expiration to 24 hours from now
        expiration = datetime.now() + timedelta(hours=24)
        expiration_str = expiration.strftime("%Y-%m-%d %H:%M:%S")
        
        # Store the token in the database
        # First, check if there's an existing token for this user and delete it
        db.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", user_id)
        
        # Insert the new token
        db.execute(
            "INSERT INTO password_reset_tokens (user_id, token, expiration) VALUES (?, ?, ?)",
            user_id, token, expiration_str
        )
        
        # Send the reset email
        reset_url = url_for('reset_password', token=token, _external=True)
        send_reset_email(email, reset_url)
        
        flash("If this email is registered, you will receive password reset instructions shortly", "info")
        return render_template("reset_password_request.html")
    
    return render_template("reset_password_request.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Handle password reset"""
    
    # Verify the token
    token_info = db.execute("SELECT * FROM password_reset_tokens WHERE token = ?", token)
    
    if not token_info:
        flash("Invalid or expired reset link", "danger")
        return redirect("/login")
    
    # Check if token is expired
    expiration = datetime.strptime(token_info[0]["expiration"], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > expiration:
        # Delete expired token
        db.execute("DELETE FROM password_reset_tokens WHERE token = ?", token)
        flash("Your reset link has expired. Please request a new one", "danger")
        return redirect("/reset_password_request")
    
    user_id = token_info[0]["user_id"]
    
    if request.method == "POST":
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        if not password or not confirm_password:
            flash("Please fill out all fields", "danger")
            return render_template("reset_password.html", token=token)
        
        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template("reset_password.html", token=token)
        
        # Hash the new password
        password_hash = generate_password_hash(password)
        
        # Update the user's password
        db.execute("UPDATE users SET hash = ? WHERE id = ?", password_hash, user_id)
        
        # Delete the used token
        db.execute("DELETE FROM password_reset_tokens WHERE token = ?", token)
        
        flash("Your password has been reset successfully. You can now log in with your new password", "success")
        return redirect("/login")
    
    return render_template("reset_password.html", token=token)

def send_reset_email(to_email, reset_url):
    """Send password reset email"""
    
    # Configure email settings - Replace with your actual email settings
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "kajus.oskutis@gmail.com")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "iwpj xwvo kzxk jcwq")
    FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@skiresort.com")
    
    # Create message
    msg = MIMEMultipart()
    msg['From'] = FROM_EMAIL
    msg['To'] = to_email
    msg['Subject'] = "Password Reset Request - Ski School"
    
    # Email body
    body = f"""
    <html>
      <body>
        <h2>Password Reset Request</h2>
        <p>Hello,</p>
        <p>We received a request to reset your password for your Ski School account.</p>
        <p>Click the link below to set a new password:</p>
        <p><a href="{reset_url}">Reset My Password</a></p>
        <p>This link will expire in 24 hours.</p>
        <p>If you didn't request a password reset, you can ignore this email.</p>
        <p>Regards,<br>Ski School Team</p>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(body, 'html'))
    
    try:
        # Connect to SMTP server and send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new customer account"""
    
    # If user is already logged in, redirect to home
    if current_user.is_authenticated:
        return redirect("/")
        
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        email = request.form.get("email")
        name = request.form.get("name")
        surname = request.form.get("surname")
        phone = request.form.get("phone")
        
        # Validate input
        if not username:
            flash("Must provide username", "danger")
            return render_template("register.html")
        
        if not password:
            flash("Must provide password", "danger")
            return render_template("register.html")
            
        if not confirmation:
            flash("Must confirm password", "danger")
            return render_template("register.html")
            
        if password != confirmation:
            flash("Passwords do not match", "danger")
            return render_template("register.html")
        
        # Check password length
        if len(password) < 8:
            flash("Password must be at least 8 characters long", "danger")
            return render_template("register.html")
        
        # Check if username already exists
        existing_user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if existing_user:
            flash("Username already exists. Please choose a different one.", "danger")
            return render_template("register.html")
        
        # Handle profile picture upload
        profile_picture_path = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                # Check if the file is an allowed image type
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                
                if file_ext not in allowed_extensions:
                    flash("Only image files (PNG, JPG, JPEG, GIF) are allowed for profile pictures", "danger")
                    return render_template("register.html")
                
                # Create a unique filename to prevent overwriting
                # We don't have a user ID yet, so use timestamp
                timestamp = int(time.time())
                filename = secure_filename(f"new_user_{timestamp}.{file_ext}")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                
                # Save the file
                file.save(filepath)
                
                # Store the relative path
                profile_picture_path = f"/static/uploads/{filename}"
        
        # Insert new user into the users database with customer role
        user_id = db.execute(
            "INSERT INTO users (username, hash, role) VALUES (?, ?, ?)",
            username,
            generate_password_hash(password),
            "customer"
        )
        
        # Update user_info with additional information
        # The trigger will create a basic user_info record, but we need to update it
        db.execute(
            "UPDATE user_info SET name = ?, surname = ?, email = ?, phone = ?, profile_picture = ? WHERE id = ?",
            name, surname, email, phone, profile_picture_path, user_id
        )
        
        flash("Registration successful! You can now log in.", "success")
        return redirect("/login")
        
    return render_template("register.html")

########################### Log-out route ##################################

@app.route("/logout")
@login_required
def logout():
    """Log user out"""
    logout_user()
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)