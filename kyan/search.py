import re
import shlex

import flask
import sqlalchemy

from kyan import models
from kyan.extensions import db

app = flask.current_app

DEFAULT_MAX_SEARCH_RESULT = 1000
DEFAULT_PER_PAGE = 75
SERACH_PAGINATE_DISPLAY_MSG = (
    "Displaying results {start}-{end} out of {total} results.<br>\n"
    "Please refine your search results if you can't find "
    "what you were looking for."
)


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


QUOTED_LITERAL_REGEX = re.compile(r'(?i)(-)?"(.+?)"')
QUOTED_LITERAL_GROUP_REGEX = re.compile(
    r"""
    (?i)
    (-)?
    (
        ".+?"
        (?:
            \|
            ".+?"
        )+
    )
    """,
    re.X,
)


class QueryPairCaller(object):
    def __init__(self, *items):
        self.items = list(items)

    def __getattr__(self, name):
        def wrapper(*args, **kwargs):
            for i in range(len(self.items)):
                method = getattr(self.items[i], name)
                if not callable(method):
                    raise Exception("Attribute %r is not callable" % method)
                self.items[i] = method(*args, **kwargs)
            return self

        return wrapper


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

    MAX_PAGES = app.config.get("MAX_PAGES", 0)

    if MAX_PAGES and page > MAX_PAGES:
        flask.abort(
            flask.Response(
                "You've exceeded the maximum number of pages. Please "
                "make your search query less broad.",
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
    if sort_column is None:
        flask.abort(400)

    order_keys = {"desc": "desc", "asc": "asc"}

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

    if user:
        user = models.User.by_id(user)
        if not user:
            flask.abort(404)
        user = user.id

    main_category = None
    sub_category = None
    main_cat_id = 0
    sub_cat_id = 0
    if category:
        cat_match = re.match(r"^(\d+)_(\d+)$", category)
        if not cat_match:
            flask.abort(400)

        main_cat_id = int(cat_match.group(1))
        sub_cat_id = int(cat_match.group(2))

        if main_cat_id > 0:
            if sub_cat_id > 0:
                sub_category = models.SubCategory.by_category_ids(
                    main_cat_id, sub_cat_id
                )
            else:
                main_category = models.MainCategory.by_id(main_cat_id)

            if not category:
                flask.abort(400)

    if rss:
        sort_column = sort_keys["id"]
        order = "desc"

    model_class = models.TorrentNameSearch if term else models.Torrent

    query = db.session.query(model_class).select_from(model_class)

    count_query = db.session.query(sqlalchemy.func.count(model_class.id))
    qpc = QueryPairCaller(query, count_query)

    if user:
        qpc.filter(models.Torrent.uploader_id == user)

        if not admin:
            qpc.filter(
                models.Torrent.flags.op("&")(int(models.TorrentFlags.DELETED)).is_(
                    False
                )
            )
            if not logged_in_user or logged_in_user.id != user:
                qpc.filter(
                    models.Torrent.flags.op("&")(int(models.TorrentFlags.ANONYMOUS))
                    == 0
                )

    if sub_category:
        qpc.filter(models.Torrent.sub_category_id == sub_category.id)
    elif main_category:
        qpc.filter(models.Torrent.main_category_id == main_category.id)

    if filter_tuple:
        qpc.filter(
            models.Torrent.flags.op("&")(int(filter_tuple[0])).is_(filter_tuple[1])
        )

    if term:
        if "|" in term:
            term = shlex.quote(term)

        search_mode = "natsort"

        or_queries = QUOTED_LITERAL_GROUP_REGEX.findall(term)
        or_clauses = []
        for or_group in or_queries:
            negate, or_group = or_group
            or_group = QUOTED_LITERAL_REGEX.findall(or_group)
            and_clauses = []
            for negate, literal in or_group:
                negate = "" if negate else "-"
                if search_mode == "natsort":
                    and_clauses.append(
                        models.TorrentNameSearch.search_vector.match(
                            f"{negate}{literal}"
                        )
                    )
                else:
                    and_clauses.append(
                        models.TorrentNameSearch.search_vector.op("@@")(
                            f"{negate}{literal}"
                        )
                    )
            or_clauses.append(sqlalchemy.and_(*and_clauses))
        query = query.filter(sqlalchemy.or_(*or_clauses))

    if not rss:
        if not term and not admin:
            query = query.filter(
                models.Torrent.flags.op("&")(int(models.TorrentFlags.DELETED)).is_(
                    False
                )
            )
            if not logged_in_user or (logged_in_user and not admin):
                query = query.filter(
                    models.Torrent.flags.op("&")(
                        int(models.TorrentFlags.ANONYMOUS)
                    ).is_(False)
                )

    if order_ == "desc":
        query = query.order_by(sqlalchemy.desc(sort_column))
    else:
        query = query.order_by(sort_column)

    return query.paginate(page=page, per_page=per_page)
