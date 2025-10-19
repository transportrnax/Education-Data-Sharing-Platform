from flask import render_template, request, flash, redirect, url_for, jsonify, Blueprint
from flask_login import login_required, current_user 
from app.main.User import User 
from ..models import TAdmin, UserQuestion
from app.extensions import mongo 
from . import admin_bp 
from ..service.Tadmin_service import TAdminService 
from bson import ObjectId 
tadmin_service_instance = TAdminService() 

@admin_bp.route('/tadmin-dashboard')
@login_required
def tadmin_dashboard_page():
    if not current_user.is_authenticated or current_user.role != User.Roles.T_ADMIN:
        flash("Access Denied: Not a logged-in T-Admin.", "danger")
        return redirect(url_for('main.index'))

    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("Critical Error: T-Admin user document not found.", "danger")
        return redirect(url_for('auth.logout'))

    tadmin_model_instance = TAdmin(user_doc)
    request_status_filter = request.args.get('request_status', UserQuestion.PENDING)

    help_requests_list, error_help = tadmin_service_instance.view_help_requests(
        admin=tadmin_model_instance, status=request_status_filter
    )
    if error_help:
        flash(f"Error loading help requests: {error_help}", "danger")

    # view_e_admins 应该调整为 view_managed_admins 或类似，并获取 EAdmin 和 SeniorEAdmin
    # 或者，为了简单起见，我们分别获取它们
    eadmin_users_docs = mongo.db.users.find({"role": User.Roles.E_ADMIN.value})
    senior_eadmin_users_docs = mongo.db.users.find({"role": User.Roles.SENIOR_EADMIN.value})
    
    all_managed_admins = [User(doc) for doc in eadmin_users_docs] + [User(doc) for doc in senior_eadmin_users_docs]


    return render_template('admin/TAdminDashBoard.html',
                           help_requests=help_requests_list or [],
                           eadmin_list=all_managed_admins or [], # 重命名为 all_managed_admins
                           current_request_filter=request_status_filter,
                           UserQuestion=UserQuestion,
                           User=User) # 传递 User 类到模板

@admin_bp.route('/tadmin/requests/<string:question_id>/answer', methods=['POST'])
@login_required
def tadmin_answer_request(question_id):
    if not current_user.is_authenticated or current_user.role != User.Roles.T_ADMIN:
        flash("Access Denied.", "danger")
        return redirect(url_for('auth.login')) 

    user_doc = mongo.db.users.find_one({"_id": current_user.user_id}) 
    if not user_doc:
        flash("Critical Error: T-Admin user document not found.", "danger")
        return redirect(url_for('auth.logout'))

    tadmin_model_instance = TAdmin(user_doc)
    tadmin_service_instance = TAdminService()
    
    answer_content = request.form.get('answer_content')
    if not answer_content or not answer_content.strip():
        flash("Answer content cannot be empty.", "danger")
    else:
        success, message = tadmin_service_instance.answer_help_request(
            admin=tadmin_model_instance,
            question_id_str=question_id,
            answer_content=answer_content
        )
        flash(message, "success" if success else "danger")
        
    return redirect(url_for('admin.tadmin_dashboard_page',
                            request_status=request.args.get('request_status', UserQuestion.PENDING)))

@admin_bp.route('/tadmin/admins/add', methods=['POST']) # 路由可以更通用
@login_required
def tadmin_add_admin_user_route(): # 重命名路由函数
    if not current_user.is_authenticated or current_user.role != User.Roles.T_ADMIN:
        flash("Access Denied.", "danger")
        return redirect(url_for('auth.login'))

    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("Critical Error: T-Admin user document not found.", "danger")
        return redirect(url_for('auth.logout'))

    tadmin_model_instance = TAdmin(user_doc)

    email = request.form.get('email')
    username = request.form.get('username')
    admin_type_str = request.form.get('admin_type') # 新的表单字段

    if not admin_type_str:
        flash("Admin type selection is required.", "danger")
        return redirect(url_for('admin.tadmin_dashboard_page'))
    
    try:
        admin_role_value = int(admin_type_str)
        if admin_role_value not in [User.Roles.E_ADMIN.value, User.Roles.SENIOR_EADMIN.value]:
            raise ValueError("Invalid role value")
    except ValueError:
        flash("Invalid admin type submitted.", "danger")
        return redirect(url_for('admin.tadmin_dashboard_page'))

    new_admin_user_model, message = tadmin_service_instance.add_admin_user(
        admin=tadmin_model_instance,
        email=email,
        username=username,
        admin_role_value=admin_role_value # 传递角色值
    )
    flash(message, "success" if new_admin_user_model else "danger")
    return redirect(url_for('admin.tadmin_dashboard_page'))

