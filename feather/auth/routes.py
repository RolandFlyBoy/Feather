"""
Authentication Routes
=====================

Basic authentication routes for logout functionality.

The login route should be implemented by your application since it may
require custom logic (email/password, magic links, OAuth only, etc.).

Provided Routes
--------------
- POST /auth/logout - Log out the current user

Usage
-----
Register the blueprint in your app::

    from feather.auth.routes import auth_bp
    app.register_blueprint(auth_bp)

Note:
    This blueprint is NOT automatically registered by Feather.
    Register it manually if you need the /auth/logout route.

Creating a Login Page
--------------------
Create your own login route in routes/pages/::

    # routes/pages/auth.py
    from flask import render_template, redirect, url_for, request
    from flask_login import login_user, current_user
    from feather import page
    from models import User

    @page.get('/login')
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('page.home'))
        return render_template('pages/login.html')

    @page.post('/login')
    def login_post():
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_url = request.args.get('next') or url_for('page.home')
            return redirect(next_url)

        return render_template('pages/login.html', error='Invalid credentials')
"""

from flask import Blueprint, redirect, session, url_for
from flask_login import logout_user, login_required

#: Blueprint for basic auth routes
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Log out the current user.

    Clears the session and redirects to the home page.
    Accepts both GET and POST for convenience.

    Returns:
        Redirect to home page.
    """
    # Everything else in the session (Google access/refresh token, stored
    # next URL, account selection) must go with the login. Clear it BEFORE
    # logout_user(): that call writes the `_remember = "clear"` marker that
    # makes Flask-Login delete the remember-me cookie in after_request, and
    # clearing afterwards discarded the marker, so the cookie survived and
    # the very next request signed the user straight back in.
    session.clear()
    logout_user()
    return redirect(url_for("page.home"))
