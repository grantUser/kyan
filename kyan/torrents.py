import functools
import os
from urllib.parse import quote, urlencode

from flask import current_app as app
from flask import url_for

from kyan import bencode

USED_TRACKERS = {}


def read_trackers_from_file(file_object):
    USED_TRACKERS.clear()

    for line in file_object:
        line = line.strip()
        if line and not line.startswith("#"):
            USED_TRACKERS[line] = None
    return USED_TRACKERS


def read_trackers():
    tracker_list_file = os.path.join(app.config["BASE_DIR"], "trackers.txt")

    if os.path.exists(tracker_list_file):
        with open(tracker_list_file, "r") as in_file:
            return read_trackers_from_file(in_file)


def default_trackers():
    if not USED_TRACKERS:
        read_trackers()
    return list(USED_TRACKERS)


def get_trackers_and_webseeds(torrent):
    trackers = {}
    webseeds = {}

    main_announce_url = app.config.get("MAIN_ANNOUNCE_URL")
    if main_announce_url:
        trackers[main_announce_url] = None

    torrent_trackers = torrent.trackers
    for torrent_tracker in torrent_trackers:
        tracker = torrent_tracker.tracker

        if tracker.is_webseed:
            webseeds[tracker.uri] = None
        else:
            trackers[tracker.uri] = None

    trackers.update(default_trackers())

    return list(trackers), list(webseeds)


def get_default_trackers():
    trackers = {}

    main_announce_url = app.config.get("MAIN_ANNOUNCE_URL")
    if main_announce_url:
        trackers[main_announce_url] = None

    trackers.update(default_trackers())

    return list(trackers)


@functools.lru_cache(maxsize=1024 * 4)
def _create_magnet(display_name, info_hash, max_trackers=5, trackers=None):
    if trackers is None:
        trackers = get_default_trackers()

    magnet_parts = [("dn", display_name)]
    magnet_parts.extend(("tr", tracker_url) for tracker_url in trackers[:max_trackers])

    return "".join(
        [
            "magnet:?xt=urn:btih:",
            info_hash,
            "&",
            urlencode(magnet_parts, quote_via=quote),
        ]
    )


def create_magnet(torrent):
    info_hash = torrent.info_hash
    if isinstance(info_hash, (bytes, bytearray)):
        info_hash = info_hash.hex()

    return _create_magnet(torrent.display_name, info_hash)


def create_default_metadata_base(torrent, trackers=None, webseeds=None):
    if trackers is None or webseeds is None:
        db_trackers, db_webseeds = get_trackers_and_webseeds(torrent)

        trackers = db_trackers if trackers is None else trackers
        webseeds = db_webseeds if webseeds is None else webseeds

    metadata_base = {
        "created by": "kyan",
        "creation date": int(torrent.created_utc_timestamp),
        "comment": url_for("torrents.view", torrent_id=torrent.id, _external=True),
    }

    if len(trackers) > 0:
        metadata_base["announce"] = trackers[0]
    if len(trackers) > 1:
        metadata_base["announce-list"] = [[tracker] for tracker in trackers]

    if webseeds:
        metadata_base["url-list"] = webseeds

    return metadata_base


def create_bencoded_torrent(torrent, bencoded_info, metadata_base=None):
    if metadata_base is None:
        metadata_base = create_default_metadata_base(torrent)

    metadata_base["encoding"] = torrent.encoding
    metadata_base.pop("info", None)
    prefixed_dict = {key: metadata_base[key] for key in metadata_base if key < "info"}
    suffixed_dict = {key: metadata_base[key] for key in metadata_base if key > "info"}

    prefix = bencode.encode(prefixed_dict)
    suffix = bencode.encode(suffixed_dict)

    bencoded_torrent = prefix[:-1] + b"4:info" + bencoded_info + suffix[1:]

    return bencoded_torrent
