import os
import uuid # For generating unique IDs\
import math

from flask import (
    render_template, request, flash, redirect, url_for, session, jsonify,
    current_app, send_from_directory
)
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from bson import ObjectId
from bson.errors import InvalidId # Make sure this is imported if you use ObjectId(app_id) directly

from . import user_bp
from ..extensions import mongo
from ..models.ActivityRecord import ActivityRecord
from ..models.UserQuestion import UserQuestion # For status constants (if used in this file)

from .user import User # Base User class and Role constants
from .service.verification_service import VerificationService, VERIFICATION_SUCCESS, VERIFICATION_FAILED_INVALID, CODE_SENT_SUCCESS, CODE_SEND_FAILED_EMAIL, CODE_SEND_FAILED_DB
from .auth_decorators import login_required, role_required, ROLE_T_ADMIN, ROLE_E_ADMIN, ROLE_O_CONVENER
from .handle_utils import valid_email
from .service.application_service import handle_admin_application_send_code, handle_admin_application_submit_details
from .service.application_service import REG_STATUS_REJECTED, REG_STATUS_PENDING_APPROVAL

from .TAdmin import TAdmin
from .EAdmin import EAdmin
from .OConvener import OConvener

REG_STATUS_PENDING_APPROVAL = "pending_admin_approval"
REG_STATUS_APPROVED = "approved"
REG_STATUS_REJECTED = "rejected"

def allowed_file(filename):
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'pdf'}) # Ensure 'ALLOWED_EXTENSIONS' is in Config
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

# ==============================================================================
# --- AUTHENTICATION ROUTES (Login, Logout, Code Handling for Login) ---
# ==============================================================================

@user_bp.route('/login', methods=['GET'])
def login_page():
    """
    Renders the login page.
    If the user is already logged in, redirects them to their respective dashboard.
    """
    if 'user_id' in session:
        user_role = session.get('user_role')
        if user_role == ROLE_T_ADMIN:
            return redirect(url_for('user.tadmin_dashboard_page'))
        elif user_role == ROLE_E_ADMIN:
            return redirect(url_for('user.eadmin_dashboard_page'))
        elif user_role == ROLE_O_CONVENER:
            return redirect(url_for('user.oconvener_dashboard_page'))
        else: # Fallback for other roles or if role is not set
            return redirect(url_for('main.index'))
    form_data = session.pop('_login_form_data', {})
    return render_template('auth/login.html', form_data=form_data)

@user_bp.route('/logout')
@login_required
def logout_page():
    """
    Logs out the current user by clearing the session.
    """
    user_email = session.get('user_email', 'Unknown user') # For logging
    ActivityRecord(userAccount=user_email, activityName="User Logout").addRecord()
    session.clear()
    flash("You have been successfully logged out.", "success")
    return redirect(url_for('user.login_page'))

@user_bp.route('/login/send-code', methods=['POST'])
def login_send_code():
    """
    Handles the request to send a verification code for login.
    """
    email = request.form.get('email', '').strip()
    session['_login_form_data'] = {'email': email} # Store for pre-filling form

    if not email:
        flash('Please enter your email address to receive a verification code.', 'login_danger')
        return redirect(url_for('user.login_page'))

    # Check if user exists before sending code for login
    user_exists = User.find_by_email(email)
    if not user_exists:
        flash('This email is not registered. Please apply for an account if you are new.', 'login_danger')
        return redirect(url_for('user.login_page'))

    status_code_str, message, _ = VerificationService.create_and_send_code(email, purpose='login')

    if status_code_str == CODE_SENT_SUCCESS:
        flash(message or "Login verification code sent. Please check your email.", 'login_success')
    else:
        flash(message or "Failed to send login verification code. Please try again.", 'login_danger')
    return redirect(url_for('user.login_page'))

@user_bp.route('/login/submit', methods=['POST'])
def login_submit():
    """
    Handles the login form submission with email and verification code.
    """
    email = request.form.get('email', '').strip()
    code = request.form.get('code', '').strip()
    session['_login_form_data'] = {'email': email} # Store for pre-filling if login fails

    if not email or not code:
        flash('Email and verification code are both required for login.', 'login_danger')
        return render_template('auth/login.html', form_data={'email': email})

    verification_status = VerificationService.verify_code(email, code, purpose='login')

    if verification_status == VERIFICATION_SUCCESS:
        user_obj = User.find_by_email(email)
        if user_obj:
            session['user_id'] = user_obj._id
            session['user_email'] = user_obj.email
            session['user_role'] = user_obj.user_role
            session.permanent = True # Make session persistent
            current_app.permanent_session_lifetime = current_app.config.get('PERMANENT_SESSION_LIFETIME')


            ActivityRecord(userAccount=email, activityName="Successful Login").addRecord()
            flash('Login successful!', 'login_success')

            # Redirect based on role
            if user_obj.user_role == ROLE_T_ADMIN:
                return redirect(url_for('user.tadmin_dashboard_page'))
            elif user_obj.user_role == ROLE_E_ADMIN:
                return redirect(url_for('user.eadmin_dashboard_page'))
            elif user_obj.user_role == ROLE_O_CONVENER:
                return redirect(url_for('user.oconvener_dashboard_page'))
            else: # Default redirect for other roles
                return redirect(url_for('main.index'))
        else:
            # This case should ideally not happen if email was verified and user exists
            flash('Login failed: User not found after code verification. Please contact support.', 'login_danger')
    else:
        flash('Login failed: Invalid or expired verification code.', 'login_danger')
    
    return render_template('auth/login.html', form_data={'email': email})

def allowed_file(filename):
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'pdf'})
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions
# =======================================================================================
# --- NEW PUBLIC APPLICATION FLOW FOR ADMIN ROLES (O-Convener / T-Admin) ---
# =======================================================================================

@user_bp.route('/apply-admin-role', methods=['GET'])
def apply_for_admin_role_page():
    if 'user_id' in session: # User already logged in
        flash("You are already logged in. Logout first to register a new admin account.", "info")
        return redirect(url_for('main.index'))

    form_data = session.pop('_direct_admin_creation_form_data', {})
    # Assuming you have 'apply_for_admin_role.html' for this first step
    return render_template('register.html',
                           form_data=form_data,
                           ROLE_O_CONVENER=User.ROLE_O_CONVENER,
                           ROLE_T_ADMIN=User.ROLE_T_ADMIN)

