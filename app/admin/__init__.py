from flask import Blueprint, redirect, url_for, render_template, request
from flask_login import current_user

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")