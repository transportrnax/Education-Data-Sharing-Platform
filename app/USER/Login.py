from flask import Flask, request, jsonify, session
from datetime import datetime, timedelta, UTC
from ..extensions import mongo
from flask_mail import Message
from ..models.ActivityRecord import ActivityRecord
from app.USER.handle_utils import valid_email, generate_code, send_verification_email
from app.USER.user import User
#from handle_utils import send_verification_email
app = Flask(__name__)

class Login:

    CODE_EXPIRATION = timedelta(minutes=5)
    SEDN_INTERVAL = timedelta(seconds=60)
  
    @staticmethod
    def send_code_api(cls, email:str):
        '''
        handle send code request
        Frequency limit check(60 seconds), user search, 
        verification code generation/storage and email sending
        '''
        # check email format
        if not cls.valid_email(email):
            ActivityRecord(datetime.now(UTC), email,"Send Verification Code Failed").addRecord()
            return {"status": "INVALID_EMAIL_FORMAT", "message": "Invalid email format"}, 400
        
        user_obj = User.find_by_email(email)
        if not user_obj:
            ActivityRecord(userAccount=email, activityName="Send Login Code Failed - Not Registered").addRecord()
            return {"status": "EMAIL_NOT_REGISTERED", "message": "This email not register"}, 404 
        
        # search users
        users = User._get_collection() #这里需要建立user数据库还没建
        user = users.find_one({"_id": user_obj._id})

        if not user:
            ActivityRecord(
                datetime.now(UTC), 
                email, 
                "Send Code Attempt - Email Not Registered"
            ).addRecord()
            return {"status": "EMAIL_NOT_REGISTERED", "message": "This email address is not registered."}, 404
        
        # check frequency limit
        now = datetime.now(UTC)
        last_code_time = user.get("code_expires_at") #这里的last_sent是mongoDB中存上次code过期的时间字段根据后期实现修改

        if last_code_time:
            last_send = last_code_time - cls.CODE_EXPIRATION
            if now < last_send + cls.SEND_INTERVAL:
                wait_seconds = (last_send + cls.SEND_INTERVAL - now).total_seconds()
                ActivityRecord(
                    now, 
                    email, 
                    "Send Code Attempt - Too Frequent"
                ).addRecord()
                return {"status": "TOO_FREQUENT", "message": f"Request too frequent, please wait {wait_seconds:.0f}"}, 429
            
        # generate code
        verification_code = cls.generate_code()
        expires_at = now + cls.CODE_EXPIRATION

        # send code to user
        if not cls.send_code(email, verification_code):
            return {"status": "EMAIL_SEND_FAILED", "message": "Send email code failed"}, 500

        # update verification code and expires_at time
        try:
            users.update_one(
                {"_id": user["_id"]},
                {"$set": {
                    "verification_code": verification_code,
                    "code_expires_at": expires_at # timezone-aware datetime
                }}
            )
            ActivityRecord(
                now, 
                email, 
                "Verification Code Sent"
            ).addRecord()
            return {"status": "VERIFICATION_CODE_SENT", "message": "Verification code has sent!"}, 200
        except Exception as e:
            print(f"Error updating verification code in DB for {email}: {e}")
            ActivityRecord(
                now,
                email,
                "DB Update Failed After Email Sent",
                details=str(e)
            ).addRecord()
            return {"status": "INTERNAL_SERVER_ERROR", "message": "Wrong!"}, 500
        
    @classmethod
    def verify_code_api(cls, email: str, code: str):
        '''
        Handle the logic for verifying login verification codes and setting up sessions
        '''
        if not email or not code:
            return {"status": "MISSING_FIELDS", "message": "Email and code are required!"}, 400
        
        users = mongo.db.users
        now = datetime.now(UTC)

        user = users.find_one({
            "email": email,
            "verification_code": code,
            "code_expires_at": {"$gt": now}
        })

        if not user:
            ActivityRecord(
                now,
                email,
                "Login: Invalid/expired code"
            ).addRecord()
            return {"status": "INVALID_CODE", "message": "verification code invalid"}, 401
        
        try:
            users.update_one(
                {"id": user["id"]},
                {"$unset": {
                    "verification_code": "",
                    "code_expires_at": ""
                }}
            )
        except Exception as e:
            print(f"Error clearing verification code for {email} after successful login: {e}")
            ActivityRecord(
                now,
                email,
                "Login: Error updating user record: "
            ).addRecord()
        
        ActivityRecord(
            now, 
            email, 
            "Successful Login"
        ).addRecord()

        # successful login -> sessions
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['user_role'] = user.get('user_role', User.ROLE_PUBLIC_CONSUMER)
        session.permanent = True
        app.permanent_session_lifetime = timedelta(days=7) 
        return {"status": "LOGIN_SUCCESS", "message": "Successful Login!"}, 200