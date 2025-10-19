import random
import string
import re
from datetime import datetime, timedelta, timezone
from flask_mail import Message
from flask import current_app
from app.extensions import mail, get_db


# Check if a given string is a valid Email address
def is_valid_email(email):
	return bool(re.compile(r"^[^@]+@[^@]+\.[^@]+$").match(email))


# Generate numerical verification code in fixed length
def generate_otp(length=6):
	return ''.join(random.choices(string.digits, k=length))


# Send OTP Email
def send_otp_email(to_email, otp_code):
	subject = "E-DBA Login Code"
	body = (f"Your login verification code is: {otp_code}\n"
	        f"This code expires after 5 minutes.")

	msg = Message(subject=subject,
	              sender=current_app.config['MAIL_USERNAME'],
	              recipients=[to_email],
	              body=body)
	mail.send(msg)

	return True


# Save OTP info to database
def store_otp(email, otp_code):
	db = get_db()
	expire_time = datetime.now(timezone.utc) + timedelta(minutes=5)
	db.OTP.update_one(
		{'email': email},
		{'$set': {
			'otp': otp_code,
			'expire_at': expire_time
		}},
		upsert=True
	)


# Verify OTP validity
def verify_otp(email, submitted_otp):
	db = get_db()
	record = db.OTP.find_one({'email': email})
	if not record:
		return False
	if record['otp'] != submitted_otp:
		return False
	if datetime.utcnow() > record['expire_at']:
		return False
	return True


# Clean used OTP
def clear_otp(email):
	db = get_db()
	db.OTP.delete_one({'email': email})