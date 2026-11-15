"""India location spelling variants and a configurable public-employer preset."""
import re

INDIA_BOARDS = [
    {"type": "smartrecruiters", "token": "Freshworks", "company": "Freshworks", "country": "in"},
    {"type": "smartrecruiters", "token": "BoschGroup", "company": "Bosch Group", "country": "in"},
    {"type": "smartrecruiters", "token": "SopraSteria1", "company": "Sopra Steria", "country": "in"},
    {"type": "lever", "token": "cred", "company": "CRED"},
    {"type": "lever", "token": "smart-working-solutions", "company": "Smart Working Solutions"},
]
CITY_GROUPS = [
    ("bangalore", "bengaluru"), ("gurgaon", "gurugram"),
    ("vizag", "visakhapatnam"), ("bombay", "mumbai"),
    ("madras", "chennai"), ("calcutta", "kolkata"),
    ("cochin", "kochi"), ("trivandrum", "thiruvananthapuram"),
    ("pondicherry", "puducherry"),
]
INDIA_PLACES = {"india", "chennai", "madurai", "hyderabad", "coimbatore", "kerala",
                "pune", "noida", "delhi", "new delhi", "ahmedabad", "jaipur",
                "indore", "chandigarh", "mohali", "kozhikode", "lucknow"}
INDIA_PLACES.update(name for group in CITY_GROUPS for name in group)


def normalize_location(value):
    value = re.sub(r"[^\w]+", " ", value.casefold()).strip()
    for group in CITY_GROUPS:
        for name in group:
            value = re.sub(r"\b" + re.escape(name) + r"\b", group[0], value)
    return value


def india_search(settings):
    return settings.get("india", {}).get("enabled", False) or any(
        place.strip().casefold() in INDIA_PLACES
        for place in settings.get("location_keywords", []))


def effective_boards(settings):
    boards = list(settings.get("boards", []))
    if india_search(settings):
        boards += settings.get("india", {}).get("boards", INDIA_BOARDS)
    unique = {}
    for board in boards:
        unique.setdefault((board["type"], board["token"], board.get("country", "")), board)
    return list(unique.values())
