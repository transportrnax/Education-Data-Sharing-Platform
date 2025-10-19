from flask import current_app
from datetime import datetime, timezone, timedelta
import random # For generating numerical CAPTCHA
import string   # For generating numerical CAPTCHA
from ...extensions import mongo
from ...models.ActivityRecord import ActivityRecord
from flask_mail import Message

# --- Constants for Verification Status ---
VERIFICATION_SUCCESS = "VERIFICATION_SUCCESS"
VERIFICATION_FAILED_INVALID = "VERIFICATION_FAILED_INVALID"
VERIFICATION_FAILED_DB_ERROR = "VERIFICATION_FAILED_DB_ERROR"
CODE_SENT_SUCCESS = "VERIFICATION_CODE_SENT" 
CODE_SEND_FAILED_EMAIL = "EMAIL_SEND_FAILED"
CODE_SEND_FAILED_DB = "CODE_SEND_FAILED_DB"

# Define the CAPTCHA collection name, consistent with your new app.py
CAPTCHA_COLLECTION_NAME = 'mail_verificationsl_verifications'

class VerificationService:
    """Handles logic related to generating, sending, and verifying email CAPTCHAs."""

    @staticmethod
    def _get_collection():
        """Returns the MongoDB collection for email CAPTCHAs."""
        return mongo.db[CAPTCHA_COLLECTION_NAME]

    @classmethod
    def create_and_send_code(cls, email: str, purpose: str = "general_verification") -> tuple[str, str, str | None]:
        """
        Generates, stores, and sends a 4-digit numerical CAPTCHA via email.

        Args:
            email (str): The recipient's email address.
            purpose (str): The purpose of the verification code (e.g., 'login', 'registration').
                           This helps in managing different types of codes if needed, though
                           the provided new app.py doesn't heavily use 'purpose' for storage structure.

        Returns:
            tuple: (status_code_string, message, verification_code or None)
        """
        # Generate 4-digit numerical CAPTCHA
        source = string.digits
        captcha_code = "".join(random.sample(source, 4))

        code_lifetime_config_key = 'VERIFICATION_CODE_LIFETIME'
        code_lifetime = current_app.config.get(code_lifetime_config_key, timedelta(minutes=5))
        if not isinstance(code_lifetime, timedelta): # Type check and fallback
            code_lifetime = timedelta(minutes=5)

        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + code_lifetime

        # Prepare record for MongoDB, similar to your new app.py
        # We include 'purpose' and 'created_at' for better record management,
        # and 'expires_at' for automatic cleanup or validation.
        captcha_record_data = {
            "email": email.lower(), # Store email in lowercase for case-insensitive lookup
            "captcha": captcha_code, # Storing the numerical code
            "expires_at": expires_at,
            "created_at": now_utc,
            "purpose": purpose # Useful for distinguishing login vs registration codes etc.
        }

        collection = cls._get_collection()
        record_id = None

        try:
            update_result = collection.update_one(
                {'email': email.lower()},  # Query condition based on email
                {'$set': captcha_record_data}, # Data to insert or update
                upsert=True  # Create a new document if no match is found
            )
            
            if update_result.upserted_id:
                record_id = update_result.upserted_id
                print(f"New CAPTCHA record created for {email}, purpose: {purpose}, ID: {record_id}")
            elif update_result.matched_count > 0:
                # If an existing record was updated, we might not get a direct ID from update_result this way.
                # We can fetch the record if ID is strictly needed for logging here.
                # For now, successful update is sufficient.
                print(f"CAPTCHA record updated for {email}, purpose: {purpose}")


            # Create and send email using Flask-Mail
            mail_instance = current_app.extensions.get('mail')
            if not mail_instance:
                raise RuntimeError("Flask-Mail is not initialized.")

            # Email subject and body from your new app.py
            # You might want to customize subject/body based on 'purpose'
            email_subject = '邮箱验证码' # "Email Verification Code"
            email_body = f'您好，您的邮箱验证码是：{captcha_code}' # "Hello, your email verification code is: {captcha_code}"
            if purpose == "registration":
                 email_subject = "E-DBA Registration Verification Code"
                 email_body = f"Welcome to E-DBA! Your email verification code for registration is: {captcha_code}\nThis code will expire in {int(code_lifetime.total_seconds() / 60)} minutes."
            elif purpose == "login":
                 email_subject = "E-DBA Login Verification Code"
                 email_body = f"Your E-DBA login verification code is: {captcha_code}\nThis code will expire in {int(code_lifetime.total_seconds() / 60)} minutes."


            sender_email = current_app.config.get('MAIL_DEFAULT_SENDER')
            if not sender_email:
                raise ValueError("MAIL_DEFAULT_SENDER is not configured.")

            msg = Message(
                subject=email_subject,
                recipients=[email],
                body=email_body,
                sender=sender_email
            )
            mail_instance.send(msg)
            print(f"CAPTCHA email sent to {email} for {purpose}.")

            ActivityRecord(
                userAccount=email,
                activityName=f"CAPTCHA Code Sent ({purpose})",
                details=f"Email: {email}" # record_id might not be available if it's an update
            ).addRecord()
            return CODE_SENT_SUCCESS, f"Verification code for {purpose} sent successfully.", captcha_code

        except Exception as e:
            print(f"Error during CAPTCHA code creation/sending for {email}: {e}")
            ActivityRecord(
                userAccount=email,
                activityName=f"Send CAPTCHA Failed ({purpose})",
                details=str(e)
            ).addRecord()
            # Determine if it was an email or DB error for more specific status
            if isinstance(e, (RuntimeError, ValueError, ConnectionError)): # More specific email/config errors
                 return CODE_SEND_FAILED_EMAIL, f"Failed to send verification email: {str(e)}", None
            return CODE_SEND_FAILED_DB, f"Internal server error during code processing: {str(e)}", None


    @classmethod
    def verify_code(cls, email: str, code_to_verify: str, purpose: str = "general_verification") -> str:
        """
        Verifies an email CAPTCHA against the stored record.
        Deletes the record upon successful verification to prevent reuse.

        Args:
            email (str): The user's email address.
            code_to_verify (str): The CAPTCHA code submitted by the user.
            purpose (str): The purpose should ideally match for stricter validation,
                           though the new app.py's simple storage doesn't differentiate by purpose.
                           For robustness, we can include it in the query.

        Returns:
            str: Status code string (VERIFICATION_SUCCESS, VERIFICATION_FAILED_INVALID, VERIFICATION_FAILED_DB_ERROR).
        """
        if not email or not code_to_verify:
            return VERIFICATION_FAILED_INVALID

        collection = cls._get_collection()
        now_utc = datetime.now(timezone.utc)

        try:
            # Find the document. We will delete it if valid.
            # Query includes purpose for stricter matching if your upsert logic in create_and_send_code
            # also considers purpose for uniqueness. If not, querying by email and captcha is enough.
            # To match the simple upsert by email in your new app.py, we'd query by email and captcha.
            query = {
                "email": email.lower(),
                "captcha": code_to_verify,
                # "purpose": purpose, # Optional: add if you store purpose-specific codes
                "expires_at": {"$gt": now_utc} # Check expiry
            }
            captcha_doc = collection.find_one(query)

            if captcha_doc:
                # CAPTCHA is valid and not expired. Delete it to prevent reuse.
                collection.delete_one({"_id": captcha_doc["_id"]})
                ActivityRecord(
                    userAccount=email,
                    activityName=f"CAPTCHA Verified Successfully ({purpose})",
                    details=f"Record ID: {captcha_doc['_id']}"
                ).addRecord()
                return VERIFICATION_SUCCESS
            else:
                # Code not found, incorrect, or expired
                ActivityRecord(
                    userAccount=email,
                    activityName=f"CAPTCHA Verification Failed ({purpose}) - Invalid/Expired"
                ).addRecord()
                return VERIFICATION_FAILED_INVALID

        except Exception as e:
            print(f"Error during CAPTCHA verification for {email}: {e}")
            ActivityRecord(
                userAccount=email,
                activityName=f"CAPTCHA Verification Failed ({purpose}) - DB Error",
                details=str(e)
            ).addRecord()
            return VERIFICATION_FAILED_DB_ERROR
        





        <div class="search-container">
        <form action="{{ url_for('main.search') }}" method="get" class="search-box">
            <input type="text" name="query" placeholder="Search..." required>
            <button type="submit">Search</button>
        </form>
    </div>