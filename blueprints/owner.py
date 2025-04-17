from flask import Blueprint, render_template, request, redirect, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from cs50 import SQL

from helpers import open_time_ranges, handle_profile_picture

owner_bp = Blueprint("owner_bp", __name__)
db = SQL("sqlite:///database.db")

########################### Owner routes ##################################

@owner_bp.route("/working_hours", methods=["GET", "POST"])
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

@owner_bp.route("/get_admin_calendar")
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

@owner_bp.route("/get_all_admin_calendars")
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

@owner_bp.route("/delete_admin_schedule", methods=["POST"])
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

@owner_bp.route("/admin_schedule", methods=["GET", "POST"])
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

@owner_bp.route("/edit_staff_info", methods=["GET", "POST"])
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
        
        # Get the user's that is being edited current profile picture
        current_user_info = db.execute("SELECT profile_picture FROM user_info WHERE id = ?", user_id)
        old_picture = current_user_info[0]["profile_picture"] if current_user_info else None
        # Handle profile picture delete and upload
        profile_picture_path = None
        if 'profile_picture' in request.files:
            profile_picture_path = handle_profile_picture(request.files['profile_picture'], user_id)

            # If there was an error with the profile picture, return early
            if profile_picture_path is None and request.files['profile_picture'].filename:
                return redirect("/settings")
        
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

@owner_bp.route("/delete_user", methods=["GET", "POST"])
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

@owner_bp.route("/add_user", methods=["GET", "POST"])
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
