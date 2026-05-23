import os
from datetime import datetime
from flask import Blueprint, render_template, request, session, redirect, flash, send_from_directory
from werkzeug.utils import secure_filename
from models.db import get_db
from utils.helpers import role_required
from utils.plagiarism import calculate_similarity
from utils.ml_models import predict_risk_from_db, predict_next_score, generate_recommendation
from utils.notifications import create_notification

student_bp = Blueprint("student_bp", __name__, url_prefix="/student")


# ================= STUDENT DASHBOARD =================
@student_bp.route("/dashboard")
@role_required("student")
def dashboard():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    student_id = session["user_id"]
    
    # ================= MY CLASSES =================
    cursor.execute("""
    SELECT c.class_id, c.class_name, c.class_code
    FROM classes c
    JOIN enrollments e ON c.class_id = e.class_id
    WHERE e.student_id = %s
    AND e.status = 'approved'
""", (student_id,))
    classes = cursor.fetchall()

    # ================= TOTAL ASSIGNMENTS =================
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM assignments a
        JOIN enrollments e ON a.class_id = e.class_id
        WHERE e.student_id = %s AND e.status = 'approved'
    """, (student_id,))
    total_assignments = cursor.fetchone()["total"]

    # ================= PENDING ASSIGNMENTS =================
    cursor.execute("""
    SELECT COUNT(*) AS pending
    FROM assignments a
    JOIN enrollments e ON a.class_id = e.class_id
    WHERE e.student_id = %s
    AND e.status = 'approved'
    AND a.assignment_id NOT IN (
        SELECT assignment_id
        FROM submissions
        WHERE student_id = %s
    )
    """, (student_id, student_id))
    pending_assignments = cursor.fetchone()["pending"]

    # ================= RECENTLY GRADED =================
    cursor.execute("""
        SELECT s.*, a.title
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.assignment_id
        WHERE s.student_id=%s AND s.status='graded'
        ORDER BY s.submitted_at DESC
        LIMIT 5
    """, (student_id,))
    graded = cursor.fetchall()

    # ================= UPCOMING DEADLINES =================
    cursor.execute("""
        SELECT a.*
        FROM assignments a
        JOIN enrollments e ON a.class_id = e.class_id
        WHERE e.student_id = %s
        AND a.deadline >= NOW()
        AND a.assignment_id NOT IN (
            SELECT assignment_id
            FROM submissions
            WHERE student_id = %s 
        )
        ORDER BY a.deadline ASC
        LIMIT 5
    """, (student_id, student_id))
    upcoming = cursor.fetchall()

# convert deadlines into readable text
    for a in upcoming:
        deadline = a["deadline"]
        now = datetime.now()

        diff = deadline - now
        seconds = diff.total_seconds()

        if seconds <= 0:
            a["deadline_text"] = "Expired"
        elif seconds < 3600:
            mins = int(seconds // 60)
            a["deadline_text"] = f"Due in {mins} minutes"
        elif seconds < 86400:
            hrs = int(seconds // 3600)
            a["deadline_text"] = f"Due in {hrs} hours"
        elif seconds < 172800:
            a["deadline_text"] = "Due tomorrow"
        else:
            days = int(seconds // 86400)
            a["deadline_text"] = f"Due in {days} days"
    # ================= CURRENT STUDENT ML FEATURES =================
    cursor.execute("""
        SELECT marks, similarity_score, status
        FROM submissions
        WHERE student_id=%s
        AND marks IS NOT NULL
    """, (student_id,))

    records = cursor.fetchall()

    previous_marks = []
    similarity_scores = []
    late_count = 0
    resubmission_count = 0

    for r in records:
        previous_marks.append(r["marks"])
        similarity_scores.append(r["similarity_score"])

        if r["status"] == "late_submission":
            late_count += 1
        if r["status"] == "resubmission_requested":
            resubmission_count += 1

    avg_marks = sum(previous_marks) / len(previous_marks) if previous_marks else 0
    avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0

    # ================= BUILD TRAINING DATA FROM DATABASE =================
    cursor.execute("""
        SELECT student_id
        FROM submissions
        WHERE marks IS NOT NULL
        GROUP BY student_id
    """)

    students = cursor.fetchall()
    all_students_data = []

    for s in students:
        sid = s["student_id"]

        cursor.execute("""
            SELECT marks, similarity_score, status
            FROM submissions
            WHERE student_id=%s AND marks IS NOT NULL
        """, (sid,))

        student_records = cursor.fetchall()

        if not student_records:
            continue

        marks_list = []
        similarity_list = []
        late = 0
        resubmit = 0

        for r in student_records:
            marks_list.append(r["marks"])
            similarity_list.append(r["similarity_score"])

            if r["status"] == "late_submission":
                late += 1
            if r["status"] == "resubmission_requested":
                resubmit += 1

        avg_marks_all = sum(marks_list) / len(marks_list)*20
        avg_similarity_all = sum(similarity_list) / len(similarity_list)

        # Auto-label
        if avg_marks_all >= 75:
            label = 0
        elif avg_marks_all >= 50:
            label = 1
        else:
            label = 2

        all_students_data.append([
            avg_marks_all,
            late,
            avg_similarity_all,
            resubmit,
            label
        ])

    # ================= ML PREDICTIONS =================
    unique_labels = set([row[4] for row in all_students_data])

    if previous_marks and len(unique_labels) >= 2:
        risk_level = predict_risk_from_db(
            [avg_marks, late_count, avg_similarity, resubmission_count],
            all_students_data
        )

        next_score_prediction = predict_next_score(previous_marks)

        recommendation = generate_recommendation(
            risk_level,
            avg_similarity,
            late_count
        )

    else:
        risk_level = "Not Enough Data"
        next_score_prediction = None
        recommendation = None

    # ================= COUNTS FOR DASHBOARD CARDS =================
    graded_count = len(graded)

    db.close()

    return render_template(
        "student/dashboard.html",
        classes=classes,
        total_classes=len(classes),
        total_assignments=total_assignments,
        pending_assignments=pending_assignments,
        graded=graded_count,
        upcoming=upcoming,
        risk_level=risk_level,
        next_score_prediction=next_score_prediction,
        recommendation=recommendation
    )
    
    # ================= VIEW CLASS =================
@student_bp.route("/class/<int:class_id>")
@role_required("student")
def view_class(class_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM assignments
        WHERE class_id = %s
        ORDER BY created_at DESC
    """, (class_id,))

    assignments = cursor.fetchall()
    db.close()

    return render_template("student/view_class.html", assignments=assignments)