@user_bp.route('/apply-admin/send-code', methods=['POST'])
def admin_application_send_code():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    requested_role = request.form.get('requested_role', '').strip()
    org_name = request.form.get('org_name', '').strip() if requested_role == User.ROLE_O_CONVENER else None

    # Store submitted data in session for pre-filling and for the next step
    application_data = {
        'username': username, 'email': email,
        'requested_role': requested_role, 'org_name': org_name
    }
    # For re-rendering this page on error if send_code fails immediately
    session['_direct_admin_creation_form_data'] = application_data
    # For carrying over to the code verification step
    session['_direct_admin_creation_pending_verification'] = application_data

    # Validation
    if not username or not email or not requested_role:
        flash('Name/Username, Email, and Desired Role are required.', 'danger')
        return redirect(url_for('user.apply_for_admin_role_page'))
    if requested_role == User.ROLE_O_CONVENER and not org_name:
        flash('Proposed Organization Name is required when applying for O-Convener.', 'danger')
        return redirect(url_for('user.apply_for_admin_role_page'))
    if not valid_email(email): # Assuming User.valid_email exists
         flash('Invalid email format.', 'danger')
         return redirect(url_for('user.apply_for_admin_role_page'))

    if User.find_by_email(email):
        flash('This email address is already registered. Please login or use a different email.', 'warning')
        return redirect(url_for('user.apply_for_admin_role_page'))

    # Send verification code (purpose can be more generic now)
    purpose = f"admin_account_creation_{requested_role.lower().replace('-', '_')}"
    status_code_str, message, _ = VerificationService.create_and_send_code(email, purpose=purpose)

    if status_code_str == CODE_SENT_SUCCESS:
        flash('A verification code has been sent to your email. Please enter it to complete your account creation.', 'success')
        session.pop('_direct_admin_creation_form_data', None) # Clear if code sent successfully
        return redirect(url_for('user.admin_application_submit_details')) # Proceed to code entry page
    else:
        flash(message or "Failed to send verification code. Please try again.", 'danger')
        return redirect(url_for('user.apply_for_admin_role_page'))


@user_bp.route('/apply-admin/submit-details', methods=['GET', 'POST'])
def admin_application_submit_details():
    if '_direct_admin_creation_pending_verification' not in session:
        flash("Invalid registration flow or session expired. Please start your application again.", 'danger')
        return redirect(url_for('user.apply_for_admin_role_page'))

    application_details_from_session = session.get('_direct_admin_creation_pending_verification', {})

    if request.method == 'GET':
        # Render the code entry form. Use 'register_OConvener.html' but ensure it does NOT ask for proof document here.
        return render_template('register.html',
                               form_data=application_details_from_session,
                               ROLE_O_CONVENER=User.ROLE_O_CONVENER) # Pass for conditional display in template if any

    # --- POST: Process code verification and direct user creation ---
    code = request.form.get('code', '').strip()

    email_to_verify = application_details_from_session.get('email')
    requested_role = application_details_from_session.get('requested_role')
    applicant_username = application_details_from_session.get('username')
    org_name_for_oconvener = application_details_from_session.get('org_name') # Will be None if not O-Convener

    if not code:
        flash('Verification code is required.', 'danger')
        return render_template('register.html', form_data=application_details_from_session, ROLE_O_CONVENER=User.ROLE_O_CONVENER)

    verification_purpose = f"admin_account_creation_{requested_role.lower().replace('-', '_')}"
    verification_status = VerificationService.verify_code(email_to_verify, code, purpose=verification_purpose)

    if verification_status != VERIFICATION_SUCCESS:
        flash('Invalid or expired verification code. Please try again.', 'danger')
        return render_template('register.html', form_data=application_details_from_session, ROLE_O_CONVENER=User.ROLE_O_CONVENER)

    # --- Code Verified - Directly Create User Account ---
    # Double-check email isn't taken in a race condition
    if User.find_by_email(email_to_verify):
        flash('This email address was registered while you were verifying. Please login or use a different email.', 'warning')
        # Clear session data
        session.pop('_direct_admin_creation_pending_verification', None)
        session.pop('_direct_admin_creation_form_data', None) # Just in case
        return redirect(url_for('user.apply_for_admin_role_page'))

    new_user = None
    user_created_successfully = False

    if requested_role == User.ROLE_T_ADMIN:
        new_user = TAdmin(email=email_to_verify, username=applicant_username)
        if new_user.save():
            user_created_successfully = True
    elif requested_role == User.ROLE_O_CONVENER:
        # Generate organization_id for the O-Convener user record
        # The organization itself is not yet approved or in the 'organizations' table
        generated_org_id = str(uuid.uuid4())
        new_user = OConvener(
            email=email_to_verify,
            username=applicant_username,
            organization_id=generated_org_id,
            organization_name=org_name_for_oconvener # Store proposed name
        )
        if new_user.save():
            user_created_successfully = True
            ActivityRecord(userAccount=email_to_verify, activityName="OConvener User Created",
                           details=f"Org ID pre-assigned: {generated_org_id}, Proposed Org Name: {org_name_for_oconvener}").addRecord()
    else:
        flash(f"Invalid role '{requested_role}' encountered during account creation.", "danger")
        # Clear session data
        session.pop('_direct_admin_creation_pending_verification', None)
        return redirect(url_for('user.apply_for_admin_role_page'))

    if user_created_successfully:
        session.pop('_direct_admin_creation_pending_verification', None)
        flash(f'{requested_role} account created successfully! Please login.', 'success')
        ActivityRecord(userAccount=email_to_verify, activityName=f"{requested_role} User Account Created Directly").addRecord()
        return redirect(url_for('user.login_page'))
    else:
        flash('An error occurred while creating your account after verification. Please try again or contact support.', 'danger')
        # Retain session data for re-attempt if appropriate, or clear and redirect
        return render_template('register.html', form_data=application_details_from_session, ROLE_O_CONVENER=User.ROLE_O_CONVENER)


# === Stage 2: O-Convener Formally Registers Their Organization (Requires EAdmin Approval) ===

