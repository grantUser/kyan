import os.path

import yaml
from flask.config import Config
from flask_assets import Environment
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

assets = Environment()
db = SQLAlchemy(engine_options={"pool_recycle": 3600})
cache = Cache()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)


class LimitedPagination:
    def __init__(self, query, page, per_page, total, items):
        self.query = query
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items


def _get_config():
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config = Config(root_path)

    yaml_config_file = "config.yaml"
    if os.path.exists(yaml_config_file):
        with open(yaml_config_file, "r") as file:
            yaml_config_data = yaml.safe_load(file)
            config.update(yaml_config_data)

    return config


config = _get_config()