# ================= JOIN CLASS =================
@student_bp.route("/join-class", methods=["POST"])
@role_required("student")
def join_class():

    class_code = request.form.get("class_code", "").strip()

    if not class_code:
        flash("Class code is required.", "danger")
        return redirect("/student/dashboard")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT class_id FROM classes WHERE class_code=%s", (class_code,))
    class_data = cursor.fetchone()

    if not class_data:
        db.close()
        flash("Invalid class code.", "danger")
        return redirect("/student/dashboard")

    cursor.execute("""
        SELECT * FROM enrollments
        WHERE class_id=%s AND student_id=%s
    """, (class_data["class_id"], session["user_id"]))

    if cursor.fetchone():
        db.close()
        flash("You are already enrolled in this class.", "warning")
        return redirect("/student/dashboard")

    cursor.execute("""
        INSERT INTO enrollments (class_id, student_id, status)
        VALUES (%s,%s,'pending')
    """, (class_data["class_id"], session["user_id"]))
    cursor.execute("""
    SELECT faculty_id
    FROM classes
    WHERE class_id=%s
    """, (class_data["class_id"],))

    faculty = cursor.fetchone()

    create_notification(
        faculty["faculty_id"],
        "New class join request received",
        f"/faculty/class/{class_data['class_id']}"
    )            

    db.commit()
    db.close()

    flash("Join request sent. Waiting for faculty approval.", "info")    
    return redirect("/student/dashboard")


