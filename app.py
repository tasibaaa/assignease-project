from flask import Flask, session
from config import Config
from routes.auth_routes import auth_bp
from routes.student_routes import student_bp
from routes.faculty_routes import faculty_bp
from datetime import timedelta
from models.db import get_db


def create_app():

    app = Flask(__name__)
    app.config.from_object(Config)

    app.secret_key = "super_secret_key_123"
    app.permanent_session_lifetime = timedelta(hours=6)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(faculty_bp)

    # ✅ GLOBAL NOTIFICATION BADGE CONTEXT PROCESSOR
    @app.context_processor
    def inject_unread_notifications():

        if "user_id" not in session:
            return dict(unread_notifications=0)

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT COUNT(*) AS unread
            FROM notifications
            WHERE user_id = %s
            AND is_read = 0
        """, (session["user_id"],))

        unread = cursor.fetchone()["unread"]

        db.close()

        return dict(unread_notifications=unread)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)