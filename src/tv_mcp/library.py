from functools import cache

from plexapi.client import PlexClient
from plexapi.myplex import MyPlexAccount

from src.tv_mcp.settings import LIBRARY_TOKEN


@cache
def account() -> MyPlexAccount:
    if not LIBRARY_TOKEN:
        raise RuntimeError("LIBRARY_TOKEN isn't set in .env")
    return MyPlexAccount(token=LIBRARY_TOKEN)


_servers: dict = {}


def servers() -> dict:
    if not _servers:
        for r in account().resources():
            if "server" not in (r.provides or ""):
                continue
            try:
                _servers[r.name] = r.connect(timeout=10)
            except Exception:
                pass
    return _servers


def _summary(server: str, item) -> dict:
    out = {
        "server": server,
        "rating_key": item.ratingKey,
        "title": item.title,
        "year": item.year,
        "type": item.type,
        "audience_rating": item.audienceRating,
        "critic_rating": item.rating,
        "genres": [g.tag for g in getattr(item, "genres", [])],
        "summary": (item.summary or "")[:240],
    }
    if item.type == "show":
        out["seasons"] = item.childCount
        out["episodes_watched"] = f"{item.viewedLeafCount}/{item.leafCount}"
    else:
        out["watched"] = bool(item.viewCount)
        out["minutes"] = round((item.duration or 0) / 60000)
    return out


def search(query: str, limit: int = 10) -> list[dict]:
    results = []
    for name, srv in servers().items():
        for item in srv.search(query, limit=limit):
            if item.type in ("show", "movie"):
                results.append(_summary(name, item))
    return results


def browse(genre: str | None, kind: str, unwatched_only: bool, limit: int) -> list[dict]:
    results = []
    for name, srv in servers().items():
        for section in srv.library.sections():
            if section.type != kind:
                continue
            filters = {"genre": genre} if genre else {}
            if unwatched_only:
                filters["unwatched"] = True
            try:
                items = section.search(sort="audienceRating:desc", maxresults=limit, **filters)
            except Exception:
                continue
            results += [_summary(name, i) for i in items]
    results.sort(key=lambda r: r["audience_rating"] or 0, reverse=True)
    return results[:limit]


def set_audio_language(server: str, rating_key: int, language: str) -> dict:
    item = servers()[server].fetchItem(rating_key)
    videos = item.episodes() if item.type == "show" else [item]
    switched = missing = 0
    for v in videos:
        v.reload()
        for part in v.iterParts():
            match = [a for a in part.audioStreams() if a.languageCode == language]
            if not match:
                missing += 1
            elif not match[0].selected:
                part.setSelectedAudioStream(match[0])
                switched += 1
    return {"switched": switched, "already_set": len(videos) - switched - missing, "no_track_in_that_language": missing}


def play_on(server: str, rating_key: int, host: str, player_id: str) -> str:
    srv = servers()[server]
    item = srv.fetchItem(rating_key)
    player = PlexClient(server=srv, baseurl=f"http://{host}:8324", identifier=player_id, token=srv._token, connect=False)
    player.machineIdentifier = player._clientIdentifier = player_id
    player.protocolCapabilities = ["playback", "navigation", "timeline"]
    player.product = "Roku"
    player.playMedia(item)
    return item.title
