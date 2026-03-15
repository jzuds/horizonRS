import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://prices.runescape.wiki/api/v1/osrs"
 
# The wiki requests a descriptive user agent so they can contact you if needed.
# https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices#Please_set_a_user_agent
USER_AGENT = "horizonRS-pipeline/1.0 (contact: zudsgaming@gmail.com)"

WIKI_API_ENDPOINTS = {
    "mapping": "mapping",
    "latest_price": "latest",
    "5m_price": "5m",
    "1h_price": "1h",
    "24h_price": "24h",
}
 
def build_session() -> requests.Session:
    """
    Shared HTTP session with exponential backoff on transient failures.
 
    Retries: 2, 4, 8, 16, 32 s on 429/5xx. Never retries 4xx (those are bugs).
    """
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist={429, 500, 502, 503, 504},
        allowed_methods={"GET"},
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session