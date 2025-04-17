from flask import Blueprint, render_template, request, redirect, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from cs50 import SQL

from helpers import open_time_ranges

instructor_bp = Blueprint("instructor_bp", __name__)
db = SQL("sqlite:///database.db")

########################### Instructor routes ##################################

@instructor_bp.route("/request_time", methods=["POST"])
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

@instructor_bp.route("/cancel_time_request", methods=["POST"])
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

@instructor_bp.route("/calendar")
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

@instructor_bp.route("/get_calendar")
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

@instructor_bp.route("/history")
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

