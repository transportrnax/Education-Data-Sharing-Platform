from flask import render_template, request, flash, redirect, url_for, Blueprint, session, send_from_directory, current_app, send_file, jsonify
from flask_login import login_required, current_user
from app.main.User import User
from app.admin.models import EAdmin
from app.extensions import mongo
from . import admin_bp
from ..service.Eadmin_service import EAdminService
from bson import ObjectId
from werkzeug.utils import secure_filename
import os
import uuid
import mimetypes

# Initialize the service
eadmin_service = EAdminService()

@admin_bp.route('/eadmin-dashboard')
@login_required
def eadmin_dashboard_page():
    """Main dashboard page for E-Admin"""
    if not current_user.is_authenticated or current_user.role != User.Roles.E_ADMIN:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('auth.login'))
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('auth.logout'))
    current_eadmin = EAdmin(user_doc)
    eadmin_service = EAdminService()
    eadmin_service.email = current_eadmin.email

    # Get registration applications
    app_status_filter = request.args.get('app_status', "pending_eadmin_approval")
    applications_list = eadmin_service.view_registration_applications(status=app_status_filter)

    # Get user logs
    current_log_page = request.args.get('log_page', 1, type=int)
    logs_per_page = 15
    logs_list, total_logs = eadmin_service.view_user_logs(limit=logs_per_page, page=current_log_page)
    total_log_pages = (total_logs + logs_per_page - 1) // logs_per_page if total_logs else 1

    # Get platform policies
    current_policy_page = request.args.get('page', 1, type=int)
    policies_per_page = 10
    platform_policies_list, total_policies = eadmin_service.view_policies(limit=policies_per_page, page=current_policy_page)
    total_policy_pages = (total_policies + policies_per_page - 1) // policies_per_page if total_policies else 1

    return render_template('admin/EAdminDashBoard.html',
                         applications=applications_list or [],
                         current_app_filter=app_status_filter,
                         logs=logs_list or [],
                         current_log_page=current_log_page,
                         total_log_pages=total_log_pages,
                         platform_policies=platform_policies_list or [],
                         current_policy_page=current_policy_page,
                         total_policy_pages=total_policy_pages)

@admin_bp.route('/eadmin/applications/<string:app_id>/approve', methods=['POST'])
@login_required
def eadmin_approve_app(app_id):
    """Approve a registration application"""
    if not current_user.is_authenticated or current_user.role != User.Roles.E_ADMIN:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('auth.login'))
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('auth.logout'))
    current_eadmin = EAdmin(user_doc)
    eadmin_service = EAdminService()
    eadmin_service.email = current_eadmin.email
    success, message = eadmin_service.approveRegistrationApplication(app_id=app_id)
    flash(message, "success" if success else "danger")
    return redirect(url_for('admin.eadmin_dashboard_page', app_status=request.args.get('app_status', "pending_eadmin_approval")))

@admin_bp.route('/eadmin/applications/<string:app_id>/reject', methods=['GET', 'POST'])
@login_required
def eadmin_reject_app_page(app_id):
    """Page for rejecting a registration application"""
    if not current_user.is_authenticated or current_user.role != User.Roles.E_ADMIN:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
        if not user_doc:
            flash("User session error.", "danger")
            return redirect(url_for('auth.logout'))
        
        current_eadmin = EAdmin(user_doc)
        eadmin_service = EAdminService()
        eadmin_service.email = current_eadmin.email
        reason = request.form.get('rejection_reason')
        if not reason:
            flash("Rejection reason is required.", "danger")
            return redirect(url_for('admin.eadmin_reject_app_page', app_id=app_id))

        success, message = eadmin_service.rejectRegistrationApplication(app_id=app_id, reason=reason)
        flash(message, "success" if success else "danger")
        return redirect(url_for('admin.eadmin_dashboard_page', app_status=request.args.get('app_status', "pending_eadmin_approval")))

    return render_template('admin/reject_application.html', app_id=app_id)

@admin_bp.route('/eadmin/policies/add', methods=['POST'])
@login_required
def eadmin_add_policy():
    if not current_user.is_authenticated or current_user.role != User.Roles.E_ADMIN: # Ensure using .value for Enum comparison if appropriate
        flash("Unauthorized access.", "danger")
        return redirect(url_for('auth.login'))
    
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('auth.logout'))
    
    # Assuming EAdmin class is correctly defined and imported for current_eadmin
    # from app.admin.models import EAdmin # Make sure EAdmin is available
    current_eadmin = EAdmin(user_doc) # If EAdmin model is used
    eadmin_service = EAdminService() # Or get it from current_app.extensions if registered
    eadmin_service.email = current_eadmin.email # Set context for the service instance

    title = request.form.get('policy_title')
    description = request.form.get('policy_description')
    policy_file = request.files.get('policy_file') # This is a FileStorage object

    if not all([title, policy_file, policy_file.filename]): # Check policy_file.filename as well
        flash("Title and policy file are required.", "danger")
        return redirect(url_for('admin.eadmin_dashboard_page'))

    # The service will handle file type checks and saving.
    # Pass the FileStorage object directly to the service.
    success, message = eadmin_service.addPolicy(title=title, policy_file_storage=policy_file, description=description)
    
    flash(message, "policy_success" if success else "policy_danger")
    return redirect(url_for('admin.eadmin_dashboard_page'))

