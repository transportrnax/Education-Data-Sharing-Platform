# src/app/USER/OConvener.py

import uuid
import re # Import re for email validation in addMember
from datetime import datetime, timezone
# Import User class from user.py in the same directory
from .user import User
# Import necessary tools/models from the main app structure
from app.extensions import mongo
from app.models.ActivityRecord import ActivityRecord

class OConvener(User):
    """
    Represents an Organization Convener, inheriting from User.
    Uses string UUIDs for user IDs and handles member management within their organization.
    Includes database operations for member management.
    """

    def __init__(self, organization_id: str = None, organization_name: str = None, **kwargs):
        """Initializes OConvener."""
        kwargs['user_role'] = User.ROLE_O_CONVENER
        super().__init__(**kwargs)
        self.organization_id = organization_id
        self.organization_name = organization_name
        if User.ACCESS_PUBLIC not in self.access_right:
            self.access_right.append(User.ACCESS_PUBLIC)
            self.access_right.sort()

    def to_dict(self) -> dict:
        """Extends base User.to_dict."""
        data = super().to_dict()
        data['organization_id'] = self.organization_id
        data['organization_name'] = self.organization_name
        return data

    # --- O-Convener Specific Methods ---

    def registerOrganization(self) -> bool:
        """Placeholder: Finalizes organization setup after admin approval."""
        if not self.organization_id or not self.organization_name:
            print(f"Error: OConvener {self.email} missing organization details.")
            return False
        print(f"OConvener {self.email}: Finalizing registration for Org ID {self.organization_id}")
        ActivityRecord(
            userAccount=self.email, 
            activityName="Organization Registration Finalized"
        ).addRecord()
        org_collection = mongo.db.organizations
        try:
             # Use string organization_id for query/upsert
            org_collection.update_one(
                {"_id": self.organization_id},
                {"$set": { "name": self.organization_name, "convener_user_id": self._id, "status": "active",
                        "created_at": datetime.now(timezone.utc) }},
                upsert=True )
            print(f"Organization record {self.organization_id} linked/created."); return True
        except Exception as e:
            print(f"Error finalizing organization record {self.organization_id}: {e}")
            ActivityRecord(
                userAccount=self.email, 
                activityName="Organization Finalization Failed", 
                details=str(e)
            ).addRecord()
            return False


    def manageMember(self, action: str, member_email: str = None, member_data: dict = None) -> bool:
        """
        Manages members within the O-Convener's organization with DB operations.
        Args:
            action (str): 'add', 'remove', or 'edit'.
            member_email (str): Email of the member (required for remove/edit).
            member_data (dict): Data for adding/editing (e.g., {'email':.., 'username':.., 'role':..}).
        Returns: bool: True if successful, False otherwise.
        """
        if not self.organization_id:
            print(f"Error: OConvener {self.email} has no assigned organization."); return False

        print(f"OConvener {self.email} managing members for org {self.organization_id}. Action: {action}")
        # Use User's static method to get the users collection
        users_collection = User._get_collection()

        # --- ADD MEMBER ---
        if action == 'add':
            if not member_data or not member_data.get('email'):
                print("Error: Member data with email required for adding."); return False
            new_member_email = member_data['email'].strip().lower() # Normalize email

            # Validate email format
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", new_member_email):
                print(f"Error: Invalid email format for {new_member_email}.")
                # flash an error message from the route instead?
                return False

            # Check if user exists by email
            existing_user_doc = users_collection.find_one({"email": new_member_email})

            if existing_user_doc:
                # User exists, check their organization status
                existing_org_id = existing_user_doc.get('organization_id')
                if existing_org_id == self.organization_id:
                    print(f"Error: User {new_member_email} already in this organization.")
                    # Consider returning a specific error code or message for the route to flash
                    return False
                elif existing_org_id is not None:
                    print(f"Error: User {new_member_email} belongs to another organization ({existing_org_id}).")
                    return False
                else:
                     # --- Add existing user (without org) to this organization ---
                    print(f"Associating existing user {new_member_email} with org {self.organization_id}")
                    try:
                        # --- MODIFIED: Prepare update fields from member_data ---
                        update_fields = {
                            "organization_id": self.organization_id,
                            "organization_name": self.organization_name,
                            "last_updated_at": datetime.now(timezone.utc)
                        }
                        if 'user_role' in member_data:
                            update_fields['user_role'] = member_data['user_role']
                        if 'access_right' in member_data: # Expecting a list of ints
                            update_fields['access_right'] = member_data['access_right']
                        if 'membership_fee' in member_data: # Add membership fee
                            update_fields['membership_fee'] = member_data['membership_fee']
                        if 'username' in member_data and member_data['username']: # Update username if provided
                             update_fields['username'] = member_data['username']

                        update_result = users_collection.update_one(
                            {"_id": existing_user_doc["_id"]}, # Use existing user's string _id
                            {"$set": update_fields}
                        )
                        # --- END MODIFIED ---

                        if update_result.modified_count > 0:
                            ActivityRecord(
                                userAccount=self.email,
                                activityName="Member Added (Existing User)",
                                details=f"Org:{self.organization_id}, Member:{new_member_email}"
                            ).addRecord()
                            return True
                        else:
                            print(f"Failed to associate existing user {new_member_email} (no changes made).")
                            return False
                    except Exception as e:
                        print(f"DB Error associating existing user: {e}")
                        ActivityRecord(userAccount=self.email, activityName="Member Add Existing Failed - DB Error", details=str(e)).addRecord()
                        return False
            else:
                 # --- Create a new user record ---
                 print(f"Creating new user {new_member_email} for org {self.organization_id}")
                 # --- MODIFIED: Create User instance with data from member_data ---
                 new_user = User(
                     email=new_member_email,
                     username=member_data.get('username'), # Get username from member_data
                     user_role=member_data.get('user_role', User.ROLE_PUBLIC_CONSUMER), # Get role
                     access_right=member_data.get('access_right', [User.ACCESS_PUBLIC]) # Get access rights list
                 )
                 new_user_dict = new_user.to_dict() # Ensure User.to_dict() includes role & access_right
                 new_user_dict["organization_id"] = self.organization_id
                 new_user_dict["organization_name"] = self.organization_name
                 if 'membership_fee' in member_data: # Add membership fee
                      new_user_dict['membership_fee'] = member_data['membership_fee']
                 now = datetime.now(timezone.utc)
                 new_user_dict["created_at"] = now
                 new_user_dict["last_updated_at"] = now
                 # --- END MODIFIED ---

                 try:
                     result = users_collection.insert_one(new_user_dict)
                     if users_collection.count_documents({"_id": new_user._id}, limit=1) > 0:
                          ActivityRecord(userAccount=self.email, activityName="Member Added (New User)", details=f"Org:{self.organization_id}, Member:{new_member_email}, ID:{new_user._id}").addRecord()
                          return True
                     else:
                          print(f"DB Insert for {new_member_email} reported success but verification failed.")
                          return False
                 except Exception as e:
                     print(f"DB Error creating new user {new_member_email}: {e}")
                     ActivityRecord(userAccount=self.email, activityName="Member Add New Failed - DB Error", details=str(e)).addRecord()
                     return False

        # --- REMOVE MEMBER ---
        elif action == 'remove':
            if not member_email:
                print("Error: Member email required for removal."); return False
            target_email = member_email.strip().lower()

            print(f"Removing member {target_email} association from org {self.organization_id}")
            try:
                # Find the user who belongs to THIS organization by email
                member_doc = users_collection.find_one({
                    "email": target_email,
                    "organization_id": self.organization_id # Ensure they are in *this* org
                })

                if not member_doc:
                    print(f"Error: Member {target_email} not found in organization {self.organization_id}."); return False

                # Unset organization fields using the member's string _id
                update_result = users_collection.update_one(
                     {"_id": member_doc["_id"]},
                     {"$unset": {
                         "organization_id": "",
                         "organization_name": ""
                        },
                      "$set": { # Also update timestamp
                         "last_updated_at": datetime.now(timezone.utc)
                        }
                     }
                 )
                if update_result.modified_count > 0:
                    ActivityRecord(userAccount=self.email, activityName="Member Removed", details=f"Org:{self.organization_id}, Member:{target_email}").addRecord()
                    return True
                else:
                    print(f"Failed to remove org association for {target_email} (no changes made or DB error)."); return False
            except Exception as e:
                print(f"DB Error removing member {target_email}: {e}")
                ActivityRecord(userAccount=self.email, activityName="Member Remove Failed - DB Error", details=str(e)).addRecord()
                return False

        # --- EDIT MEMBER ---
        elif action == 'edit':
            if not member_email or not member_data:
                 print("Error: Member email and data required for editing."); return False
            target_email = member_email.strip().lower()

            print(f"Editing member {target_email} in org {self.organization_id}")
            try:
                # Find the user object within this organization
                # We need the object to use its validation/save logic via setters
                member_obj = User.find_by_email(target_email)

                # Verify the found user belongs to this OConvener's organization
                # Fetch fresh doc data to check org_id, as find_by_email creates an object
                # which might not have all fields if they were added later via direct update
                member_doc = users_collection.find_one({"_id": member_obj._id}) if member_obj else None
                if not member_obj or not member_doc or member_doc.get('organization_id') != self.organization_id:
                     print(f"Error: Member {target_email} not found in organization {self.organization_id}."); return False

                # Apply changes using User's setter methods (they handle save and logging)
                update_made = False
                if 'username' in member_data:
                     result_code = member_obj.set_username(member_data['username'], performed_by=self) # Pass self as performer
                     if result_code == "USERNAME_SET_SUCCESS": update_made = True
                     # Optionally handle specific errors from setter, e.g., flash message

                if 'access_right' in member_data:
                    # Check if OConvener has permission to change rights before calling
                    # For now, assume they can, but this needs business logic validation
                    print(f"Attempting to set access rights for {target_email} to {member_data['access_right']}")
                    result_code = member_obj.set_access_right(member_data['access_right'], performed_by=self)
                    if result_code == "ACCESS_RIGHT_UPDATED": update_made = True
                    else: print(f"Failed to set access right: {result_code}")

                # Add other editable fields here, using their respective setters
                # e.g., if 'user_role' can be edited by OConvener (check permissions!)
                # if 'user_role' in member_data:
                #    result_code = member_obj.set_user_role(member_data['user_role'], performed_by=self) # Might fail on permission
                #    if result_code == "USER_ROLE_UPDATED": update_made = True

                if update_made:
                    # Logging for edit action (individual setters already log their specific changes)
                    ActivityRecord(userAccount=self.email, activityName="Member Edit Initiated", details=f"Org:{self.organization_id}, Member:{target_email}, Data:{member_data}").addRecord()
                    print(f"Member {target_email} edited successfully (individual changes logged by setters).")
                else:
                    print(f"No valid or permitted updates applied for member {target_email}.")
                return update_made # Return True if at least one valid change was saved

            except Exception as e:
                print(f"Error editing member {target_email}: {e}")
                ActivityRecord(userAccount=self.email, activityName="Member Edit Failed", details=str(e)).addRecord()
                return False
        else:
            print(f"Error: Unknown manageMember action '{action}'"); return False

    # --- Other OConvener Methods ---
    # (setFunctionAvailability, getWorkspaceLog, setOrganization, getOrganization
    #  should already have correct DB logic using string IDs from previous response)

    def setFunctionAvailability(self, service_name: str, is_available: bool) -> bool:
        """Enables/disables services for the organization using string organization_id."""
        if not self.organization_id: print(f"Error: OConvener {self.email} has no assigned organization."); return False
        org_collection = mongo.db.organizations
        try:
            update_result = org_collection.update_one({"_id": self.organization_id}, {"$set": {f"available_services.{service_name}": is_available}})
            if update_result.matched_count > 0:
                ActivityRecord(userAccount=self.email, activityName="Service Availability Changed", details=f"Org:{self.organization_id}, Svc:{service_name}, Status:{is_available}").addRecord()
                return True
            else: print(f"Error: Organization {self.organization_id} not found."); return False
        except Exception as e: print(f"DB Error setting function availability: {e}"); return False

    def getWorkspaceLog(self, page: int = 1, limit: int = 15) -> tuple[list, int]:
        if not self.organization_id:
            print(f"Error: OConvener {self.email} has no assigned organization.")
            return [], 0

        log_collection = mongo.db.activity_log
        users_collection = User._get_collection()
        logs_for_page = []
        total_logs_count = 0

        member_emails = [member['email'] for member in users_collection.find(
            {"organization_id": self.organization_id},
            {"email": 1})
        ]
        member_emails.append(self.email)
        query = {"userAccount": {"$in": member_emails}}
        total_logs_count = log_collection.count_documents(query)

        skip_value = (page - 1) * limit
        if skip_value < 0: 
            skip_value = 0
        logs_cursor = log_collection.find(query).sort([("activityTime", -1), ("_id", -1)]).skip(skip_value).limit(limit)
        logs_for_page = list(logs_cursor)
        ActivityRecord(userAccount=self.email, activityName="Workspace Log Viewed", details=f"Org:{self.organization_id}, Page:{page}").addRecord()
        return logs_for_page, total_logs_count


    def setOrganization(self, organization_name: str = None) -> bool:
        """Updates the associated organization's name."""
        if not self.organization_id: print(f"Error: OConvener {self.email} has no organization assigned."); return False
        updates = {}
        if organization_name is not None: updates["organization_name"] = organization_name.strip()
        if not updates or updates["organization_name"] == self.organization_name: print("No organization details provided or name is unchanged."); return False
        old_org_name = self.organization_name; self.organization_name = updates["organization_name"]
        if not self.save(): print("Failed to save OConvener after updating org name."); self.organization_name = old_org_name; return False # Rollback
        org_collection = mongo.db.organizations; org_updates = {"name": updates["organization_name"]}
        try:
            org_result = org_collection.update_one({"_id": self.organization_id}, {"$set": org_updates})
            if org_result.matched_count == 0: print(f"Warning: Org record {self.organization_id} not found in organizations collection.")
        except Exception as e: print(f"Error updating organizations collection for {self.organization_id}: {e}"); return False # Consider rollback
        ActivityRecord(userAccount=self.email, activityName="Organization Metadata Set", details=f"Org:{self.organization_id}, Updates:{updates}").addRecord()
        return True

    def getOrganization(self) -> dict | None:
        """
        Returns details of the associated organization from the 'organizations' collection
        using the organization_id stored on the OConvener instance.
        """
        if not self.organization_id:
            # This OConvener user object itself doesn't have an organization_id assigned yet.
            # This might happen if EAdmin approval process didn't set it, or it's an older user.
            print(f"OConvener {self.email} (User ID: {self._id}) does not have an organization_id in their user record.")
            return None

        org_collection = mongo.db.organizations # Collection for organization entities
        try:
            # Fetch the organization document using the ID stored on the OConvener instance
            org_doc = org_collection.find_one({"_id": self.organization_id})

            if org_doc:
                # Ensure _id and convener_user_id are strings if they are ObjectIds, for consistency in templates
                if '_id' in org_doc and not isinstance(org_doc['_id'], str):
                    org_doc['_id'] = str(org_doc['_id'])
                if 'convener_user_id' in org_doc and org_doc.get('convener_user_id') and not isinstance(org_doc.get('convener_user_id'), str):
                    org_doc['convener_user_id'] = str(org_doc['convener_user_id'])
                return org_doc
            else:
                # The OConvener user has an organization_id, but no matching record in 'organizations' collection.
                # This means they need to complete the organization registration step.
                print(f"Organization record for ID '{self.organization_id}' (linked to OConvener {self.email}) not found in 'organizations' collection.")
                # Return a dictionary that at least contains the expected name and id
                # so the dashboard can still show "pending setup" and the "Register" button.
                # The template condition `if organization and organization._id` will evaluate to true if we return this.
                # To make the "Register" button appear, we need this to effectively be None or not have `_id`.
                # So, returning None is correct if the org is not yet in the 'organizations' table.
                return None
        except Exception as e:
            print(f"Error fetching organization details for ID '{self.organization_id}' (OConvener {self.email}): {e}")
            return None

    def registerOrganization(self) -> bool:
        """
        Finalizes organization setup in the 'organizations' collection.
        Uses self.organization_id and self.organization_name from the OConvener instance.
        """
        if not self.organization_id or not self.organization_name:
            print(f"Error: OConvener {self.email} is missing organization_id or organization_name for registration.")
            ActivityRecord(
                userAccount=self.email,
                activityName="Organization Registration Failed - Missing Details",
                details=f"OrgID: {self.organization_id}, OrgName: {self.organization_name}"
            ).addRecord()
            return False

        print(f"OConvener {self.email}: Attempting to register/update organization '{self.organization_name}' (ID: {self.organization_id}) in 'organizations' collection.")
        org_collection = mongo.db.organizations
        now = datetime.now(timezone.utc)
        try:
            # Use upsert=True to create if not exists, or update if it does.
            # This is important if an admin pre-creates an org shell, or if re-registering.
            org_data_to_set = {
                "name": self.organization_name,
                "convener_user_id": self._id, # Link to this OConvener's user ID
                "status": "active", # Set to active upon registration by O-Convener
                "last_updated_at": now
            }
            update_result = org_collection.update_one(
                {"_id": self.organization_id},
                {"$set": org_data_to_set,
                 "$setOnInsert": {"created_at": now, "_id": self.organization_id}}, # Set created_at only on insert
                upsert=True
            )

            if update_result.matched_count > 0 or update_result.upserted_id:
                print(f"Organization record '{self.organization_name}' (ID: {self.organization_id}) successfully saved/updated in 'organizations' collection.")
                ActivityRecord(
                    userAccount=self.email,
                    activityName="Organization Registered/Updated",
                    details=f"OrgID: {self.organization_id}, Name: {self.organization_name}"
                ).addRecord()
                return True
            else:
                # This case should be rare with upsert=True if no exception occurred
                print(f"Organization record {self.organization_id} - No change made by update_one (upsert).")
                return False
        except Exception as e:
            print(f"DB Error during organization registration/update for ID {self.organization_id}: {e}")
            ActivityRecord(
                userAccount=self.email,
                activityName="Organization Registration DB Error",
                details=f"OrgID: {self.organization_id}, Error: {str(e)}"
            ).addRecord()
            return False
    
    def __repr__(self):
        """Custom string representation for OConvener"""
        org_info = f", Org: {self.organization_name} ({self.organization_id})" if self.organization_id else ""
        return f"<OConvener email='{self.email}' id='{self._id}'{org_info}>" # Use string _id]\