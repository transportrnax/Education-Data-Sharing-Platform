# src/app/USER/EAdmin.py

from flask import current_app, session # Need session to get current admin email
from bson import ObjectId
from datetime import datetime, timezone
from app.main.User import User # Import the base User class
from app.extensions import mongo # Import mongo instance
from app.models.ActivityRecord import ActivityRecord # For logging E-Admin actions
# Import registration constants (or define them centrally)
import uuid
from werkzeug.utils import secure_filename
import os
from app.admin.models import EAdmin

PENDING_EADMIN_APPROVAL = "pending_eadmin_approval"  # EAdmin 审批后的状态，等待 SEadmin 审批
PENDING_SEADMIN_APPROVAL = "pending_seadmin_approval" # 新增状态，专指等待SEadmin审批
ACTIVE = "active"  # SEAdmin 批准后的状态
REJECTED_BY_EADMIN = "rejected_by_eadmin" # EAdmin 拒绝
REJECTED_BY_SEADMIN = "rejected_by_seadmin" # SEadmin 拒绝 (新增)
NOT_SUBMITTED = "not_submitted"

class EAdminService:
    # --- User Log Viewing ---
    def view_user_logs(self, limit=200, page=1):
        """
        Retrieves user activity logs from the database.
        Args:
            limit (int): Max number of logs per page.
            page (int): Page number to retrieve.
        Returns:
            tuple: (list of log documents, total number of logs)
        """
        print(f"E-Admin {self.email} viewing user logs.")
        try:
            log_collection = mongo.db.activity_log
            skip = (page - 1) * limit
            logs_cursor = log_collection.find().sort("activityTime", -1).skip(skip).limit(limit)
            total_logs = log_collection.count_documents({}) # For pagination calculation
            logs = list(logs_cursor)
            #print(logs)
            return logs, total_logs
        except Exception as e:
            print(f"Error fetching activity logs by {self.email}: {e}")
            # ActivityRecord(
            #     userAccount=self.email, 
            #     activityName="View User Log Error", 
            #     details=str(e)
            # ).addRecord()
            return [], 0

    # --- Registration Application Management ---
    def view_registration_applications(self, status="pending_eadmin_approval"):
        """
        Retrieves pending (or specified status) O-Convener registration applications.
         Args:
            status (str): The status of applications to retrieve.
        Returns:
            list: A list of application documents.
        """
        try:
            reg_collection = mongo.db.org_register_request
            apps_cursor = reg_collection.find({"status": status}).sort("submitted_at", 1)
            apps_cursor = list(apps_cursor)
            #print(apps_cursor)
            return apps_cursor
        except Exception as e:
            #print(f"Error fetching registration applications by {self.email}: {e}")
            # ActivityRecord(
            #     userAccount=self.email, 
            #     activityName="View Registrations Error", 
            #     details=str(e)
            # ).addRecord()
            return []

    def approveRegistrationApplication(self, app_id: str) -> tuple[bool, str]:
        """
        审批通过指定的注册申请（只用org_register_request集合，status控制流程）
        """
        print(f"E-Admin {self.email} attempting to approve application ID: {app_id}")
        try:
            app_object_id = ObjectId(app_id)
        except Exception as e:
            return False, f"Invalid application ID format: {str(e)}"

        reg_collection = mongo.db.org_register_request
        application_doc = reg_collection.find_one({"_id": app_object_id})
        if not application_doc:
            return False, f"Application request with ID '{app_id}' not found."
        if application_doc.get('status') != 'pending_eadmin_approval':
            return False, f"Application is not pending E-Admin approval (current status: {application_doc.get('status')})."

        # 审批通过，更新status
        update_result = reg_collection.update_one(
            {"_id": app_object_id, "status": "pending_eadmin_approval"},
            {"$set": {
                "status": "pending_seadmin_approval",
                "approved_by": self.email,
                "approved_at": datetime.now(timezone.utc)
            }}
        )
        if update_result.matched_count == 0:
            return False, f"Could not approve application {app_id} as its status was not 'pending_eadmin_approval'."
        return True, f"Application {app_id} approved successfully."

    def rejectRegistrationApplication(self, app_id: str, reason: str = "No reason provided.") -> tuple[bool, str]:
        """
        驳回指定的注册申请（只用org_register_request集合，status控制流程）
        """
        print(f"E-Admin {self.email} attempting to reject application ID: {app_id}")
        try:
            app_object_id = ObjectId(app_id)
        except Exception as e:
            return False, f"Invalid application ID format: {str(e)}"
        reg_collection = mongo.db.org_register_request
        application = reg_collection.find_one({"_id": app_object_id})
        if not application:
            return False, "Application not found."
        if application.get('status') != 'pending_eadmin_approval':
            return False, f"Application is not pending E-Admin approval (status: {application.get('status')})."
        update_result = reg_collection.update_one(
            {"_id": app_object_id},
            {"$set": {
                "status": "rejected",
                "rejected_by": self.email,
                "rejected_at": datetime.now(timezone.utc),
                "rejection_reason": reason
            }}
        )
        if update_result.modified_count > 0:
            return True, f"Application {app_id} rejected."
        else:
            return False, "Application status could not be updated (already processed or DB error)."

    # --- Policy Management (Method Stubs - Require Implementation) ---
    POLICY_COLLECTION_NAME = "platform_policies"
    ALLOWED_POLICY_EXTENSIONS = {'pdf'}

    def _get_policy_collection(self):
        return mongo.db[self.POLICY_COLLECTION_NAME]
    
    def _allowed_policy_file(self, filename):
        return '.' in filename and \
                filename.rsplit('.', 1)[1].lower() in self.ALLOWED_POLICY_EXTENSIONS
    def view_policies(self, limit=50, page = 1):
        try:
            policy_collection = self._get_policy_collection()
            print(policy_collection)
            skip = (page - 1) * limit
            policies = policy_collection.find().sort("upload_timestamp", -1).skip(skip).limit(limit)
            total_policies = policy_collection.count_documents({})
            policies = list(policies)
            # ActivityRecord(
            #     userAccount=self.email,
            #     activityName="View Platform Policies",
            #     details=f"Page: {page}, Limit: {limit}"
            # ).addRecord()
            return policies, total_policies
        except Exception as e:
            print(f"Error fetching platform policies by {self.email}: {e}")
            # ActivityRecord(
            #     userAccount=self.email,
            #     activityName="View Platform policies Error",
            #     details=str(e)
            # ).addRecord()
            return [], 0


    def addPolicy(self, title: str, policy_file_storage, description: str = None) -> tuple[bool, str]:
        """Adds a new policy to the system, storing file_path as a relative path."""
        print(f"E-Admin {self.email} attempting to add new policy: {title}")
        if not title or not title.strip():
            return False, "Policy title is required."
        if not policy_file_storage or not policy_file_storage.filename:
            return False, "Policy PDF file is required."
        if not self._allowed_policy_file(policy_file_storage.filename):
            return False, "Invalid file type. Only PDF files are allowed for policies."
        filename = secure_filename(policy_file_storage.filename)
        rel_dir = 'uploads/policies'
        if not os.path.exists(rel_dir):
            os.makedirs(rel_dir, exist_ok=True)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        rel_path = os.path.join(rel_dir, unique_filename).replace('\\', '/')
        abs_path = os.path.abspath(rel_path)
        try:
            policy_file_storage.save(abs_path)

            policy_collection = self._get_policy_collection()
            now = datetime.now(timezone.utc)
            policy_data = {
                "title": title.strip(),
                "description": description.strip() if description else None,
                "filename": unique_filename,  # Stored unique filename
                "original_filename": filename,  # Original filename for display
                "file_path": rel_path,         # 只存 uploads/policies/xxx.pdf
                "created_at": now,
                "created_by": self.email,
                "last_updated_at": now,
                "last_updated_by": self.email
            }
            result = policy_collection.insert_one(policy_data)
            message = f"Policy '{title}' added successfully with ID: {result.inserted_id}."
            return True, message
        except Exception as e:
            print(f"Error adding policy '{title}' by {self.email}: {e}")
            # Attempt to clean up saved file if DB insert fails
            if os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                except OSError as ose:
                    print(f"Error cleaning up policy file {abs_path} after DB error: {ose}")
            return False, f"An error occurred while adding the policy: {str(e)}"

    def updatePolicy(self, policy_id: str, title: str = None, description: str = None, new_policy_file_storage=None) -> tuple[bool, str]:
        """
        Updates an existing platform data sharing policy.
        Args:
            policy_id (str): The ID of the policy to update.
            title (str, optional): The new title.
            description (str, optional): The new description.
            new_policy_file_storage (FileStorage, optional): A new PDF file to replace the existing one.
        Returns:
            tuple: (success_boolean, message_string)
        """
        print(f"E-Admin {self.email} attempting to update policy ID: {policy_id}")
        try:
            p_object_id = ObjectId(policy_id)
        except Exception as e:
            return False, f"Invalid Policy ID format: {e}"

        policy_collection = self._get_policy_collection()
        existing_policy = policy_collection.find_one({"_id": p_object_id})

        if not existing_policy:
            return False, "Policy not found."

        updates = {}
        if title and title.strip() and title.strip() != existing_policy.get("title"):
            updates["title"] = title.strip()
        if description is not None: # Allow empty string to clear description
             if description.strip() != existing_policy.get("description"):
                updates["description"] = description.strip() if description.strip() else None


        old_filepath = existing_policy.get("filepath")
        log_details = f"PolicyID: {policy_id}"

        if new_policy_file_storage and new_policy_file_storage.filename:
            if not self._allowed_policy_file(new_policy_file_storage.filename):
                return False, "Invalid new file type. Only PDF files are allowed."

            original_filename = secure_filename(new_policy_file_storage.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER', './uploads/policies') # Ensure consistency
            unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
            new_filepath = os.path.join(upload_folder, unique_filename)

            try:
                new_policy_file_storage.save(new_filepath)
                updates["filename"] = unique_filename
                
                updates["original_filename"] = original_filename
                updates["filepath"] = new_filepath 
                log_details += f", NewFile: {unique_filename}"
            except Exception as e:
                return False, f"Error saving new policy file: {e}"

        if not updates and not new_policy_file_storage: # Check if new_policy_file_storage was actually processed
            return True, "No changes detected for the policy."

        updates["last_updated_timestamp"] = datetime.now(timezone.utc)
        updates["last_updated_by_email"] = self.email

        try:
            result = policy_collection.update_one({"_id": p_object_id}, {"$set": updates})
            if result.modified_count > 0:
                # If a new file was uploaded and the old one exists, delete the old file
                if new_policy_file_storage and old_filepath and os.path.exists(old_filepath) and old_filepath != new_filepath:
                    try:
                        os.remove(old_filepath)
                        print(f"Old policy file {old_filepath} deleted.")
                    except OSError as ose:
                        print(f"Error deleting old policy file {old_filepath}: {ose}")
                        # Non-critical error, policy record is updated. Log this.
                        # ActivityRecord(
                        #     userAccount=self.email,
                        #     activityName="Update Policy - Old File Deletion Error",
                        #     details=f"PolicyID: {policy_id}, File: {old_filepath}, Error: {str(ose)}"
                        # ).addRecord()

                message = f"Policy '{existing_policy.get('title')}' (ID: {policy_id}) updated successfully."
                # ActivityRecord(
                #     userAccount=self.email,
                #     activityName="Update Platform Policy Success",
                #     details=log_details + f", Updates: {list(updates.keys())}"
                # ).addRecord()
                return True, message
            else:
                # This might happen if only file was changed but no metadata, or if data was same
                if new_policy_file_storage and not updates: # Only file was changed
                     message = f"Policy '{existing_policy.get('title')}' (ID: {policy_id}) file updated successfully."
                     ActivityRecord(
                         userAccount=self.email,
                         activityName="Update Platform Policy File Success",
                         details=log_details
                     ).addRecord()
                     return True, message
                return False, "Policy could not be updated or no changes made."
        except Exception as e:
            print(f"Error updating policy {policy_id} by {self.email}: {e}")
            # If new file was saved but DB update failed, attempt to clean up new file
            if new_policy_file_storage and 'new_filepath' in locals() and os.path.exists(new_filepath):
                try:
                    os.remove(new_filepath)
                except OSError as ose:
                     print(f"Error cleaning up new policy file {new_filepath} after DB error: {ose}")
            # ActivityRecord(
            #     userAccount=self.email,
            #     activityName="Update Platform Policy Error",
            #     details=f"PolicyID: {policy_id}, Error: {str(e)}"
            # ).addRecord()
            return False, f"An error occurred while updating the policy: {str(e)}"

    def deletePolicy(self, policy_id: str) -> tuple[bool, str]:
        """Deletes a platform data sharing policy and its associated file."""
        print(f"E-Admin {self.email} attempting to delete policy ID: {policy_id}")
        try:
            p_object_id = ObjectId(policy_id)
        except Exception as e:
            return False, f"Invalid Policy ID format: {e}"

        policy_collection = self._get_policy_collection()
        policy_to_delete = policy_collection.find_one({"_id": p_object_id})

        if not policy_to_delete:
            return False, "Policy not found."

        filepath_to_delete = policy_to_delete.get("filepath") # Get filepath from DB
        policy_title = policy_to_delete.get("title", "N/A")


        try:
            result = policy_collection.delete_one({"_id": p_object_id})
            if result.deleted_count > 0:
                if filepath_to_delete and os.path.exists(filepath_to_delete):
                    try:
                        os.remove(filepath_to_delete)
                        print(f"Policy file {filepath_to_delete} deleted successfully.")
                    except OSError as ose:
                        # Log that DB record was deleted but file wasn't. This is an inconsistency.
                        print(f"Error deleting policy file {filepath_to_delete} for policy ID {policy_id}: {ose}")
                        # ActivityRecord(
                        #     userAccount=self.email,
                        #     activityName="Delete Platform Policy - File Deletion Error",
                        #     details=f"PolicyID: {policy_id}, Filepath: {filepath_to_delete}, Error: {str(ose)}"
                        # ).addRecord()
                        return True, f"Policy '{policy_title}' record deleted, but its file '{filepath_to_delete}' could not be removed. Please check server logs."

                message = f"Policy '{policy_title}' (ID: {policy_id}) and its associated file deleted successfully."
                # ActivityRecord(
                #     userAccount=self.email,
                #     activityName="Delete Platform Policy Success",
                #     details=f"PolicyID: {policy_id}, Title: {policy_title}, File: {filepath_to_delete}"
                # ).addRecord()
                return True, message
            else:
                return False, "Policy could not be deleted (not found or DB error)."
        except Exception as e:
            print(f"Error deleting policy {policy_id} by {self.email}: {e}")
            # ActivityRecord(
            #     userAccount=self.email,
            #     activityName="Delete Platform Policy Error",
            #     details=f"PolicyID: {policy_id}, Error: {str(e)}"
            # ).addRecord()
            return False, f"An error occurred while deleting the policy: {str(e)}"