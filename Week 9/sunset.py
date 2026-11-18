from datetime import datetime, timezone
from email.utils import format_datetime
from functools import wraps

from flask import current_app, jsonify, make_response


def http_date(dt):
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


def deprecate_at(sunset_date, replacement=None):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if datetime.now(timezone.utc) >= sunset_date:
                return jsonify(
                    error="gone",
                    sunset=sunset_date.isoformat(),
                    use_instead=replacement,
                ), 410

            current_app.logger.warning("deprecated_call")
            response = make_response(view(*args, **kwargs))
            response.headers["Sunset"] = http_date(sunset_date)
            response.headers["Deprecation"] = "true"
            if replacement is not None:
                response.headers.add("Link", f'<{replacement}>; rel="successor-version"')
            return response

        return wrapped

    return decorate
