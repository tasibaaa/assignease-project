from datetime import datetime, timedelta
from models.db import get_db
from utils.notifications import create_notification

def send_deadline_reminders():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    reminder_date = datetime.now() + timedelta(days=2)

    cursor.execute("""
        SELECT assignment_id, title
        FROM assignments
        WHERE DATE(deadline) = DATE(%s)
    """, (reminder_date,))

    assignments = cursor.fetchall()

    for a in assignments:

        cursor.execute("""
        SELECT student_id
        FROM enrollments
        WHERE class_id IN (
            SELECT class_id
            FROM assignments
            WHERE assignment_id=%s
        )
        """, (a["assignment_id"],))

        students = cursor.fetchall()

        for s in students:

            create_notification(
                s["student_id"],
                f"Reminder: Assignment '{a['title']}' is due in 2 days."
            )

    db.close()