# ================= VIEW ASSIGNMENT =================
@student_bp.route("/assignment/<int:assignment_id>")
@role_required("student")
def view_assignment(assignment_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT a.*, c.class_name
        FROM assignments a
        JOIN classes c ON a.class_id = c.class_id
        WHERE a.assignment_id=%s
    """, (assignment_id,))

    assignment = cursor.fetchone()

    if not assignment:
        db.close()
        flash("Assignment not found.", "danger")
        return redirect("/student/dashboard")

    cursor.execute("""
        SELECT *
        FROM submissions
        WHERE assignment_id=%s AND student_id=%s
        ORDER BY submitted_at DESC
    """, (assignment_id, session["user_id"]))

    submissions = cursor.fetchall()
    db.close()

    return render_template(
        "student/view_assignment.html",
        assignment=assignment,
        submissions=submissions
    )


# ================= SUBMIT ASSIGNMENT =================
@student_bp.route("/submit/<int:assignment_id>", methods=["POST"])
@role_required("student")
def submit_assignment(assignment_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT deadline FROM assignments WHERE assignment_id=%s", (assignment_id,))
    assignment = cursor.fetchone()

    if not assignment:
        db.close()
        flash("Assignment not found.", "danger")
        return redirect("/student/dashboard")

    file = request.files.get("file")

    if not file or not file.filename.lower().endswith(".pdf"):
        db.close()
        flash("Only PDF files are allowed.", "danger")
        return redirect(request.referrer)

    filename = secure_filename(file.filename)
    os.makedirs("uploads/submissions", exist_ok=True)
    filepath = os.path.join("uploads/submissions", filename)
    file.save(filepath)

    submitted_time = datetime.now()
    is_late = submitted_time > assignment["deadline"]
    similarity_score = calculate_similarity(filepath, assignment_id)

    status = "late_submission" if is_late else "submitted"

    cursor.execute("""
        INSERT INTO submissions
        (assignment_id, student_id, file_name, submitted_at, similarity_score, status)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        assignment_id,
        session["user_id"],
        filename,
        submitted_time,
        similarity_score,
        status
    ))

    db.commit()
    db.close()

    flash("Assignment submitted successfully!", "success")
    return redirect(request.referrer)


@student_bp.route("/view-submission/<filename>")
@role_required("student")
def view_submission_file(filename):

    uploads_path = os.path.join("uploads", "submissions")
    return send_from_directory(uploads_path, filename)

@student_bp.route("/my-assignments")
@role_required("student")
def my_assignments():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    student_id = session["user_id"]

    cursor.execute("""
        SELECT 
            a.assignment_id,
            a.title,
            a.deadline,
            c.class_name,
            s.status,
            s.submitted_at
        FROM assignments a
        JOIN classes c ON a.class_id = c.class_id
        JOIN enrollments e ON e.class_id = a.class_id
        LEFT JOIN submissions s 
            ON s.assignment_id = a.assignment_id
            AND s.student_id = %s
        WHERE e.student_id = %s 
        AND e.status = 'approved'
        ORDER BY a.deadline ASC
    """, (student_id, student_id))

    assignments = cursor.fetchall()

    db.close()

    return render_template(
        "student/my_assignments.html",
        assignments=assignments
    )
@student_bp.route("/student/notifications")
@role_required("student")
def notifications():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM notifications
        WHERE user_id=%s
        ORDER BY created_at DESC
    """, (session["user_id"],))

    notifications = cursor.fetchall()

    db.close()

    return render_template(
        "student/notifications.html",
        notifications=notifications
    )
@student_bp.route("/my-classes")
@role_required("student")
def my_classes():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    student_id = session["user_id"]

    # approved classes
    cursor.execute("""
        SELECT c.*
        FROM classes c
        JOIN enrollments e
        ON c.class_id = e.class_id
        WHERE e.student_id=%s
        AND e.status='approved'
    """, (student_id,))
    approved_classes = cursor.fetchall()


    # pending requests
    cursor.execute("""
        SELECT c.*
        FROM classes c
        JOIN enrollments e
        ON c.class_id = e.class_id
        WHERE e.student_id=%s
        AND e.status='pending'
    """, (student_id,))
    pending_classes = cursor.fetchall()


    # rejected requests
    cursor.execute("""
        SELECT c.*
        FROM classes c
        JOIN enrollments e
        ON c.class_id = e.class_id
        WHERE e.student_id=%s
        AND e.status='rejected'
    """, (student_id,))
    rejected_classes = cursor.fetchall()


    db.close()

    return render_template(
        "student/my_classes.html",
        approved_classes=approved_classes,
        pending_classes=pending_classes,
        rejected_classes=rejected_classes
    )