<a id="readme-top"></a>

# 🏔️ Ski School Management System

#### Video Demo: <URL HERE>

<!-- TABLE OF CONTENTS -->
<details> 
  <summary>Table of contents</summary> 
  <ol> 
    <li><a href="#📝description">📝 Description</a></li> 
    <li><a href="#✨features">✨ Features</a></li> 
    <li><a href="#🔐role-permissions">🔐 Role permissions</li>
    <li><a href="#🏗️built-with">🏗️ Built With</a></li> 
    <li><a href="#🗂️project-structure">🗂️ Project Structure</a></li> 
    <li><a href="#🔍key-components-explained">🔍 Key Components Explained</a></li> 
    <li><a href="#🧠design-decisions--trade-offs">🧠 Design Decisions & Trade-offs</a></li> 
    <li><a href="#🚀getting-started">🚀 Getting Started</a></li> 
    <li><a href="#💻usage">💻 Usage</a></li> 
    <li><a href="#🛣️features-to-be-implemented">🛣️ Features To Be Implemented</a></li>
  </ol>
</details>

<!-- DESCRIPION -->

## 📝Description

A web-based role-specific scheduling and user management system for ski/snowboard schools, built with Flask. While designed for winter sports schools, it can easily be adapted for gyms, studios, tutoring centers, and any other service-based organization requiring schedule-based access control. It supports multiple user roles—**Owner**, **Admin**, **Instructor**, and **Customer**—each with different levels of access.

<!-- FEATURES -->

## ✨Features

- **🔐 Role-Based Access Control** – Different dashboards and actions for Owners, Admins, Instructors, and Customers.

- **📅 Dynamic Calendar Views** – Day, month, and list-based schedules tailored to user roles.

- **🧑‍🏫 Lesson Booking System** – Smart filtering based on availability and ski type.

- **🔁 Time-Off Requests** – Instructors submit requests; Admins manage approvals.

- **👤 Customizable User Profiles** – Editable fields vary depending on role.

- **🛡️ Secure Auth** – Login, registration, and password reset with expiring tokens.

- **🧾 Admin Oversight** – Admin dashboard for managing requests and lesson visibility.

- **🔍 Searchable Database** – Admins can book for existing customers by email, name, or phone.

- **📦 Auto-Synced User Info** – Updates across tables when users are added or removed.

- **🎨 Responsive UI** – Mobile-friendly layout styled with Bootstrap and CSS.

<!-- ROLE PERMISSIONS -->

## 🔐Role permissions

<details> 
  <summary><strong>Click to view full role-based permissions</strong></summary>

#### All logged-in users

