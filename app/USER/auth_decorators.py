# src/app/auth_decorators.py (New File)

from functools import wraps
from flask import session, redirect, url_for, abort, g
from .user import User # Adjust path if needed

def login_required(f):
    """Ensures user is logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('user.login_page')) # Redirect to user blueprint login
        # Store user in g for access within the request
        g.user = User.find_by_id(session['user_id'])
        if g.user is None:
             session.clear() # Clear invalid session
             return redirect(url_for('user.login_page'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    """Ensures user is logged in and has one of the allowed roles."""
    if not isinstance(allowed_roles, list):
        allowed_roles = [allowed_roles] # Ensure it's a list

    def decorator(f):
        @wraps(f)
        @login_required # Apply login_required first
        def decorated_function(*args, **kwargs):
            # g.user should be set by @login_required
            if not hasattr(g, 'user') or g.user.user_role not in allowed_roles:
                abort(403) # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Constants for Roles (can be imported from User model too) ---
ROLE_T_ADMIN = "T-Admin"
ROLE_E_ADMIN = "E-Admin"
ROLE_O_CONVENER = "O-Convener"

{% if current_user.access_level[0] %}
                    <a href="{{ url_for('datauser.public_consumer')}}">Dashboard</a>
                    <!-- <a href="{{ url_for('main.course_list') }}">View Courses</a> -->
                {% elif current_user.access_level[1] %}
                    <a href="{{ url_for('datauser.private_consumer')}}">Dashboard</a>
                    <!-- <a href="{{ url_for('main.request_thesis') }}">Download Thesis</a>
                    <a href="{{ url_for('main.verify_student') }}">Student Identity Verification</a> -->
                {% elif current_user.access_level[2] %}
                    <a href="{{ url_for('datauser.provider_dashboard')}}">Dashboard</a>
                    <!-- <a href="{{ url_for('main.provide_services') }}">Provide Services</a> -->
                {% endif %}