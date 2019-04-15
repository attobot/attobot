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
logger.setLevel(logging.WARNING)

GITHUB_API = "https://api.github.com/"

BOT_USER = "attobot"
BOT_PASS = os.environ['BOT_PASS']

META_NAME = "METADATA.jl"
META_ORG  = "JuliaLang"
META_BRANCH = "metadata-v2"

SECRET = os.environ["SECRET"]

TAG_REQ = "\n".join((
    "Please make sure that:",
    "- CI passes for supported Julia versions (if applicable).",
    "- Version bounds reflect minimum requirements."
))

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
    if rj["encoding"] == "base64":
        return base64.b64decode(rj["content"])
    elif rj["encoding"] == "utf-8":
        return rj["content"]
    else:
        raise Exception("Unknown encoding %s" % enc)

def gh_encode(str):
    return {"content":  base64.b64encode(str),
            "encoding": "base64"}


def errorissue(repo_fullname, user, message):
    r = requests.post(urljoin(GITHUB_API, "repos", repo_fullname, "issues"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "title": "Error tagging new release",
                "body": message + "\ncc: @" + user
                })
    raise Exception(message)


def semverkey(s):
    m = re.match(r"(\d+)\.(\d+)\.(\d+)(([+-])[0-9A-Za-z-]+)?", s)
    if not m:
        raise Exception('Invalid semver key %s' % s)
    x = int(m.group(1))
    y = int(m.group(2))
    z = int(m.group(3))
    if m.group(4):
        if m.group(5) == "+":
            q = 1
        else:
            q = -1
    else:
        q = 0
    return x,y,z,q