- Can access their profile settings and edit their own profile, **name, surname, email, phone number, birthday, ski type, hourly rate, profile picture** although different roles have different access to seeing and changing some of them:
  - Staffs **hourly rate** (how much they earn per lesson) is visible to them, but only owner can change it.
  - While Customers can`t even see **hourly rate** since they are not employees.
  - Staff can`t change their **name**/**surname** since they are employees- their publicly displayed information can only be changed by owner.
  - Instructors can not change their **ski type**- since they have to have a specific license to teach customers skiing or snowboarding.
  - While Customers can and according to their **ski type** only Instructors with the same type will be show when they try to book a lesson.
- Can change their password.
- Log out.

#### All logged-out users

- Can register for new account (with **Customer** role auto-assigned)
- Can log in to already existing account.
- Can submit **"Forgot password?"** request that sends an email with link that contains expiring token (in 24 hours) to change their password.

#### Owner

- Can **create** a user with any chosen role.
- Can **delete** user by their username.
- Can **manage** all employees information.
- Can edit companies **Working Hours**.
- Can assign what day, what time, which admin(s) works and see their schedule in a table based calendar.
- Can access all pages that **Admin** role can.

#### Admin

- Can access **Admin Dashboard** page that displays:
  - **Time Requests** section displays all time requests from Instructors that haven`t been processed yet.
  - **Upcoming Lessons** section displays all lessons that did not finish yet until the end of the day.
  - **Admin Work Schedule** section displays "your" work schedule in green and all other admins in yellow.
- Can access **Time Requests** page, where they can:
  - See all unprocessed time open or close requests.
  - Accept or deny them and leave a note (if needed).
  - See history of all the requests.
- Can access **Instructor Schedule** page, where they can:
  - See all instructors schedules day by day:
    - When instructor has opened their time to be available or not.
    - When customers have booked a lesson.
  - Press on any lesson and see all of the customer information
  - Press on any instructors open time and manually add a lesson (to resolve an issue- if administrator gets a call to work phone and customer books a lesson with a phone call)
    - When adding a lesson they can chose weather its a new user or an already existing one, if its already existing one, they can search the database by their name, email or phone number.

#### Instructor

- Can access **Instructor Dashboard** page that displays:
  - **My Calendar** section of the page where instructors can:
    - See list based **calendar** that displays **upcoming lessons** (a single most relevant- today or any feature day that has at least one lessons in it)
      - Can press on any lesson and see more information about the customer and upcoming lesson
    - You can also toggle to **"monthly calendar"** view where you can see table based calendar of the whole month.
      - When the company is working
      - What time it opens
      - When you(instructor) has opened the times to be able to work
      - When customers booked a lesson
      - Can press on any lesson and see more information about the customer and upcoming lesson
  - **Request Time Off/On** section of the page where instructors can:
    - Request to open or close time (admins need to approve or deny it, because of the reason when there is too many instructors that day or when instructor wants to close the time when they already have lessons in that time window, so before closing admins need to resolve, move the lesson to another instructors time)
  - **Pending Time Requests** section of the page where they can see, pending and history of all the time requests.
- Can access **History** page where instructor can:
  - View all previous lessons

#### Customer

- Can access **Book Lesson** page where customers can:
  - Book a lesson
  - When booking a lesson they can chose weather to book it by time or by instructor (to allow customers to book a lesson easier if they prefer a certain instructor)
  - In either scenario the booking will only show the days, times and instructors that are available.
  - When booking a lesson only instructor that are the same ski type as customer will be displayed
- Can access **My Lessons** page where customers can: - See **Upcoming Lessons** section of the page, that displays all upcoming lessons. - See **Past Lessons** section of the page, that displays all past lessons
</details>

<!-- BUILT WITH -->

## 🏗️Built With

#### Main frameworks/libraries/add-ons/plugins:

- [Python](https://www.python.org/) – Core programming language

- [Flask](https://flask.palletsprojects.com/) – Lightweight web framework

- [HTML5](https://developer.mozilla.org/en-US/docs/Web/Guide/HTML/HTML5) – Structure and markup of web pages

- [CSS3](https://developer.mozilla.org/en-US/docs/Web/CSS) – Styling and layout

- [SQLite](https://www.sqlite.org/) – Database

- [Jinja2](https://jinja.palletsprojects.com/) – Templating engine for rendering HTML

- [Flask-Login](https://flask-login.readthedocs.io/) – User session and authentication

- [Werkzeugsecurity](https://werkzeug.palletsprojects.com/en/stable/) - Password and file security

- [Bootstrap 3](https://getbootstrap.com/) – Responsive front-end components

- [Font Awesome 4](https://fontawesome.com/) - Icon styling

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## 🗂️Project Structure

The project is a Flask web application organized into clearly separated components: routing (via blueprints), templates, static files, and utility scripts. Here's a breakdown of the structure and functionality:

<p>
📦CS50 Final Project/
<br>├── 📜app.py # Main application file, registers blueprints and initializes Flask
<br>├── 📊database.db # SQLite database storing user and event data
<br>├── 📜helpers.py # Utility functions used across the app
<br>├── 🗒️requirements.txt # Python package dependencies
<br>├── 🗒️README.md # This documentation file
<br>├── 📂blueprints/ # Contains route logic for different user roles
<br>│ ├── 📜admin.py # Admin-specific pages logic
<br>│ ├── 📜customer.py # Customer-specific pages logic
<br>│ ├── 📜instructor.py # Instructor-specific pages logic
<br>│ └── 📜owner.py # Owner-specific pages logic
<br>├── 📂templates/ # Jinja2 HTML templates for rendering the front-end
<br>│ ├── 📂owner/ # All 'owner' role templates
<br>│ ├── 📂admin/ # All 'admin' role templates
<br>│ ├── 📂instructor/ # All 'instructor' role templates
<br>│ ├── 📂customer/ # All 'customer' role templates
<br>│ ├── 🗒️layout.html # Base HTML structure used across pages
<br>│ ├── 🗒️login.html # Login form
<br>│ ├── 🗒️register.html # User registration form
<br>│ └── 🗒️reset_password.html # Password reset UI
<br>├── 📂static/ # Static front-end assets
<br>│ ├── 🗒️styles.css # Custom CSS styling
<br>│ ├── 🖼️logo.png # App logo
<br>│ ├── 🖼️favicon.ico # App icon
<br>│ └── 📂uploads/ # Uploaded user profile pictures
<br>├── 📂flask_session/ # Session storage files generated by Flask-Session
<br>└── 🗒️.gitignore # Files/directories to ignore in version control
</p>

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## 🔍Key Components Explained

- **`app.py`**
  The main entry point of the application. It initializes the Flask app, registers all blueprints (routes for each role), and starts the server.

- **`blueprints/`**
  Each `.py` file defines routes and logic for a specific user role:

  - `admin.py`, `owner.py`, `instructor.py`, `customer.py` provide role-specific backend processes.

- **`helpers.py`**
  Contains reusable helper functions.

- **`templates/`**
  Jinja2 templates that render HTML content for the web interface. Includes forms, dashboard layouts, and shared structures like `layout.html`.

- **`static/`**
  Holds front-end assets such as CSS styles, Icons, Logos and uploaded user profile images.

- **`database.db`**
  SQLite database storing users, roles, events, and possibly session data.

---

This structure ensures a clean separation of logic, templates, and static assets. Each role’

This structure ensures the project is scalable, easy to maintain, and cleanly separates

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## 🧠Design Decisions & Trade-offs

Throughout development, several key decisions were made to balance usability, maintainability, and scalability. Here's a breakdown of a few notable ones and the reasoning behind them:

### 🔐 Role-Based Blueprints vs. Centralized Routing

**Decision:** Each user role (Owner, Admin, Instructor, Customer) has its own Blueprint.

**Why:**  
This was chosen to provide clear separation of concerns. It allows each role to be developed and maintained independently with less risk of introducing bugs that affect other roles. While it adds more folders and files, the clarity it provides for scaling the project is worth the trade-off.

---

### 🗃️ Two-Table User Data Design

**Decision:** Separate `users` table (for login credentials and roles) and `user_info` table (for profile data).

**Why:**  
Splitting the tables improves database normalization and makes the system more flexible. It allows for cleaner queries, better user data management, and easier updates or deletions. It also enhances security by separating authentication from personal data.

---

### 📆 Instructors Can't Edit Their Own Availability Directly

**Decision:** Instructors must submit time-off or time-on requests instead of directly editing their availability.

**Why:**  
This introduces an approval process to ensure lesson scheduling remains consistent and avoids conflicts, such as instructors trying to close availability when they already have lessons booked. Admins serve as gatekeepers to validate and resolve potential issues before changes are finalized.

---

### 🎨 Bootstrap 3 over Bootstrap 5

**Decision:** The app uses Bootstrap 3 for styling.

**Why:**  
Although Bootstrap 5 offers newer components and utilities, Bootstrap 3 was chosen due to existing familiarity and faster development during prototyping. Future updates may include migration to a newer framework once I get more familiar with it.

---

### 🧾 Customers and Ski Type Matching

**Decision:** Customers can only book lessons with instructors of the same ski type (Ski or Snowboard).

**Why:**  
To ensure that customers receive lessons from certified instructors who match their preferred activity. This reduces the likelihood of mismatches and improves the quality of instruction.

---

#### These decisions were made with long-term project goals in mind, including scalability, user experience, and maintainability. Feedback and suggestions are always welcome!

## 🚀Getting Started

### 🔧 Prerequisites

- Python 3.8+
- pip
- Virtual environment manager (optional but recommended)

### 💽 Installation

1. **Clone the repository**:

```bash
  git clone https://github.com/your-username/ski-school-management.git
  cd ski-school-management
```

2. **Create a virtual environment and activate it:**

```bash
  python -m venv venv
  source venv/bin/activate # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**

```bash
  pip install -r requirements.txt
```

4. **Run the app:**

```bash
  flask run
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### 💻Usage

Once the app is running locally:

- Open your browser and go to: http://127.0.0.1:5000/ (or the link provided under "flask run" command)
- Register or log in using your credentials
- Navigate through the application based on your assigned role:
  - Owners: Full access to user and system management
  - Admins: Manage bookings, instructors, time-off requests
  - Instructors: View schedule, request time-off, track lessons
  - Customers: Book lessons, view upcoming lessons

Note: You may need to add the first Owner manually via the database, or extend the app to support Owner registration during initial setup.

There is few users already assigned in the database, to log-in to them:

- Role: Owner
  - Username: Owner
  - Password: 1
- Role: Admin
  - Username: Admin
  - Password: 1
- Role: Instructor
  - Username: Instructor
  - Password: 1
- Role: Customer
  - Username: Customer
  - Password: 1
  <p align="right">(<a href="#readme-top">back to top</a>)</p>

## 🛣️Features To Be Implemented

- Edit settings menu:
  - Dont allow changing their birthday
  - Dont allow admins/instructors changing their profile picture
- Add few new pages:
  - Where instructors could see how many lessons they had in certain time, how much they earned (money per lesson)
  - Where admins could see how much they earned (money per hour)
- When clicking on a lesson, allow staff to press on customers name/surname to access and see the history of their lessons

<p align="right">(<a href="#readme-top">back to top</a>)</p>
