from flask import Blueprint, redirect, url_for, render_template, request
from flask_login import current_user
from app.main.User import User

workspace_bp = Blueprint("workspace", __name__, url_prefix="/workspace/routes")

from . import dashboard_route
from . import member_route
from . import organization_route
from . import service_route
