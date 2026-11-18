import hashlib

from flask import request

from handlers import v1_create_order, v2_create_order

V2_PERCENT = 5
V2_COHORTS = {"beta", "internal"}
V2_FORCE_ACCOUNTS = {"acct_42", "acct_99"}


def route_to_v2(body):
    if request.headers.get("X-Cohort") in V2_COHORTS:
        return True

    acct = body.get("account_id")
    if not isinstance(acct, str) or not acct:
        return False
    if acct in V2_FORCE_ACCOUNTS:
        return True

    digest = hashlib.md5(acct.encode()).hexdigest()
    return int(digest, 16) % 100 < V2_PERCENT


def dispatch(body):
    if route_to_v2(body):
        return v2_create_order(body)
    return v1_create_order(body)
