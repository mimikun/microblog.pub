import mimetypes
import os
import subprocess
from datetime import datetime
from enum import Enum

import yaml
from itsdangerous import JSONWebSignatureSerializer
from little_boxes import strtobool
from little_boxes.activitypub import DEFAULT_CTX
from pymongo import MongoClient

import sass
from utils.key import KEY_DIR
from utils.key import get_key
from utils.key import get_secret_key
from utils.media import MediaCache


class ThemeStyle(Enum):
    LIGHT = "light"
    DARK = "dark"


DEFAULT_THEME_STYLE = ThemeStyle.LIGHT.value

DEFAULT_THEME_PRIMARY_COLOR = {
    ThemeStyle.LIGHT: "#1d781d",  # Green
    ThemeStyle.DARK: "#33ff00",  # Purple
}


VERSION = (
    subprocess.check_output(["git", "describe", "--always"]).split()[0].decode("utf-8")
)
VERSION_DATE = (
    subprocess.check_output(["git", "show", VERSION])
    .decode()
    .splitlines()[2]
    .split("Date:")[-1]
    .strip()
)

DEBUG_MODE = strtobool(os.getenv("MICROBLOGPUB_DEBUG", "false"))

HEADERS = [
    "application/activity+json",
    "application/ld+json;profile=https://www.w3.org/ns/activitystreams",
    'application/ld+json; profile="https://www.w3.org/ns/activitystreams"',
    "application/ld+json",
]


with open(os.path.join(KEY_DIR, "me.yml")) as f:
    conf = yaml.load(f)

    USERNAME = conf["username"]
    NAME = conf["name"]
    DOMAIN = conf["domain"]
    SCHEME = "https" if conf.get("https", True) else "http"
    BASE_URL = SCHEME + "://" + DOMAIN
    ID = BASE_URL
    SUMMARY = conf["summary"]
    ICON_URL = conf["icon_url"]
    PASS = conf["pass"]
    EXTRA_INBOXES = conf.get("extra_inboxes", [])

    HIDE_FOLLOWING = conf.get("hide_following", True)

    # Theme-related config
    theme_conf = conf.get("theme", {})
    THEME_STYLE = ThemeStyle(theme_conf.get("style", DEFAULT_THEME_STYLE))
    THEME_COLOR = theme_conf.get("color", DEFAULT_THEME_PRIMARY_COLOR[THEME_STYLE])


SASS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sass")
theme_css = f"$primary-color: {THEME_COLOR};\n"
with open(os.path.join(SASS_DIR, f"{THEME_STYLE.value}.scss")) as f:
    theme_css += f.read()
    theme_css += "\n"
with open(os.path.join(SASS_DIR, "base_theme.scss")) as f:
    raw_css = theme_css + f.read()
    CSS = sass.compile(string=raw_css, output_style="compressed")


USER_AGENT = f"microblog.pub/{VERSION}; +{BASE_URL}"

mongo_client = MongoClient(
    host=[os.getenv("MICROBLOGPUB_MONGODB_HOST", "localhost:27017")]
)

DB_NAME = "{}_{}".format(USERNAME, DOMAIN.replace(".", "_"))
DB = mongo_client[DB_NAME]
GRIDFS = mongo_client[f"{DB_NAME}_gridfs"]
MEDIA_CACHE = MediaCache(GRIDFS, USER_AGENT)


def _drop_db():
    if not DEBUG_MODE:
        return

    mongo_client.drop_database(DB_NAME)


KEY = get_key(ID, ID + "#main-key", USERNAME, DOMAIN)


JWT_SECRET = get_secret_key("jwt")
JWT = JSONWebSignatureSerializer(JWT_SECRET)


def _admin_jwt_token() -> str:
    return JWT.dumps(  # type: ignore
        {"me": "ADMIN", "ts": datetime.now().timestamp()}
    ).decode(  # type: ignore
        "utf-8"
    )


ADMIN_API_KEY = get_secret_key("admin_api_key", _admin_jwt_token)

ME = {
    "@context": DEFAULT_CTX,
    "type": "Person",
    "id": ID,
    "following": ID + "/following",
    "followers": ID + "/followers",
    "featured": ID + "/featured",
    "liked": ID + "/liked",
    "inbox": ID + "/inbox",
    "outbox": ID + "/outbox",
    "preferredUsername": USERNAME,
    "name": NAME,
    "summary": SUMMARY,
    "endpoints": {},
    "url": ID,
    "manuallyApprovesFollowers": False,
    "attachment": [],
    "icon": {
        "mediaType": mimetypes.guess_type(ICON_URL)[0],
        "type": "Image",
        "url": ICON_URL,
    },
    "publicKey": KEY.to_dict(),
}

# Default emojis, space-separated, update `me.yml` to customize emojis
EMOJIS = "😺 😸 😹 😻 😼 😽 🙀 😿 😾"
if conf.get("emojis"):
    EMOJIS = conf["emojis"]

# Emoji template for the FE
EMOJI_TPL = '<img src="https://cdn.jsdelivr.net/npm/twemoji@12.0.0/2/svg/{filename}.svg" alt="{raw}" class="emoji">'
if conf.get("emoji_tpl"):
    EMOJI_TPL = conf["emoji_tpl"]

# Hosts blacklist
BLACKLIST = conf.get("blacklist", [])

# By default, we keep 14 of inbox data ; outbox is kept forever (along with bookmarked stuff, outbox replies, liked...)
DAYS_TO_KEEP = 14
