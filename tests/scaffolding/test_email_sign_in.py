"""Sign-in links by email (feather/auth/email_link.py), in a generated app.

Each app runs in its own interpreter, like test_app_types_096, because
generated apps all define ``app``, ``config`` and ``models``.
"""

import pytest

from tests.scaffolding.test_app_types_096 import _run_in_project

pytestmark = pytest.mark.scaffolding

EMAIL_APP = {
    "database": "sqlite",
    "db_url": "sqlite:///app.db",
    "include_auth": True,
    "tenant_mode": "single",
    "admin_email": "admin@test.com",
    "sign_in": "email",
}

FLOW = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
from urllib.parse import urlparse

import feather.auth.email_link as email_link

sent = []
email_link.send_link = lambda email, link: sent.append((email, link)) or True

from app import app
from feather.db import db
from models import User

app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
with app.app_context():
    db.create_all()
    db.session.add(User(email="owner@test.com", username="owner", active=True, role="admin"))
    db.session.commit()

client = app.test_client()
result = {"method": app.config.get("SIGN_IN_METHOD")}
anon = client.get("/admin/users")
result["anonymous_admin"] = [anon.status_code, anon.headers.get("Location", ""), "/auth/email/login" in anon.get_data(as_text=True)]
result["form"] = client.get("/auth/email/login").status_code
result["bad_address"] = client.post("/auth/email/login", data={"email": "not-an-address"}).status_code
sent_page = client.post("/auth/email/login", data={"email": "Owner@Test.com "})
result["sent"] = sent_page.status_code
result["sent_to"] = sent[-1][0] if sent else None
link = urlparse(sent[-1][1])
token = link.query.split("token=", 1)[1]
confirm = client.get(link.path + "?" + link.query)
result["confirm"] = confirm.status_code
result["confirm_signs_nobody_in"] = client.get("/admin/users").status_code
result["verify"] = client.post("/auth/email/verify", data={"token": token}).status_code
result["admin_after"] = client.get("/admin/users").status_code
other = app.test_client()
result["reused"] = other.post("/auth/email/verify", data={"token": token}).status_code
result["tampered"] = other.post("/auth/email/verify", data={"token": token[:-3] + "abc"}).status_code
print("RESULT " + json.dumps(result))
"""

GOOGLE_ONLY = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
from app import app
app.config["TESTING"] = True
print("RESULT " + json.dumps({"email_login": app.test_client().get("/auth/email/login").status_code}))
"""


def test_a_link_signs_in_once_and_only_after_the_button(scaffold_project):
    result = _run_in_project(scaffold_project(EMAIL_APP), FLOW)
    assert result["method"] == "email"
    status, location, linked = result["anonymous_admin"]
    assert "/auth/email/login" in location or linked, result["anonymous_admin"]  # pointed at email sign-in
    assert result["form"] == 200
    assert result["bad_address"] == 400
    assert result["sent"] == 200 and result["sent_to"] == "owner@test.com"
    # Opening the link shows a button; a mail scanner opening it signs nobody in.
    assert result["confirm"] == 200 and result["confirm_signs_nobody_in"] in (302, 401, 403)
    assert result["verify"] == 302 and result["admin_after"] == 200
    assert result["reused"] == 400
    assert result["tampered"] == 400


OWNER_FIRST_SIGN_IN = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import feather.auth.email_link as email_link
sent = []
email_link.send_link = lambda email, link: sent.append(link) or True
from app import app
from feather.db import db
from models import User
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
with app.app_context():
    db.create_all()
client = app.test_client()

def sign_in(address):
    client.post("/auth/email/login", data={"email": address})
    token = sent[-1].split("token=", 1)[1]
    client.post("/auth/email/verify", data={"token": token})

sign_in("admin@test.com")
owner = client.get("/admin/users").status_code
client.post("/auth/logout")
sign_in("stranger@test.com")
with app.app_context():
    stranger = User.query.filter_by(email="stranger@test.com").one()
    admin = User.query.filter_by(email="admin@test.com").one()
    print("RESULT " + json.dumps({"owner_admin": owner, "admin_role": admin.role, "admin_active": admin.active,
                                  "stranger_active": stranger.active, "stranger_role": stranger.role}))
"""


def test_the_apps_own_admin_is_let_in_on_their_first_sign_in(scaffold_project):
    # Nobody runs seeds.py for an app built for them; the owner must not be
    # locked out of it, and nobody else gets in without approval.
    result = _run_in_project(scaffold_project(EMAIL_APP), OWNER_FIRST_SIGN_IN)
    assert result["owner_admin"] == 200
    assert result["admin_role"] == "admin" and result["admin_active"] is True
    assert result["stranger_active"] is False and result["stranger_role"] == "user"


def test_email_sign_in_is_off_for_a_google_app(scaffold_project):
    result = _run_in_project(scaffold_project({**EMAIL_APP, "sign_in": "google"}), GOOGLE_ONLY)
    assert result["email_login"] == 404
