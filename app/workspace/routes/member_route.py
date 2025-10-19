from flask import request, flash, redirect, url_for, session, current_app, send_file # 新增 send_file
from flask_login import login_required, current_user
from bson import ObjectId
from io import BytesIO
from . import workspace_bp
from ..service.MemberService import MemberService
from ..service.OrganizationService import OrganizationService 
from ..models import OConvener 
from app.main.User import User 
from app.extensions import mongo 
from app.auth.utils import is_valid_email
from ..utils import ACTIVE, PENDING_EADMIN_APPROVAL, PENDING_SEADMIN_APPROVAL, REJECTED_BY_EADMIN, REJECTED_BY_SEADMIN, NOT_SUBMITTED

@workspace_bp.route('/member/add', methods=['POST'])
@login_required
def oconvener_add_member_route():
    if not current_user.is_authenticated or current_user.role != User.Roles.O_CONVENER:
        flash("You are not OConvener", "danger")
        session['_add_member_form_data'] = request.form.to_dict()
        session['_show_add_member_modal'] = True
        return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))

    active_organization_entity = OrganizationService.get_organization_details(current_user.organization_id)

    if not active_organization_entity or active_organization_entity.get('status') != ACTIVE:
        flash("Organization has not been activated or the Settings have not been completed! ", "warning")
        session['_add_member_form_data'] = request.form.to_dict()
        session['_show_add_member_modal'] = True
        return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))

    email_to_add = request.form.get('email', '').strip()
    username_to_add = request.form.get('username', '').strip()
    membership_fee_str = request.form.get('membership_fee', '0.0').strip()

    if not email_to_add:
        flash("Member is needed", "danger")
        session['_add_member_form_data'] = request.form.to_dict()
        session['_show_add_member_modal'] = True
        return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))

    membership_fee_to_store = float(membership_fee_str)
    if membership_fee_to_store < 0:
        raise ValueError("Fee cannot less than 0")

    access_level_list = [
        request.form.get('access_level_public') == 'on', 
        request.form.get('access_level_private_consume') == 'on',
        request.form.get('access_level_private_provide') == 'on'
    ]

    if not any(access_level_list):
        flash("Please select at least one access level", "danger")
        session['_add_member_form_data'] = request.form.to_dict()
        session['_show_add_member_modal'] = True
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    assigned_role = User.Roles.NORMAL 
    member_data_for_service = {
        'username': username_to_add if username_to_add else None,
        'role': assigned_role.value,  
        'access_level': access_level_list, 
        'membership_fee': membership_fee_to_store,
        'organization_id': current_user.organization_id,
    }

    member_service = MemberService() 
    try:
        success, message = member_service.add_member(
            oconvener=current_user, 
            member_email=email_to_add, 
            member_data=member_data_for_service
        )
        flash(message, "success" if success else "danger")
        if not success: 
            session['_add_member_form_data'] = request.form.to_dict()
            session['_show_add_member_modal'] = True
    except Exception as e:
        current_app.logger.error(f"Error in oconvener_add_member_route for {email_to_add}: {e}", exc_info=True)
        flash("An internal error occurred when adding members. Please try again later.", "danger")
        session['_add_member_form_data'] = request.form.to_dict() 
        session['_show_add_member_modal'] = True
        
    return redirect(url_for('workspace.oconvener_dashboard_page'))


@workspace_bp.route('/oconvener/members/upload_excel', methods=['POST'])
@login_required 
def oconvener_upload_members_excel_route():
    if 'user_id' not in session and '_user_id' not in session : 
        flash("Please log in to access this page.", "warning")
        return redirect(url_for('auth.login'))

    user_session_key = session.get('user_id') or session.get('_user_id') 
    user_id_obj = ObjectId(user_session_key)

    user_doc = mongo.db.users.find_one({"_id": user_id_obj})
    if not user_doc:
        flash("User not found. Please log in again.", "danger")
        session.clear()
        return redirect(url_for('auth.login'))

    if user_doc.get('role') != User.Roles.O_CONVENER.value: 
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('workspace.oconvener_dashboard_page')) 
    
    current_oconvener_obj = OConvener(user_doc)
    if 'excel_file' not in request.files:
        flash('No Excel file part in the request.', 'danger')
        return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))

    file = request.files['excel_file']
    if file.filename == '':
        flash('No Excel file selected for upload.', 'danger')
        return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))

    if file and (file.filename.lower().endswith('.xlsx') or file.filename.lower().endswith('.xls')):
        try:
            file_stream = BytesIO(file.read())
            file_level_success, summary_msg, successful_emails, failed_details = MemberService.add_members_from_excel(
                current_oconvener_obj, 
                file_stream
            )
            if not file_level_success:
                flash(summary_msg, "danger")
            else:
                msg_type = "info"
                if len(failed_details) > 0 and len(successful_emails) == 0 : msg_type = "warning"
                elif len(failed_details) > 0 and len(successful_emails) > 0: msg_type = "warning"
                elif len(successful_emails) > 0: msg_type = "success"
                flash(summary_msg, msg_type)

                if successful_emails:
                    display_limit = 5
                    success_msg = f"Successfully added/associated ({len(successful_emails)}): {', '.join(successful_emails[:display_limit])}"
                    if len(successful_emails) > display_limit:
                        success_msg += f"... and {len(successful_emails) - display_limit} more."
                    flash(success_msg, "success")
                
                if failed_details:
                    flash(f"Found {len(failed_details)} entries that could not be processed (details below):", "warning")
                    display_failure_limit = 10 
                    for i, failure in enumerate(failed_details):
                        if i < display_failure_limit:
                            flash(f"Failed - Identifier: {failure.get('email', 'N/A')}, Reason: {failure.get('reason', 'Unknown')}", "danger")
                        else:
                            flash(f"... and {len(failed_details) - display_failure_limit} more failures.", "danger")
                            break
        except Exception as e:
            current_app.logger.error(f"Excel upload route critical error: {e}", exc_info=True)
            flash(f"An unexpected critical error occurred: {str(e)}", 'danger')
        return redirect(url_for('workspace.oconvener_dashboard_page'))
    else:
        flash('Invalid file type. Please upload an Excel file (.xlsx or .xls).', 'danger')
        return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))


