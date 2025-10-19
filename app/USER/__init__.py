from flask import Blueprint

user_bp = Blueprint(
    "user",
    __name__,
    template_folder='../template' # Points to src/app/template/
)

# Make sure this line exists ONLY if you created src/app/USER/routes.py
from . import routes
