# src/app/USER/T_Admin.py

from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timezone # Use timezone if using timezone-aware datetimes

# Assuming User is in the same directory, and models are in ../models
from .user import User
from ..models.UserQuestion import UserQuestion
from ..models.ActivityRecord import ActivityRecord
from ..extensions import mongo # Import mongo instance
from .handle_utils import valid_email
class TAdmin(User):
    """
    Represents a Technical Administrator (T-Admin) user.
    Handles help requests and manages E-Admin accounts.
    Inherits from User and uses MongoDB ObjectIds.
    """

    def __init__(self, **kwargs):
        """Initializes a TAdmin user, ensuring the role is set correctly."""
        kwargs['user_role'] = User.ROLE_T_ADMIN # Ensure role is T-Admin
        super().__init__(**kwargs)
        # Add any T-Admin specific initialization if needed

    # --- Help Request Management ---

    def viewHelpRequest(self, status: str = UserQuestion.STATUS_PENDING, limit: int = 100) -> tuple[list | None, str | None]:
        """
        Retrieves a list of user-submitted help requests, filtered by status.
        Args:
            status (str): The status to filter by (e.g., 'pending', 'answered').
                          Defaults to UserQuestion.STATUS_PENDING.
            limit (int): Maximum number of requests to return. Defaults to 100.
        Returns:
            tuple: (list of UserQuestion objects or None, error_message or None)
        """
        print(f"T-Admin {self.email} viewing help requests with status: {status}")
        try:
            questions = UserQuestion.find_by_status(status, limit=limit) # Adjust if method name differs
            if questions is None: # Check if the find method indicated an error
                 raise Exception("Failed to retrieve questions from UserQuestion class method.")

            ActivityRecord(
                userAccount=self.email,
                activityName="Viewed Help Requests",
                details=f"Status: {status}, Limit: {limit}"
            ).addRecord()
            return questions, None # Return list of objects and no error
        except Exception as e:
            error_msg = f"Error viewing help requests by {self.email}: {e}"
            print(error_msg)
            ActivityRecord(
                userAccount=self.email,
                activityName="View Help Requests Error",
                details=str(e)
            ).addRecord()
            return None, error_msg # Return None and error message

    def answerHelpRequest(self, question_id_str: str, answer_content: str) -> tuple[bool, str]:
        """
        Provides an answer to a specific help request.
        Args:
            question_id_str (str): The string representation of the question's ObjectId.
            answer_content (str): The answer text provided by the T-Admin.
        Returns:
            tuple: (success_boolean, message_string)
        """
        print(f"T-Admin {self.email} answering question ID: {question_id_str}")
        if not question_id_str or not answer_content or not answer_content.strip():
            return False, "Question ID and non-empty answer content are required."

        try:
            q_obj_id = ObjectId(question_id_str)
        except InvalidId:
            return False, f"Invalid Question ID format: {question_id_str}"
        except Exception as e:
             return False, f"Error processing Question ID: {e}"

        try:
            question = UserQuestion.find_by_id(q_obj_id) # Fetch the question object

            if not question:
                return False, f"Help Request with ID {question_id_str} not found."

            if question.status != UserQuestion.STATUS_PENDING:
                # Decide if answering non-pending questions is allowed
                return False, f"Help Request {question_id_str} is not pending (status: {question.status}). Cannot answer."

            # Use the solveQuestion method, passing the T-Admin's email
            success = question.sloveQuestion(answer=answer_content.strip(), answered_by=self.email)

            if success:
                # Logging is handled within solveQuestion
                return True, f"Successfully answered question {question_id_str}."
            else:
                # solveQuestion might have failed internally (e.g., DB error)
                return False, f"Failed to update answer for question {question_id_str}."

        except Exception as e:
            error_msg = f"Error answering question {question_id_str} by {self.email}: {e}"
            print(error_msg)
            ActivityRecord(
                userAccount=self.email,
                activityName="Answer Help Request Error",
                details=f"QID: {question_id_str}, Error: {str(e)}"
            ).addRecord()
            return False, f"An unexpected error occurred: {e}"

    # --- E-Admin Management ---

    def viewEAdmin(self) -> tuple[list | None, str | None]:
        """
        Retrieves and returns a list of all E-Admin user objects.
        Returns:
            tuple: (list of User objects or None, error_message or None)
        """
        print(f"T-Admin {self.email} viewing E-Admins.")
        try:
            users_collection = User._get_collection()
            eadmin_docs = users_collection.find({"user_role": User.ROLE_E_ADMIN})
            eadmin_users = [User.from_document(doc) for doc in eadmin_docs] # Convert docs to User objects
            ActivityRecord(userAccount=self.email, activityName="Viewed E-Admins").addRecord()
            return eadmin_users, None # Return list of objects, no error
        except Exception as e:
            error_msg = f"Error viewing E-Admins by {self.email}: {e}"
            print(error_msg)
            ActivityRecord(
                userAccount=self.email,
                activityName="View E-Admins Error",
                details=str(e)
            ).addRecord()
            return None, error_msg # Return None, error message


    def addEAdmin(self, email: str, username: str = None) -> tuple[User | None, str | None]:
        """
        Creates a new E-Admin user.
         Args:
            email (str): The email for the new E-Admin.
            username (str, optional): The username for the new E-Admin. Defaults to None.
        Returns:
            tuple: (new User object or None, status message or None)
        """
        print(f"T-Admin {self.email} attempting to add E-Admin: {email}")
        if not email or not valid_email(email): # Assuming valid_email is accessible/static
            return None, "Valid email is required to add E-Admin."

        # Check if email already exists
        if User.find_by_email(email):
             msg = f"Email '{email}' already exists."
             ActivityRecord(userAccount=self.email, activityName="Add E-Admin Failed", details=msg).addRecord()
             return None, msg

        try:
            # Create a new User instance, let User class handle _id generation (ObjectId)
            new_eadmin = User(
                email=email,
                username=username, # User __init__ handles default if None
                user_role=User.ROLE_E_ADMIN # Set role specifically
            )
            saved_id = new_eadmin.save() # Save the new user (returns ObjectId or None)

            if saved_id: # Check if save returned the ObjectId
                 # Logging is handled within save()
                 return new_eadmin, f"E-Admin {email} added successfully (ID: {saved_id})."
            else:
                # Error should have been logged within save()
                return None, f"Failed to save new E-Admin {email} to database."
        except Exception as e:
             error_msg = f"Error adding E-Admin {email}: {e}"
             print(error_msg)
             ActivityRecord(userAccount=self.email, activityName="Add E-Admin Error", details=error_msg).addRecord()
             return None, f"An unexpected error occurred: {e}"


    def editEAdmin(self, eadmin_id_str: str, updates: dict) -> tuple[bool, str]:
        """
        Modifies an existing E-Admin's properties using User setters.
        Args:
            eadmin_id_str (str): The string UUID of the E-Admin.
            updates (dict): Dictionary of fields to update (e.g., {'username': 'new_name'}).
        Returns:
            tuple: (success_boolean, message_string)
        """
        print(f"T-Admin {self.email} attempting to edit E-Admin ID: {eadmin_id_str}")
        if not updates:
            return False, "No update data provided."
        eadmin_user = User.find_by_id(eadmin_id_str)

        if not eadmin_user:
            return False, f"E-Admin with ID {eadmin_id_str} not found."
        if eadmin_user.user_role != User.ROLE_E_ADMIN:
             return False, f"User {eadmin_id_str} is not an E-Admin (Role: {eadmin_user.user_role})."

        update_results = {}
        overall_success = True
        update_made = False

        # --- Apply updates using setter methods ---
        if 'username' in updates:
            result_code = eadmin_user.set_username(updates['username'], performed_by=self)
            update_results['username'] = result_code
            if result_code != "USERNAME_SET_SUCCESS": overall_success = False
            else: update_made = True

        if 'email' in updates:
             # Important: set_email should check for uniqueness before saving
             result_code = eadmin_user.set_email(updates['email'], performed_by=self)
             update_results['email'] = result_code
             if result_code != "EMAIL_SET_SUCCESS": overall_success = False
             else: update_made = True

        if 'access_right' in updates:
             # Convert access rights from form (list of strings) to list of integers
             try:
                 # Example: Assuming form sends values like ['1', '2']
                 access_right_values = [int(r) for r in updates['access_right']]
             except (ValueError, TypeError):
                 return False, "Invalid format for access rights."

             result_code = eadmin_user.set_access_right(access_right_values, performed_by=self)
             update_results['access_right'] = result_code
             if result_code != "ACCESS_RIGHT_UPDATED": overall_success = False
             else: update_made = True

        # --- Compile message ---
        if not update_made and overall_success: # No valid fields to update or no change
            message = f"No changes applied to E-Admin {eadmin_id_str}."
            return True, message # Technically successful as no errors occurred

        if overall_success:
            message = f"E-Admin {eadmin_id_str} updated successfully."
            # Log the overall edit action, specific changes are logged by setters
            ActivityRecord(userAccount=self.email, activityName="E-Admin Edited", details=f"TargetID: {eadmin_id_str}, Updates: {list(updates.keys())}").addRecord()
            return True, message
        else:
            # Collate specific errors from results
            error_details = "; ".join([f"{k}: {v}" for k, v in update_results.items() if v not in ["USERNAME_SET_SUCCESS", "EMAIL_SET_SUCCESS", "ACCESS_RIGHT_UPDATED"]])
            message = f"Failed to update E-Admin {eadmin_id_str}. Errors: {error_details}"
            ActivityRecord(userAccount=self.email, activityName="E-Admin Edit Failed", details=f"TargetID: {eadmin_id_str}, Errors: {error_details}").addRecord()
            return False, message


    def deleteEAdmin(self, eadmin_id_str: str) -> tuple[bool, str]:
        """
        Removes an E-Admin account from the system.
        Args:
            eadmin_id_str (str): The string representation of the E-Admin's ObjectId.
        Returns:
            tuple: (success_boolean, message_string)
        """
        eadmin_user = User.find_by_id(eadmin_id_str)
        if not eadmin_user:
            return False, f"E-Admin with ID {eadmin_id_str} not found."
        if eadmin_user.user_role != User.ROLE_E_ADMIN:
            return False, f"User {eadmin_id_str} is not an E-Admin."

        # Delete directly from collection using the string UUID
        try:
            collection = User._get_collection()
            # Query using the string _id directly
            delete_result = collection.delete_one({"_id": eadmin_id_str})

            if delete_result.deleted_count > 0:
                msg = f"E-Admin {eadmin_id_str} deleted successfully."
                ActivityRecord(userAccount=self.email, activityName="E-Admin Deleted", details=f"Deleted ID: {eadmin_id_str}, Email: {eadmin_user.email}").addRecord()
                return True, msg
            else:
                # This indicates the user was found just before but couldn't be deleted (race condition?)
                msg = f"Failed to delete E-Admin {eadmin_id_str} (delete count 0)."
                ActivityRecord(userAccount=self.email, activityName="E-Admin Delete Failed", details=f"Target ID: {eadmin_id_str}").addRecord()
                return False, msg
        except Exception as e:
            error_msg = f"Database error deleting E-Admin {eadmin_id_str}: {e}"
            print(error_msg)
            ActivityRecord(userAccount=self.email, activityName="E-Admin Delete DB Error", details=f"Target ID: {eadmin_id_str}, Error: {str(e)}").addRecord()
            return False, f"An unexpected database error occurred: {e}"
        
    def __repr__(self):
        """Custom string representation for TAdmin"""
        return f"<TAdmin email='{self.email}' id='{self._id}'>"