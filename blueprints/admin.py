from flask import Blueprint, render_template, request, redirect, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from cs50 import SQL

from helpers import open_time_ranges

admin_bp = Blueprint("admin_bp", __name__)
db = SQL("sqlite:///database.db")

########################### Admin routes ##################################

@admin_bp.route("/home")
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

@admin_bp.route("/get_my_calendar")
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

@admin_bp.route("/manage_time_requests", methods=["GET", "POST"])
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

@admin_bp.route("/instructor_schedule", methods=["GET"])
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

@admin_bp.route("/search_customers", methods=["GET"])
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

@admin_bp.route("/add_lesson", methods=["POST"])
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
