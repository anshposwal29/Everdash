from flask import request, abort, redirect, url_for
from functools import wraps
from flask_login import current_user
from config import Config


def check_ip_address():
    """Check if the request IP address is allowed"""
    # Get the real IP address (handles proxy situations)
    if request.headers.get('X-Forwarded-For'):
        ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        ip_address = request.remote_addr

    allowed_prefix = Config.IP_PREFIX_ALLOWED

    # Check if IP starts with allowed prefix
    if not ip_address.startswith(allowed_prefix):
        return False

    return True


def require_ip_whitelist(f):
    """Decorator to require IP whitelist for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_ip_address():
            abort(403, description="Access denied. Your IP address is not authorized to access this resource.")
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def ip_and_admin_required(f):
    """Decorator combining IP whitelist and admin authentication"""
    @wraps(f)
    @require_ip_whitelist
    @admin_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function