@workspace_bp.route('/member/edit/<string:member_id_str>', methods=['POST']) 
@login_required
def oconvener_edit_member_route(member_id_str: str):
    """
    Handles member editing form submission from a modal (non-AJAX).
    Redirects back to the dashboard, possibly with session data to re-open modal on error.
    """
    # Permission & Setup Checks
    member_obj_id = ObjectId(member_id_str)
    member_doc_to_verify = mongo.db.users.find_one(
        {"_id": member_obj_id, "organization_id": current_user.organization_id}
    )
    if not member_doc_to_verify:
        flash("This member not in your organization", "member_management_edit_danger")
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    updates = {}
    form_has_errors = False

    # --- Field Validations (from request.form) ---
    email_str = request.form.get('email', '').strip()
    if not email_str:
        flash('Email Address is must', 'member_management_edit_danger')
        form_has_errors = True
    elif not is_valid_email(email_str):
        flash('Please input valid email address', 'member_management_edit_danger')
        form_has_errors = True
    # Only add to updates if changed from original, MemberService can also do this check
    elif email_str != member_doc_to_verify.get('email'):
        updates['email'] = email_str

    username_str = request.form.get('username', '').strip()
    if username_str != member_doc_to_verify.get('username'):
        updates['username'] = username_str
    
    submitted_access_levels = [
        request.form.get('access_level_public') == 'on',
        request.form.get('access_level_private_consume') == 'on',
        request.form.get('access_level_private_provide') == 'on'
    ]
    if submitted_access_levels != member_doc_to_verify.get('access_level', [False,False,False]):
        updates['access_level'] = submitted_access_levels

    fee_str = request.form.get('membership_fee', '').strip()
    current_app.logger.debug(f"POST /member/edit/{member_id_str} (Non-AJAX): fee_str='{fee_str}'")
    if not fee_str:
        flash("Fee is null", "member_management_edit_danger")
        form_has_errors = True
    else:
        try:
            submitted_fee = float(fee_str)
            if submitted_fee < 0:
                flash("Fee cannot less than 0", "member_management_edit_danger")
                form_has_errors = True
            else:
                updates['membership_fee'] = submitted_fee
        except ValueError:
            current_app.logger.error(f"POST /member/edit/{member_id_str} (Non-AJAX): ValueError for fee_str='{fee_str}'")
            form_has_errors = True
    
    if form_has_errors:
        session['_show_edit_member_modal_on_error'] = member_id_str # Signal to JS to open this member's edit modal
        session['_edit_member_form_data'] = request.form.to_dict() # Store submitted data for repopulation
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    if not updates:
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    success, message_from_service = MemberService.edit_member(
        oconvener=current_user,
        member_id_to_edit=member_id_str,
        updates=updates
    )

    if success:
        flash(message_from_service, "member_management_edit_success")
    else:
        flash(message_from_service, "member_management_edit_danger")
        # If service fails, also store data and signal to reopen modal
        session['_show_edit_member_modal_on_error'] = member_id_str
        session['_edit_member_form_data'] = request.form.to_dict()
        
    return redirect(url_for('workspace.oconvener_dashboard_page'))

@workspace_bp.route('/member/remove/<string:member_email>', methods=['POST'])
@login_required
def oconvener_remove_member_route(member_email: str):
    # check organization status
    org_service = OrganizationService()
    active_organization_entity = org_service.get_organization_details(current_user.organization_id)
    if not active_organization_entity or active_organization_entity.get('status') != ACTIVE:
        flash("No active organization", "warning")
        return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))
    
    oconvener_object = current_user 
    if not isinstance(oconvener_object, OConvener):
        user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.get_id())}) # 假设ID是ObjectId
        if user_doc and user_doc.get('role') == User.Roles.O_CONVENER.value:
            oconvener_object = OConvener(user_doc)
        else:
            return redirect(request.referrer or url_for('workspace.oconvener_dashboard_page'))

    success, message = MemberService.remove_member(
        oconvener=oconvener_object, 
        member_email_to_remove=member_email
    )
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('workspace.oconvener_dashboard_page'))