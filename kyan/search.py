import re
import shlex

import flask
import sqlalchemy

from kyan import models
from kyan.extensions import db

app = flask.current_app

DEFAULT_MAX_SEARCH_RESULT = 1000
DEFAULT_PER_PAGE = 75
SEARCH_PAGINATE_DISPLAY_MSG = (
    "Displaying results {start}-{end} out of {total} results.<br>\n"
    "Please refine your search results if you can't find "
    "what you were looking for."
)


class QueryPairCaller(object):
    def __init__(self, *items):
        self.items = list(items)

    def __getattr__(self, name):
        def wrapper(*args, **kwargs):
            for i in range(len(self.items)):
                method = getattr(self.items[i], name)
                if not callable(method):
                    raise Exception(f"Attribute {method} is not callable")
                self.items[i] = method(*args, **kwargs)
            return self

        return wrapper


def _generate_query_string(term, category, filter, user):
    params = {}
    if term:
        params["q"] = str(term)
    if category:
        params["c"] = str(category)
    if filter:
        params["f"] = str(filter)
    if user:
        params["u"] = str(user)
    return params


def search_db(
    term="",
    user=None,
    sort="id",
    order="desc",
    category="0_0",
    quality_filter="0",
    page=1,
    rss=False,
    admin=False,
    logged_in_user=None,
    per_page=75,
):
    if page > 4294967295:
        flask.abort(404)

    MAX_PAGES = app.config["SEARCH"].get("MAX_PAGES", 0)

    same_user = logged_in_user and logged_in_user.id == user
    MAX_PAGES = 0 if same_user or admin else MAX_PAGES

    if MAX_PAGES and page > MAX_PAGES:
        flask.abort(
            flask.Response(
                "You've exceeded the maximum number of pages. Please make your search query less broad.",
                403,
            )
        )

    sort_keys = {
        "id": models.Torrent.id,
        "size": models.Torrent.filesize,
        "comments": models.Torrent.comment_count,
        "seeders": models.Statistic.seed_count,
        "leechers": models.Statistic.leech_count,
        "downloads": models.Statistic.download_count,
    }

    sort_column = sort_keys.get(sort.lower())
    if not sort_column:
        flask.abort(400)

    order_keys = ["desc", "asc"]
    order_ = order.lower()
    if order_ not in order_keys:
        flask.abort(400)

    filter_keys = {
        "0": None,
        "1": (models.TorrentFlags.REMAKE, False),
        "2": (models.TorrentFlags.TRUSTED, True),
        "3": (models.TorrentFlags.COMPLETE, True),
    }

    sentinel = object()
    filter_tuple = filter_keys.get(quality_filter.lower(), sentinel)
    if filter_tuple is sentinel:
        flask.abort(400)

    user = models.User.by_id(user) if user else None

    main_category, sub_category = None, None
    main_cat_id, sub_cat_id = 0, 0
    if category:
        cat_match = re.match(r"^(\d+)_(\d+)$", category)
        if not cat_match:
            flask.abort(400)

        main_cat_id, sub_cat_id = map(int, cat_match.groups())

        if main_cat_id > 0:
            if sub_cat_id > 0:
                sub_category = models.SubCategory.by_category_ids(
                    main_cat_id, sub_cat_id
                )
            else:
                main_category = models.MainCategory.by_id(main_cat_id)

    model_class = models.Torrent
    query = db.session.query(model_class)

    count_query = db.session.query(sqlalchemy.func.count(model_class.id))
    qpc = QueryPairCaller(query, count_query)

    if user:
        qpc.filter(models.Torrent.uploader_id == user.id)

        if not admin:
            qpc.filter(
                ~models.Torrent.flags.op("&")(int(models.TorrentFlags.DELETED)).is_(
                    True
                )
            )
            if not same_user or rss:
                qpc.filter(
                    ~models.Torrent.flags.op("&")(
                        int(models.TorrentFlags.HIDDEN | models.TorrentFlags.ANONYMOUS)
                    ).is_(True)
                )
    else:
        if not admin:
            qpc.filter(
                ~models.Torrent.flags.op("&")(int(models.TorrentFlags.DELETED)).is_(
                    True
                )
            )
            if logged_in_user and not rss:
                qpc.filter(
                    ~models.Torrent.flags.op("&")(int(models.TorrentFlags.HIDDEN)).is_(
                        True
                    )
                    | (models.Torrent.uploader_id == logged_in_user.id)
                )
            else:
                qpc.filter(
                    ~models.Torrent.flags.op("&")(int(models.TorrentFlags.HIDDEN)).is_(
                        True
                    )
                )

    if main_category:
        qpc.filter(models.Torrent.main_category_id == main_cat_id)
    elif sub_category:
        qpc.filter(
            models.Torrent.main_category_id == main_cat_id,
            models.Torrent.sub_category_id == sub_cat_id,
        )

    if filter_tuple:
        qpc.filter(
            models.Torrent.flags.op("&")(int(filter_tuple[0])).is_(filter_tuple[1])
        )

    if term:
        for item in shlex.split(term, posix=False):
            if len(item) >= 2:
                qpc.filter(models.Torrent.display_name.ilike(f"%{item}%"))

    query, count_query = qpc.items

    query = query.order_by(getattr(sort_column, order)())

    if rss:
        query = query.limit(per_page)
    else:
        query = query.paginate(page=page, per_page=per_page)

        if term:
            query.display_msg = SEARCH_PAGINATE_DISPLAY_MSG.format(
                start=query.page * query.per_page - query.per_page + 1,
                end=min(query.page * query.per_page, query.total),
                total=query.total,
            )

    return query