@user_bp.route('/register/send-code', methods=['POST']) 
def handle_send_registration_code():

    org_name = request.form.get('org_name', '').strip()
    
    email = request.form.get('email_for_code', '').strip()
    form_data_for_session = {'org_name': org_name, 'email_for_code': email}
    if not email:
        flash('Please enter your email address to receive a verification code.', 'login_danger')
        return redirect(url_for('user.oconvener_setup_organization_page'))

    if not org_name:
        flash('Organization Name is required.', 'danger')
        session['_register_org_form_data'] = form_data_for_session 
        return redirect(url_for('user.oconvener_setup_organization_page')) 

    if not email or not valid_email(email):
        flash('A valid Email address is required.', 'danger')
        session['_register_org_form_data'] = form_data_for_session 
        return redirect(url_for('user.oconvener_setup_organization_page'))

    purpose = "oconvener_org_setup_verification"
    status_code_str, message, _ = VerificationService.create_and_send_code(email, purpose=purpose)

    if status_code_str == CODE_SENT_SUCCESS:
        flash('Verification code sent successfully. Please enter it below.', 'success')
        session['_register_org_form_data'] = form_data_for_session
    else:
        flash(message or 'Failed to send verification code. Please try again.', 'danger')
        session['_register_org_form_data'] = form_data_for_session
    print(session['_register_org_form_data'])
    return redirect(url_for('user.oconvener_setup_organization_page'))

@user_bp.route('/oconvener/setup-organization', methods=['GET'])
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_setup_organization_page():
    current_user_doc = OConvener.find_by_id(session['user_id'])
    current_oconvener = OConvener(**current_user_doc.to_dict())

    org_id_on_user = current_oconvener.organization_id
    org_name_on_user = current_oconvener.organization_name

    if not org_id_on_user:
        flash('Critical error: Your O-Convener account is missing an assigned Organization ID. This should have been set upon account creation. Please contact an administrator.', 'danger')
        return redirect(url_for('user.oconvener_dashboard_page'))

    # Check if an organization approval request is already pending or if org is active
    pending_org_request = mongo.db.organization_approval_requests.find_one({
        "oconvener_user_id": current_oconvener._id,
        "organization_id_on_user": org_id_on_user,
        "status": "pending_eadmin_approval"
    })
    active_organization = mongo.db.organizations.find_one({"_id": org_id_on_user, "status": "active"})

    if active_organization:
        flash(f"Your organization '{active_organization.get('name')}' is already formally registered and active.", "info")
        return redirect(url_for('user.oconvener_dashboard_page'))

    if pending_org_request:
        flash(f"Your application to register organization '{pending_org_request.get('organization_name')}' is already pending E-Admin approval.", "info")
        return redirect(url_for('user.oconvener_dashboard_page'))
    form_data_from_session = session.pop('_register_org_form_data', None) # 使用 pop 获取并移除
    print(form_data_from_session)

    if form_data_from_session:
        form_data = {
            'organization_id': org_id_on_user, 
            'org_name': form_data_from_session.get('org_name', ''), 
            'email_for_code': form_data_from_session.get('email_for_code', ''), 
        }
        if not form_data['email_for_code'] and hasattr(current_oconvener, 'email'):
             form_data['email_for_code'] = current_oconvener.email
    else:
        form_data = {
            'organization_id': org_id_on_user,
            'org_name': org_name_on_user,
            'email_for_code': current_oconvener.email if hasattr(current_oconvener, 'email') else '',
            'code': '' 
        }

    print(form_data)
    return render_template('register_Organization.html', form_data=form_data)


