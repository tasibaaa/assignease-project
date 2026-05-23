from flask import Blueprint, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models.db import get_db
import os
import re

auth_bp = Blueprint("auth_bp", __name__)

# ================= HOME =================
@auth_bp.route("/")
def home():
    return render_template("index.html")


# ================= SIGNUP =================
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        # -------- GET FORM DATA -------- #
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        phone = request.form.get("phone")
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        role = request.form["role"]

        enrollment_no = request.form.get("enrollment_no")
        course = request.form.get("course")
        semester = request.form.get("semester")

        employee_id = request.form.get("employee_id")
        department = request.form.get("department")
        designation = request.form.get("designation")

        profile_pic = request.files.get("profile_pic")

        # -------- BASIC VALIDATIONS -------- #

        if not name or not email or not password or not confirm_password or not role:
            flash("All required fields must be filled.", "danger")
            return redirect("/signup")

        email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_pattern, email):
            flash("Invalid email format.", "danger")
            return redirect("/signup")

        if phone and not re.match(r"^\d{10}$", phone):
            flash("Phone number must be 10 digits.", "danger")
            return redirect("/signup")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect("/signup")

        password_pattern = r"^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$"
        if not re.match(password_pattern, password):
            flash("Password must contain 8+ characters, 1 uppercase, 1 number, and 1 special character.", "danger")
            return redirect("/signup")

        db = get_db()
        cursor = db.cursor(dictionary=True)

        # -------- EMAIL UNIQUENESS -------- #
        cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            db.close()
            flash("Email already registered.", "danger")
            return redirect("/signup")

        # -------- ROLE VALIDATION -------- #
        if role == "student":
            if not enrollment_no or not course or not semester:
                db.close()
                flash("All student fields are required.", "danger")
                return redirect("/signup")

        if role == "faculty":
            if not employee_id or not department or not designation:
                db.close()
                flash("All faculty fields are required.", "danger")
                return redirect("/signup")

        # -------- HASH PASSWORD -------- #
        hashed_password = generate_password_hash(password)

        # -------- INSERT USER -------- #
        cursor.execute("""
            INSERT INTO users
            (name, email, phone, password, role,
             enrollment_no, course, semester,
             employee_id, department, designation)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            name, email, phone, hashed_password, role,
            enrollment_no, course, semester,
            employee_id, department, designation,
            
        ))

        db.commit()

        # 🔥 AUTO LOGIN AFTER SIGNUP
        new_user_id = cursor.lastrowid

        session["user_id"] = new_user_id
        session["role"] = role
        session["name"] = name

        db.close()

        flash("Welcome! Your account has been created.", "success")

        # Redirect directly to role dashboard
        return redirect("/dashboard")

    return render_template("auth/signup.html")


# ================= LOGIN =================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        db.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["user_id"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            return redirect("/dashboard")

        flash("Invalid credentials.", "danger")

    return render_template("auth/login.html")


# ================= LOGOUT =================
@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ================= ROLE REDIRECT =================
@auth_bp.route("/dashboard")
def dashboard():

    if "role" not in session:
        return redirect("/login")

    if session["role"] == "student":
        return redirect("/student/dashboard")

    elif session["role"] == "faculty":
        return redirect("/faculty/dashboard")  # ✅ FIXED HERE

    elif session["role"] == "admin":
        return redirect("/admin/dashboard")

    return redirect("/login")
