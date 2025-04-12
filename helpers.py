from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import time
import os

########################### Functions that repeat ##################################

# Function to calculate the open time ranges
def open_time_ranges(time_requests):
    """Processes time_requests to compute merged open ranges"""
    open_ranges = []

    for req in time_requests:
        start = datetime.strptime(req["start_time"], "%H:%M").time()
        end = datetime.strptime(req["end_time"], "%H:%M").time()

        if req["request_type"] == "open":
            new_range = {"start": start, "end": end}
            i = 0
            while i < len(open_ranges):
                existing = open_ranges[i]
                if new_range["start"] <= existing["end"] and new_range["end"] >= existing["start"]:
                    new_range["start"] = min(new_range["start"], existing["start"])
                    new_range["end"] = max(new_range["end"], existing["end"])
                    open_ranges.pop(i)
                else:
                    i += 1
            open_ranges.append(new_range)
            open_ranges.sort(key=lambda x: x["start"])

        elif req["request_type"] == "close":
            updated_ranges = []
            for open_range in open_ranges:
                s, e = open_range["start"], open_range["end"]
                if start <= s and end >= e:
                    continue
                elif start > s and end < e:
                    updated_ranges += [{"start": s, "end": start}, {"start": end, "end": e}]
                elif start <= s < end < e:
                    updated_ranges.append({"start": end, "end": e})
                elif s < start < e <= end:
                    updated_ranges.append({"start": s, "end": start})
                else:
                    updated_ranges.append(open_range)
            open_ranges = updated_ranges

    return open_ranges

# Handle profile picture uploads
def handle_profile_picture(file_field, user_id=None, old_picture=None):
    """
    Handle profile picture uploads and manage old pictures.
    
    Args:
        file_field: The file field from request.files
        user_id: The user ID (optional, for existing users)
        old_picture: Path to old profile picture (optional)
        
    Returns:
        str: Path to the new profile picture or None if no picture was uploaded
    """

    upload_folder="static/uploads"

    if not file_field or not file_field.filename:
        return None
        
    # Check if the file is an allowed image type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    file_ext = file_field.filename.rsplit('.', 1)[1].lower() if '.' in file_field.filename else ''
    
    if file_ext not in allowed_extensions:
        flash("Only (PNG, JPG, JPEG, GIF) type files are allowed", "danger")
        return None
    
    # Create a unique filename to prevent overwriting
    timestamp = int(time.time())
    if user_id:
        filename = secure_filename(f"user_{user_id}_{timestamp}.{file_ext}")
    else:
        filename = secure_filename(f"new_user_{timestamp}.{file_ext}")
        
    filepath = os.path.join(upload_folder, filename)
    
    # Save the new file
    file_field.save(filepath)
    
    profile_picture_path = f"/static/uploads/{filename}"
    
    # Delete old profile picture if it exists
    if old_picture and old_picture != profile_picture_path:
        old_file_path = os.path.join(os.getcwd(), old_picture.lstrip('/'))
        try:
            if os.path.exists(old_file_path):
                os.remove(old_file_path)
        except Exception as e:
            print(f"Error removing old profile picture: {e}")
    
    return profile_picture_path