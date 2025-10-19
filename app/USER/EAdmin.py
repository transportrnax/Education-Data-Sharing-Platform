# src/app/USER/EAdmin.py

from flask import current_app, session # Need session to get current admin email
from bson import ObjectId
from datetime import datetime, timezone
from .user import User # Import the base User class
from ..extensions import mongo # Import mongo instance
from ..models.ActivityRecord import ActivityRecord # For logging E-Admin actions
# Import registration constants (or define them centrally)
from .Register import REG_STATUS_PENDING_APPROVAL, REG_STATUS_APPROVED, REG_STATUS_REJECTED
import uuid
from .OConvener import OConvener
from werkzeug.utils import secure_filename
import os
class EAdmin(User):
    """
    Represents an Enterprise Administrator (E-Admin) user.
    Includes methods corresponding to E-Admin functionalities.
    """
    def __init__(self, **kwargs):
        """Initializes an EAdmin user, ensuring the role is set correctly."""
        kwargs['user_role'] = User.ROLE_E_ADMIN # Ensure role is E-Admin
        super().__init__(**kwargs)

    # --- User Log Viewing ---
    def viewUserLog(self, limit=200, page=1):
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
            ActivityRecord(
                userAccount=self.email, 
                activityName="View User Log Error", 
                details=str(e)
            ).addRecord()
            return [], 0

    # --- Registration Application Management ---
    def viewRegistrationApplication(self, status=REG_STATUS_PENDING_APPROVAL):
        """
        Retrieves pending (or specified status) O-Convener registration applications.
         Args:
            status (str): The status of applications to retrieve.
        Returns:
            list: A list of application documents.
        """
        print(f"E-Admin {self.email} viewing registration applications with status: {status}")
        try:
            reg_collection = mongo.db.organization_approval_requests
            apps_cursor = reg_collection.find({"status": status}).sort("submitted_at", 1)
            apps_cursor = list(apps_cursor)
            #print(apps_cursor)
            return apps_cursor
        except Exception as e:
            print(f"Error fetching registration applications by {self.email}: {e}")
            ActivityRecord(
                userAccount=self.email, 
                activityName="View Registrations Error", 
                details=str(e)
            ).addRecord()
            return []

    def approveRegistrationApplication(self, app_id: str) -> tuple[bool, str]:
        print(f"E-Admin {self.email} attempting to approve application ID: {app_id}")
        try:
            app_object_id = ObjectId(app_id)
        except Exception as e:
            return False, f"Invalid application ID format: {str(e)}"

        approval_requests_collection = mongo.db.organization_approval_requests
        organizations_collection = mongo.db.organizations
        users_collection = mongo.db.USERS # To update O-Convener's user record if needed

        application_doc = approval_requests_collection.find_one({"_id": app_object_id})

        if not application_doc:
            return False, f"Application request with ID '{app_id}' not found."

        # Ensure REG_STATUS_PENDING_APPROVAL is correctly defined/imported
        if application_doc.get('status') != REG_STATUS_PENDING_APPROVAL:
            return False, f"Application is not pending approval (current status: {application_doc.get('status')})."

        oconvener_user_id = application_doc.get('oconvener_user_id')
        # This is the organization_id already assigned to the O-Convener user
        # and submitted with their organization registration request.
        organization_id_from_app = application_doc.get('organization_id_on_user')
        approved_org_name = application_doc.get('org_name') # Name from the application
        applicant_email = application_doc.get('email') # Email of the O-Convener

        if not oconvener_user_id or not organization_id_from_app or not approved_org_name:
            message = "Application data is incomplete (missing O-Convener ID, Organization ID, or Organization Name)."
            approval_requests_collection.update_one(
                {"_id": app_object_id},
                {"$set": {"status": REG_STATUS_REJECTED, "rejection_reason": message}}
            )
            ActivityRecord(userAccount=self.email, activityName="Org Approval Rejected - Incomplete Data", details=f"AppID: {app_id}. {message}").addRecord()
            return False, message

        # --- Check 1: Verify the O-Convener user actually exists ---
        oconvener_user_doc = users_collection.find_one({"_id": oconvener_user_id}) # Assuming oconvener_user_id is a string from app_doc
        print(oconvener_user_doc)
        if not oconvener_user_doc:
            message = f"O-Convener user (ID: {oconvener_user_id}) associated with this application not found. Cannot approve."
            approval_requests_collection.update_one(
                {"_id": app_object_id},
                {"$set": {"status": REG_STATUS_REJECTED, "rejection_reason": message}}
            )
            ActivityRecord(userAccount=self.email, activityName="Org Approval Rejected - OConvener User Not Found", details=f"AppID: {app_id}. {message}").addRecord()
            return False, message
        
        # --- Check 2: Ensure this organization isn't already active for this O-Convener ---
        # This prevents re-approving an already active setup via a duplicate/lingering request.
        already_active_org = organizations_collection.find_one({
            "_id": organization_id_from_app,
            "convener_user_id": oconvener_user_id, # Ensure correct ObjectId comparison
            "status": {"$in": ["active", "approved"]} # "active" is the typical final state
        })

        if already_active_org:
            message = (f"Organization '{already_active_org.get('name')}' (ID: {organization_id_from_app}) "
                       f"is already active and managed by O-Convener (User ID: {oconvener_user_id}). "
                       f"This approval request (AppID: {app_id}) is redundant or for an already finalized setup.")
            
            # Mark the current approval request as rejected/duplicate.
            approval_requests_collection.update_one(
                {"_id": app_object_id},
                {"$set": {"status": REG_STATUS_REJECTED, "rejection_reason": "Organization already active and approved."}}
            )
            ActivityRecord(
                userAccount=self.email,
                activityName="Organization Approval Rejected - Already Active",
                details=f"AppID: {app_id}. {message}"
            ).addRecord()
            return False, message

        # --- All checks passed, proceed with approval ---
        current_time = datetime.now(timezone.utc)

        # 1. Update the status of the approval request in 'organization_approval_requests'
        update_result_req = approval_requests_collection.update_one(
            {"_id": app_object_id, "status": REG_STATUS_PENDING_APPROVAL}, # Ensure we only update pending ones
            {"$set": {
                "status": REG_STATUS_APPROVED,
                "approved_by": self.email,
                "approved_at": current_time
            }}
        )

        if update_result_req.matched_count == 0:
            current_status_check = approval_requests_collection.find_one({"_id": app_object_id}, {"status": 1})
            status_msg = current_status_check.get('status') if current_status_check else 'Unknown or Not Found'
            return False, f"Could not approve application {app_id} as its status was not '{REG_STATUS_PENDING_APPROVAL}'. Current status: {status_msg}."

        org_data_to_set = {
            "name": approved_org_name,
            "convener_user_id": oconvener_user_id,
            "status": "active", # Set to "active" upon successful approval
            "last_updated_at": current_time,
            "proof_document_path": application_doc.get('proof_document_path'), # From the application
            "email": applicant_email # O-Convener's email, useful to have on the org record
            # Add any other fields that should be on the official organization record
        }
        organizations_collection.update_one(
            {"_id": organization_id_from_app}, # The pre-assigned organization_id
            {"$set": org_data_to_set,
             "$setOnInsert": {"created_at": current_time, "_id": organization_id_from_app}},
            upsert=True
        )

        # 3. Ensure the O-Convener's user record (in 'users' collection) reflects the
        #    approved organization name, as it might have been changed by EAdmin or during application.
        if oconvener_user_doc.get('organization_name') != approved_org_name or \
           oconvener_user_doc.get('organization_id') != organization_id_from_app: # Should match, but good to ensure
            users_collection.update_one(
                {"_id": ObjectId(oconvener_user_id)},
                {"$set": {
                    "organization_name": approved_org_name,
                    "organization_id": organization_id_from_app, # Ensure this is correctly set
                    "last_updated_at": current_time
                }}
            )

        message = (f"Organization '{approved_org_name}' (ID: {organization_id_from_app}) "
                   f"for O-Convener {applicant_email} (User ID: {oconvener_user_id}) approved successfully.")
        ActivityRecord(
            userAccount=self.email,
            activityName="Organization Registration Approved",
            details=(f"AppID: {app_id}, OrgID: {organization_id_from_app}, OrgName: {approved_org_name}, "
                     f"OConvenerID: {oconvener_user_id}, OConvenerEmail: {applicant_email}")
        ).addRecord()
        return True, message

    def rejectRegistrationApplication(self, app_id: str, reason: str = "No reason provided.") -> tuple[bool, str]:
        """
        Rejects a specific O-Convener registration application.
        Args:
            app_id (str): The string representation of the application's ObjectId.
            reason (str): Optional reason for rejection.
        Returns:
            tuple: (success_boolean, message_string)
        """
        print(f"E-Admin {self.email} attempting to reject application ID: {app_id}")
        try:
            app_object_id = ObjectId(app_id)
            reg_collection = mongo.db.organization_approval_requests

            # Find the application and ensure it's pending
            application = reg_collection.find_one({"_id": app_object_id})
            if not application:
                return False, "Application not found."
            if application['status'] != REG_STATUS_PENDING_APPROVAL:
                return False, f"Application is not pending approval (status: {application['status']})."
            # Update status to rejected
            update_result = reg_collection.update_one(
                {"_id": app_object_id}, 
                {"$set": {
                    "status": 'rejected',
                    "rejected_by": self.email, 
                    "rejected_at": datetime.now(timezone.utc),
                    "rejection_reason": reason
                 }}
            )

            if update_result.modified_count > 0:
                message = f"Application {app_id} rejected."
                ActivityRecord(
                    userAccount=self.email, 
                    activityName="O-Convener Rejected", 
                    details=f"AppID: {app_id if app_id else ''}, Email: {application.get('email', '')}, Reason: {reason if reason else ''}"
                ).addRecord()
                return True, message
            else:
                # Should not happen if find_one succeeded, but handle defensively
                message = "Application status could not be updated (already processed or DB error)."
                return False, message

        except Exception as e:
            print(f"Error rejecting application {app_id} by {self.email}: {e}")
            ActivityRecord(
                userAccount=self.email, 
                activityName="O-Convener Rejection Error", 
                details=f"AppID: {app_id}, Error: {str(e)}"
            ).addRecord()
            return False, f"An unexpected error occurred: {e}"


    # --- Policy Management (Method Stubs - Require Implementation) ---
    POLICY_COLLECTION_NAME = "platform_policies"
    ALLOWED_POLICY_EXTENSIONS = {'pdf'}

    def _get_policy_collection(self):
        return mongo.db[self.POLICY_COLLECTION_NAME]
    
    def _allowed_policy_file(self, filename):
        return '.' in filename and \
                filename.rsplit('.', 1)[1].lower() in self.ALLOWED_POLICY_EXTENSIONS
    def viewPolicy(self, limit=50, page = 1):
        try:
            policy_collection = self._get_policy_collection()
            print(policy_collection)
            skip = (page - 1) * limit
            policies = policy_collection.find().sort("upload_timestamp", -1).skip(skip).limit(limit)
            total_policies = policy_collection.count_documents({})
            policies = list(policies)
            ActivityRecord(
                userAccount=self.email,
                activityName="View Platform Policies",
                details=f"Page: {page}, Limit: {limit}"
            ).addRecord()
            return policies, total_policies
        except Exception as e:
            print(f"Error fetching platform policies by {self.email}: {e}")
            ActivityRecord(
                userAccount=self.email,
                activityName="View Platform policies Error",
                details=str(e)
            ).addRecord()
            return [], 0
        

    def addPolicy(self, title: str, policy_file_storage, description: str = None) -> tuple[bool, str]:
        """Placeholder: Adds a new policy to the system."""
        print(f"E-Admin {self.email} attempting to add new policy: {title}")
        if not title or not title.strip():
            return False, "Policy title is required."
        if not policy_file_storage or not policy_file_storage.filename:
            return False, "Policy PDF file is required."
        if not self._allowed_policy_file(policy_file_storage.filename):
            return False, "Invalid file type. Only PDF files are allowed for policies."
        filename = secure_filename(policy_file_storage.filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER','./uploads/polocies')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)

        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(upload_folder, unique_filename)

        try:
            policy_file_storage.save(filepath)

            policy_collection = self._get_policy_collection()
            now = datetime.now(timezone.utc)
            policy_data = {
                "title": title.strip(),
                "description": description.strip() if description else None,
                "filename": unique_filename, # Stored unique filename
                "original_filename": filename, # Original filename for display
                "filepath": filepath,
                "upload_timestamp": now,
                "uploaded_by_email": self.email,
                "last_updated_timestamp": now,
                "last_updated_by_email": self.email
            }
            result = policy_collection.insert_one(policy_data)
            message = f"Policy '{title}' added successfully with ID: {result.inserted_id}."
            ActivityRecord(
                userAccount=self.email,
                activityName="Add Platform Policy Success",
                details=f"PolicyID: {result.inserted_id}, Title: {title}, File: {unique_filename}"
            ).addRecord()
            return True, message
        except Exception as e:
            print(f"Error adding policy '{title}' by {self.email}: {e}")
            # Attempt to clean up saved file if DB insert fails
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError as ose:
                    print(f"Error cleaning up policy file {filepath} after DB error: {ose}")
            ActivityRecord(
                userAccount=self.email,
                activityName="Add Platform Policy Error",
                details=f"Title: {title}, Error: {str(e)}"
            ).addRecord()
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
                updates["filepath"] = new_filepath # Update filepath
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
                        ActivityRecord(
                            userAccount=self.email,
                            activityName="Update Policy - Old File Deletion Error",
                            details=f"PolicyID: {policy_id}, File: {old_filepath}, Error: {str(ose)}"
                        ).addRecord()

                message = f"Policy '{existing_policy.get('title')}' (ID: {policy_id}) updated successfully."
                ActivityRecord(
                    userAccount=self.email,
                    activityName="Update Platform Policy Success",
                    details=log_details + f", Updates: {list(updates.keys())}"
                ).addRecord()
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
            ActivityRecord(
                userAccount=self.email,
                activityName="Update Platform Policy Error",
                details=f"PolicyID: {policy_id}, Error: {str(e)}"
            ).addRecord()
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
                        ActivityRecord(
                            userAccount=self.email,
                            activityName="Delete Platform Policy - File Deletion Error",
                            details=f"PolicyID: {policy_id}, Filepath: {filepath_to_delete}, Error: {str(ose)}"
                        ).addRecord()
                        return True, f"Policy '{policy_title}' record deleted, but its file '{filepath_to_delete}' could not be removed. Please check server logs."

                message = f"Policy '{policy_title}' (ID: {policy_id}) and its associated file deleted successfully."
                ActivityRecord(
                    userAccount=self.email,
                    activityName="Delete Platform Policy Success",
                    details=f"PolicyID: {policy_id}, Title: {policy_title}, File: {filepath_to_delete}"
                ).addRecord()
                return True, message
            else:
                return False, "Policy could not be deleted (not found or DB error)."
        except Exception as e:
            print(f"Error deleting policy {policy_id} by {self.email}: {e}")
            ActivityRecord(
                userAccount=self.email,
                activityName="Delete Platform Policy Error",
                details=f"PolicyID: {policy_id}, Error: {str(e)}"
            ).addRecord()
            return False, f"An error occurred while deleting the policy: {str(e)}"