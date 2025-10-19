# app/USER/registration_handler.py
from flask import current_app, jsonify
from datetime import datetime, timedelta, timezone
import os
import uuid # For generating unique filenames
from werkzeug.utils import secure_filename # For secure file uploads
from app.extensions import mongo
from app.USER.handle_utils import valid_email, generate_code, send_verification_email
from app.USER.user import User
from app.models.ActivityRecord import ActivityRecord
from .service.verification_service import VerificationService, CODE_SENT_SUCCESS, CODE_SEND_FAILED_EMAIL, CODE_SEND_FAILED_DB, VERIFICATION_SUCCESS, VERIFICATION_FAILED_INVALID, VERIFICATION_FAILED_DB_ERROR # <-- Import service

# --- Registration Status Constants ---
REG_STATUS_PENDING_EMAIL = "pending_email_verification"
REG_STATUS_PENDING_APPROVAL = "pending_admin_approval"
REG_STATUS_APPROVED = "approved"
REG_STATUS_REJECTED = "rejected"

# --- Helper function for file validation ---
def allowed_file(filename):
    # Get allowed extensions from config, default to {'pdf'} if not set
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'pdf'})
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

class RegistrationHandler:
    """Handles the business logic for O-Convener registration."""

    @classmethod
    def handle_complete_registration(cls, org_name: str, email: str, proof_file_storage, code: str):
        """
        Handles final registration submission: verifies code, saves file, creates application record.
        """
        # --- Basic Input Validation ---
        if not org_name or not org_name.strip() or not email or not proof_file_storage or not code:
            # Should be caught by route, but double-check
            return {"status": "MISSING_FIELDS", "message": "All fields and code are required."}, 400
        if not valid_email(email):
             return {"status": "INVALID_EMAIL_FORMAT", "message": "Invalid email format."}, 400
        if not proof_file_storage.filename or not allowed_file(proof_file_storage.filename):
            return {"status": "INVALID_FILE", "message": "Invalid or missing proof document (PDF required)."}, 400

        email_lower = email.strip().lower()

        # --- Verify Code First using VerificationService ---
        verification_status = VerificationService.verify_code(email_lower, code, purpose='registration')

        if verification_status != VERIFICATION_SUCCESS:
            # Code is invalid, expired, or DB error occurred during verification
            message = "Verification code is invalid or has expired." if verification_status == VERIFICATION_FAILED_INVALID else "An error occurred during code verification."
            status_code = 401 if verification_status == VERIFICATION_FAILED_INVALID else 500
            # Log failure (already logged by service, but maybe add context here?)
            ActivityRecord(userAccount=email_lower, activityName="Registration Complete Failed - Code Verify", details=f"Verification Status: {verification_status}").addRecord()
            return {"status": "VERIFICATION_FAILED", "message": message}, status_code

        # --- Code Verified - Proceed with Checks, File Upload, and Saving Application ---

        # Re-check if user/app exists *just in case* one was created between sending code and now
        if User.find_by_email(email_lower):
             ActivityRecord(userAccount=email_lower, activityName="Reg Complete Failed - Email Exists Now").addRecord()
             return {"status": "EMAIL_ALREADY_EXISTS", "message": "Email registered while verifying code."}, 409
        reg_collection = mongo.db.registration_applications
        if reg_collection.find_one({"email": email_lower, "status": {"$nin": [REG_STATUS_REJECTED]}}):
             ActivityRecord(userAccount=email_lower, activityName="Reg Complete Failed - Pending App Exists Now").addRecord()
             return {"status": "APPLICATION_ALREADY_PENDING", "message": "Application submitted while verifying code."}, 409

        # --- Handle File Upload (as before, maybe use subdirs) ---
        stored_proof_filename = None
        file_path = None
        try:
            filename = secure_filename(proof_file_storage.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER', './uploads')
            if not os.path.exists(upload_folder): os.makedirs(upload_folder)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(upload_folder, unique_filename)
            proof_file_storage.save(file_path)
            stored_proof_filename = unique_filename # Store only unique name now
            print(f"Proof document saved: {stored_proof_filename}")
        except Exception as e:
            print(f"Error saving proof file for {email_lower} during completion: {e}")
            ActivityRecord(userAccount=email_lower, activityName="Reg Complete Failed - File Upload Error", details=str(e)).addRecord()
            # Note: Code was already verified and consumed. This is an inconsistent state.
            # Maybe try to re-issue code? Or just report error? Reporting error is simpler.
            return {"status": "FILE_UPLOAD_ERROR", "message": "Failed to upload proof document after code verification."}, 500

        # --- Save FINAL Application Record ---
        # Status is now directly 'pending_admin_approval' because email is verified
        now_utc = datetime.now(timezone.utc)
        application_data = {
            "org_name": org_name.strip(),
            "email": email_lower,
            "proof_document": stored_proof_filename,
            "status": REG_STATUS_PENDING_APPROVAL, # Email verified, now pending admin
            "submitted_at": now_utc,
            "email_verified_at": now_utc # Add timestamp for email verification
        }
        try:
            reg_collection.delete_many({"email": email_lower, "status": REG_STATUS_REJECTED}) # Clean old rejected
            result = reg_collection.insert_one(application_data)
            application_id = result.inserted_id
            ActivityRecord(
                userAccount=email_lower,
                activityName="Registration Completed",
                details=f"App ID: {application_id}, Status: {REG_STATUS_PENDING_APPROVAL}"
            ).addRecord()
            # Notify user application is pending admin review
            return {"status": "REGISTRATION_SUCCESS", "message": "Registration complete! Your application is pending administrator approval.", "application_id": str(application_id)}, 201 # Created
        except Exception as e:
            print(f"Error saving final registration application for {email_lower}: {e}")
            ActivityRecord(userAccount=email_lower, activityName="Reg Complete Failed - DB Error", details=str(e)).addRecord()
            # Code verified, file saved, but DB failed. Inconsistent state!
            # Cleanup file? Difficult to recover automatically.
            return {"status": "INTERNAL_SERVER_ERROR", "message": "Failed to save registration application after verification."}, 500
