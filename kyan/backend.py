import json
import os
import re
from collections import OrderedDict
from datetime import datetime, timedelta
from ipaddress import ip_address

import sqlalchemy
from flask import current_app, request
from werkzeug.utils import secure_filename

from kyan import models, utils
from kyan.extensions import db

app = current_app

CHARACTER_BLACKLIST = ["\u202E"]  # RIGHT-TO-LEFT OVERRIDE

FILENAME_BLACKLIST = [
    "con",
    "nul",
    "prn",
    "aux",
    "com0",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt0",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
]

ILLEGAL_XML_CHARS_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]"
)


def sanitize_string(string, replacement="\uFFFD"):
    return ILLEGAL_XML_CHARS_RE.sub(replacement, string)


class TorrentExtraValidationException(Exception):
    def __init__(self, errors={}):
        self.errors = errors


@utils.cached_function
def get_category_id_map():
    cat_id_map = {}
    for main_cat in models.MainCategory.query:
        cat_id_map[main_cat.id_as_string] = [main_cat.name]
        for sub_cat in main_cat.sub_categories:
            cat_id_map[sub_cat.id_as_string] = [main_cat.name, sub_cat.name]
    return cat_id_map


def _replace_utf8_values(dict_or_list):
    did_change = False
    if isinstance(dict_or_list, dict):
        for key in [key for key in dict_or_list.keys() if key.endswith(".utf-8")]:
            new_key = key.replace(".utf-8", "")
            dict_or_list[new_key] = dict_or_list.pop(key)
            did_change = True
        for value in dict_or_list.values():
            did_change = _replace_utf8_values(value) or did_change
    elif isinstance(dict_or_list, list):
        for item in dict_or_list:
            did_change = _replace_utf8_values(item) or did_change
    return did_change


def _recursive_dict_iterator(source):
    for key, value in source.items():
        yield key, value
        if isinstance(value, dict):
            yield from _recursive_dict_iterator(value)


def _validate_torrent_filenames(torrent):
    file_tree = json.loads(torrent.filelist.filelist_blob.decode("utf-8"))
    for path_part, value in _recursive_dict_iterator(file_tree):
        base_name = path_part.rsplit(".", 1)[0].lower()
        if base_name in FILENAME_BLACKLIST or any(
            c in path_part for c in CHARACTER_BLACKLIST
        ):
            return False
    return True


def validate_torrent_post_upload(torrent, upload_form=None):
    errors = {"torrent_file": []}
    minimum_anonymous_torrent_size = app.config["MINIMUM_ANONYMOUS_TORRENT_SIZE"]
    if not torrent.user and torrent.filesize < minimum_anonymous_torrent_size:
        errors["torrent_file"].append("Torrent too small for an anonymous uploader")

    if not _validate_torrent_filenames(torrent):
        errors["torrent_file"].append("Torrent has forbidden characters in filenames")

    errors = {k: v for k, v in errors.items() if v}
    if errors:
        if upload_form:
            for field_name, field_errors in errors.items():
                getattr(upload_form, field_name).errors.extend(field_errors)
            upload_form._errors = None
        raise TorrentExtraValidationException(errors)


def check_uploader_ratelimit(user):
    now = datetime.utcnow()
    next_allowed_time = now

    Torrent = models.Torrent

    def filter_uploader(query):
        if user:
            return query.filter(
                sqlalchemy.or_(
                    Torrent.user == user,
                    Torrent.uploader_ip == ip_address(request.remote_addr).packed,
                )
            )
        else:
            return query.filter(
                Torrent.uploader_ip == ip_address(request.remote_addr).packed
            )

    time_range_start = now - timedelta(seconds=app.config["UPLOAD_BURST_DURATION"])
    torrent_count_query = db.session.query(sqlalchemy.func.count(Torrent.id))
    torrent_count = (
        filter_uploader(torrent_count_query)
        .filter(Torrent.created_time >= time_range_start)
        .scalar()
    )

    if torrent_count >= app.config["MAX_UPLOAD_BURST"]:
        last_torrent = (
            filter_uploader(Torrent.query).order_by(Torrent.created_time.desc()).first()
        )
        after_timeout = last_torrent.created_time + timedelta(
            seconds=app.config["UPLOAD_TIMEOUT"]
        )

        if now < after_timeout:
            next_allowed_time = after_timeout

    return now, torrent_count, next_allowed_time


