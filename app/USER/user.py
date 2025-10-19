import uuid 
from app.extensions import mongo # Correct import
import re
from datetime import datetime, timezone # Use timezone
from app.models.ActivityRecord import ActivityRecord
from app.models.UserQuestion import UserQuestion
class User:
    """User base class, using String UUID for _id."""
    # --- Constants ---
    # (Keep ROLE_* and ACCESS_* constants as before)
    ROLE_T_ADMIN = "T-Admin"
    ROLE_E_ADMIN = "E-Admin"
    ROLE_O_CONVENER = "O-Convener"
    ROLE_PRIVATE_PROVIDER = "PrivateDataProvider" 
    ROLE_PRIVATE_CONSUMER = "PrivateDataConsumer"
    ROLE_PUBLIC_CONSUMER = "PublicDataConsumer"
    VALID_ROLES = [ROLE_T_ADMIN, ROLE_E_ADMIN, ROLE_O_CONVENER, ROLE_PRIVATE_PROVIDER, ROLE_PRIVATE_CONSUMER, ROLE_PUBLIC_CONSUMER]
    ACCESS_PUBLIC = 1
    ACCESS_PRIVATE_CONSUME = 2
    ACCESS_PRIVATE_PROVIDE = 3
    VALID_ACCESS_RIGHTS = [ACCESS_PUBLIC, ACCESS_PRIVATE_CONSUME, ACCESS_PRIVATE_PROVIDE]

    # --- Initialization ---
    # _id is now expected to be a string (UUID) or None
    def __init__(self, email: str, username: str = None, user_role: str = ROLE_PUBLIC_CONSUMER,
                 access_right: list = None, _id: str = None, created_at: datetime = None,
                 last_updated_at: datetime = None, **kwargs):
        # If _id is None (new user), generate a string UUID
        self._id = _id if _id else str(uuid.uuid4()) # Generate string UUID
        self.email = email
        self.username = username if username else (email.split('@')[0] if '@' in email else email)
        self.user_role = user_role if user_role in self.VALID_ROLES else self.ROLE_PUBLIC_CONSUMER
        self.access_right = self._validate_access_rights(access_right if access_right is not None else [self.ACCESS_PUBLIC])
        self.created_at = created_at if created_at else datetime.now(timezone.utc)
        self.last_updated_at = last_updated_at if last_updated_at else self.created_at
        self._load_extra_data(kwargs)

    # --- Helpers ---
    def _load_extra_data(self, data):
        for key, value in data.items():
            if not hasattr(self, key): 
                setattr(self, key, value)
    
    @staticmethod
    def _get_collection():
        if mongo.db is None: 
            raise RuntimeError("MongoDB not initialized.")
        return mongo.db.USERS

    def _validate_access_rights(self, rights):
        # (Implementation remains the same as before)
        default_right = [self.ACCESS_PUBLIC]
        if not isinstance(rights, list): 
            return default_right
        valid_rights = sorted(list(set(r for r in rights if r in self.VALID_ACCESS_RIGHTS)))
        if not valid_rights: 
            return default_right
        is_consumer = getattr(self, 'user_role', None) in [self.ROLE_PUBLIC_CONSUMER, self.ROLE_PRIVATE_CONSUMER]
        if is_consumer and self.ACCESS_PRIVATE_PROVIDE in valid_rights:
            valid_rights.remove(self.ACCESS_PRIVATE_PROVIDE)
            if not valid_rights: 
                return default_right
        return valid_rights

    def to_dict(self):
        # Returns the dictionary representation, includes the string _id generated in __init__
        return {
            "_id": self._id, # Include the string _id
            "email": self.email, 
            "username": self.username, 
            "user_role": self.user_role,
            "access_right": self.access_right, 
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at
            
        }

    # --- DB Interaction ---
    def save(self):
        collection = self._get_collection()
        # Use a copy for modification before saving
        user_data = self.to_dict()
        now = datetime.now(timezone.utc)
        user_data['last_updated_at'] = now
        action = ""; log_details = ""

        # Determine if it's an update (check if doc with self._id exists)
        # or insert (doc doesn't exist or self._id was just generated)
        is_update = False
        if collection.count_documents({"_id": self._id}, limit=1) > 0:
            is_update = True

        try:
            if is_update: # Update existing document
                # Don't try to set _id during update
                update_data = {k: v for k, v in user_data.items() if k != '_id'}
                result = collection.update_one({"_id": self._id}, {"$set": update_data})
                if result.matched_count == 0: raise ValueError(f"User ID {self._id} not found for update.")
                if result.modified_count > 0:
                    action = "User Updated"; log_details = f"ID:{self._id}"
                    ActivityRecord(
                        userAccount=self.email, 
                        activityName=action, 
                        details=log_details
                    ).addRecord()
                    print(f"User '{self.email}' updated.")
                else: 
                    print(f"User '{self.email}' data unchanged.")
                return self._id
            else: 
                # Check email uniqueness before inserting
                if collection.find_one({"email": self.email}): 
                    raise ValueError(f"Email '{self.email}' exists.")
                user_data['created_at'] = now # Set created_at for new doc
                # The user_data already contains the generated string _id
                result = collection.insert_one(user_data)
                # Verify insertion using the known string ID
                if collection.count_documents({"_id": self._id}, limit=1) > 0:
                    action = "User Created"; log_details = f"ID:{self._id}"
                    ActivityRecord(
                        userAccount=self.email, 
                        activityName=action, 
                        details=log_details
                    ).addRecord()
                    print(f"User '{self.email}' created with ID: {self._id}")
                    return self._id
                else:
                    raise RuntimeError("Insert operation failed unexpectedly.") # Should not happen if insert_one doesn't raise error

        except Exception as e:
            error_action = "User Update Failed" if is_update else "User Creation Failed"
            print(f"{error_action} for '{self.email}': {e}")
            ActivityRecord(
                userAccount=self.email, 
                activityName=f"{error_action} - DB Error", 
                details=str(e)
            ).addRecord()
            return None #


    @classmethod
    def from_document(cls, doc):
        if not doc: return None
        role = doc.get('user_role')
        target_cls = cls # Default to base class
        # Add subclass logic here if TAdmin, EAdmin inherit User
        # e.g., if role == cls.ROLE_T_ADMIN: target_cls = TAdmin
        try:
            return target_cls(
                _id=doc.get('_id'), # Expecting string _id from DB
                email=doc.get('email'), username=doc.get('username'),
                user_role=role, access_right=doc.get('access_right'), created_at=doc.get('created_at'),
                last_updated_at=doc.get('last_updated_at'),
                **{k: v for k, v in doc.items() if k not in ['_id', 'email', 'username', 'user_role', 'access_right', 'created_at', 'last_updated_at']}
            )
        except Exception as e: print(f"Error creating User from doc: {e}"); return None


    @classmethod
    def find_by_id(cls, user_id: str): # Expect user_id to be a string
        """Finds a user by their string UUID (_id)."""
        if not isinstance(user_id, str):
             print(f"Error: find_by_id expects a string ID, got {type(user_id)}")
             return None
        collection = cls._get_collection()
        try:
            # Query using the string _id directly
            doc = collection.find_one({"_id": user_id})
            return cls.from_document(doc)
        except Exception as e:
            print(f"Error finding user by ID '{user_id}': {e}")
            return None

    @classmethod
    def find_by_email(cls, email: str):
        # (Implementation remains the same, queries by email)
        if not email or not isinstance(email, str): 
            return None
        collection = cls._get_collection()
        try:
            doc = collection.find_one({"email": email})
            return cls.from_document(doc)
        except Exception as e: print(f"Error finding user by email '{email}': {e}"); return None

    # --- Core Methods (login, logout, seekHelp) ---
    def login(self): # Symbolic
        ActivityRecord(userAccount=self.email, activityName="Login Process Initiated").addRecord()
        return self

    def logout(self): # Symbolic
        ActivityRecord(userAccount=self.email, activityName="Logout Action Triggered").addRecord()
        return "LOGOUT_SUCCESS"

    def seekHelp(self, question_content: str) -> str:
         if not question_content or not isinstance(question_content, str) or not question_content.strip():
              ActivityRecord(userAccount=self.email, activityName="Seek Help Failed - Empty Content").addRecord()
              return "HELP_REQUEST_FAILED_EMPTY"
         # Ensure UserQuestion can be imported
         try:
             user_question = UserQuestion(user_account=self.email, question=question_content.strip())
             if user_question.raiseQuestion():
                 return "HELP_REQUEST_SUBMITTED"
             else:
                 return "HELP_REQUEST_FAILED_DB"
         except NameError: # If UserQuestion dummy was used
             print("Error: UserQuestion model not available for seekHelp.")
             return "HELP_REQUEST_FAILED_MISSING_MODEL"


    # --- Getters/Setters ---
    # (These methods remain logically the same, ensure they call the modified save() )
    def get_email(self) -> str: 
        return self.email
    
    def set_email(self, new_email: str, performed_by: 'User' = None) -> str:
        log_actor = performed_by.email if performed_by else self.email
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", new_email): return "INVALID_EMAIL_FORMAT"
        # Use classmethod for find_by_email
        existing_user = User.find_by_email(new_email)
        if existing_user and existing_user._id != self._id: 
            return "EMAIL_ALREADY_EXISTS"
        
        old_email = self.email; self.email = new_email
        if self.save(): # Calls modified save
            ActivityRecord(
                userAccount=log_actor, 
                activityName="Email Changed", 
                details=f"Target:{self._id}, Old:{old_email}, New:{new_email}"
            ).addRecord()
            return "EMAIL_SET_SUCCESS"
        else: 
            self.email = old_email
            return "EMAIL_SET_FAILED_DB_ERROR"

    # ... (Implement get_username, set_username, get_access_right, set_access_right, get_user_role, set_user_role similarly, ensuring they call self.save()) ...
    def get_username(self) -> str: 
        return self.username
    def set_username(self, new_username: str, performed_by: 'User' = None) -> str:
        log_actor = performed_by.email if performed_by else self.email
        if not new_username or not new_username.strip(): 
            return "USERNAME_CANNOT_BE_EMPTY"
        old_username = self.username; self.username = new_username.strip()
        if self.save():
            ActivityRecord(userAccount=log_actor, activityName="Username Changed", details=f"Target:{self._id}, Old:{old_username}, New:{self.username}").addRecord()
            return "USERNAME_SET_SUCCESS"
        else: 
            self.username = old_username
            return "USERNAME_SET_FAILED_DB_ERROR"

    def get_access_right(self) -> list: 
        return self.access_right
    
    def set_access_right(self, new_rights: list, performed_by: 'User' = None) -> str:
        log_actor = performed_by.email if performed_by else self.email
        old_rights = self.access_right[:]
        validated_rights = self._validate_access_rights(new_rights)
        if not validated_rights: 
            return "INVALID_ACCESS_RIGHT"
        self.access_right = validated_rights
        if self.save():
            ActivityRecord(userAccount=log_actor, activityName="Access Right Updated", details=f"Target:{self._id}, Old:{old_rights}, New:{self.access_right}").addRecord()
            return "ACCESS_RIGHT_UPDATED"
        else: 
            self.access_right = old_rights
            return "ACCESS_RIGHT_SET_FAILED_DB_ERROR"

    def get_user_role(self) -> str: 
        return self.user_role
    
    def set_user_role(self, new_role: str, performed_by: 'User') -> str:
        if not performed_by or performed_by.user_role != self.ROLE_T_ADMIN:
            ActivityRecord(
                userAccount=performed_by.email if performed_by else '?', 
                activityName="Set User Role Failed - Permission Denied"
            ).addRecord()
            return "PERMISSION_DENIED"
        if new_role not in self.VALID_ROLES: 
            return "INVALID_USER_ROLE"
        old_role = self.user_role; self.user_role = new_role
        self.access_right = self._validate_access_rights(self.access_right)
        if self.save():
            ActivityRecord(
                userAccount=performed_by.email, 
                activityName="User Role Updated", 
                details=f"Target:{self.email}, Old:{old_role}, New:{new_role}"
            ).addRecord()
            return "USER_ROLE_UPDATED"
        else: 
            self.user_role = old_role
            return "USER_ROLE_SET_FAILED_DB_ERROR"


    # --- Representation & Comparison ---
    def __repr__(self):
        # Represent using the string _id
        return f"<User email='{self.email}' role='{self.user_role}' id='{self._id}'>"

    def __eq__(self, other) -> bool:
        # Compare based on string _id
        if isinstance(other, User):
            # Both _id must be strings and equal
            return isinstance(self._id, str) and isinstance(other._id, str) and self._id == other._id
        return False

    def __hash__(self) -> int:
        # Hash based on the string _id
        if isinstance(self._id, str):
             return hash(self._id)
        # Fallback for potentially unsaved object (though __init__ now assigns _id)
        return hash((self.email, self.created_at))