@admin_bp.route('/tadmin/eadmins/<string:eadmin_id>/edit', methods=['GET', 'POST'])
@login_required
def tadmin_edit_admin_user_page(eadmin_id):
    if not current_user.is_authenticated or current_user.role != User.Roles.T_ADMIN:
        if request.method == 'POST':
            return jsonify({'success': False, 'message': 'Access Denied. Not a logged-in T-Admin.'}), 403
        flash("Access Denied. Not a logged-in T-Admin.", "danger")
        return redirect(url_for('auth.login'))

    tadmin_user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)}) # Use current_user.user_id
    if not tadmin_user_doc:
        if request.method == 'POST':
            return jsonify({'success': False, 'message': 'Critical Error: T-Admin user document not found.'}), 500
        flash("Critical Error: T-Admin user document not found.", "danger")
        return redirect(url_for('auth.logout'))

    tadmin_model_instance = TAdmin(tadmin_user_doc) # 当前TAdmin实例

    # 获取要编辑的用户
    user_to_edit = User.get_by_id(eadmin_id) # User.get_by_id 返回 User 对象
    if not user_to_edit or user_to_edit.role not in [User.Roles.E_ADMIN, User.Roles.SENIOR_EADMIN]:
        flash('Admin user not found or specified user is not an E-Admin or Senior E-Admin.', "danger")
        return redirect(url_for('admin.tadmin_dashboard_page'))

    if request.method == 'POST':
        updates = {}
        form_username = request.form.get('username','').strip()
        if form_username and form_username != user_to_edit.username:
            updates['username'] = form_username
        
        form_email = request.form.get('email','').strip()
        if form_email and form_email.lower() != user_to_edit.email.lower():
            updates['email'] = form_email
            
        # 新增：处理角色变更
        form_admin_type_str = request.form.get('admin_type_edit')
        if form_admin_type_str:
            try:
                form_admin_role_value = int(form_admin_type_str)
                if form_admin_role_value in [User.Roles.E_ADMIN.value, User.Roles.SENIOR_EADMIN.value] and \
                   user_to_edit.role.value != form_admin_role_value:
                    updates['admin_role_value'] = form_admin_role_value
            except ValueError:
                flash("Invalid role type submitted for edit.", "danger")
                # 重新渲染编辑表单并显示错误
                return render_template('admin/t_admin_edit_eadmin.html', # 或者通用编辑模板
                                       eadmin=user_to_edit, # 传递 User 对象
                                       User=User) # 传递 User 类

        if not updates:
            flash('No changes were submitted to update.', "info") # 使用 info 级别
            # 返回 JSON 或重定向取决于你的 AJAX 实现
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest': # 假设你用 AJAX
                 return jsonify({'success': True, 'message': 'No changes were submitted.'})
            return redirect(url_for('admin.tadmin_dashboard_page'))


        # 使用 TAdminService 中的 edit_e_admin (可能需要重命名为 edit_admin_user)
        success, message = tadmin_service_instance.edit_e_admin( # 确保这个 service 方法能处理角色更新
            admin=tadmin_model_instance, # TAdmin performing the action
            eadmin_user_id=eadmin_id, # ID of the user being edited
            updates=updates
        )
        flash(message, "success" if success else "danger")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': success, 'message': message})
        
        if success:
            return redirect(url_for('admin.tadmin_dashboard_page'))
        else:
            # 如果失败，重新渲染编辑页面并预填数据
            return render_template('admin/t_admin_edit_eadmin.html',
                                   eadmin=user_to_edit, # 旧数据用于显示
                                   form_data=request.form, # 新提交的数据用于预填
                                   User=User) # 传递 User 类

    # GET request
    return render_template('admin/t_admin_edit_eadmin.html', # 或通用编辑模板
                           eadmin=user_to_edit, # 传递 User 对象给模板，模板中可以用 eadmin.role.value
                           User=User) # 传递 User 类用于在模板中访问 Roles

@admin_bp.route('/tadmin/admins/<string:admin_user_id>/delete', methods=['POST']) # 路由可以更通用
@login_required
def tadmin_delete_admin_user_route(admin_user_id): # 重命名
    if not current_user.is_authenticated or current_user.role != User.Roles.T_ADMIN:
        flash("Access Denied.", "danger")
        return redirect(url_for('auth.login'))

    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.user_id)})
    if not user_doc:
        flash("Critical Error: T-Admin user document not found.", "danger")
        return redirect(url_for('auth.logout'))

    tadmin_model_instance = TAdmin(user_doc)
    
    # 使用 TAdminService 中的 delete_admin_user
    success, message = tadmin_service_instance.delete_admin_user(
        tadmin=tadmin_model_instance,
        admin_user_id_to_delete=admin_user_id
    )
    flash(message, "success" if success else "danger")
    return redirect(url_for('admin.tadmin_dashboard_page'))
