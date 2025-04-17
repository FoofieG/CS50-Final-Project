from flask import Blueprint, render_template, request, redirect, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from cs50 import SQL

from helpers import open_time_ranges

customer_bp = Blueprint("customer_bp", __name__)
db = SQL("sqlite:///database.db")

########################### Customer routes ##################################

@customer_bp.route("/book_lesson", methods=["GET", "POST"])
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
        open_ranges = open_time_ranges(time_requests)
        
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

@customer_bp.route("/get_available_times_for_date", methods=["GET"])
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
        
        # Get open time ranges from the requests
        open_ranges = open_time_ranges(time_requests)
        
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

@customer_bp.route("/get_available_instructors", methods=["GET"])
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
        
        # Get open time ranges from the requests
        open_ranges = open_time_ranges(time_requests)
        
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

@customer_bp.route("/get_instructor_available_dates", methods=["GET"])
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

@customer_bp.route("/get_available_dates", methods=["GET"])
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

@customer_bp.route("/get_instructor_available_times", methods=["GET"])
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
    
    # Get open time ranges from the requests
    open_ranges = open_time_ranges(time_requests)
    
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

@customer_bp.route("/cancel_lesson", methods=["POST"])
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
    
    # Get open time ranges from the requests
    open_ranges = open_time_ranges(time_requests)
    
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

@customer_bp.route("/my_lessons", methods=["GET"])
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