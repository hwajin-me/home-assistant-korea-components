"""Bounded public Kakao review/photo previews; never retain author profiles."""

from math import isfinite
from urllib.parse import urlsplit, urlunsplit


def _object(value):
    return value if isinstance(value, dict) else {}


def _number(value, *, maximum=None, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        return None
    if maximum is not None and value > maximum or integer and int(value) != value:
        return None
    return int(value) if integer else value


def photo_url(value):
    """Allow only public Kakao/Daum media hosts, upgrading CDN links to HTTPS."""
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if (
            url.scheme not in ("http", "https")
            or url.username
            or url.password
            or url.port not in (None, 80, 443)
        ):
            return None
        if not any(
            host == domain or host.endswith("." + domain)
            for domain in ("daumcdn.net", "kakaocdn.net")
        ):
            return None
        return urlunsplit(("https", host, url.path, url.query, ""))
    except ValueError:
        return None


def public_media(data, place_id):
    """Use only fields observed in panel3; limits prevent unbounded HA attributes."""
    restrict = _object(data.get("restrict"))
    reviews_allowed = (
        _object(restrict.get("review_read")).get("is_restrict") is not True
    )
    photos_allowed = _object(restrict.get("photo")).get("is_restrict") is not True
    reviews = _object(data.get("kakaomap_review")) if reviews_allowed else {}
    score = _object(reviews.get("score_set"))
    photos = _object(data.get("photos")) if photos_allowed else {}
    previews = []
    rows = reviews.get("reviews")
    if isinstance(rows, list):
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            if row.get("status") != "S":
                continue
            text = row.get("contents")
            if not isinstance(text, str):
                continue
            previews.append(
                {
                    "text": text[:500],
                    "rating": _number(row.get("star_rating"), maximum=5),
                    "date": str(row.get("registered_at") or "")[:40],
                }
            )
    urls = []
    main = (
        photo_url(_object(data.get("summary")).get("main_photo_url"))
        if photos_allowed
        else None
    )
    if main:
        urls.append(main)
    rows = photos.get("photos")
    if isinstance(rows, list):
        for row in rows[:20]:
            url = photo_url(_object(row).get("url"))
            if url and url not in urls:
                urls.append(url)
    return {
        "place_url": f"https://place.map.kakao.com/{place_id}",
        "rating": _number(score.get("average_score"), maximum=5),
        "review_count": _number(score.get("review_count"), integer=True),
        "photo_count": _number(
            _object(photos.get("counts")).get("total"), integer=True
        ),
        "reviews": previews,
        "photos": urls[:10],
        "main_photo": main or next(iter(urls), None),
        "reviews_has_more": reviews.get("has_next") is True
        or isinstance(reviews.get("reviews"), list)
        and len(reviews["reviews"]) > 5,
        "reviews_restricted": not reviews_allowed,
        "photos_restricted": not photos_allowed,
    }
