import os
import random
import string
from utils.notifications import create_notification
from flask import (
    Blueprint, render_template, request,
    session, redirect, flash
)

from werkzeug.utils import secure_filename
from models.db import get_db
from utils.helpers import role_required
from flask import send_from_directory
from datetime import datetime



faculty_bp = Blueprint("faculty_bp", __name__, url_prefix="/faculty")


# ================= HELPER: GENERATE UNIQUE CLASS CODE =================
def generate_class_code():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        cursor.execute("SELECT class_id FROM classes WHERE class_code=%s", (code,))
        if not cursor.fetchone():
            db.close()
            return code


# ================= FACULTY DASHBOARD =================
@faculty_bp.route("/dashboard")
@role_required("faculty")
def dashboard():

    db = get_db()
    cursor = db.cursor(dictionary=True)
    faculty_id = session["user_id"]

    cursor.execute("""
        SELECT COUNT(*) AS total_classes
        FROM classes
        WHERE faculty_id=%s
    """, (faculty_id,))
    total_classes = cursor.fetchone()["total_classes"]

    cursor.execute("""
        SELECT COUNT(DISTINCT e.student_id) AS total_students
        FROM enrollments e
        JOIN classes c ON e.class_id = c.class_id
        WHERE c.faculty_id=%s
    """, (faculty_id,))
    total_students = cursor.fetchone()["total_students"]

    cursor.execute("""
        SELECT COUNT(*) AS total_assignments
        FROM assignments a
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
    """, (faculty_id,))
    total_assignments = cursor.fetchone()["total_assignments"]

    cursor.execute("""
        SELECT COUNT(*) AS total_submissions
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.assignment_id
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
    """, (faculty_id,))
    total_submissions = cursor.fetchone()["total_submissions"]

    cursor.execute("""
    SELECT COUNT(*) AS pending
    FROM submissions s
    JOIN assignments a ON s.assignment_id = a.assignment_id
    JOIN classes c ON a.class_id = c.class_id
    WHERE c.faculty_id=%s
    AND s.marks IS NULL
    """, (faculty_id,))
    pending = cursor.fetchone()["pending"]

    cursor.execute("""
        SELECT c.class_name,
               ROUND(AVG(s.marks),2) AS average_marks
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.assignment_id
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
        AND s.status='graded'
        GROUP BY c.class_id
    """, (faculty_id,))
    class_average_data = cursor.fetchall()

    cursor.execute("""
        SELECT
            SUM(CASE WHEN s.status='submitted' THEN 1 ELSE 0 END) AS on_time,
            SUM(CASE WHEN s.status='late_submission' THEN 1 ELSE 0 END) AS late
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.assignment_id
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
    """, (faculty_id,))
    submission_status = cursor.fetchone()

    cursor.execute("""
        SELECT u.name,
               ROUND(AVG(s.marks),2) AS avg_marks
        FROM submissions s
        JOIN users u ON s.student_id = u.user_id
        JOIN assignments a ON s.assignment_id = a.assignment_id
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
        AND s.status='graded'
        GROUP BY s.student_id
        ORDER BY avg_marks DESC
        LIMIT 1
    """, (faculty_id,))
    top_performer = cursor.fetchone()

    cursor.execute("""
        SELECT u.name,
               ROUND(AVG(s.marks),2) AS avg_marks
        FROM submissions s
        JOIN users u ON s.student_id = u.user_id
        JOIN assignments a ON s.assignment_id = a.assignment_id
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
        AND s.status='graded'
        GROUP BY s.student_id
        ORDER BY avg_marks ASC
        LIMIT 1
    """, (faculty_id,))
    lowest_performer = cursor.fetchone()

    cursor.execute("""
        SELECT u.name, a.title, s.submitted_at
        FROM submissions s
        JOIN users u ON s.student_id = u.user_id
        JOIN assignments a ON s.assignment_id = a.assignment_id
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
        ORDER BY s.submitted_at DESC
        LIMIT 5
    """, (faculty_id,))
    recent = cursor.fetchall()
    # ================= SUBMISSION TREND =================
    cursor.execute("""
    SELECT DATE(s.submitted_at) AS day,
    COUNT(*) AS total
    FROM submissions s
    JOIN assignments a ON s.assignment_id = a.assignment_id
    JOIN classes c ON a.class_id = c.class_id
    WHERE c.faculty_id=%s
    GROUP BY DATE(s.submitted_at)
    ORDER BY day
    """, (faculty_id,))
    submission_trend = cursor.fetchall()


    # ================= PLAGIARISM DISTRIBUTION =================
    cursor.execute("""
    SELECT
    SUM(CASE WHEN similarity_score < 40 THEN 1 ELSE 0 END) AS low,
    SUM(CASE WHEN similarity_score BETWEEN 40 AND 69 THEN 1 ELSE 0 END) AS medium,
    SUM(CASE WHEN similarity_score >= 70 THEN 1 ELSE 0 END) AS high
    FROM submissions s
    JOIN assignments a ON s.assignment_id = a.assignment_id
    JOIN classes c ON a.class_id = c.class_id
    WHERE c.faculty_id=%s
    """, (faculty_id,))
    plagiarism_data = cursor.fetchone()
    db.close()

    return render_template(
        "faculty/dashboard.html",
        total_classes=total_classes,
        total_students=total_students,
        total_assignments=total_assignments,
        total_submissions=total_submissions,
        pending=pending,
        class_average_data=class_average_data,
        submission_status=submission_status,
        top_performer=top_performer,
        lowest_performer=lowest_performer,
        recent_submissions=recent,
        submission_trend=submission_trend,
        plagiarism_data=plagiarism_data
    )