@admin_bp.route('/eadmin/policies/<string:policy_id>/delete', methods=['POST'])
@login_required
def eadmin_delete_policy(policy_id):
    """Delete a platform policy"""
    if not current_user.is_authenticated or current_user.role != User.Roles.E_ADMIN:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('auth.login'))
    
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('auth.logout'))
    
    current_eadmin = EAdmin(user_doc)
    eadmin_service = EAdminService()
    eadmin_service.email = current_eadmin.email
    success, message = eadmin_service.deletePolicy(policy_id=policy_id)
    flash(message, "policy_success" if success else "policy_danger")
    return redirect(url_for('admin.eadmin_dashboard_page'))

@admin_bp.route('/eadmin/policies/edit/<string:policy_id>', methods=['GET', 'POST'])
@login_required
def eadmin_edit_policy(policy_id):
    if not current_user.is_authenticated or current_user.role != User.Roles.E_ADMIN:
        return (jsonify({'success': False, 'message': 'Unauthorized access.'}), 403) if request.is_json else redirect(url_for('auth.login'))

    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        return (jsonify({'success': False, 'message': 'User session error.'}), 401) if request.is_json else redirect(url_for('auth.logout'))

    current_eadmin = EAdmin(user_doc)
    eadmin_service = EAdminService()
    eadmin_service.email = current_eadmin.email

    policy_collection = mongo.db.platform_policies
    policy = policy_collection.find_one({"_id": ObjectId(policy_id)})
    if not policy:
        return (jsonify({'success': False, 'message': 'Policy not found.'}), 404) if request.is_json else redirect(url_for('admin.eadmin_dashboard_page'))

    if request.method == 'POST':
        new_title = request.form.get('policy_title')
        new_description = request.form.get('policy_description')
        new_file = request.files.get('policy_file')
        success, message = eadmin_service.updatePolicy(
            policy_id=policy_id,
            title=new_title,
            description=new_description,
            new_policy_file_storage=new_file if new_file and new_file.filename else None
        )
        if request.is_json:
            return jsonify({'success': success, 'message': message})
        flash(message, "policy_success" if success else "policy_danger")
        return redirect(url_for('admin.eadmin_dashboard_page'))

    # GET: 返回policy数据用于modal预填充
    if request.is_json:
        # 只返回需要的字段
        return jsonify({
            'success': True,
            'policy': {
                'title': policy.get('title', ''),
                'description': policy.get('description', ''),
                'file_path': policy.get('file_path', ''),
                'original_filename': policy.get('original_filename', policy.get('filename', ''))
            }
        })
    return render_template('admin/edit_policy.html', policy=policy)

@admin_bp.route('/eadmin/proofdocuments/upload', methods=['POST'])
@login_required
def upload_proof_document():
    if not current_user.is_authenticated or current_user.role != User.Roles.E_ADMIN:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('auth.login'))
    file = request.files.get('proof_document')
    if not file or not file.filename:
        flash("No file selected.", "danger")
        return redirect(request.referrer or url_for('admin.eadmin_dashboard_page'))
    if not file.filename.lower().endswith('.pdf'):
        flash("Only PDF files are allowed.", "danger")
        return redirect(request.referrer or url_for('admin.eadmin_dashboard_page'))
    filename = secure_filename(file.filename)
    upload_dir = os.path.abspath(os.path.join(current_app.root_path, '..', 'uploads', 'proof'))
    os.makedirs(upload_dir, exist_ok=True)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    file.save(os.path.join(upload_dir, unique_filename))
    flash(f"Proof document uploaded: {unique_filename}", "success")
    # Optionally record in DB
    return redirect(url_for('admin.eadmin_dashboard_page'))

@admin_bp.route('/eadmin/proofdocuments/<filename>')
@login_required
def serve_proof_document(filename):
    upload_dir = os.path.abspath(os.path.join(current_app.root_path, '..', 'uploads', 'proof'))
    if '..' in filename or filename.startswith('/'):
        flash("Invalid filename.", "danger")
        return redirect(url_for('admin.eadmin_dashboard_page'))
    abs_file = os.path.join(upload_dir, filename)
    if not abs_file.startswith(upload_dir) or not os.path.isfile(abs_file):
        flash("Proof document not found.", "danger")
        return redirect(request.referrer or url_for('admin.eadmin_dashboard_page'))
    return send_from_directory(upload_dir, filename, as_attachment=False)

@admin_bp.route('/eadmin/policies/file/<filename>')
@login_required
def serve_policy_file(filename):
    upload_dir = os.path.abspath(os.path.join(current_app.root_path, '..', 'uploads', 'policies'))
    if '..' in filename or filename.startswith('/'):
        flash("Invalid filename.", "danger")
        return redirect(url_for('admin.eadmin_dashboard_page'))
    abs_file = os.path.join(upload_dir, filename)
    if not abs_file.startswith(upload_dir) or not os.path.isfile(abs_file):
        flash("Policy file not found.", "danger")
        return redirect(request.referrer or url_for('admin.eadmin_dashboard_page'))
    return send_from_directory(upload_dir, filename, as_attachment=False)