@user_bp.route('/oconvener/submit-organization-setup', methods=['POST'])
@login_required
@role_required(ROLE_O_CONVENER)
def handle_organization_setup_submission():
    current_user_doc = OConvener.find_by_id(session['user_id'])
    current_oconvener = OConvener(**current_user_doc.to_dict())

    org_name_from_form = request.form.get('org_name', '').strip()
    code = request.form.get('code', '').strip()
    proof_document_file = request.files.get('proof_document')
    email_for_verification = request.form.get('email', session.get('_oconvener_reg_pending_verification', {}).get('email'))

    form_data_for_session = {
        'org_name': org_name_from_form,
        'email_for_code': email_for_verification, 
    }

    if not org_name_from_form:
        flash('Organization Name is required.', 'danger')
        session['_register_org_form_data'] = form_data_for_session # 出错时保存数据
        return redirect(url_for('user.oconvener_setup_organization_page'))

    if not code:
        flash('Verification code is required.', 'danger')
        session['_register_org_form_data'] = form_data_for_session
        return redirect(url_for('user.oconvener_setup_organization_page'))

    if not current_oconvener.organization_id: # Should always be present now
        flash('Error: Your account does not have an assigned Organization ID. Please contact an administrator.', 'danger')
        return redirect(url_for('user.oconvener_dashboard_page'))

    # Proof document validation
    if not proof_document_file or proof_document_file.filename == '':
        flash('A proof document (PDF) is required to register your organization.', 'danger')
        return redirect(url_for('user.oconvener_setup_organization_page'))
    
    stored_proof_filename = None
    if proof_document_file and allowed_file(proof_document_file.filename):
        try:
            filename = secure_filename(proof_document_file.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER')
            if not os.path.exists(upload_folder): os.makedirs(upload_folder)
            unique_filename = f"{uuid.uuid4().hex}_{filename}" # Ensure uuid is imported
            proof_document_file.save(os.path.join(upload_folder, unique_filename))
            stored_proof_filename = unique_filename
        except Exception as e:
            current_app.logger.error(f"Error uploading proof file for organization registration: {e}")
            flash('An error occurred while uploading the proof document. Please try again.', 'danger')
            return redirect(url_for('user.oconvener_setup_organization_page'))
    else:
        flash('Invalid proof document file type. Only PDF files are allowed.', 'danger')
        return redirect(url_for('user.oconvener_setup_organization_page'))

    # Update the organization_name on the OConvener user object itself if it has changed
    # from what was set during user creation.
    if current_oconvener.organization_name != org_name_from_form:
        current_oconvener.organization_name = org_name_from_form
        if not current_oconvener.save():
            flash('Failed to update your user record with the new organization name. Please try again.', 'danger')
            # Potentially delete uploaded file if this fails, or handle more robustly
            return redirect(url_for('user.oconvener_setup_organization_page'))

    # Create an organization approval request instead of directly writing to 'organizations'
    org_approval_request_data = {
        "oconvener_user_id": current_oconvener._id,
        "organization_id_on_user": current_oconvener.organization_id, # The ID system assigned to the user
        "org_name": org_name_from_form,
        "proof_document_path": stored_proof_filename,
        "status": "pending_admin_approval",
        "submitted_at": datetime.now(timezone.utc), # Ensure datetime, timezone imported
        "email": email_for_verification
    }
    
    try:
        # Check if a request for this user and org_id already exists and is pending
        existing_request = mongo.db.organization_approval_requests.find_one({
            "oconvener_user_id": current_oconvener._id,
            "organization_id_on_user": current_oconvener.organization_id,
            "status": "pending_eadmin_approval"
        })
        if existing_request:
            flash(f"You have already submitted organization '{org_name_from_form}' for approval. It is currently pending.", "info")
            return redirect(url_for('user.oconvener_dashboard_page'))

        mongo.db.organization_approval_requests.insert_one(org_approval_request_data)
        flash(f"Organization '{org_name_from_form}' has been submitted for E-Admin approval!", 'success')
        session.pop('_oconvener_org_submission_form_data', None)
        ActivityRecord(userAccount=current_oconvener.email, activityName="Organization Submitted for Approval",
                       details=f"Org ID on User: {current_oconvener.organization_id}, Submitted Name: {org_name_from_form}").addRecord()
        return redirect(url_for('user.oconvener_dashboard_page'))
    except Exception as e:
        current_app.logger.error(f"Database error submitting organization for approval: {e}")
        flash(f"Failed to submit organization '{org_name_from_form}' for approval due to a server error.", 'danger')
        return redirect(url_for('user.oconvener_setup_organization_page'))


# ==============================================================================
# --- DASHBOARD AND OTHER USER-SPECIFIC ROUTES (T-Admin, E-Admin, O-Convener, Seek Help) ---
# ==============================================================================

# --- T-Admin Routes ---
@user_bp.route('/tadmin-dashboard')
@login_required
@role_required(ROLE_T_ADMIN)
def tadmin_dashboard_page():
    # (Your existing T-Admin dashboard logic - seems fine)
    # Ensure current_tadmin is instantiated correctly
    current_user_doc = User.find_by_id(session['user_id'])
    if not current_user_doc: flash("User session error.", "danger"); return redirect(url_for('user.logout_page'))
    current_tadmin = TAdmin(**current_user_doc.to_dict())

    request_status_filter = request.args.get('request_status', UserQuestion.STATUS_PENDING)
    help_requests_list, error_help = current_tadmin.viewHelpRequest(status=request_status_filter)
    if error_help: flash(f"Error loading help requests: {error_help}", "danger")

    eadmin_users_list, error_eadmin = current_tadmin.viewEAdmin()
    if error_eadmin: flash(f"Error loading E-Admin list: {error_eadmin}", "danger")

    return render_template('TAdminDashBoard.html', # Ensure this template exists
                           help_requests=help_requests_list or [],
                           eadmin_list=eadmin_users_list or [],
                           current_request_filter=request_status_filter,
                           UserQuestion=UserQuestion) # For accessing status constants in template

@user_bp.route('/tadmin/requests/<string:question_id>/answer', methods=['POST'])
@login_required
@role_required(ROLE_T_ADMIN)
def tadmin_answer_request(question_id):
    # (Your existing logic)
    current_user_doc = User.find_by_id(session['user_id'])
    current_tadmin = TAdmin(**current_user_doc.to_dict())
    answer_content = request.form.get('answer_content')
    if not answer_content or not answer_content.strip():
        flash("Answer content cannot be empty.", "danger")
    else:
        success, message = current_tadmin.answerHelpRequest(question_id_str=question_id, answer_content=answer_content)
        flash(message, "success" if success else "danger")
    return redirect(url_for('user.tadmin_dashboard_page', request_status=request.args.get('request_status', UserQuestion.STATUS_PENDING)))

@user_bp.route('/tadmin/eadmins/add', methods=['POST'])
@login_required
@role_required(ROLE_T_ADMIN)
def tadmin_add_eadmin():
    # (Your existing logic for T-Admin to add E-Admin)
    current_user_doc = User.find_by_id(session['user_id'])
    current_tadmin = TAdmin(**current_user_doc.to_dict())
    email = request.form.get('email')
    username = request.form.get('username')
    new_eadmin, message = current_tadmin.addEAdmin(email=email, username=username if username else None)
    flash(message, "success" if new_eadmin else "danger")
    return redirect(url_for('user.tadmin_dashboard_page'))

@user_bp.route('/tadmin/eadmins/<string:eadmin_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_T_ADMIN)
def tadmin_edit_eadmin_page(eadmin_id):
    # (Your existing logic)
    # Note: Ensure t_admin_edit_eadmin.html template exists and handles form_data for POST errors
    current_user_doc = User.find_by_id(session['user_id'])
    current_tadmin = TAdmin(**current_user_doc.to_dict())
    eadmin_user_to_edit = User.find_by_id(eadmin_id)
    if not eadmin_user_to_edit or eadmin_user_to_edit.user_role != ROLE_E_ADMIN:
        flash("E-Admin not found or specified user is not an E-Admin.", "danger")
        return redirect(url_for('user.tadmin_dashboard_page'))

    if request.method == 'POST':
        updates = {}
        new_username = request.form.get('username','').strip()
        if new_username and new_username != eadmin_user_to_edit.username:
            updates['username'] = new_username
        # Add other updatable fields here, e.g., email, carefully
        if updates:
            success, message = current_tadmin.editEAdmin(eadmin_id_str=eadmin_id, updates=updates)
            flash(message, "success" if success else "danger")
            if success: return redirect(url_for('user.tadmin_dashboard_page'))
        else:
            flash("No changes detected or submitted.", "info")
        return render_template('t_admin_edit_eadmin.html', eadmin=eadmin_user_to_edit, form_data=request.form) # Re-render with form data
    return render_template('t_admin_edit_eadmin.html', eadmin=eadmin_user_to_edit)


@user_bp.route('/tadmin/eadmins/<string:eadmin_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_T_ADMIN)
def tadmin_delete_eadmin(eadmin_id):
    # (Your existing logic)
    current_user_doc = TAdmin.find_by_id(session['user_id'])
    current_tadmin = TAdmin(**current_user_doc.to_dict())
    success, message = current_tadmin.deleteEAdmin(eadmin_id_str=eadmin_id)
    flash(message, "success" if success else "danger")
    return redirect(url_for('user.tadmin_dashboard_page'))

# --- E-Admin Routes ---
@user_bp.route('/eadmin-dashboard')
@login_required
@role_required(ROLE_E_ADMIN)
def eadmin_dashboard_page():
    # (Your existing E-Admin dashboard logic)
    current_user_doc = EAdmin.find_by_id(session['user_id'])
    if not current_user_doc: flash("User session error.", "danger"); return redirect(url_for('user.logout_page'))
    current_eadmin = EAdmin(**current_user_doc.to_dict())

    app_status_filter = request.args.get('app_status', REG_STATUS_PENDING_APPROVAL)
    print(app_status_filter)
    # viewRegistrationApplication should now handle applications from the new admin role application flow
    applications_list = current_eadmin.viewRegistrationApplication(status=app_status_filter)
    print(applications_list)
    current_log_page = request.args.get('log_page', 1, type=int)
    logs_per_page = 15 # Or from config
    logs_list, total_logs = current_eadmin.viewUserLog(limit=logs_per_page, page=current_log_page)
    total_log_pages = (total_logs + logs_per_page - 1) // logs_per_page if total_logs > 0 else 1
    

    current_policy_page = request.args.get('page', 1, type=int) # 'page' for policy pagination
    policies_per_page = 10 # Or from config
    platform_policies_list, total_policies = current_eadmin.viewPolicy(limit=policies_per_page, page=current_policy_page)
    total_policy_pages = (total_policies + policies_per_page - 1) // policies_per_page if total_policies > 0 else 1
    
    return render_template('EAdminDashBoard.html',
                           applications=applications_list or [],
                           current_app_filter=app_status_filter,
                           logs=logs_list or [], # Pass logs_list as logs for the template
                           current_log_page=current_log_page,
                           total_log_pages=total_log_pages,
                           platform_policies=platform_policies_list or [],
                           current_policy_page=current_policy_page,
                           total_policy_pages=total_policy_pages)

@user_bp.route('/eadmin/applications/<string:app_id>/approve', methods=['POST'])
@login_required
@role_required(ROLE_E_ADMIN)
def eadmin_approve_app(app_id):
    current_user_doc = User.find_by_id(session['user_id'])
    current_eadmin = EAdmin(**current_user_doc.to_dict())
    success, message = current_eadmin.approveRegistrationApplication(app_id=app_id) # EAdmin.py needs update
    flash(message, "success" if success else "danger")
    return redirect(url_for('user.eadmin_dashboard_page', app_status=request.args.get('app_status', REG_STATUS_PENDING_APPROVAL)))

@user_bp.route('/eadmin/applications/<string:app_id>/reject-page', methods=['GET']) # Renamed for clarity
@login_required
@role_required(ROLE_E_ADMIN)
def eadmin_reject_app_page(app_id):
    try:
        app_object_id = ObjectId(app_id)
    except InvalidId:
        flash("Invalid application ID.", "danger")
        return redirect(url_for('user.eadmin_dashboard_page'))
    application_doc = mongo.db.organization_approval_requests.find_one({"_id": app_object_id})
    if not application_doc:
        flash("Application not found.", "danger")
        return redirect(url_for('user.eadmin_dashboard_page'))
    return render_template('eadmin_reject_reason.html', app_id=app_id, app=application_doc)


@user_bp.route('/eadmin/applications/<string:app_id>/reject-submit', methods=['POST'])
@login_required
@role_required(ROLE_E_ADMIN)
def eadmin_reject_app_submit(app_id):
    current_user_doc = User.find_by_id(session['user_id'])
    current_eadmin = EAdmin(**current_user_doc.to_dict())
    rejection_reason = request.form.get('rejection_reason', "No specific reason provided.")
    success, message = current_eadmin.rejectRegistrationApplication(app_id=app_id, reason=rejection_reason)
    flash(message, "success" if success else "danger")
    return redirect(url_for('user.eadmin_dashboard_page', app_status=request.args.get('app_status', REG_STATUS_REJECTED)))


@user_bp.route('/uploads/proofs/<path:filename>') 
@login_required 
def serve_proof_document(filename):
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder or not os.path.isdir(upload_folder):
        flash("Upload folder is not configured correctly.", "danger")
        return redirect(request.referrer or url_for('main.index'))
    try:
        return send_from_directory(os.path.abspath(upload_folder), secure_filename(filename), as_attachment=False)
    except FileNotFoundError:
        flash("Requested proof document not found.", "danger")
        return redirect(request.referrer or url_for('main.index'))
    except Exception as e:
        current_app.logger.error(f"Error serving proof document {filename}: {e}")
        flash("Could not serve the requested document.", "danger")
        return redirect(request.referrer or url_for('main.index'))

@user_bp.route('/eadmin/policies/add', methods=['POST'])
@login_required
@role_required(ROLE_E_ADMIN)
def eadmin_add_policy():
    current_user_doc = User.find_by_id(session['user_id'])
    if not current_user_doc: # Should be caught by @login_required, but defensive
        flash("User session error.", "danger")
        return redirect(url_for('user.logout_page'))
    current_eadmin = EAdmin(**current_user_doc.to_dict())

    title = request.form.get('policy_title')
    description = request.form.get('policy_description')
    policy_file = request.files.get('policy_file')

    if not title or not policy_file or not policy_file.filename:
        flash("Policy title and PDF file are required.", "policy_danger")
        return redirect(url_for('user.eadmin_dashboard_page', active_tab='policies'))

    success, message = current_eadmin.addPolicy(title, policy_file, description)
    flash(message, "policy_success" if success else "policy_danger")
    return redirect(url_for('user.eadmin_dashboard_page', active_tab='policies'))

@user_bp.route('/eadmin/policies/<string:policy_id>/update', methods=['POST'])
@login_required
@role_required(ROLE_E_ADMIN)
def eadmin_update_policy(policy_id):
    current_user_doc = User.find_by_id(session['user_id'])
    if not current_user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('user.logout_page'))
    current_eadmin = EAdmin(**current_user_doc.to_dict())

    # Names in the form are like 'update_policy_title_xxxx'
    title = request.form.get(f'update_policy_title_{policy_id}')
    description = request.form.get(f'update_policy_description_{policy_id}')
    new_policy_file = request.files.get(f'update_policy_file_{policy_id}')
    
    success, message = current_eadmin.updatePolicy(policy_id, title, description, new_policy_file)
    flash(message, "policy_success" if success else "policy_danger")
    return redirect(url_for('user.eadmin_dashboard_page', active_tab='policies'))

@user_bp.route('/eadmin/policies/<string:policy_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_E_ADMIN)
def eadmin_delete_policy(policy_id):
    current_user_doc = User.find_by_id(session['user_id'])
    if not current_user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('user.logout_page'))
    current_eadmin = EAdmin(**current_user_doc.to_dict())

    success, message = current_eadmin.deletePolicy(policy_id)
    flash(message, "policy_success" if success else "policy_danger")
    return redirect(url_for('user.eadmin_dashboard_page', active_tab='policies'))

@user_bp.route('/uploads/proofs/<path:filename>') 
@login_required 
def serve_policy_document(filename):
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder or not os.path.isdir(upload_folder):
        flash("Upload folder is not configured correctly.", "danger")
        return redirect(request.referrer or url_for('main.index'))
    try:
        return send_from_directory(os.path.abspath(upload_folder), secure_filename(filename), as_attachment=False)
    except FileNotFoundError:
        flash("Requested proof document not found.", "danger")
        return redirect(request.referrer or url_for('main.index'))
    except Exception as e:
        current_app.logger.error(f"Error serving proof document {filename}: {e}")
        flash("Could not serve the requested document.", "danger")
        return redirect(request.referrer or url_for('main.index'))
    
@user_bp.route('/oconvener-dashboard')
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_dashboard_page():
    current_user_doc = OConvener.find_by_id(session['user_id'])
    if not current_user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('user.logout_page'))
    current_oconvener = OConvener(**current_user_doc.to_dict())

    # Initialize variables for template context
    view_status = "not_submitted"  # Default: O-Convener needs to submit org registration
    organization_display_data = None # Data to display about the organization (name, id, actual status)
    approval_request_details = None # Full document from organization_approval_requests if relevant
    rejection_reason_detail = None
    
    current_log_page = 1
    total_log_pages = 1
    logs_per_page = 15
    # Data for fully approved/active state
    members_list = []
    organization_logs = []
    service_names_map = {
        'thesisAccess': 'Thesis Access Service',
        'courseInfo': 'Course Information Service',
        'identityCheck': 'Student Identity Check Service',
        'gpaRecord': 'Student GPA Record Access Service'
    }
    available_services_data = {}

    if not current_oconvener.organization_id:
        flash("Critical Error: Your account is not configured with an Organization ID. Please contact support.", "danger")
        view_status = "error_config" # Special status for this critical error
        return render_template('OConvenerDashBoard.html',
                               oconvener_user=current_oconvener,
                               view_status=view_status,
                               organization_data=None) # Pass None for organization_data

    # 1. Check 'organizations' table for an ACTIVE organization
    #    current_oconvener.getOrganization() queries the 'organizations' table.
    active_organization_entity = current_oconvener.getOrganization() # This returns doc from 'organizations' or None

    if active_organization_entity and active_organization_entity.get('status') == "active":
        view_status = "approved_active"
        organization_display_data = active_organization_entity

        # Populate data for active state
        members_docs = User._get_collection().find({
            "organization_id": current_oconvener.organization_id,
            "_id": {"$ne": current_oconvener._id}
        })
        members_list = [User.from_document(doc) for doc in members_docs] # Ensure User.from_document handles missing fields gracefully
        organization_logs = current_oconvener.getWorkspaceLog(limit=20)
        available_services_data = active_organization_entity.get('available_services', {})
    else:
        # 2. If not active in 'organizations', check 'organization_approval_requests'
        latest_request = mongo.db.organization_approval_requests.find_one(
            {
                "oconvener_user_id": current_oconvener._id,
                "organization_id_on_user": current_oconvener.organization_id
            },
            sort=[("submitted_at", -1)] # Get the most recent request
        )

        if latest_request:
            approval_request_details = latest_request # Pass the full request document
            request_status_from_db = latest_request.get("status")
            org_name_from_request = latest_request.get("org_name", current_oconvener.organization_name)

            if request_status_from_db == REG_STATUS_PENDING_APPROVAL:
                view_status = "pending_approval"
                organization_display_data = { # Synthesize for display
                    "_id": current_oconvener.organization_id,
                    "name": org_name_from_request,
                    "status_display": "Pending E-Admin Approval"
                }
            elif request_status_from_db == REG_STATUS_REJECTED:
                view_status = "rejected"
                rejection_reason_detail = latest_request.get("rejection_reason")
                organization_display_data = { # Synthesize for display
                    "_id": current_oconvener.organization_id,
                    "name": org_name_from_request,
                    "status_display": "Rejected by E-Admin"
                }
            elif request_status_from_db == REG_STATUS_APPROVED:
                # Request is 'approved' in organization_approval_requests,
                # but org is not 'active' in 'organizations' table.
                view_status = "issue_sync"
                organization_display_data = { # Synthesize for display
                    "_id": current_oconvener.organization_id,
                    "name": org_name_from_request,
                    "status_display": "Approval Processed - Awaiting Activation"
                }
                flash("Your organization's approval has been processed, but final activation is pending. If this persists, please contact support.", "warning")
            # else: if status is something else or not present, it will fall through to 'not_submitted' if no active_org found
        else:
            # No active organization in 'organizations' table AND no relevant approval request found.
            # This means the O-Convener needs to submit their organization.
            view_status = "not_submitted"
            organization_display_data = { # Synthesize for display
                "_id": current_oconvener.organization_id,
                "name": current_oconvener.organization_name, # Proposed name from user record
                "status_display": "Not Submitted for Approval"
            }

    if view_status == "approved_active":
        members_docs = User._get_collection().find({
            "organization_id": current_oconvener.organization_id,
            "_id": {"$ne": current_oconvener._id}
        })
        members_list = [User.from_document(doc) for doc in members_docs]

        if organization_display_data: 
             available_services_data = organization_display_data.get('available_services', {})

        try:
            current_log_page = request.args.get('log_page', 1, type=int)
            if current_log_page < 1:
                current_log_page = 1
        except ValueError:
            current_log_page = 1 

        organization_logs, total_logs_count = current_oconvener.getWorkspaceLog(page=current_log_page, limit=logs_per_page)
        if total_logs_count > 0:
            total_log_pages = math.ceil(total_logs_count / logs_per_page)
        else:
            total_log_pages = 1

        if current_log_page > total_log_pages and total_log_pages > 0:
            current_log_page = total_log_pages
            organization_logs, _ = current_oconvener.getWorkspaceLog(page=current_log_page, limit=logs_per_page)

    return render_template(
        'OConvenerDashBoard.html',
        oconvener_user=current_oconvener,
        organization_data=organization_display_data,
        view_status=view_status,
        approval_request_data=approval_request_details,
        rejection_reason=rejection_reason_detail,
        members_list=members_list,
        available_services=available_services_data,
        service_names=service_names_map,
        organization_logs=organization_logs,          
        current_log_page=current_log_page,            
        total_log_pages=total_log_pages,              
        User=User                                    
    )

@user_bp.route('/oconvener/organization/update-name', methods=['POST'])
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_update_org_name():
    # (Your existing logic - ensure current_oconvener.setOrganization updates 'organizations' collection
    #  and potentially the OConvener user object's organization_name field if it's also stored there)
    current_user_doc = OConvener.find_by_id(session['user_id'])
    current_oconvener = OConvener(**current_user_doc.to_dict())
    new_org_name = request.form.get('organization_name', '').strip()

    if not new_org_name:
        flash("Organization name cannot be empty.", "org_details_danger")
    elif not current_oconvener.organization_id:
        flash("Cannot update name: Your account is not yet fully associated with an organization ID.", "org_details_danger")
    else:
        # OConvener.setOrganization should update the 'name' in the 'organizations' collection
        # and also self.organization_name on the OConvener object, then self.save() the user object.
        success = current_oconvener.setOrganization(organization_name=new_org_name)
        if success:
            flash("Organization name updated successfully.", "org_details_success")
        else:
            flash("Failed to update organization name. Please try again.", "org_details_danger")
    return redirect(url_for('user.oconvener_dashboard_page'))


@user_bp.route('/oconvener/member/add', methods=['POST'])
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_add_member():
    current_user_doc = OConvener.find_by_id(session['user_id'])
    if not current_user_doc:
        flash("User session error.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    current_oconvener = OConvener(**current_user_doc.to_dict())
    active_organization_entity = current_oconvener.getOrganization()
    if not current_oconvener.organization_id or \
       not active_organization_entity or \
       active_organization_entity.get('status') != 'active':
        flash("Your organization is not yet fully set up or approved. Cannot manage members.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    # --- get table ---
    email_to_add = request.form.get('email', '').strip().lower()
    username_to_add = request.form.get('username', '').strip()
    role_to_assign = request.form.get('user_role', User.ROLE_PUBLIC_CONSUMER)
    access_level_str = request.form.get('access_right_level') 

    # --- verification ---
    if not email_to_add:
        flash("Member email is required.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    if not access_level_str:
        flash("Please select an Access Right Level.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    # --- handle access level and money ---
    access_rights_to_assign = []
    membership_fee_to_store = 0 
    selected_access_level = 0

    try:
        selected_access_level = int(access_level_str)
        if selected_access_level == User.ACCESS_PUBLIC: # Level 1 in Label (Value=1)
            access_rights_to_assign = [User.ACCESS_PUBLIC]
            membership_fee_to_store = 1000.0
        elif selected_access_level == User.ACCESS_PRIVATE_CONSUME: # Level 2 in Label (Value=2)
            access_rights_to_assign = [User.ACCESS_PUBLIC, User.ACCESS_PRIVATE_CONSUME]
            membership_fee_to_store = 100.0
        elif selected_access_level == User.ACCESS_PRIVATE_PROVIDE: # Level 3 in Label (Value=3)
            access_rights_to_assign = [User.ACCESS_PUBLIC, User.ACCESS_PRIVATE_CONSUME, User.ACCESS_PRIVATE_PROVIDE]
            membership_fee_to_store = 0.0
        else:
            flash(f"Invalid access right level value received: {access_level_str}", "member_management_danger")
            return redirect(url_for('user.oconvener_dashboard_page'))

        access_rights_to_assign.sort() 

    except ValueError:
        flash(f"Invalid access right level value received: {access_level_str}", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    member_data = {
        'email': email_to_add,
        'user_role': role_to_assign,
        'access_right': access_rights_to_assign, 
        'membership_fee': membership_fee_to_store 
    }
    if username_to_add:
        member_data['username'] = username_to_add

    # --- OConvener method to handle the add member---

    success = current_oconvener.manageMember(action='add', member_data=member_data)

    if success:
        flash(f"Member '{email_to_add}' (Role: {role_to_assign}, Access Level: {selected_access_level}, Fee: {membership_fee_to_store} RMB) processing initiated.", "member_management_success")
    else:
        flash(f"Failed to add member '{email_to_add}'. See console/logs for details.", "member_management_danger")

    return redirect(url_for('user.oconvener_dashboard_page'))

@user_bp.route('/oconvener/member/remove/<string:member_email_to_remove>', methods=['POST'])
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_remove_member(member_email_to_remove):
    current_user_doc = OConvener.find_by_id(session['user_id'])
    if not current_user_doc:
        flash("User session error.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    current_oconvener = OConvener(**current_user_doc.to_dict())

    if not current_oconvener.organization_id:
        flash("Your organization is not yet fully set up or approved. Cannot manage members.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    if not member_email_to_remove: # Should not happen if called from the form correctly
        flash("No member email specified for removal.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    success = current_oconvener.manageMember(action='remove', member_email=member_email_to_remove)

    if success:
        flash(f"Member '{member_email_to_remove}' has been removed from the organization.", "member_management_success")
    else:
        flash(f"Failed to remove member '{member_email_to_remove}'. They might not be in your organization or an error occurred.", "member_management_danger")

    return redirect(url_for('user.oconvener_dashboard_page'))

@user_bp.route('/oconvener/member/edit/<string:member_id>', methods=['GET'])
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_edit_member_page(member_id):
    current_user_doc = OConvener.find_by_id(session['user_id'])
    if not current_user_doc:
        flash("User session error.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    current_oconvener = OConvener(**current_user_doc.to_dict())

    if not current_oconvener.organization_id:
        flash("Your organization is not yet fully set up or approved. Cannot manage members.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    # Fetch the member to edit. User._id are string UUIDs.
    member_to_edit_doc = User._get_collection().find_one({"_id": member_id})
    if not member_to_edit_doc or member_to_edit_doc.get('organization_id') != current_oconvener.organization_id:
        flash("Member not found or does not belong to your organization.", "member_management_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    # Ensure access_right is a list of integers for the template
    if 'access_right' in member_to_edit_doc and not isinstance(member_to_edit_doc['access_right'], list):
        pass 

    member_object = User(**member_to_edit_doc) # Or User.from_document(member_to_edit_doc)

    return render_template('oconvener_edit_member.html',
                           member=member_object,
                           oconvener_user=current_oconvener,
                           User=User) 

@user_bp.route('/oconvener/member/edit/<string:member_id>/submit', methods=['POST'])
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_edit_member_submit(member_id):
    current_user_doc = OConvener.find_by_id(session['user_id'])
    if not current_user_doc: # ... (error handling) ...
        flash("User session error.", "member_management_edit_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    current_oconvener = OConvener(**current_user_doc.to_dict())

    if not current_oconvener.organization_id or \
       (current_oconvener.getOrganization() and current_oconvener.getOrganization().get('status') != 'active'):
        flash("Your organization is not yet fully set up or approved. Cannot manage members.", "member_management_edit_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))

    member_doc_for_email = User._get_collection().find_one({"_id": member_id}, {"email": 1, "organization_id": 1})
    if not member_doc_for_email or member_doc_for_email.get('organization_id') != current_oconvener.organization_id:
        flash("Member to edit not found or does not belong to your organization.", "member_management_edit_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    
    member_email_to_edit = member_doc_for_email.get('email')

    member_data_updates = {}
    if 'username' in request.form:
        member_data_updates['username'] = request.form.get('username', '').strip()
    
    if 'user_role' in request.form:
        member_data_updates['user_role'] = request.form.get('user_role')

    if 'access_rights' in request.form: # access_rights will be a list of strings from checkboxes
        access_rights_str_list = request.form.getlist('access_rights')
        processed_access_rights = []
        for ar_str in access_rights_str_list:
            try:
                processed_access_rights.append(int(ar_str))
            except ValueError:
                flash(f"Invalid access right value submitted for update: {ar_str}", "member_management_edit_danger")
                # You might want to redirect back to the edit page here with an error
                return redirect(url_for('user.oconvener_edit_member_page', member_id=member_id))
        # Ensure Public access is always included if it's a base right or handle as per your logic.
        if not processed_access_rights: # If all unchecked, assign default or error
             processed_access_rights = [User.ACCESS_PUBLIC] # Example: default to public if none selected
        elif User.ACCESS_PUBLIC not in processed_access_rights:
             processed_access_rights.append(User.ACCESS_PUBLIC) # Or based on your rules
             processed_access_rights.sort()
        member_data_updates['access_right'] = processed_access_rights


    if not member_data_updates:
        flash("No changes submitted for the member.", "member_management_edit_info")
        return redirect(url_for('user.oconvener_dashboard_page'))

    success = current_oconvener.manageMember(action='edit', member_email=member_email_to_edit, member_data=member_data_updates)

    if success:
        flash(f"Member '{member_email_to_edit}' updated successfully.", "member_management_edit_success")
    else:
        flash(f"Failed to update member '{member_email_to_edit}'. Check input or logs for details.", "member_management_edit_danger")

    return redirect(url_for('user.oconvener_dashboard_page'))

@user_bp.route('/oconvener/services/set-availability', methods=['POST'])
@login_required
@role_required(ROLE_O_CONVENER)
def oconvener_set_service_availability():
    current_user_doc = OConvener.find_by_id(session['user_id'])
    if not current_user_doc:
        flash("User session error.", "service_availability_danger") # Use specific category
        return redirect(url_for('user.oconvener_dashboard_page'))
    current_oconvener = OConvener(**current_user_doc.to_dict())

    if not current_oconvener.organization_id:
        flash("Your organization is not yet fully set up. Cannot set service availability.", "service_availability_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    
    active_organization_entity = current_oconvener.getOrganization()
    if not active_organization_entity or active_organization_entity.get('status') != 'active':
        flash("Your organization is not yet active. Service availability cannot be changed.", "service_availability_danger")
        return redirect(url_for('user.oconvener_dashboard_page'))
    
    # Example service keys (ensure these match what's in service_names_map in the dashboard route)
    expected_service_keys = ['thesisAccess', 'courseInfo', 'identityCheck', 'gpaRecord']
    
    services_updated_count = 0
    services_failed_count = 0

    for service_key in expected_service_keys:
        form_field_name = f"service_{service_key}"
        # Checkboxes not checked are not present in request.form
        is_available = form_field_name in request.form and request.form[form_field_name] == "true"
        
        # Call the method in OConvener.py to update this specific service
        # The setFunctionAvailability method in OConvener.py already handles DB update and logging
        success = current_oconvener.setFunctionAvailability(service_name=service_key, is_available=is_available)
        if success:
            services_updated_count += 1
        else:
            services_failed_count += 1
            # The OConvener method should log specific errors.
            # We can flash a generic error or a more specific one if the method returns it.
            flash(f"Failed to update availability for service '{service_key}'.", "service_availability_danger")

    if services_failed_count == 0 and services_updated_count > 0:
        flash("Service availability settings saved successfully.", "service_availability_success")
    elif services_updated_count > 0 and services_failed_count > 0:
        flash("Some service availability settings were saved, but others failed. Please check logs.", "service_availability_warning")
    elif services_failed_count > 0 and services_updated_count == 0 :
        flash("Failed to save any service availability settings. Please check logs or try again.", "service_availability_danger")
    else: # No changes submitted or no expected services found in form (should not happen with checkboxes)
        flash("No changes to service availability were detected or applied.", "service_availability_info")

    return redirect(url_for('user.oconvener_dashboard_page'))

# --- GENERAL USER ROUTES ---

@user_bp.route('/seek-help', methods=['GET', 'POST'])
@login_required # Any logged-in user can seek help
def seek_help_page():
    # (Your existing logic seems fine)
    current_user_doc = User.find_by_id(session.get('user_id'))
    if not current_user_doc: flash("User session error.", "warning"); return redirect(url_for('user.login_page'))
    current_user_instance = User(**current_user_doc.to_dict()) # Use base User or specific if needed

    if request.method == 'POST':
        question_content = request.form.get('question_content','').strip()
        if not question_content:
            flash("Question content cannot be empty.", "seek_help_warning")
        else:
            result_status = current_user_instance.seekHelp(question_content)
            if result_status == "HELP_REQUEST_SUBMITTED":
                flash("Your help request has been submitted successfully.", "seek_help_success")
                return redirect(url_for('main.index')) # Or a "request submitted" page
            else:
                flash(f"Failed to submit help request ({result_status}). Please try again.", "seek_help_danger")
        return render_template('seek_help.html', current_content=question_content, user_email=current_user_instance.email)

    return render_template('seek_help.html', user_email=current_user_instance.email) # Ensure seek_help.html exists