# ================= CREATE CLASS =================
@faculty_bp.route("/create-class", methods=["GET", "POST"])
@role_required("faculty")
def create_class():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":

     class_name = request.form.get("class_name")
     academic_year = request.form.get("academic_year")
     semester = request.form.get("semester")
     description = request.form.get("description")

    if not class_name:
        flash("Class name is required.", "danger")
        return redirect(request.url)

    class_code = generate_class_code()

    cursor.execute("""
        INSERT INTO classes
        (class_name, class_code, faculty_id,
         academic_year, semester, description)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        class_name,
        class_code,
        session["user_id"],
        academic_year,
        semester,
        description
    ))

    db.commit()
    db.close()

    flash("Class created successfully!", "success")

    return redirect("/faculty/classes")

    db.close()
    return render_template("faculty/create_class.html")


# ================= VIEW ALL CLASSES + SEARCH FILTER =================
@faculty_bp.route("/classes")
@role_required("faculty")
def view_classes():

    search = request.args.get("search", "")
    status = request.args.get("status", "")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    query = """
        SELECT 
        c.*,
        COUNT(DISTINCT e.student_id) AS student_count,
        COUNT(DISTINCT a.assignment_id) AS assignment_count
        FROM classes c
        LEFT JOIN enrollments e 
        ON c.class_id = e.class_id
        LEFT JOIN assignments a 
        ON c.class_id = a.class_id
        WHERE c.faculty_id = %s
    """

    params = [session["user_id"]]

# Search filter
    if search:
        query += " AND (c.class_name LIKE %s OR c.class_code LIKE %s)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")

# Status filter (active / archived)
    if status:
        query += " AND c.status = %s"
        params.append(status)

    query += """
        GROUP BY c.class_id
        ORDER BY c.created_at DESC
    """

    cursor.execute(query, tuple(params))
    classes = cursor.fetchall()

    db.close()

    return render_template(
    "faculty/classes.html",
    classes=classes,
    search=search,
    status=status
)
    # ================= APPROVE STUDENT REQUEST =================

@faculty_bp.route("/approve-student/<int:class_id>/<int:student_id>", methods=["POST"])
@role_required("faculty")
def approve_student(class_id, student_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # approve enrollment
    cursor.execute("""
        UPDATE enrollments
        SET status='approved'
        WHERE class_id=%s AND student_id=%s
    """, (class_id, student_id))


    # get class name
    cursor.execute("""
        SELECT class_name
        FROM classes
        WHERE class_id=%s
    """, (class_id,))

    class_data = cursor.fetchone()


    # notify student
    create_notification(
        student_id,
        f"Your request to join {class_data['class_name']} has been approved",
        f"/student/class/{class_id}"
    )


    db.commit()
    db.close()

    flash("Student approved successfully!", "success")

    return redirect(request.referrer)
# ================= REJECT STUDENT REQUEST =================

@faculty_bp.route("/reject-student/<int:class_id>/<int:student_id>", methods=["POST"])
@role_required("faculty")
def reject_student(class_id, student_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        UPDATE enrollments
        SET status='rejected'
        WHERE class_id=%s AND student_id=%s
    """, (class_id, student_id))


    # get class name
    cursor.execute("""
        SELECT class_name
        FROM classes
        WHERE class_id=%s
    """, (class_id,))

    class_data = cursor.fetchone()


    # notify student
    create_notification(
        student_id,
        f"Your request to join {class_data['class_name']} was rejected",
        f"/student/class/{class_id}"
    )


    db.commit()
    db.close()

    flash("Student request rejected!", "warning")

    return redirect(request.referrer)

