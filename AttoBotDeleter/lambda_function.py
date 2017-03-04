#!/usr/bin/env python
import hashlib
import hmac
import base64
import botocore.vendored.requests as requests
import json
import re
import os
import difflib
import time

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

# decode github content dicts
def gh_decode(rj):
    enc = rj["encoding"]
    cnt = rj["content"]
    if enc == "base64":
        return base64.b64decode(cnt)
    elif enc == "utf-8":
        return cnt

def errorissue(repo_fullname, user, message):
    r = requests.post(urljoin(GITHUB_API, "repos", repo_fullname, "issues"),
            auth=(BOT_USER, BOT_PASS),
            json={
                "title": "Error tagging new release",
                "body": message + "\ncc: @" + user
                })
    raise Exception(message)

# main function
# "event" has 2 fields
#   - body64: base64 encoding of the webhook body
#   - signature: github signature
def lambda_handler(event, context):
    body_str = base64.b64decode(event["body64"])
    logger.info(body_str)
    if not verify_signature(SECRET, event["signature"], body_str):
        raise Exception('[Unauthorized] Authentication error')

    # https://developer.github.com/v3/activity/events/types/#pullrequestevent
    body = json.loads(body_str)
    if body["action"] != "closed":
        return 'Not a "closed" event'

    if body["pull_request"]["user"]["login"] != "attobot":
        return 'Not an attobot pull request'

    PR_URL = body["pull_request"]["url"]
    
    # branch name
    REF = body["pull_request"]["head"]["ref"]

    # we pause for 20 seconds to see if the branch is reopened, e.g. for retriggering Travis
    time.sleep(20)

    # check if branch is still open
    r = requests.get(PR_URL)
    rj = r.json()
    if rj["state"] != "closed":
        return "Pull request has been reopened"

    # delete attobot branch
    r = requests.delete(urljoin(GITHUB_API, "repos", BOT_USER, META_NAME, "git/refs/heads", REF),
            auth=(BOT_USER, BOT_PASS))


    if r.status_code == 204:
        return "Branch " + REF + " succesfully deleted."
    else:
        return "Could not delete branch " + REF
