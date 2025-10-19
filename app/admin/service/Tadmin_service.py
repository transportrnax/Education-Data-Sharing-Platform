from bson import ObjectId
from ..models import UserQuestion, TAdmin
from app.models.ActivityRecord import ActivityRecord
from app.extensions import mongo
from app.main.User import User 
from datetime import datetime, UTC

class TAdminService:
    def view_help_requests(self, admin: TAdmin, status: str = UserQuestion.PENDING, limit: int = 100) -> tuple[list | None, str | None]:
        """
        Retrieves a list of user-submitted help requests, filtered by status.
        (admin is an instance of TAdmin model from app.models)
        """
        try:
            questions = UserQuestion.find_by_status(status, limit=limit)
            # ActivityRecord(
            #     userAccount=admin.email,
            #     activityName="Viewed Help Requests",
            #     details=f"Status: {status}, Limit: {limit}"
            # ).addRecord()
            return questions, None
        except Exception as e:
            error_msg = f"Error viewing help requests by {admin.email}: {e}"
            # ActivityRecord(
            #     userAccount=admin.email,
            #     activityName="View Help Requests Error",
            #     details=str(e)
            # ).addRecord()
            return None, error_msg

    def answer_help_request(self, admin: TAdmin, question_id_str: str, answer_content: str) -> tuple[bool, str]:
        """
        Provides an answer to a specific help request.
        (admin is an instance of TAdmin model)
        """
        if not question_id_str or not answer_content or not answer_content.strip():
            return False, "Question ID and non-empty answer content are required."
        try:
            question = UserQuestion.find_by_id(question_id_str)
            if not question:
                return False, f"Help Request with ID {question_id_str} not found."
            if question.status != UserQuestion.PENDING:
                return False, f"Help Request {question_id_str} is not pending (status: {question.status}). Cannot answer."
            
            # Assumes UserQuestion model (from models.py) has an instance method solveQuestion
            success = question.solveQuestion(answer=answer_content.strip(), answered_by=admin.email)
            if success:
                return True, f"Successfully answered question {question_id_str}."
            else:
                # ActivityRecord(
                #     userAccount=admin.email,
                #     activityName="Answer Help Request Failed",
                #     details=f"QID: {question_id_str} - solveQuestion method returned false."
                # ).addRecord()
                return False, f"Failed to update answer for question {question_id_str} (solveQuestion failed)."
        except Exception as e:
            error_msg = f"Error answering question {question_id_str} by {admin.email}: {e}"
            # ActivityRecord(
            #     userAccount=admin.email,
            #     activityName="Answer Help Request Error",
            #     details=f"QID: {question_id_str}, Error: {str(e)}"
            # ).addRecord()
            return False, f"An unexpected error occurred: {e}"

    def view_e_admins(self, admin: TAdmin, roles: int) -> tuple[list[User] | None, str | None]:
        """
        Retrieves and returns a list of all E-Admin user objects.
        (admin is an instance of TAdmin model)
        """
        try:
            eadmin_docs = mongo.db.users.find({"role": roles})
            eadmin_users = [User(doc) for doc in eadmin_docs] 
            #ActivityRecord(userAccount=admin.email, activityName="Viewed E-Admins").addRecord()
            return eadmin_users, None
        except Exception as e:
            error_msg = f"Error viewing E-Admins by {admin.email}: {e}"
            # ActivityRecord(
            #     userAccount=admin.email,
            #     activityName="View E-Admins Error",
            #     details=str(e)
            # ).addRecord()
            return None, error_msg

    def add_admin_user(self, admin: TAdmin, email: str, username: str, admin_role_value: int) -> tuple[User | None, str | None]: # 修改方法名和参数
        """
        Creates a new E-Admin or Senior E-Admin user.
        (admin is an instance of TAdmin model)
        admin_role_value is the integer value from User.Roles enum.
        """
        if not email or not username:
            # ActivityRecord(userAccount=admin.email, activityName="Add Admin User Failed - Missing Fields", details=f"Attempted email: {email}").addRecord()
            return None, "Email and username are required."

        if not admin_role_value or admin_role_value not in [User.Roles.E_ADMIN.value, User.Roles.SENIOR_EADMIN.value]:
            return None, "Invalid admin role specified."

        if User.get_by_email(email.lower()):
            msg = f"Email '{email}' already exists."
            # ActivityRecord(userAccount=admin.email, activityName="Add Admin User Failed - Email Exists", details=msg).addRecord()
            return None, msg

        try:
            # 根据角色确定 access_level，如果需要区分的话
            # 目前假设 EAdmin 和 Senior EAdmin 的 access_level 相同，权限通过 role 区分
            # 如果 Senior EAdmin 需要不同的 access_level，在这里设置
            access_level_for_new_admin = [False, False, True] # 示例，根据实际需要调整

            user_doc_to_insert = {
                "_id": ObjectId(),
                "email": email.lower(),
                "username": username,
                "role": admin_role_value, # 使用传入的角色值
                "access_level": access_level_for_new_admin,
                "created_at": datetime.now(UTC),
                "last_updated_at": datetime.now(UTC)
                # 根据需要添加其他字段，如 organization_id (如果适用)
            }
            result = mongo.db.users.insert_one(user_doc_to_insert)

            if result.inserted_id:
                new_admin_user = User(user_doc_to_insert) # 使用 User 基类创建实例
                role_name = User.Roles(admin_role_value).name
                # ActivityRecord(
                #     userAccount=admin.email,
                #     activityName=f"Added {role_name}",
                #     details=f"Admin Email: {new_admin_user.email}, ID: {new_admin_user.user_id}"
                # ).addRecord()
                return new_admin_user, f"{role_name} {email} added successfully (ID: {new_admin_user.user_id})."
            else:
                # ActivityRecord(userAccount=admin.email, activityName="Add Admin User Failed - No Insert ID", details=f"Attempted email: {email}").addRecord()
                return None, "Failed to add admin user: No ID returned after insert."
        except Exception as e:
            error_msg = f"Error adding admin user {email}: {e}"
            # ActivityRecord(userAccount=admin.email, activityName="Add Admin User Error", details=error_msg).addRecord()
            return None, f"An unexpected error occurred while adding admin user: {e}"

    # ... (edit_e_admin, delete_e_admin 方法可能也需要调整以适应角色，但暂时保持不变，仅处理 EAdmin) ...
    # 如果需要编辑/删除 SeniorEAdmin，可以创建类似的方法或使现有方法更通用

    def edit_e_admin(self, admin: TAdmin, eadmin_user_id: str, updates: dict) -> tuple[bool, str]:
        """
        Modifies an existing E-Admin's properties.
        'updates' dict can contain 'username', 'email'.
        TODO: Make this method more generic if it needs to edit Senior EAdmins as well,
              or create a separate method. For now, it targets E_ADMIN role.
        """
        if not updates:
            return True, "No update data provided."

        eadmin_to_edit = User.get_by_id(eadmin_user_id)

        if not eadmin_to_edit:
            return False, f"Admin user with ID {eadmin_user_id} not found."
        # Ensure we are editing an E_ADMIN or SENIOR_EADMIN if this TAdmin is allowed to edit both
        if eadmin_to_edit.role not in [User.Roles.E_ADMIN, User.Roles.SENIOR_EADMIN]:
            return False, f"User {eadmin_user_id} is not an E-Admin or Senior E-Admin (Role: {eadmin_to_edit.role.name})."

        mongo_update_payload = {}
        log_details_updates = []

        if 'username' in updates and updates['username'] and updates['username'] != eadmin_to_edit.username:
            mongo_update_payload['username'] = updates['username']
            log_details_updates.append("username")

        if 'email' in updates and updates['email'] and updates['email'].lower() != eadmin_to_edit.email:
            new_email_lower = updates['email'].lower()
            existing_user_with_new_email = User.get_by_email(new_email_lower)
            if existing_user_with_new_email and str(existing_user_with_new_email.user_id) != str(eadmin_to_edit.user_id):
                return False, f"New email '{updates['email']}' already exists for another user."
            mongo_update_payload['email'] = new_email_lower
            log_details_updates.append("email")
        
        # If TAdmin can change the role between EAdmin and SeniorEAdmin
        if 'admin_role_value' in updates and updates['admin_role_value'] in [User.Roles.E_ADMIN.value, User.Roles.SENIOR_EADMIN.value]:
            if eadmin_to_edit.role.value != int(updates['admin_role_value']):
                 mongo_update_payload['role'] = int(updates['admin_role_value'])
                 log_details_updates.append("role")


        if not mongo_update_payload:
            return True, f"No changes applied to Admin user {eadmin_user_id}."

        mongo_update_payload['last_updated_at'] = datetime.now(UTC)

        try:
            # Ensure user_id is ObjectId if your User.get_by_id expects ObjectId but stores string
            # Or if User.user_id is always ObjectId
            target_id = ObjectId(eadmin_to_edit.user_id) if isinstance(eadmin_to_edit.user_id, str) else eadmin_to_edit.user_id

            result = mongo.db.users.update_one(
                {"_id": target_id},
                {"$set": mongo_update_payload}
            )
            if result.modified_count > 0:
                # ActivityRecord(...)
                return True, f"Admin user {eadmin_user_id} updated successfully."
            else:
                # This can happen if the data submitted is identical to current data
                return True, f"No effective changes made to Admin user {eadmin_user_id} in DB (data might be identical)."
        except Exception as e:
            # ActivityRecord(...)
            return False, f"An unexpected database error occurred: {e}"


    def delete_admin_user(self, tadmin: TAdmin, admin_user_id_to_delete: str) -> tuple[bool, str]: # Renamed
        """
        Removes an E-Admin or Senior E-Admin account from the system.
        """
        user_to_delete = User.get_by_id(admin_user_id_to_delete) # User.get_by_id should handle string ID to ObjectId if needed

        if not user_to_delete:
            return False, f"Admin user with ID {admin_user_id_to_delete} not found."
        
        # Allow TAdmin to delete E_ADMIN or SENIOR_EADMIN
        if user_to_delete.role not in [User.Roles.E_ADMIN, User.Roles.SENIOR_EADMIN]:
            return False, f"User {admin_user_id_to_delete} is not an E-Admin or Senior E-Admin (Role: {user_to_delete.role.name}). Cannot delete."

        try:
            # Ensure user_id is ObjectId for deletion if your DB uses ObjectIds
            target_id = ObjectId(user_to_delete.user_id) if isinstance(user_to_delete.user_id, str) else user_to_delete.user_id
            result = mongo.db.users.delete_one({"_id": target_id})
            if result.deleted_count > 0:
                role_name = user_to_delete.role.name
                msg = f"{role_name} {user_to_delete.email} (ID: {admin_user_id_to_delete}) deleted successfully."
                # ActivityRecord(...)
                return True, msg
            else:
                # ActivityRecord(...)
                return False, f"Failed to delete admin user {admin_user_id_to_delete}."
        except Exception as e:
            # ActivityRecord(...)
            return False, f"An unexpected database error occurred: {e}"
