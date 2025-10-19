# src/app/USER/application_service.py

import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app, session # session is used here to manage application data persistence across steps
from datetime import datetime, timezone

from ...extensions import mongo
from ..user import User # For User.ROLE_O_CONVENER, User.valid_email, User.find_by_email
from .verification_service import VerificationService, CODE_SENT_SUCCESS, VERIFICATION_SUCCESS
from ...models.ActivityRecord import ActivityRecord
from ..handle_utils import valid_email
# Constants for application status (can be imported from a central place if they exist elsewhere)
REG_STATUS_REJECTED = "rejected"
REG_STATUS_PENDING_APPROVAL = "pending_admin_approval"

def allowed_file(filename):
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'pdf'})
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def handle_admin_application_send_code(form_data):
    """
    Processes the first step of an admin role application: data collection and code sending.
    Args:
        form_data (dict): Data from the application form (username, email, requested_role, org_name).
    Returns:
        dict: A result dictionary containing status, message, flash_category, and action hint.
    """
    username = form_data.get('username', '').strip()
    email = form_data.get('email', '').strip()
    requested_role = form_data.get('requested_role', '').strip()
    org_name = form_data.get('org_name', '').strip() if requested_role == User.ROLE_O_CONVENER else None

    application_data_for_session = {
        'username': username,
        'email': email,
        'requested_role': requested_role,
        'org_name': org_name
    }
    # Store data in session for re-rendering current form on error, and for the next step
    session['_admin_application_step1_form_data'] = application_data_for_session
    session['_admin_application_pending_verification'] = application_data_for_session


    if not username or not email or not requested_role:
        return {
            'success': False, 'message': 'Name (Username), Email, and Desired Role are required.',
            'flash_category': 'application_danger', 'action': 'redirect_to_apply_page'
        }
    if requested_role == User.ROLE_O_CONVENER and not org_name:
        return {
            'success': False, 'message': 'Proposed Organization Name is required when applying for O-Convener.',
            'flash_category': 'application_danger', 'action': 'redirect_to_apply_page'
        }
    if not valid_email(email): # Assuming User class has a static method `valid_email`
        return {
            'success': False, 'message': 'Invalid email format.',
            'flash_category': 'application_danger', 'action': 'redirect_to_apply_page'
        }

    if User.find_by_email(email):
        return {
            'success': False, 'message': 'This email address is already associated with an existing account. Please login or use a different email.',
            'flash_category': 'application_warning', 'action': 'redirect_to_apply_page'
        }

    reg_apps_collection = mongo.db.registration_applications
    if reg_apps_collection.find_one({"email": email.lower(), "status": {"$ne": REG_STATUS_REJECTED}}):
        return {
            'success': False, 'message': 'An application with this email is already pending or has been approved. Please check your email or contact support.',
            'flash_category': 'application_warning', 'action': 'redirect_to_apply_page'
        }

    purpose = f"admin_application_{requested_role.lower().replace('-', '_')}"
    status_code_str, message, _ = VerificationService.create_and_send_code(email, purpose=purpose)

    if status_code_str == CODE_SENT_SUCCESS:
        return {
            'success': True, 'message': 'A verification code has been sent to your email. Please enter it on the next page to complete your application.',
            'flash_category': 'application_success', 'action': 'redirect_to_submit_details_page'
        }
    else:
        return {
            'success': False, 'message': message or "Failed to send verification code. Please ensure your email is correct and try again.",
            'flash_category': 'application_danger', 'action': 'redirect_to_apply_page'
        }


def handle_admin_application_submit_details(application_details_from_session, form_data, files_data):
    """
    Processes the final submission of an admin role application: code verification, file upload, and saving.
    Args:
        application_details_from_session (dict): Data stored in session from the first step.
        form_data (dict): Data from the current form (verification code).
        files_data (werkzeug.datastructures.FileStorage): Uploaded files (proof document).
    Returns:
        dict: A result dictionary containing status, message, flash_category, and action hint.
    """
    code = form_data.get('code', '').strip()
    proof_document_file = files_data.get('proof_document') if files_data else None

    email_to_verify = application_details_from_session.get('email')
    requested_role = application_details_from_session.get('requested_role')
    applicant_username = application_details_from_session.get('username')
    org_name_for_oconvener = application_details_from_session.get('org_name')

    if not code:
        return {
            'success': False, 'message': 'Verification code is required.',
            'flash_category': 'application_danger', 'action': 'render_submit_details_page',
            'form_data_for_template': application_details_from_session # Pass back session data for re-rendering
        }

    verification_purpose = f"admin_application_{requested_role.lower().replace('-', '_')}"
    verification_status = VerificationService.verify_code(email_to_verify, code, purpose=verification_purpose)

    if verification_status != VERIFICATION_SUCCESS:
        return {
            'success': False, 'message': 'Invalid or expired verification code. Please try again or request a new one.',
            'flash_category': 'application_danger', 'action': 'render_submit_details_page',
            'form_data_for_template': application_details_from_session
        }

    stored_proof_filename = None
    if requested_role == User.ROLE_O_CONVENER:
        if not proof_document_file or proof_document_file.filename == '':
            return {
                'success': False, 'message': 'A proof document (PDF) is required for O-Convener applications.',
                'flash_category': 'application_danger', 'action': 'render_submit_details_page',
                'form_data_for_template': application_details_from_session
            }
        if proof_document_file and allowed_file(proof_document_file.filename):
            try:
                filename = secure_filename(proof_document_file.filename)
                upload_folder = current_app.config.get('UPLOAD_FOLDER')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                proof_document_file.save(os.path.join(upload_folder, unique_filename))
                stored_proof_filename = unique_filename
            except Exception as e:
                current_app.logger.error(f"Error uploading proof file for O-Convener application: {e}")
                return {
                    'success': False, 'message': 'An error occurred while uploading the proof document. Please try again.',
                    'flash_category': 'application_danger', 'action': 'render_submit_details_page',
                    'form_data_for_template': application_details_from_session
                }
        else:
            return {
                'success': False, 'message': 'Invalid proof document file type. Only PDF files are allowed.',
                'flash_category': 'application_danger', 'action': 'render_submit_details_page',
                'form_data_for_template': application_details_from_session
            }

    application_to_save = {
        "applicant_username": applicant_username,
        "email": email_to_verify.lower(),
        "requested_role": requested_role,
        "org_name": org_name_for_oconvener,
        "proof_document": stored_proof_filename,
        "status": REG_STATUS_PENDING_APPROVAL,
        "submitted_at": datetime.now(timezone.utc),
        "email_verified_at": datetime.now(timezone.utc)
    }

    try:
        mongo.db.registration_applications.insert_one(application_to_save)
        ActivityRecord(userAccount=email_to_verify, activityName=f"{requested_role} Application Submitted").addRecord()
        return {
            'success': True, 'message': 'Your application has been submitted successfully and is pending administrator approval!',
            'flash_category': 'application_success', 'action': 'redirect_to_main_index',
            'clear_session_keys': ['_admin_application_pending_verification', '_admin_application_step1_form_data']
        }
    except Exception as e:
        current_app.logger.error(f"Error saving admin application to DB: {e}")
        return {
            'success': False, 'message': 'An error occurred while submitting your application. Please try again later or contact support.',
            'flash_category': 'application_danger', 'action': 'render_submit_details_page',
            'form_data_for_template': application_details_from_session
        }