import os
from datetime import timedelta

class Config:
    MONGO_URI = "mongodb://localhost:27017/EDBA"
    #MONGO_DB = "EDBA"
    SECRET_KEY = "114514"

    # set the lifetime for the session
    PERMENT_SESSION_LIFETIME = timedelta(days=7)

    # Ideal production time SMTP configuration
    # MAIL_SERVER = 'smtp.arianet.xyz'
    # MAIL_PORT = 587
    # MAIL_USE_TLS = True
    # MAIL_USERNAME = 'sys@arianet.xyz'
    # MAIL_PASSWORD = 'zxaulbtcqnlfcagg'
    # MAIL_DEFAULT_SENDER = ('E-DBA System', 'sys@arianet.xyz')

    # Test-purpose SMTP configuration
    MAIL_SERVER = 'localhost'
    MAIL_PORT = 1025
    MAIL_USERNAME = None
    MAIL_PASSWORD = None
    MAIL_USE_TLS = False
    MAIL_USE_SSL = False
    MAIL_DEFAULT_SENDER = {'E-DBA System', 'sys@arianet.xyz'}
    # Run test smtp daemon with following command:
    # `python -m aiosmtpd -n -l localhost:1025`

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads'))
    ALLOWS_EXTENTIONS = {"pdf"}
    