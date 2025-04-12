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
from helpers import open_time_ranges, handle_profile_picture # Import custom functions from helpers.py

# Configure application
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "123")
app.config["UPLOAD_FOLDER"] = "static/uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)  
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

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
    # Handle case where user_id can't be converted to int
    except (ValueError, TypeError):
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

########################### Register blueprints for all the different roles ##################################
from blueprints.customer import customer_bp
from blueprints.instructor import instructor_bp
from blueprints.admin import admin_bp
from blueprints.owner import owner_bp

app.register_blueprint(customer_bp, url_prefix="/customer")
app.register_blueprint(instructor_bp, url_prefix="/instructor")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(owner_bp, url_prefix="/owner")

########################### Routes for all USERS ##################################

@app.route("/")
def index():
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
    # User settings page

    # FIXME: Add better validation for phone numbers

    user_info = db.execute(
        """
        SELECT users.id, users.username, users.role, user_info.* 
        FROM users
        JOIN user_info ON users.id = user_info.id 
        WHERE users.id = ?
        """, 
        current_user.id
    )
    
    if not user_info:
        flash("Error retrieving user information", "danger")
        return redirect("/")
    
    user_info = user_info[0]
    
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
            profile_picture_path = handle_profile_picture(request.files['profile_picture'], current_user.id, user_info["profile_picture"])

            # If there was an error with the profile picture, return early
            if profile_picture_path is None and request.files['profile_picture'].filename:
                return redirect("/settings")
        try:
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
            print(f"Error updating profile: {str(e)}", "danger")
        
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
    ## Change user password
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    # Validate inputs
    if not current_password or not new_password or not confirm_password:
        flash("All password fields are required", "danger")
        return redirect("/settings")
    
    if new_password != confirm_password:
        flash("New password and confirmation password do not match", "danger")
        return redirect("/settings")
    
    if len(new_password) < 8:
        flash("Password must be at least 8 characters long", "danger")
        return redirect("/settings")
    
    old_password = db.execute("SELECT hash FROM users WHERE id = ?", current_user.id)
    
    if not old_password:
        flash("User not found", "danger")
        return redirect("/settings")
    
    # Verify current password
    if not check_password_hash(old_password[0]["hash"], current_password):
        flash("Current password is incorrect", "danger")
        return redirect("/settings")
    
    new_hash = generate_password_hash(new_password)
    
    try:
        # Update password in database
        db.execute("UPDATE users SET hash = ? WHERE id = ?", new_hash, current_user.id)
        flash("Your password has been updated successfully!", "success")
    except Exception as e:
        print(f"Error updating password: {str(e)}", "danger")
    
    return redirect("/settings")

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

### Forgot password reset routes ###
@app.route("/reset_password_request", methods=["GET", "POST"])
def reset_password_request():
    # Handle password reset requests
    if request.method == "POST":
        email = request.form.get("email")
        
        if not email:
            flash("Please enter your email address", "danger")
            return render_template("reset_password_request.html")
        
        # Find user by email
        user_info = db.execute("SELECT * FROM user_info WHERE email = ?", email)
        
        if not user_info:
            # Don't reveal that the email doesn't exist for security reasons
            flash("If this email is registered, you will receive password reset instructions shortly", "info")
            return render_template("reset_password_request.html")
        
        user_id = user_info[0]["id"]
        
        # Generate a token
        token = secrets.token_urlsafe(32)
        
        # Set expiration to 24 hours from now
        expiration = datetime.now() + timedelta(hours=24)
        expiration_str = expiration.strftime("%Y-%m-%d %H:%M:%S")
        
        # Check if there's an existing token for this user and delete it
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
    # Handles password reset
    
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
        flash("Your reset link has expired", "danger")
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
        
        password_hash = generate_password_hash(password)
        
        # Update the user's password
        db.execute("UPDATE users SET hash = ? WHERE id = ?", password_hash, user_id)
        
        # Delete the used token
        db.execute("DELETE FROM password_reset_tokens WHERE token = ?", token)
        
        flash("Password changed", "success")
        return redirect("/login")
    
    return render_template("reset_password.html", token=token)

def send_reset_email(to_email, reset_url):
    # Send password reset email
    
    # Configure email settings
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
    # Register a new customer account

    # FIXME: Add better validation for phone numbers
    
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
        
        # Validate inputs
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
        
        if len(password) < 8:
            flash("Password must be at least 8 characters long", "danger")
            return render_template("register.html")
        
        # Check if username already exists
        existing_user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if existing_user:
            flash("Username already exists", "danger")
            return render_template("register.html")

        profile_picture_path = None
        if 'profile_picture' in request.files:
            profile_picture_path = handle_profile_picture(request.files['profile_picture'])
            
            # If there was an error with the profile picture, return early
            if profile_picture_path is None and request.files['profile_picture'].filename:
                return render_template("register.html")
        
        # Insert new user into the users database with customer role
        user_id = db.execute(
            "INSERT INTO users (username, hash, role) VALUES (?, ?, ?)",
            username,
            generate_password_hash(password),
            "customer"
        )
        
        # Update user_info with additional information
        # The trigger will create a basic user_info record, but we need to update everything else
        db.execute(
            "UPDATE user_info SET name = ?, surname = ?, email = ?, phone = ?, profile_picture = ? WHERE id = ?",
            name, surname, email, phone, profile_picture_path, user_id
        )
        
        flash("Registration successful!", "success")
        return redirect("/login")
        
    return render_template("register.html")

########################### Log-out route ##################################

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)