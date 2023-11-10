import logging
import string

from flask import Flask, flash, g, render_template, url_for
from flask_assets import Bundle
from markupsafe import Markup

from kyan import models
from kyan.api_handler import api_blueprint
from kyan.extensions import assets, cache, db, limiter
# from kyan.extensions import fix_paginate
from kyan.template_utils import bp as template_utils_bp
from kyan.utils import random_string
from kyan.views import register_views


def add_categories(categories, main_class, sub_class):
    for main_cat_name, sub_cat_names in categories:
        main_cat = main_class(name=main_cat_name)
        for i, sub_cat_name in enumerate(sub_cat_names):
            # Composite keys can't autoincrement, set sub_cat id manually (1-index)
            sub_cat = sub_class(id=i + 1, name=sub_cat_name, main_category=main_cat)
        db.session.add(main_cat)


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)

    # Don't refresh cookie each request
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False

    # Debugging
    if app.config["DEBUG"]:
        app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False
        app.logger.setLevel(logging.DEBUG)

        # Forbid caching
        @app.after_request
        def forbid_cache(response):
            response.headers[
                "Cache-Control"
            ] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        # Add a timer header to the requests when debugging
        import time

        @app.before_request
        def timer_before_request():
            g.request_start_time = time.time()

        @app.after_request
        def timer_after_request(response):
            response.headers["X-Timer"] = time.time() - g.request_start_time
            return response

    else:
        app.logger.setLevel(logging.WARNING)

    # Logging
    if "LOG_FILE" in app.config:
        from logging.handlers import RotatingFileHandler

        app.log_handler = RotatingFileHandler(
            app.config["LOG_FILE"], maxBytes=10000, backupCount=1
        )
        app.logger.addHandler(app.log_handler)

    # Log errors and display a message to the user in production mode
    if not app.config["DEBUG"]:

        @app.errorhandler(500)
        def internal_error(e):
            random_id = random_string(8, string.ascii_uppercase + string.digits)
            app.logger.error("Exception occurred! Unique ID: %s", random_id, exc_info=e)
            markup_source = " ".join(
                [
                    "<strong>An error occurred!</strong>",
                    "Debug information has been logged.",
                    f"Please pass along this ID: <kbd>{random_id}</kbd>",
                ]
            )
            flash(markup_source, "danger")
            return render_template("error.html"), 500

    # Enable the jinja2 do extension.
    app.jinja_env.add_extension("jinja2.ext.do")

    # Database
    # fix_paginate()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config.get(
        "SQLALCHEMY_DATABASE_URI", None
    )
    app.config["SQLALCHEMY_DATABASE_CHARSET"] = "utf8mb4"

    # Assets
    assets.init_app(app)
    assets._named_bundles = {}  # Hack to fix state carrying over in tests
    main_js = Bundle("js/main.js", filters="rjsmin", output="js/main.min.js")
    bs_js = Bundle(
        "js/bootstrap-select.js", filters="rjsmin", output="js/bootstrap-select.min.js"
    )
    assets.register("main_js", main_js)
    assets.register("bs_js", bs_js)

    # Blueprints
    app.register_blueprint(template_utils_bp)
    app.register_blueprint(api_blueprint)
    register_views(app)

    app.config[
        "DEFAULT_GRAVATAR_URL"
    ] = "https://api.dicebear.com/5.x/lorelei-neutral/png?seed=kyan"

    cache.init_app(app, config=app.config)
    limiter.init_app(app)

    db.init_app(app)
    with app.app_context():
        db.create_all()

        kyan_categories = [
            (
                "Anime",
                [
                    "Anime Music Video",
                    "English-translated",
                    "Non-English-translated",
                    "Raw",
                ],
            ),
            ("Audio", ["Lossless", "Lossy"]),
            ("Literature", ["English-translated", "Non-English-translated", "Raw"]),
            (
                "Live Action",
                [
                    "English-translated",
                    "Idol/Promotional Video",
                    "Non-English-translated",
                    "Raw",
                ],
            ),
            ("Pictures", ["Graphics", "Photos"]),
            ("Software", ["Applications", "Games"]),
        ]

        kyan_category_test = models.MainCategory.query.first()
        if not kyan_category_test:
            add_categories(kyan_categories, models.MainCategory, models.SubCategory)

            db.session.commit()

    return app
