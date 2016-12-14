#!/usr/bin/env python
import hashlib
import hmac
import base64
import botocore.vendored.requests as requests
import json
import re
import os

from posixpath import join as urljoin

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

GITHUB_API = "https://api.github.com/"

BOT_USER = "attobot"
BOT_PASS = os.environ['BOT_PASS']

META_NAME = "METADATA.jl"
META_ORG  = "JuliaLang"
META_BRANCH = "metadata-v2"

SECRET = os.environ["SECRET"]

# seems like the best option is to base64 encode the body?
# https://github.com/pristineio/lambda-webhook
# https://forums.aws.amazon.com/thread.jspa?messageID=713853
# https://developer.github.com/webhooks/securing/
def verify_signature(secret, signature, payload):
    computed_hash = hmac.new(str(secret), payload, hashlib.sha1)
    computed_signature = 'sha1=' + computed_hash.hexdigest()
    return hmac.compare_digest(computed_signature, str(signature))


# main function
# "event" has 2 fields
#   - body64: base64 encoding of the webhook body
#   - signature: github signature
def lambda_handler(event, context):
    body_str = base64.b64decode(event["body64"])
    logger.info(body_str)
    if not verify_signature(SECRET, event["signature"], body_str):
        raise Exception('[Unauthorized] Authentication error')

    # https://developer.github.com/v3/activity/events/types/#releaseevent
    body = json.loads(body_str)
    if body["action"] != "published":
        return 'Not a "published" event'

    release = body["release"]
    repository = body["repository"]

    AUTHOR = release["author"]["login"]
    TAG_NAME = release["tag_name"]
    HTML_URL = release["html_url"]

    REPO_NAME = repository["name"]
    REPO_FULLNAME = repository["full_name"]
    REPO_URLS = [repository["git_url"], repository["ssh_url"], repository["clone_url"]]
    REPO_HTML_URL = repository["html_url"]

    if REPO_NAME.endswith(".jl"):
        PKG_NAME = REPO_NAME[:-3]
    else:
        raise Exception('Invalid repository name: does not end in .jl')

    if not re.match(r"v\d+.\d+.\d+", TAG_NAME):
        raise Exception('Invalid tag name')

    VERSION = TAG_NAME[1:]

    # 1) verify this is indeed the package with the correct name
    r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "url"),
                     params={"ref": META_BRANCH})

    if r.status_code == 404:
        REGISTER = true

    else:
        REGISTER = false

        rj = r.json()
        if rj["encoding"] == "base64":
            REPO_URL_META = base64.b64decode(rj["content"]).rstrip()
        elif rj["encoding"] == "utf-8":
            REPO_URL_META = rj["content"].rstrip()

        if REPO_URL_META not in REPO_URLS:
            raise Exception('Repository path does not match that in METADATA')

        # 2) get last version
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions"),
                         params={"ref": META_BRANCH})
        rj = r.json()
        LAST_VERSION = max([d["name"] for d in rj], key=lambda s: map(int, s.split('.')))

        # 3) get last version sha1
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions", LAST_VERSION, "sha1"),
                         params={"ref": META_BRANCH})
        rj = r.json()
        if rj["encoding"] == "base64":
            LAST_VERSION_SHA1 = base64.b64decode(rj["content"]).rstrip()
        elif rj["encoding"] == "utf-8":
            LAST_VERSION_SHA1 = rj["content"].rstrip()


    # 4) get the commit hash corresponding to the tag
    r = requests.get(urljoin(GITHUB_API, "repos", REPO_FULLNAME, "git/refs/tags", TAG_NAME))
    rj = r.json()

    # 4a) if annotated tag: need to make another request
    if rj["object"]["type"] == "tag":
        r = requests.get(rj["object"]["url"])
        rj = r.json()

    SHA1 = rj["object"]["sha"]

    # 5) get the REQUIRE file from the commit
    r = requests.get(urljoin(GITHUB_API, "repos", REPO_FULLNAME, "contents", "REQUIRE"),
                     params={"ref": SHA1})
    rj = r.json()
    REQUIRE_CONTENT = rj["content"]
    REQUIRE_ENCODING = rj["encoding"]

    # 6) get current METADATA head commit
    r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "git/refs/heads", META_BRANCH))
    rj = r.json()
    LAST_COMMIT_SHA = rj["object"]["sha"]
    LAST_COMMIT_URL = rj["object"]["url"]

    # 7) get tree corresponding to last METADATA commit
    r = requests.get(LAST_COMMIT_URL)
    rj = r.json()
    LAST_TREE_SHA = rj["tree"]["sha"]

    # 8) create blob for REQUIRE
    r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "content": REQUIRE_CONTENT,
                "encoding": REQUIRE_ENCODING
                })
    rj = r.json()
    REQUIRE_BLOB_SHA = rj["sha"]

    # 9) create blob for SHA1
    r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "content": SHA1 + "\n",
                "encoding": "utf-8"
                })
    rj = r.json()
    SHA1_BLOB_SHA = rj["sha"]

    # 9.5) create blob for url if necessary
    if REGISTER:
        r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
                auth=(BOT_USER, BOT_PASS),
                json={
                    "content": REPO_URLS[0] + "\n",
                    "encoding": "utf-8"
                    })
        rj = r.json()
        URL_BLOB_SHA = rj["sha"]


    # 10) create new tree
    tree_data = {
        "base_tree": LAST_TREE_SHA,
        "tree": [
            {
                "path": urljoin(PKG_NAME,"versions",VERSION,"requires"),
                "mode": "100644",
                "type": "blob",
                "sha": REQUIRE_BLOB_SHA
            },
            {
                "path": urljoin(PKG_NAME,"versions",VERSION,"sha1"),
                "mode": "100644",
                "type": "blob",
                "sha": SHA1_BLOB_SHA
            }
        ]
    }

    if REGISTER:
        tree_data["tree"].append({
            "path": urljoin(PKG_NAME,"url"),
            "mode": "100644",
            "type": "blob",
            "sha": URL_BLOB_SHA
        })

    r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/trees"),
        auth=(BOT_USER, BOT_PASS),
        json=tree_data)
    rj = r.json()
    NEW_TREE_SHA = rj["sha"]

    # 11) create commit
    if REGISTER:
        msg = "Register " + REPO_NAME + " " + TAG_NAME + " [" + HTML_URL + "]"
    else:
        msg = "Tag " + REPO_NAME + " " + TAG_NAME + " [" + HTML_URL + "]"
    r = requests.post(urljoin(GITHUB_API,"repos", BOT_USER, META_NAME, "git/commits"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "message": msg,
                "parents": [ LAST_COMMIT_SHA ],
                "tree": NEW_TREE_SHA
            })
    rj = r.json()
    NEW_COMMIT_SHA = rj["sha"]

    # 12) Create new ref (i.e. branch)
    NEW_BRANCH_NAME = PKG_NAME + "/" + TAG_NAME
    r = requests.post(urljoin(GITHUB_API,"repos", BOT_USER, META_NAME, "git/refs"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "ref": "refs/heads/" + NEW_BRANCH_NAME,
                "sha": NEW_COMMIT_SHA
            })

    # 13) Create pull request
    if REGISTER:
        title = "Register new package " + REPO_NAME + " " + TAG_NAME
        body = "Release: " + HTML_URL + "\n" +
            "cc: @" + AUTHOR
    else:
        diff_url = urljoin(REPO_HTML_URL, "compare", LAST_VERSION_SHA1 + "..." + SHA1)
        title = "Tag " + REPO_NAME + " " + TAG_NAME
        body = "Release: " + HTML_URL + "\n" +
            "Diff: [vs v" + LAST_VERSION + "](" + diff_url + ")\n" +
            "cc: @" + AUTHOR

    r = requests.post(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "pulls"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "title": title,
                "body": body,
                "head": BOT_USER + ":" + NEW_BRANCH_NAME,
                "base": META_BRANCH
            })
    rj = r.json()

    return "PR created: " + rj["url"]
