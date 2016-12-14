#!/usr/bin/env python
import hashlib
import hmac
import base64
import botocore.vendored.requests as requests
import json
import re
import os
import difflib

from posixpath import join as urljoin

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

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

# decode github content dicts
def gh_decode(rj):
    enc = rj["encoding"]
    cnt = rj["content"]
    if enc == "base64":
        return base64.b64decode(cnt)
    elif enc == "utf-8":
        return cnt



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
    REPO_URLS = [repository["clone_url"], repository["git_url"], repository["ssh_url"]]
    REPO_HTML_URL = repository["html_url"]

    if REPO_NAME.endswith(".jl"):
        PKG_NAME = REPO_NAME[:-3]
    else:
        raise Exception('Invalid repository name: does not end in .jl')

    if not re.match(r"v\d+.\d+.\d+", TAG_NAME):
        raise Exception('Invalid tag name')

    VERSION = TAG_NAME[1:]

    # 1) check if package registered
    r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "url"),
                     params={"ref": META_BRANCH})

    if r.status_code == 404:
        REGISTER = True

    else:
        REGISTER = False
        rj = r.json()
        # verify this is indeed the package with the correct name
        REPO_URL_META = gh_decode(rj).rstrip()
        if REPO_URL_META not in REPO_URLS:
            raise Exception('Repository path does not match that in METADATA')

        # 1a) get last version
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions"),
                         params={"ref": META_BRANCH})
        rj = r.json()
        LAST_VERSION = max([d["name"] for d in rj], key=lambda s: map(int, s.split('.')))

        # 1b) get last version sha1
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions", LAST_VERSION, "sha1"),
                         params={"ref": META_BRANCH})
        rj = r.json()
        LAST_SHA1 = gh_decode(rj).rstrip()

        # 1c) get last requires
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions", LAST_VERSION, "requires"),
                         params={"ref": META_BRANCH})
        rj = r.json()
        LAST_REQUIRE = gh_decode(rj)


    # 2) get the commit hash corresponding to the tag
    r = requests.get(urljoin(GITHUB_API, "repos", REPO_FULLNAME, "git/refs/tags", TAG_NAME))
    rj = r.json()

    # 2a) if annotated tag: need to make another request
    if rj["object"]["type"] == "tag":
        r = requests.get(rj["object"]["url"])
        rj = r.json()

    SHA1 = rj["object"]["sha"]

    # 3) get the REQUIRE file from the commit
    r = requests.get(urljoin(GITHUB_API, "repos", REPO_FULLNAME, "contents", "REQUIRE"),
                     params={"ref": SHA1})
    rj = r.json()
    REQUIRE_CONTENT = rj["content"]
    REQUIRE_ENCODING = rj["encoding"]
    REQUIRE = gh_decode(rj)

    # 4) get current METADATA head commit
    r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "git/refs/heads", META_BRANCH))
    rj = r.json()
    PREV_COMMIT_SHA = rj["object"]["sha"]
    PREV_COMMIT_URL = rj["object"]["url"]

    # 5) get tree corresponding to last METADATA commit
    r = requests.get(PREV_COMMIT_URL)
    rj = r.json()
    PREV_TREE_SHA = rj["tree"]["sha"]

    # 6a) create blob for REQUIRE
    r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "content": REQUIRE_CONTENT,
                "encoding": REQUIRE_ENCODING
                })
    rj = r.json()
    REQUIRE_BLOB_SHA = rj["sha"]

    # 6b) create blob for SHA1
    r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "content": SHA1 + "\n",
                "encoding": "utf-8"
                })
    rj = r.json()
    SHA1_BLOB_SHA = rj["sha"]

    # 6c) create blob for url if necessary
    if REGISTER:
        r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
                auth=(BOT_USER, BOT_PASS),
                json={
                    "content": REPO_URLS[0] + "\n",
                    "encoding": "utf-8"
                    })
        rj = r.json()
        URL_BLOB_SHA = rj["sha"]


    # 7) create new tree
    tree_data = {
        "base_tree": PREV_TREE_SHA,
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

    # 8) create commit
    if REGISTER:
        msg = "Register " + REPO_NAME + " " + TAG_NAME + " [" + HTML_URL + "]"
    else:
        msg = "Tag " + REPO_NAME + " " + TAG_NAME + " [" + HTML_URL + "]"
    r = requests.post(urljoin(GITHUB_API,"repos", BOT_USER, META_NAME, "git/commits"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "message": msg,
                "parents": [ PREV_COMMIT_SHA ],
                "tree": NEW_TREE_SHA
            })
    rj = r.json()
    NEW_COMMIT_SHA = rj["sha"]

    # 9) Create new ref (i.e. branch)
    NEW_BRANCH_NAME = PKG_NAME + "/" + TAG_NAME
    r = requests.post(urljoin(GITHUB_API,"repos", BOT_USER, META_NAME, "git/refs"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "ref": "refs/heads/" + NEW_BRANCH_NAME,
                "sha": NEW_COMMIT_SHA
            })

    if r.status_code == 422:
        EXISTING = True
        # 9a) PR already exists, update the ref instead
        r = requests.patch(urljoin(GITHUB_API,"repos", BOT_USER, META_NAME, "git/refs/heads", NEW_BRANCH_NAME),
                auth=(BOT_USER, BOT_PASS),
                json={
                    "sha": NEW_COMMIT_SHA,
                    "force": True
                })
    else:
        EXISTING = False

    # 10) Get travis link
    # this sometimes misses, if the tag has not yet made it to travis
    TRAVIS_PR_LINE = ""
    r = requests.get(urljoin("https://api.travis-ci.org/","repos",REPO_FULLNAME,"branches",TAG_NAME))
    if r.status_code == requests.codes.ok:
        rj = r.json()
        build_id = str(rj["branch"]["id"])
        if SHA1 == rj["commit"]["sha"]:
            badge_url = urljoin("https://api.travis-ci.org/", REPO_FULLNAME + ".svg?branch=" + TAG_NAME)
            build_url = urljoin("https://travis-ci.org/", REPO_FULLNAME, "builds", build_id)
            TRAVIS_PR_LINE = "Travis: [![Travis Build Status](" + badge_url + ")](" + build_url + ")\n"

    # 11) Create pull request
    if REGISTER:
        title = "Register new package " + REPO_NAME + " " + TAG_NAME
        body = "Repository: [" + REPO_NAME + "](" + REPO_HTML_URL + ")\n" + \
            "Release: [" + TAG_NAME + "](" + HTML_URL + ")\n" + \
            TRAVIS_PR_LINE + \
            "cc: @" + AUTHOR
    else:
        diff_url = urljoin(REPO_HTML_URL, "compare", LAST_SHA1 + "..." + SHA1)

        req_diff = "".join(difflib.unified_diff(
            LAST_REQUIRE.splitlines(True),
            REQUIRE.splitlines(True),
            LAST_VERSION + "/requires",
            VERSION + "/requires"))

        if req_diff == "":
            req_status = "no changes"
        else:
            req_status = "\n```diff\n" + req_diff + "```"

        title = "Tag " + REPO_NAME + " " + TAG_NAME
        body = "Repository: [" + REPO_NAME + "](" + REPO_HTML_URL + ")\n" + \
            "Release: [" + TAG_NAME + "](" + HTML_URL + ")\n" + \
            TRAVIS_PR_LINE + \
            "Diff: [vs v" + LAST_VERSION + "](" + diff_url + ")\n" + \
            "`requires` vs v" + LAST_VERSION + ": " + req_status + "\n" + \
            "cc: @" + AUTHOR

    if EXISTING:
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "pulls"),
                params={
                    "head": BOT_USER + ":" + NEW_BRANCH_NAME
                })
        rj = r.json()[0] # assume it is the only return value

        r = requests.post(rj["comments_url"],
                auth=(BOT_USER, BOT_PASS),
                json={
                    "body": body,
                })
        rj = r.json()

        return "Comment created: " + rj["url"]

    else:
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
