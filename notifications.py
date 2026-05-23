from models.db import get_db

def create_notification(user_id, message, link=None):

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO notifications (user_id, message, link)
        VALUES (%s, %s, %s)
    """, (user_id, message, link))

    db.commit()
    db.close()