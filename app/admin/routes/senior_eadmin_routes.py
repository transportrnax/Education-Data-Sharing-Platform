# app/admin/routes/senior_eadmin_routes.py
from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.admin.models import SeniorEAdmin # 确保导入 SeniorEAdmin
from app.main.User import User as MainUser # 导入 User.Roles
from app.extensions import mongo
from . import admin_bp # 假设你的 admin_bp 在 __init__.py 中定义
from app.admin.service.senior_eadmin_service import SeniorEAdminService
from bson import ObjectId
# 导入状态常量 (如果它们在 utils.py)
from ..service.Eadmin_service import PENDING_SEADMIN_APPROVAL, ACTIVE, REJECTED_BY_SEADMIN

senior_eadmin_service = SeniorEAdminService()

@admin_bp.route('/senior-eadmin/dashboard')
@login_required
def senior_eadmin_dashboard_page():
    if current_user.role != MainUser.Roles.SENIOR_EADMIN:
        flash("Unauthorized access to Senior E-Admin dashboard.", "danger")
        return redirect(url_for('main.index')) # 或者合适的跳转

    # 从数据库获取最新的 SeniorEAdmin 用户信息，以防 session 中的数据过时
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("User session error.", "danger")
        return redirect(url_for('auth.logout')) # 或者 'auth.login'

    current_senior_eadmin = SeniorEAdmin(user_doc)

    # 获取待 Senior EAdmin 审批的组织列表
    pending_orgs, error_msg = senior_eadmin_service.get_pending_organizations_for_senior_approval(current_senior_eadmin)
    if error_msg:
        flash(error_msg, "danger")

    approved_orgs = list(mongo.db.org_register_request.find({"status": ACTIVE, "seadmin_approved_by": current_senior_eadmin.email}))
    rejected_orgs = list(mongo.db.org_register_request.find({"status": REJECTED_BY_SEADMIN, "seadmin_rejected_by": current_senior_eadmin.email}))


    return render_template('admin/senior_eadmin_dashboard.html',
                           pending_organizations=pending_orgs,
                           approved_organizations=approved_orgs,
                           rejected_organizations=rejected_orgs,
                           current_senior_eadmin=current_senior_eadmin)

@admin_bp.route('/senior-eadmin/approve/<string:request_id>', methods=['POST'])
@login_required
def senior_eadmin_approve_organization(request_id):
    if current_user.role != MainUser.Roles.SENIOR_EADMIN:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('admin.senior_eadmin_dashboard_page'))

    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    current_senior_eadmin = SeniorEAdmin(user_doc)

    success, message = senior_eadmin_service.approve_organization_final(current_senior_eadmin, request_id)
    flash(message, "success" if success else "danger")
    return redirect(url_for('admin.senior_eadmin_dashboard_page'))

@admin_bp.route('/senior-eadmin/reject/<string:request_id>', methods=['POST'])
@login_required
def senior_eadmin_reject_organization(request_id):
    if current_user.role != MainUser.Roles.SENIOR_EADMIN:
        flash("Unauthorized action.", "danger")
        # return redirect(url_for('admin.senior_eadmin_dashboard_page'))
        return redirect(url_for('main.index'))


    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    current_senior_eadmin = SeniorEAdmin(user_doc)

    rejection_reason = request.form.get('rejection_reason')
    if not rejection_reason or not rejection_reason.strip():
        flash("Rejection reason is required.", "warning")
        # 可以重定向回一个带有拒绝原因输入框的页面，或者直接显示在仪表盘上
        return redirect(url_for('admin.senior_eadmin_reject_organization_page', request_id=request_id)) # 跳转到拒绝页面

    success, message = senior_eadmin_service.reject_organization_final(current_senior_eadmin, request_id, rejection_reason)
    flash(message, "success" if success else "danger")
    return redirect(url_for('admin.senior_eadmin_dashboard_page'))

@admin_bp.route('/senior-eadmin/reject-page/<string:request_id>', methods=['GET'])
@login_required
def senior_eadmin_reject_organization_page(request_id):
    if current_user.role != MainUser.Roles.SENIOR_EADMIN:
        flash("Unauthorized.", "danger")
        return redirect(url_for('main.index'))

    try:
        org_request = mongo.db.org_register_request.find_one({"_id": ObjectId(request_id), "status": PENDING_SEADMIN_APPROVAL})
        if not org_request:
            flash("Organization request not found or not in correct state for rejection.", "warning")
            return redirect(url_for('admin.senior_eadmin_dashboard_page'))
    except Exception as e:
        flash("Invalid request ID.", "danger")
        current_app.logger.error(f"Invalid ObjectId for rejection page: {request_id} - {e}")
        return redirect(url_for('admin.senior_eadmin_dashboard_page'))

    return render_template('admin/senior_eadmin_reject_reason.html', org_request=org_request)