def handle_torrent_upload(upload_form, uploading_user=None, fromAPI=False):
    torrent_data = upload_form.torrent_file.parsed_data
    no_or_new_account = not uploading_user or (
        uploading_user.age < app.config["RATELIMIT_ACCOUNT_AGE"]
        and not uploading_user.is_trusted
    )

    if app.config["RATELIMIT_UPLOADS"] and no_or_new_account:
        now, torrent_count, next_time = check_uploader_ratelimit(uploading_user)
        if next_time > now:
            upload_form.ratelimit.errors = ["You've gone over the upload ratelimit."]
            raise TorrentExtraValidationException()

    if not uploading_user:
        if app.config["RAID_MODE_LIMIT_UPLOADS"]:
            upload_form.rangebanned.errors = [app.config["RAID_MODE_UPLOADS_MESSAGE"]]
            raise TorrentExtraValidationException()
        elif models.RangeBan.is_rangebanned(ip_address(request.remote_addr).packed):
            upload_form.rangebanned.errors = [
                "Your IP is banned from uploading anonymously."
            ]
            raise TorrentExtraValidationException()

    if torrent_data.db_id is not None:
        old_torrent = models.Torrent.by_id(torrent_data.db_id)
        db.session.delete(old_torrent)
        db.session.commit()
        _delete_info_dict(old_torrent)

    info_dict = torrent_data.torrent_dict["info"]
    changed_to_utf8 = _replace_utf8_values(torrent_data.torrent_dict)
    display_name = (
        upload_form.display_name.data.strip()
        or info_dict["name"].decode("utf8").strip()
    )
    information = (upload_form.information.data or "").strip()
    description = (upload_form.description.data or "").strip()
    display_name = sanitize_string(display_name)
    information = sanitize_string(information)
    description = sanitize_string(description)

    torrent_filesize = info_dict.get("length") or sum(
        f["length"] for f in info_dict.get("files")
    )
    torrent_encoding = torrent_data.torrent_dict.get("encoding", b"utf-8").decode(
        "utf-8"
    )
    torrent = models.Torrent(
        id=torrent_data.db_id,
        info_hash=torrent_data.info_hash,
        display_name=display_name,
        torrent_name=torrent_data.filename,
        information=information,
        description=description,
        encoding=torrent_encoding,
        filesize=torrent_filesize,
        user=uploading_user,
        uploader_ip=ip_address(request.remote_addr).packed,
    )
    info_dict_path = torrent.info_dict_path
    info_dict_dir = os.path.dirname(info_dict_path)
    os.makedirs(info_dict_dir, exist_ok=True)
    with open(info_dict_path, "wb") as out_file:
        out_file.write(torrent_data.bencoded_info_dict)
    torrent.stats = models.Statistic()
    torrent.has_torrent = True
    torrent.flags = 0
    torrent.anonymous = upload_form.is_anonymous.data if uploading_user else True
    torrent.hidden = upload_form.is_hidden.data
    torrent.remake = upload_form.is_remake.data
    torrent.complete = upload_form.is_complete.data
    can_mark_trusted = uploading_user and uploading_user.is_trusted
    torrent.trusted = upload_form.is_trusted.data if can_mark_trusted else False
    can_mark_locked = uploading_user and uploading_user.is_moderator
    torrent.comment_locked = (
        upload_form.is_comment_locked.data if can_mark_locked else False
    )
    (
        torrent.main_category_id,
        torrent.sub_category_id,
    ) = upload_form.category.parsed_data.get_category_ids()
    torrent_filelist = info_dict.get("files")
    used_path_encoding = changed_to_utf8 and "utf-8" or torrent_encoding
    parsed_file_tree = dict()
    if not torrent_filelist:
        file_tree_root = parsed_file_tree
        torrent_filelist = [{"length": torrent_filesize, "path": [info_dict["name"]]}]
    else:
        file_tree_root = parsed_file_tree.setdefault(
            info_dict["name"].decode(used_path_encoding), {}
        )
    for file_dict in torrent_filelist:
        path_parts = [
            path_part.decode(used_path_encoding) for path_part in file_dict["path"]
        ]
        filename = path_parts.pop()
        current_directory = file_tree_root
        for directory in path_parts:
            current_directory = current_directory.setdefault(directory, {})
        if filename:
            current_directory[filename] = file_dict["length"]
    parsed_file_tree = utils.sorted_pathdict(parsed_file_tree)
    json_bytes = json.dumps(parsed_file_tree, separators=(",", ":")).encode("utf8")
    torrent.filelist = models.TorrentFilelist(filelist_blob=json_bytes)
    db.session.add(torrent)
    db.session.flush()
    trackers = {}
    announce = torrent_data.torrent_dict.get("announce", b"").decode("ascii")
    if announce:
        trackers[announce] = None
    announce_list = torrent_data.torrent_dict.get("announce-list", [])
    for announce in announce_list:
        trackers[announce[0].decode("ascii")] = None
    webseed_list = torrent_data.torrent_dict.get("url-list") or []
    if isinstance(webseed_list, bytes):
        webseed_list = [webseed_list]
    webseeds = {webseed.decode("utf-8"): None for webseed in webseed_list}
    db_trackers = {}
    for announce in trackers:
        tracker = models.Trackers.by_uri(announce)
        if not tracker:
            tracker = models.Trackers(uri=announce)
            db.session.add(tracker)
            db.session.flush()
        elif tracker.is_webseed:
            tracker.is_webseed = False
            db.session.flush()
        db_trackers[tracker] = None
    for webseed_url in webseeds:
        webseed = models.Trackers.by_uri(webseed_url)
        if not webseed:
            webseed = models.Trackers(uri=webseed_url, is_webseed=True)
            db.session.add(webseed)
            db.session.flush()
        if webseed.is_webseed:
            db_trackers[webseed] = None
    for order, tracker in enumerate(db_trackers):
        torrent_tracker = models.TorrentTrackers(
            torrent_id=torrent.id, tracker_id=tracker.id, order=order
        )
        db.session.add(torrent_tracker)
    validate_torrent_post_upload(torrent, upload_form)
    db.session.add(models.TrackerApi(torrent.info_hash, "insert"))
    db.session.commit()
    torrent_file = upload_form.torrent_file.data
    if app.config.get("BACKUP_TORRENT_FOLDER"):
        torrent_file.seek(0, 0)
        torrent_dir = app.config["BACKUP_TORRENT_FOLDER"]
        os.makedirs(torrent_dir, exist_ok=True)
        torrent_path = os.path.join(
            torrent_dir,
            "{}.{}".format(torrent.id, secure_filename(torrent_file.filename)),
        )
        torrent_file.save(torrent_path)
    torrent_file.close()
    return torrent


def _delete_info_dict(torrent):
    info_dict_path = torrent.info_dict_path
    if os.path.exists(info_dict_path):
        os.remove(info_dict_path)
