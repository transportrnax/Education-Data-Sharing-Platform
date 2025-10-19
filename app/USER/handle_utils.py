import re
import random
from flask import current_app
from flask_mail import Message
#from app.extensions import mail
from app.models.ActivityRecord import ActivityRecord
from datetime import datetime, timezone, UTC, timedelta

@staticmethod
def valid_email(email: str) -> bool:
    # check if email is valid
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z-]+\.[a-zA-Z-.]+$"
    return re.match(pattern, email) is not None
    
@staticmethod
def generate_code() -> str:
    # generate random code
    return str(random.randint(100000, 999999))
    
@staticmethod
def send_verification_email(email: str, code: str, purpose: str = "login") -> bool:
    if not current_app:
        print("Error: Attempted to send email outside of Flask application context.")
        return False
    
    mail = current_app.extensions.get('mail')
    try:
        sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        code_lifetime_config_key = 'VERIFICATION_CODE_LIFETIME' if 'VERIFICATION_CODE_LIFETIME' in current_app.config else 'PERMANENT_SESSION_LIFETIME'
        code_lifetime = current_app.config.get(code_lifetime_config_key, timedelta(minutes=5))
        if not isinstance(code_lifetime, timedelta): # 添加类型检查和回退
            print(f"Warning: Invalid timedelta format for {code_lifetime_config_key}. Using default 5 minutes.")
            code_lifetime = timedelta(minutes=5)
        expiration_minutes = code_lifetime.total_seconds() / 60


        if purpose == "registration":
            subject = "verification code for E-DBA registration"
            body = f"Welcome to register for E-DBA! Your email verification code is {code}\nThis verification code will be valid within {expiration_minutes:.0f} minutes."
        else: 
            subject = "Your E-DBA login verification code"
            body = f"Your login verification code is: {code}\nThis verification code will be valid within  {expiration_minutes:.0f} minutes"

        if not sender:
            print("Error: MAIL_DEFAULT_SENDER not configured.")
            return False

        msg = Message(subject=subject, recipients=[email], body=body, sender=sender)
        mail.send(msg)
        print(f"{purpose.capitalize().replace('_', ' ')} verification email sent to {email}")
        return True
    except Exception as e:
        print(f"!!! Failed to send {purpose} verification email to {email}: {str(e)}")
        
        try:
            ActivityRecord(
                userAccount=email, 
                activityName=f"Send {purpose.capitalize()} Email Failed",
                details=str(e),     
            ).addRecord()
        except Exception as log_e:
             print(f"Failed to log email sending error: {log_e}")
        return False