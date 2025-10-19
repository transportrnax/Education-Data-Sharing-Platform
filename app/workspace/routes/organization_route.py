import os
import uuid
from flask import render_template, request, flash, redirect, url_for, session, current_app, send_from_directory
from flask_mail import Message
from flask_login import login_required, current_user
from app.extensions import mail
from werkzeug.utils import secure_filename
from . import workspace_bp
from ..service.OrganizationService import OrganizationService
from app.auth.utils import is_valid_email, generate_otp, send_otp_email, store_otp, verify_otp, clear_otp
from ..utils import (
    ACTIVE, PENDING_EADMIN_APPROVAL, PENDING_SEADMIN_APPROVAL, REJECTED_BY_EADMIN, REJECTED_BY_SEADMIN, NOT_SUBMITTED, allowed_file_for_proof
)

@workspace_bp.route('/organization/setup', methods=['GET'])
@login_required
def oconvener_setup_organization_page():
    """
    Displays the form for an O-Convener to submit their organization for approval.
    """
    # Check if organization is already active
    active_org = OrganizationService.get_organization_details(current_user.organization_id)
    if active_org and active_org.get('status') == ACTIVE:
        flash(f"Organization '{active_org.get('name')}' is already set up and active.", "info")
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    pending_request = None
    if current_user.user_id and hasattr(current_user, 'organization_id') and current_user.organization_id:
        pending_request = OrganizationService.get_latest_organization_approval_request(
            current_user.user_id, current_user.organization_id
        )

    if pending_request and pending_request.get('status') == PENDING_EADMIN_APPROVAL:
        flash(f"Your application for organization '{pending_request.get('org_name')}' is currently awaiting E-Admin approval.", "info")
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    form_data = session.pop('_org_setup_form_data', {})
    form_data.setdefault('organization_id', getattr(current_user, 'organization_id', None))
    form_data.setdefault('org_name', getattr(current_user, 'organization_name', ''))
    form_data.setdefault('email_for_code', getattr(current_user, 'email', ''))
    form_data.setdefault('code', '')

    return render_template('workspace/register_Organization.html', form_data=form_data)


@workspace_bp.route('/organization/send-verification-code', methods=['POST'])
@login_required
def oconvener_org_setup_send_code():
    email_for_code = request.form.get('email_for_code', '').strip()
    org_name = request.form.get('org_name', '').strip()
    session['_org_setup_form_data'] = {
        'org_name': org_name,
        'email_for_code': email_for_code,
        'code': request.form.get('code', '')
    }

    if not org_name:
        flash('Organization Name is required.', 'danger')
        return redirect(url_for('workspace.oconvener_setup_organization_page'))
    if not email_for_code or not is_valid_email(email_for_code):
        flash('A valid email address is required to send the verification code.', 'danger')
        return redirect(url_for('workspace.oconvener_setup_organization_page'))

    try:
        otp = generate_otp()
        send_otp_email(email_for_code, otp)  # 使用auth.utils的封装
        store_otp(email_for_code, otp)
        flash('A verification code has been sent to your email address. Please check your inbox.', 'success')
    except Exception as e:
        current_app.logger.error(f"Error sending OTP for organization setup to {email_for_code}: {e}")
        flash('An error occurred while sending the verification code. Please try again later.', 'danger')

    return redirect(url_for('workspace.oconvener_setup_organization_page'))


@workspace_bp.route('/organization/submit-setup', methods=['POST'])
@login_required
def oconvener_submit_organization_setup():
    """
    Handles the submission of the organization setup form by the O-Convener.
    """
    org_name_from_form = request.form.get('org_name', '').strip()
    code_from_form = request.form.get('code', '').strip()
    proof_document_file = request.files.get('proof_document')
    # Use the email that was used for sending the code.
    email_for_verification = request.form.get('email_for_code', '').strip()
    if not email_for_verification: # Fallback if not in form (e.g. if form was modified)
        email_for_verification = session.get('_org_setup_form_data', {}).get('email_for_code', getattr(current_user, 'email', ''))

    # Store/update form data in session for repopulation in case of errors
    session['_org_setup_form_data'] = {
        'org_name': org_name_from_form,
        'email_for_code': email_for_verification,
        'code': code_from_form # Keep submitted code for repopulation
    }

    if not org_name_from_form or not code_from_form or not proof_document_file or not proof_document_file.filename:
        flash('All fields are required: Organization Name, Verification Code, and Proof Document.', 'danger')
        return redirect(url_for('workspace.oconvener_setup_organization_page'))
    
    if not email_for_verification or not is_valid_email(email_for_verification):
        flash('A valid email (used for code verification) is required.', 'danger')
        return redirect(url_for('workspace.oconvener_setup_organization_page'))

    # Verify OTP using app.auth.utils
    if not verify_otp(email_for_verification, code_from_form):
        flash('Invalid or expired verification code. Please request a new one if needed.', 'danger')
        return redirect(url_for('workspace.oconvener_setup_organization_page'))

    stored_proof_filename = None
    if allowed_file_for_proof(proof_document_file.filename):
        filename = secure_filename(proof_document_file.filename)
        proof_dir = os.path.join(current_app.root_path, '..', 'uploads', 'proof')
        if not os.path.exists(proof_dir):
            try:
                os.makedirs(proof_dir, exist_ok=True)
            except OSError as e:
                current_app.logger.error(f"Could not create upload folder '{proof_dir}': {e}")
                flash("File upload system error. Please contact support.", "danger")
                return redirect(url_for('workspace.oconvener_setup_organization_page'))
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        try:
            proof_document_file.save(os.path.join(proof_dir, unique_filename))
            stored_proof_filename = unique_filename
        except Exception as e:
            flash("Could not save the proof document. Please try again.", "danger")
            return redirect(url_for('workspace.oconvener_setup_organization_page'))
    else:
        flash('Invalid file type for proof document. Only PDF files are allowed.', 'danger')
        return redirect(url_for('workspace.oconvener_setup_organization_page'))

    # Proceed with organization submission
    # current_user is assumed to be an OConvener instance by Flask-Login's load_user
    success, message = OrganizationService.submit_org_for_approval(
        current_user, org_name_from_form, stored_proof_filename, email_for_verification
    )

    flash(message, "success" if success else "danger")
    if success:
        session.pop('_org_setup_form_data', None) # Clear form data from session on success
        clear_otp(email_for_verification) # Clear the used OTP
        return redirect(url_for('workspace.oconvener_dashboard_page'))
    else:
        # If submission fails, keep the session data so form can be repopulated
        return redirect(url_for('workspace.oconvener_setup_organization_page'))


@workspace_bp.route('/organization/update-name', methods=['POST'])
@login_required
def oconvener_update_org_name_route():
    """Handles updating the organization's name by the O-Convener."""
    new_org_name = request.form.get('organization_name', '').strip()
    if not new_org_name:
        flash("Organization name cannot be empty.", "org_details_danger")
    else:
        success, message = OrganizationService.update_org_name(current_user, new_org_name)
        flash(message, "org_details_success" if success else "org_details_danger")
    return redirect(url_for('workspace.oconvener_dashboard_page'))


@workspace_bp.route('/organization/proof/<path:filename>')
@login_required
def serve_organization_proof_document(filename):
    proof_directory = os.path.join(current_app.root_path, '..', 'uploads', 'proof')
    if not os.path.isdir(proof_directory):
        flash("Proof directory does not exist.", "danger")
        return redirect(url_for('workspace.oconvener_dashboard_page'))
    return send_from_directory(proof_directory, filename, as_attachment=False)