# ================= REMOVE STUDENT FROM CLASS =================
@faculty_bp.route("/remove-student/<int:class_id>/<int:student_id>", methods=["POST"])
@role_required("faculty")
def remove_student(class_id, student_id):

    db = get_db()
    cursor = db.cursor()

    # remove enrollment
    cursor.execute("""
        DELETE FROM enrollments
        WHERE class_id=%s AND student_id=%s
    """, (class_id, student_id))

    db.commit()
    db.close()

    flash("Student removed successfully!", "success")

    return redirect(request.referrer)

# ================= ALL ASSIGNMENTS PAGE =================
@faculty_bp.route("/all-assignments")
@role_required("faculty")
def all_assignments():

    search = request.args.get("search", "")
    class_filter = request.args.get("class_id", "")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    query = """
        SELECT a.*, c.class_name
        FROM assignments a
        JOIN classes c ON a.class_id = c.class_id
        WHERE c.faculty_id=%s
    """

    params = [session["user_id"]]

    if search:
        query += " AND a.title LIKE %s"
        params.append(f"%{search}%")

    if class_filter:
        query += " AND a.class_id=%s"
        params.append(class_filter)

    query += " ORDER BY a.deadline ASC"

    cursor.execute(query, tuple(params))
    assignments = cursor.fetchall()

    cursor.execute("""
        SELECT class_id, class_name
        FROM classes
        WHERE faculty_id=%s
    """, (session["user_id"],))
    classes = cursor.fetchall()

    db.close()

    return render_template(
    "faculty/all_assignments.html",
    assignments=assignments,
    classes=classes,
    search=search,
    class_filter=class_filter,
    now=datetime.now
)


# ================= CREATE ASSIGNMENT =================
@faculty_bp.route("/create-assignment", methods=["GET", "POST"])
@role_required("faculty")
def create_assignment():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT class_id, class_name
        FROM classes
        WHERE faculty_id=%s
    """, (session["user_id"],))
    classes = cursor.fetchall()

    selected_class_id = request.args.get("class_id")

    if request.method == "POST":

        class_id = request.form.get("class_id")
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline = request.form.get("deadline")
        total_score = request.form.get("total_score")

        if not class_id or not title or not deadline or not total_score:
            flash("All required fields must be filled.", "danger")
            return redirect(request.url)

        cursor.execute("""
            INSERT INTO assignments
            (class_id, title, description, deadline, total_score)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            class_id,
            title,
            description if description else None,
            deadline,
            total_score
        ))

        assignment_id = cursor.lastrowid

        cursor.execute("""
            SELECT student_id
            FROM enrollments
            WHERE class_id=%s
        """, (class_id,))
        students = cursor.fetchall()

        for s in students:
            create_notification(
                s["student_id"],
                f"New assignment posted: {title}",
                f"/student/assignment/{assignment_id}"
            )

        db.commit()
        db.close()

        flash("Assignment created successfully!", "success")
        return redirect("/faculty/all-assignments")

    db.close()
    return render_template(
        "faculty/create_assignment.html",
        classes=classes,
        selected_class_id=selected_class_id
    )
