from functools import wraps
from flask import session, redirect

def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "role" not in session or session["role"] != role:
                return redirect("/login")
            return f(*args, **kwargs)
        return wrapper
    return decorator