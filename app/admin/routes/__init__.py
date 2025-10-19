from flask import Blueprint, redirect, url_for, render_template, request
from flask_login import current_user
from app.main.User import User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin/routes")

from . import Tadmin_routes
from . import Eadmin_routes
from . import senior_eadmin_routes