from flask import Blueprint, redirect, url_for, render_template, request
from flask_login import current_user
from app.main.User import User

workspace_bp = Blueprint("workspace", __name__, url_prefix="/workspace")

@workspace_bp.before_app_request
def check_identity():
	if request.endpoint and (
        request.endpoint.startswith('auth.') or
        request.endpoint == 'static' or 
        request.endpoint == 'main.index' 
    ):  return
	if not current_user.is_authenticated:
		return redirect(url_for("auth.login"))
	
	if current_user.role != User.Roles.O_CONVENER:
 		redirect(url_for("auth.login"))