@faculty_bp.route("/class/<int:class_id>")
@role_required("faculty")
def view_class(class_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    faculty_id = session["user_id"]

    # verify class ownership
    cursor.execute("""
        SELECT *
        FROM classes
        WHERE class_id=%s AND faculty_id=%s
    """, (class_id, faculty_id))

    class_data = cursor.fetchone()

    if not class_data:
        db.close()
        flash("Unauthorized access.", "danger")
        return redirect("/faculty/classes")

    # ---------------- PAGINATION / SHOW ALL ----------------

    page = request.args.get("page", 1, type=int)
    show_all = request.args.get("show_all")

    if show_all:
        per_page = 1000
    else:
        per_page = 5

    offset = (page - 1) * per_page

    # total students count
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM enrollments
        WHERE class_id=%s
    """, (class_id,))

    total_students = cursor.fetchone()["total"]

    # paginated students
    cursor.execute("""
        SELECT u.user_id, u.name, u.email
        FROM enrollments e
        JOIN users u ON e.student_id = u.user_id
        WHERE e.class_id=%s
        ORDER BY u.name ASC
        LIMIT %s OFFSET %s
    """, (class_id, per_page, offset))

    students = cursor.fetchall()

    total_pages = (total_students + per_page - 1) // per_page

    # assignments
    cursor.execute("""
        SELECT *
        FROM assignments
        WHERE class_id=%s
        ORDER BY created_at DESC
    """, (class_id,))

    assignments = cursor.fetchall()
# ================= PENDING JOIN REQUESTS =================

    cursor.execute("""
    SELECT u.user_id, u.name, u.email
    FROM enrollments e
    JOIN users u ON e.student_id = u.user_id
    WHERE e.class_id=%s
    AND e.status='pending'
    """, (class_id,))

    pending_requests = cursor.fetchall()
    db.close()

    return render_template(
    "faculty/view_class.html",
    class_data=class_data,
    students=students,
    assignments=assignments,
    pending_requests=pending_requests,
    page=page,
    total_pages=total_pages
)

# ================= ARCHIVE CLASS =================
@faculty_bp.route("/archive-class/<int:class_id>", methods=["POST"])
@role_required("faculty")
def archive_class(class_id):
    print("ARCHIVE ROUTE HIT")
    db = get_db()
    cursor = db.cursor()

    faculty_id = session["user_id"]

    # verify ownership
    cursor.execute("""
        SELECT class_id
        FROM classes
        WHERE class_id=%s AND faculty_id=%s
    """, (class_id, faculty_id))

    class_data = cursor.fetchone()

    if not class_data:
        db.close()
        flash("Unauthorized action.", "danger")
        return redirect("/faculty/classes")

    # toggle status
    cursor.execute("""
        UPDATE classes
        SET status = CASE
            WHEN status='active' THEN 'archived'
            ELSE 'active'
        END
        WHERE class_id=%s
    """, (class_id,))

    db.commit()
    db.close()

    flash("Class status updated successfully!", "success")

    return redirect("/faculty/classes")
# ================= DELETE CLASS =================
@faculty_bp.route("/delete-class/<int:class_id>", methods=["POST"])
@role_required("faculty")
def delete_class(class_id):

    db = get_db()
    cursor = db.cursor()

    faculty_id = session["user_id"]

    # Verify faculty owns this class
    cursor.execute("""
        SELECT class_id
        FROM classes
        WHERE class_id=%s AND faculty_id=%s
    """, (class_id, faculty_id))

    if not cursor.fetchone():
        db.close()
        flash("Unauthorized action.", "danger")
        return redirect("/faculty/classes")


    # 1️⃣ Delete submissions linked to assignments of this class
    cursor.execute("""
        DELETE submissions
        FROM submissions
        JOIN assignments
        ON submissions.assignment_id = assignments.assignment_id
        WHERE assignments.class_id=%s
    """, (class_id,))


    # 2️⃣ Delete assignments of this class
    cursor.execute("""
        DELETE FROM assignments
        WHERE class_id=%s
    """, (class_id,))


    # 3️⃣ Delete enrollments of this class
    cursor.execute("""
        DELETE FROM enrollments
        WHERE class_id=%s
    """, (class_id,))


    # 4️⃣ Finally delete class itself
    cursor.execute("""
        DELETE FROM classes
        WHERE class_id=%s
    """, (class_id,))


    db.commit()
    db.close()

    flash("Class deleted permanently.", "success")

    return redirect("/faculty/classes")
# ================= VIEW SUBMISSIONS =================
@faculty_bp.route("/submissions/<int:assignment_id>")
@role_required("faculty")
def view_submissions(assignment_id):

    search = request.args.get("search", "")
    status = request.args.get("status", "")
    plagiarism = request.args.get("plagiarism", "")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # verify faculty owns assignment
    cursor.execute("""
        SELECT a.assignment_id, a.class_id
        FROM assignments a
        JOIN classes c ON a.class_id = c.class_id
        WHERE a.assignment_id=%s AND c.faculty_id=%s
    """, (assignment_id, session["user_id"]))

    assignment = cursor.fetchone()

    if not assignment:
        db.close()
        flash("Unauthorized access.", "danger")
        return redirect("/faculty/allassignments")

    class_id = assignment["class_id"]


    # ================= NOT SUBMITTED FILTER =================

    if status == "not_submitted":

        query = """
            SELECT
                u.user_id,
                u.name,
                NULL AS status,
                NULL AS similarity_score,
                NULL AS submitted_at,
                NULL AS file_name,
                NULL AS submission_id
            FROM enrollments e
            JOIN users u ON e.student_id = u.user_id
            WHERE e.class_id = %s
            AND e.status='approved'
            AND u.user_id NOT IN (
                SELECT student_id
                FROM submissions
                WHERE assignment_id = %s
            )
        """

        params = [class_id, assignment_id]

        if search:
            query += " AND u.name LIKE %s"
            params.append(f"%{search}%")

        query += " ORDER BY u.name ASC"


    # ================= NORMAL SUBMISSION FILTER =================

    else:

        query = """
            SELECT s.*, u.name
            FROM submissions s
            JOIN users u ON s.student_id = u.user_id
            WHERE s.assignment_id = %s
        """

        params = [assignment_id]

        # search filter
        if search:
            query += " AND u.name LIKE %s"
            params.append(f"%{search}%")

        # status filter
        if status:
            query += " AND s.status = %s"
            params.append(status)

        # plagiarism filter
        if plagiarism == "high":
            query += " AND s.similarity_score >= 70"

        elif plagiarism == "medium":
            query += " AND s.similarity_score BETWEEN 40 AND 69"

        elif plagiarism == "low":
            query += " AND s.similarity_score < 40"

        query += " ORDER BY s.submitted_at DESC"


    cursor.execute(query, tuple(params))
    submissions = cursor.fetchall()

    db.close()

    return render_template(
        "faculty/view_submissions.html",
        submissions=submissions,
        assignment_id=assignment_id,
        class_id=class_id
    )
    # ================= UPDATE ASSIGNMENT =================
@faculty_bp.route("/update-assignment/<int:assignment_id>", methods=["GET", "POST"])
@role_required("faculty")
def update_assignment(assignment_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get assignment
    cursor.execute("""
        SELECT *
        FROM assignments
        WHERE assignment_id=%s
    """, (assignment_id,))

    assignment = cursor.fetchone()

    if not assignment:
        db.close()
        flash("Assignment not found.", "danger")
        return redirect("/faculty/all-assignments")

    if request.method == "POST":

        title = request.form.get("title")
        description = request.form.get("description")
        deadline = request.form.get("deadline")
        total_score = request.form.get("total_score")

        cursor.execute("""
            UPDATE assignments
            SET title=%s,
                description=%s,
                deadline=%s,
                total_score=%s
            WHERE assignment_id=%s
        """, (
            title,
            description,
            deadline,
            total_score,
            assignment_id
        ))

        db.commit()
        db.close()

        flash("Assignment updated successfully!", "success")
        return redirect("/faculty/all-assignments")

    db.close()

    return render_template(
        "faculty/update_assignment.html",
        assignment=assignment
    )
    # ================= GRADE SUBMISSION =================
@faculty_bp.route("/grade/<int:submission_id>", methods=["POST"])
@role_required("faculty")
def grade(submission_id):

    marks = request.form.get("marks")
    feedback = request.form.get("feedback")
    action = request.form.get("action")

    db = get_db()
    cursor = db.cursor()

    if action == "finalize":

        cursor.execute("""
            UPDATE submissions
            SET marks=%s,
                feedback=%s,
                status='graded'
            WHERE submission_id=%s
        """, (marks, feedback, submission_id))

    elif action == "resubmit":

        cursor.execute("""
            UPDATE submissions
            SET feedback=%s,
                status='resubmission_requested'
            WHERE submission_id=%s
        """, (feedback, submission_id))

    db.commit()
    db.close()

    flash("Submission updated successfully!", "success")

    return redirect(request.referrer)
# ================= FACULTY NOTIFICATIONS =================
@faculty_bp.route("/notifications")
@role_required("faculty")
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
    cursor.execute("""
    UPDATE notifications
    SET is_read=1
    WHERE user_id=%s
    """, (session["user_id"],))
    db.close()

    return render_template(
        "faculty/notifications.html",
        notifications=notifications
    )