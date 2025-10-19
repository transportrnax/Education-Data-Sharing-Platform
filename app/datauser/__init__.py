from .models import *
from .routes import *
from .services import *
from flask import Blueprint

datauser_bp = Blueprint("datauser", __name__, url_prefix="/api/datauser")
public_bp = Blueprint("public", __name__, url_prefix="/api/public")
consumer_bp = Blueprint("consumer", __name__, url_prefix="/api/consumer")
mock_bp = Blueprint("mock", __name__, url_prefix="/mock")