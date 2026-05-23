import os

class Config:
    SECRET_KEY = "assign_ease_super_secret"

    DB_CONFIG = {
        "host": "localhost",
        "user": "root",
        "password": "",
        "database": "assignease",
        "port": 3306
    }

    UPLOAD_FOLDER = "uploads"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024