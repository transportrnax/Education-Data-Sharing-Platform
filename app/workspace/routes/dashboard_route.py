from flask import render_template, request, flash, current_app
from flask_login import login_required, current_user
from bson import ObjectId
import math
import os
from . import workspace_bp
from app.extensions import mongo 
from app.main.User import User
from ..service.OrganizationService import OrganizationService
from ..service.WorkspaceService import WorkspaceService
from ..service.MemberService import MemberService
from ..models import OConvener
from ..utils import (
    ACTIVE, PENDING_EADMIN_APPROVAL, PENDING_SEADMIN_APPROVAL, REJECTED_BY_EADMIN, REJECTED_BY_SEADMIN, NOT_SUBMITTED
)

@workspace_bp.route('/')
@workspace_bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def oconvener_dashboard_page():
    """
    Displays the O-Convener's dashboard.
    Shows organization status, member list, services, and logs.
    """
    #print(current_user.organization_id)
    if not hasattr(current_user, 'organization_id'): 
        flash("User profile is incomplete or not an O-Convener.", "danger")
        return render_template('home.html') 

    view_status = NOT_SUBMITTED
    organization_display_data = None
    approval_request_details = None
    rejection_reason_detail = None
    members_list_for_template: list[dict] = []
    organization_logs: list[dict] = []
    total_logs_count = 0
    total_log_pages = 1
    current_log_page = request.args.get('log_page', 1, type=int)
    if current_log_page < 1: current_log_page = 1
    logs_per_page = 15

    available_services_data: dict[str, bool] = {}
    service_names_map = {
        'thesisAccess': 'Thesis Access Service',
        'courseInfo': 'Course Information Service',
        'identityCheck': 'Student Identity Check Service',
        'gpaRecord': 'Student GPA Record Access Service'
    }
    workspace_display_data = None

    db = mongo.db
    bank_account_info = None
    bank_error = None
    bank_success = None

    if request.method == 'POST' and 'bind_bank_account' in request.form:
        account = request.form.get('account')
        bank = request.form.get('bank')
        name = request.form.get('name')
        password = request.form.get('password')
        org_id = current_user.organization_id

        if not all([account, bank, name, password, org_id]):
            bank_error = "信息不完整"
        else:
            # 查找是否有匹配的银行账户
            bank_account = db.BANK_ACCOUNT.find_one({'account': account, 'bank': bank, 'name': name, 'password': password})
            if not bank_account:
                bank_error = "未找到该银行账户"
            else:
                db.BANK_ACCOUNT.update_one(
                    {'_id': bank_account['_id']},
                    {'$set': {'organization_id': org_id}}
                )
                bank_success = "银行账户绑定成功！"

    # 查询当前组织的bank account信息
    org_id = current_user.organization_id
    if org_id:
        bank_account_info = db.BANK_ACCOUNT.find_one({'organization_id': org_id})

    if not current_user.organization_id: 
        flash("Critical Error: Your account is not configured with an Organization ID. Please contact support.", "danger")
    else:
        org_service = OrganizationService()
        workspace_service = WorkspaceService()
        member_service = MemberService()

        active_organization_entity = org_service.get_organization_details(current_user.organization_id)
        
        if active_organization_entity and active_organization_entity.get('status') == ACTIVE:
            view_status = ACTIVE
            organization_display_data = active_organization_entity
            
            workspace_entity_obj = workspace_service.get_workspace_org(current_user.organization_id)
            
            if not workspace_entity_obj:
                oconvener_for_service = current_user
                if not isinstance(current_user, OConvener) and hasattr(current_user, '_data'):
                     oconvener_for_service = OConvener(current_user._data) # 假设 User 对象有 _data

                workspace_entity_obj = workspace_service.create_workspace(oconvener_for_service)
                if workspace_entity_obj:
                    flash("Workspace was successfully created.", "info")

            if workspace_entity_obj: 
                workspace_display_data = workspace_entity_obj.to_dict() if hasattr(workspace_entity_obj, 'to_dict') else None
                
                raw_members_list = member_service.get_organization_members(
                    current_user.organization_id,
                    exclude_user_id=current_user.user_id if isinstance(current_user.user_id, str) else current_user.user_id
                )

                for member_user_obj in raw_members_list:
                
                    member_id_for_query = member_user_obj.user_id
                    if isinstance(member_id_for_query, str):
                        member_id_for_query = ObjectId(member_id_for_query)

                    member_full_doc = mongo.db.users.find_one({"_id": member_id_for_query})
                    if member_full_doc:
                        members_list_for_template.append({
                                "user_id": str(member_full_doc["_id"]),
                                "email": member_full_doc.get("email", "N/A"),
                                "username": member_full_doc.get("username", "N/A"),
                                "access_level": member_full_doc.get("access_level", [False, False, False]),
                                "membership_fee": member_full_doc.get("membership_fee", 0.0),
                                "role_name": User.Roles(member_full_doc.get("user_role", User.Roles.NORMAL.value)).name # 显示角色名
                        })
                    else:
                        current_app.logger.warning(f"Could not find full document for member ID: {member_user_obj.user_id}")

                organization_logs, total_logs_count = workspace_service.get_organization_logs(
                    current_user.organization_id,
                    current_user.email,
                    page=current_log_page, 
                    limit=logs_per_page
                )
                if total_logs_count > 0 and logs_per_page > 0:
                    total_log_pages = math.ceil(total_logs_count / logs_per_page)
                else:
                    total_log_pages = 1

                if current_log_page > total_log_pages and total_log_pages > 0: 
                    current_log_page = total_log_pages
                    organization_logs, total_logs_count = workspace_service.get_organization_logs(
                        current_user.organization_id, current_user.email, page=current_log_page, limit=logs_per_page)

                available_services_data = active_organization_entity.get('services', {})
        else:
            if current_user.user_id:
                
                approval_request_details = org_service.get_latest_organization_approval_request(
                    oconvener_user_id = current_user.user_id, 
                    organization_id = current_user.organization_id 
                )

            if approval_request_details:
                status = approval_request_details.get("status")
                org_name_from_request = approval_request_details.get("org_name", current_user.organization_name)
                created_time = approval_request_details.get("created_at")
                if status == PENDING_EADMIN_APPROVAL:
                    view_status = PENDING_EADMIN_APPROVAL
                    organization_display_data = {"_id": current_user.organization_id, "name": org_name_from_request}
                elif status == REJECTED_BY_EADMIN:
                    view_status = REJECTED_BY_EADMIN
                    rejection_reason_detail = approval_request_details.get("rejection_reason")
                    organization_display_data = {"_id": current_user.organization_id, "name": org_name_from_request}
                elif status == PENDING_SEADMIN_APPROVAL:
                    view_status = PENDING_SEADMIN_APPROVAL
                    organization_display_data = {"_id": current_user.organization_id, "name": org_name_from_request}
                elif status == REJECTED_BY_SEADMIN:
                    view_status = REJECTED_BY_SEADMIN
                    organization_display_data = {"_id": current_user.organization_id, "name": org_name_from_request}
                elif status == ACTIVE: 
                    view_status = ACTIVE
                    organization_display_data = {"_id": current_user.organization_id, "name": org_name_from_request, "created_at": created_time}
            else: 
                view_status = NOT_SUBMITTED
                organization_display_data = {"_id": current_user.organization_id, "name": current_user.organization_name}
    
    return render_template(
        'workspace/workspace.html', 
        oconvener_user=current_user,
        organization_data=organization_display_data,
        workspace_data=workspace_display_data, 
        view_status=view_status,
        approval_request_data=approval_request_details,
        rejection_reason=rejection_reason_detail,
        members_list=members_list_for_template,
        available_services=available_services_data,
        service_names=service_names_map,
        organization_logs=organization_logs,          
        current_log_page=current_log_page,            
        total_log_pages=total_log_pages,              
        UserRolesEnum=User.Roles,
        bank_account_info=bank_account_info,
        bank_error=bank_error,
        bank_success=bank_success
    )