# main function
# "event" has 2 fields
#   - body64: base64 encoding of the webhook body
#   - signature: github signature
def lambda_handler(event, context):
    raise Exception('Temporarily disabled')

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
        return "The repository does not have a .jl suffix."

    if not re.match(r"v\d+\.\d+\.\d+$", TAG_NAME):
        errorissue(REPO_FULLNAME, AUTHOR, "The tag name \"" + TAG_NAME + "\" is not of the appropriate SemVer form (vX.Y.Z).")

    VERSION = TAG_NAME[1:]

    # 1) check if package registered
    r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "url"),
                     auth=(BOT_USER, BOT_PASS),
                     params={"ref": META_BRANCH})

    if r.status_code == 404:
        REGISTER = True

    else:
        REGISTER = False
        rj = r.json()
        # verify this is indeed the package with the correct name
        REPO_URL_META = gh_decode(rj).rstrip()
        if REPO_URL_META not in REPO_URLS:
            errorissue(REPO_FULLNAME, AUTHOR, "The URL of this package does not match that stored in METADATA.jl.")

        # 1a) get last version
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions"),
                         auth=(BOT_USER, BOT_PASS),
                         params={"ref": META_BRANCH})
        rj = r.json()
        ALL_VERSIONS = [d["name"] for d in rj]
        PREV_VERSIONS = filter(lambda v : semverkey(v) < semverkey(VERSION), ALL_VERSIONS)
        if not PREV_VERSIONS:
            errorissue(REPO_FULLNAME, AUTHOR, "Cannot tag a new version \"" + TAG_NAME + "\" preceding all existing versions.")
        LAST_VERSION = max(PREV_VERSIONS, key=semverkey)

        # 1b) get last version sha1
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions", LAST_VERSION, "sha1"),
                         auth=(BOT_USER, BOT_PASS),
                         params={"ref": META_BRANCH})
        rj = r.json()
        LAST_SHA1 = gh_decode(rj).rstrip()

        # 1c) get last requires
        # this may not exist in some very old cases
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "contents", PKG_NAME, "versions", LAST_VERSION, "requires"),
                         auth=(BOT_USER, BOT_PASS),
                         params={"ref": META_BRANCH})
        if r.status_code == 200:
            rj = r.json()
            LAST_REQUIRE = gh_decode(rj)
        else:
            LAST_REQUIRE = ""


    # 2) get the commit hash corresponding to the tag
    r = requests.get(urljoin(GITHUB_API, "repos", REPO_FULLNAME, "git/refs/tags", TAG_NAME),
                     auth=(BOT_USER, BOT_PASS))
    rj = r.json()

    # 2a) if annotated tag: need to make another request
    if rj["object"]["type"] == "tag":
        r = requests.get(rj["object"]["url"],
                    auth=(BOT_USER, BOT_PASS))
        rj = r.json()

    SHA1 = rj["object"]["sha"]

    # 3) get the REQUIRE file from the commit
    r = requests.get(urljoin(GITHUB_API, "repos", REPO_FULLNAME, "contents", "REQUIRE"),
                     auth=(BOT_USER, BOT_PASS),
                     params={"ref": SHA1})
    if r.status_code == 404:
        errorissue(REPO_FULLNAME, AUTHOR, "The REQUIRE file could not be found.")

    rj = r.json()
    REQUIRE = gh_decode(rj).replace('\r\n', '\n') # normalize line endings

    # 4) get current METADATA head commit
    r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "git/refs/heads", META_BRANCH),
                auth=(BOT_USER, BOT_PASS))
    rj = r.json()
    PREV_COMMIT_SHA = rj["object"]["sha"]
    PREV_COMMIT_URL = rj["object"]["url"]

    # 5) get tree corresponding to last METADATA commit
    r = requests.get(PREV_COMMIT_URL,
                auth=(BOT_USER, BOT_PASS))
    rj = r.json()
    PREV_TREE_SHA = rj["tree"]["sha"]

    # 6a) create blob for REQUIRE
    r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
            auth=(BOT_USER, BOT_PASS),
            json=gh_encode(REQUIRE))
    rj = r.json()
    REQUIRE_BLOB_SHA = rj["sha"]

    # 6b) create blob for SHA1
    r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
            auth=(BOT_USER, BOT_PASS),
            json=gh_encode(SHA1+"\n"))
    rj = r.json()
    SHA1_BLOB_SHA = rj["sha"]

    # 6c) create blob for url if necessary
    if REGISTER:
        r = requests.post(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/blobs"),
                auth=(BOT_USER, BOT_PASS),
                json=gh_encode(REPO_URLS[0]+"\n"))
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

    # 7.5) get user info for commit
    r = requests.get(urljoin(GITHUB_API,"users",AUTHOR),
                auth=(BOT_USER, BOT_PASS))
    rj = r.json()
    AUTHOR_NAME = rj["name"]
    if AUTHOR_NAME is None:
        AUTHOR_NAME = AUTHOR

    AUTHOR_EMAIL = rj["email"]
    if AUTHOR_EMAIL is None:
        # get the email from the last commit by the author
        r = requests.get(urljoin(GITHUB_API, "repos", REPO_FULLNAME, "commits"),
                auth=(BOT_USER, BOT_PASS),
                params={"author": AUTHOR})
        rj = r.json()
        if rj:
            AUTHOR_EMAIL = rj[0]["commit"]["author"]["email"]
        else:
            # otherwise use fallback (may or may not link to the author)
            AUTHOR_EMAIL = AUTHOR + "@users.noreply.github.com"


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
                "tree": NEW_TREE_SHA,
                "author": {
                    "name": AUTHOR_NAME,
                    "email": AUTHOR_EMAIL
                },
                "committer": {
                    "name": "AttoBot",
                    "email": "AttoBot@users.noreply.github.com"
                }
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
        body = "Repository: [" + REPO_FULLNAME + "](" + REPO_HTML_URL + ")\n" + \
            "Release: [" + TAG_NAME + "](" + HTML_URL + ")\n" + \
            TRAVIS_PR_LINE + \
            "cc: @" + AUTHOR + "\n" + \
            "\n" + TAG_REQ + "\n" + \
            "\n@" + AUTHOR + " This PR will remain open for three days for feedback (which is optional). If you get feedback, please let us know if you are making changes, and we'll merge once you're done."
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
            # Ensure closing ``` is on its own line
            if not req_diff.endswith("\n"):
                req_diff += "\n"
            req_status = "\n```diff\n" + req_diff + "```"

        title = "Tag " + REPO_NAME + " " + TAG_NAME
        body = "Repository: [" + REPO_FULLNAME + "](" + REPO_HTML_URL + ")\n" + \
            "Release: [" + TAG_NAME + "](" + HTML_URL + ")\n" + \
            TRAVIS_PR_LINE + \
            "Diff: [vs v" + LAST_VERSION + "](" + diff_url + ")\n" + \
            "`requires` vs v" + LAST_VERSION + ": " + req_status + "\n" + \
            "cc: @" + AUTHOR + "\n" + \
            "\n" + TAG_REQ

    if EXISTING:
        r = requests.get(urljoin(GITHUB_API, "repos", META_ORG, META_NAME, "pulls"),
                params={
                    "head": BOT_USER + ":" + NEW_BRANCH_NAME,
                    "state": "all"
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
