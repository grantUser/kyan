import binascii
import functools
import json
import re

import requests
from flask import Blueprint, Response, abort, g, jsonify, request, url_for

from kyan import backend, forms, models
from kyan.extensions import cache
from kyan.views.torrents import _create_upload_category_choices

api_blueprint = Blueprint("api", __name__, url_prefix="/api")

# API HELPERS


def basic_auth_user(f):
    @functools.wraps(f)
    def decorator(*args, **kwargs):
        auth = request.authorization
        if auth:
            user = models.User.by_username_or_email(auth.get("username"))
            if user and user.validate_authorization(auth.get("password")):
                g.user = user
        return f(*args, **kwargs)

    return decorator


def api_require_user(f):
    @functools.wraps(f)
    def decorator(*args, **kwargs):
        if g.user is None:
            return jsonify({"errors": ["Bad authorization"]}), 403
        return f(*args, **kwargs)

    return decorator


# API ROUTES

UPLOAD_API_FORM_KEYMAP = {
    "torrent_file": "torrent",
    "display_name": "name",
    "is_anonymous": "anonymous",
    "is_hidden": "hidden",
    "is_complete": "complete",
    "is_remake": "remake",
    "is_trusted": "trusted",
}
UPLOAD_API_FORM_KEYMAP_REVERSE = {v: k for k, v in UPLOAD_API_FORM_KEYMAP.items()}
UPLOAD_API_DEFAULTS = {
    "name": "",
    "category": "",
    "anonymous": False,
    "hidden": False,
    "complete": False,
    "remake": False,
    "trusted": True,
    "information": "",
    "description": "",
}


@api_blueprint.route("/upload", methods=["POST"])
@api_blueprint.route("/v2/upload", methods=["POST"])
@basic_auth_user
@api_require_user
def v2_api_upload():
    mapped_dict = {"torrent_file": request.files.get("torrent")}

    request_data_field = request.form.get("torrent_data")
    if request_data_field is None:
        return jsonify({"errors": ["missing torrent_data field"]}), 400

    try:
        request_data = json.loads(request_data_field)
    except json.decoder.JSONDecodeError:
        return jsonify({"errors": ["unable to parse valid JSON in torrent_data"]}), 400

    for key, default in UPLOAD_API_DEFAULTS.items():
        mapped_key = UPLOAD_API_FORM_KEYMAP_REVERSE.get(key, key)
        value = request_data.get(key, default)
        mapped_dict[mapped_key] = value if value is not None else default

    upload_form = forms.UploadForm(None, data=mapped_dict, meta={"csrf": False})
    upload_form.category.choices = _create_upload_category_choices()

    if upload_form.validate():
        try:
            torrent = backend.handle_torrent_upload(upload_form, g.user)
            torrent_metadata = {
                "url": url_for("torrents.view", torrent_id=torrent.id, _external=True),
                "id": torrent.id,
                "name": torrent.display_name,
                "hash": torrent.info_hash.hex(),
                "magnet": torrent.magnet_uri,
            }
            return jsonify(torrent_metadata)
        except backend.TorrentExtraValidationException:
            pass

    mapped_errors = {
        UPLOAD_API_FORM_KEYMAP.get(k, k): v for k, v in upload_form.errors.items()
    }
    return jsonify({"errors": mapped_errors}), 400


@api_blueprint.route("/avatar/<string:username>", methods=["GET"])
@cache.cached(timeout=18000)
def gravatar_proxy(username):
    user = models.User.by_username(username)
    gravatar_url = user.gravatar_url()

    response = requests.get(gravatar_url)

    if response.status_code == 200:
        return Response(response.content, content_type=response.headers["Content-Type"])
    else:
        abort(404)


# INFO

ID_PATTERN = "^[0-9]+$"
INFO_HASH_PATTERN = "^[0-9a-fA-F]{40}$"


@api_blueprint.route("/info/<torrent_id_or_hash>", methods=["GET"])
@basic_auth_user
@api_require_user
def v2_api_info(torrent_id_or_hash):
    torrent_id_or_hash = torrent_id_or_hash.lower().strip()

    id_match = re.match(ID_PATTERN, torrent_id_or_hash)
    hex_hash_match = re.match(INFO_HASH_PATTERN, torrent_id_or_hash)

    torrent = None

    if id_match:
        torrent = models.Torrent.by_id(int(torrent_id_or_hash))
    elif hex_hash_match:
        a2b_hash = binascii.unhexlify(torrent_id_or_hash)
        torrent = models.Torrent.by_info_hash(a2b_hash)
    else:
        return jsonify({"errors": ["Query was not a valid id or hash."]}), 400

    viewer = g.user

    if not torrent:
        return jsonify({"errors": ["Query was not a valid id or hash."]}), 400

    if torrent.deleted and not (viewer and viewer.is_superadmin):
        return jsonify({"errors": ["Query was not a valid id or hash."]}), 400

    submitter = None
    if not torrent.anonymous and torrent.user:
        submitter = torrent.user.username
    if torrent.user and (viewer == torrent.user or viewer.is_moderator):
        submitter = torrent.user.username

    files = {}
    if torrent.filelist:
        files = json.loads(torrent.filelist.filelist_blob.decode("utf-8"))

    torrent_metadata = {
        "submitter": submitter,
        "url": url_for("torrents.view", torrent_id=torrent.id, _external=True),
        "id": torrent.id,
        "name": torrent.display_name,
        "creation_date": torrent.created_time.strftime("%Y-%m-%d %H:%M UTC"),
        "hash_b32": torrent.info_hash_as_b32,
        "hash_hex": torrent.info_hash_as_hex,
        "magnet": torrent.magnet_uri,
        "main_category": torrent.main_category.name,
        "main_category_id": torrent.main_category.id,
        "sub_category": torrent.sub_category.name,
        "sub_category_id": torrent.sub_category.id,
        "information": torrent.information,
        "description": torrent.description,
        "stats": {
            "seeders": torrent.stats.seed_count,
            "leechers": torrent.stats.leech_count,
            "downloads": torrent.stats.download_count,
        },
        "filesize": torrent.filesize,
        "files": files,
        "is_trusted": torrent.trusted,
        "is_complete": torrent.complete,
        "is_remake": torrent.remake,
    }

    return jsonify(torrent_metadata), 200
