import hmac
import secrets
from flask import request, session, abort

# Application package marker


def init_csrf_and_security(app):
    """Session-bound CSRF protection for all state-changing form requests."""
    @app.context_processor
    def inject_csrf_token():
        def csrf_token():
            token = session.get("_csrf_token")
            if not token:
                token = secrets.token_urlsafe(32)
                session["_csrf_token"] = token
            return token
        return {"csrf_token": csrf_token}

    @app.before_request
    def validate_csrf():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("_csrf_token", "")
            supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
            if not expected or not supplied or not hmac.compare_digest(expected, supplied):
                abort(400, description="Invalid or missing CSRF token. Refresh the page and try again.")
