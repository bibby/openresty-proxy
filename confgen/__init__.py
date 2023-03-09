import logging
import os


def truthy(n):
    return str(n).lower().strip() not in ["0", "no", "false", "n"]


CONF_DIR = "/etc/nginx/conf.d"
CERT_DIR = "/etc/nginx/certs"

log_level = logging.INFO
environ = os.environ.get
user_log_level = environ("LOG_LEVEL", log_level)
if not isinstance(user_log_level, int):
    level = getattr(logging, str(user_log_level).upper(), None)
    if isinstance(level, int):
        log_level = level

logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)
