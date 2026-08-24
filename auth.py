# auth.py
"""Registro/login normal y 'Continuar con Google' (OAuth 2.0 manual, sin
Authlib: el flujo es simple y `requests` ya es una dependencia del
proyecto). El propósito actual es únicamente dejar entrar a los usuarios
para que puedan generar documentos ilimitados mientras se decide cuándo
activar un plan de pago (ver comentario en app.py sobre user_can_generate).
"""

import os
import re
import secrets
import logging
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

import db

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', '')

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'


def google_oauth_enabled():
    """El botón 'Continuar con Google' sólo se muestra si las tres variables
    están configuradas; si falta alguna, se oculta en vez de romper la
    página (ver GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI en .env.example)."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)


def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.get_user_by_id(user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login', next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user['is_admin']:
            return redirect(url_for('welcome'))
        return view(*args, **kwargs)
    return wrapped


def _log_in_as(user_id):
    session.clear()
    session['user_id'] = user_id


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('welcome'))

    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not name:
            error = 'Escribe tu nombre.'
        elif not EMAIL_RE.match(email):
            error = 'Ese correo no parece válido.'
        elif len(password) < 8:
            error = 'La contraseña debe tener al menos 8 caracteres.'
        elif db.get_user_by_email(email):
            error = 'Ya existe una cuenta con ese correo. Inicia sesión.'
        else:
            user_id = db.create_user(email, name, password_hash=generate_password_hash(password))
            _log_in_as(user_id)
            return redirect(url_for('welcome'))

    return render_template('register.html', error=error, google_enabled=google_oauth_enabled())


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('welcome'))

    next_url = request.values.get('next') or url_for('welcome')
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = db.get_user_by_email(email)

        if not user or not user['password_hash'] or not check_password_hash(user['password_hash'], password):
            error = 'Correo o contraseña incorrectos.'
        else:
            db.touch_admin_status(user)
            _log_in_as(user['id'])
            return redirect(next_url)

    return render_template('login.html', error=error, next=next_url, google_enabled=google_oauth_enabled())


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('welcome'))


@auth_bp.route('/auth/google')
def google_start():
    if not google_oauth_enabled():
        return redirect(url_for('auth.login'))

    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    session['oauth_next'] = request.args.get('next') or url_for('welcome')

    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    return redirect(f'{GOOGLE_AUTH_URL}?{urlencode(params)}')


@auth_bp.route('/auth/google/callback')
def google_callback():
    if not google_oauth_enabled():
        return redirect(url_for('auth.login'))

    expected_state = session.pop('oauth_state', None)
    if not expected_state or request.args.get('state') != expected_state:
        logger.warning('Estado OAuth inválido al volver de Google (posible CSRF).')
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        return redirect(url_for('auth.login'))

    try:
        token_resp = requests.post(GOOGLE_TOKEN_URL, data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': GOOGLE_REDIRECT_URI,
            'grant_type': 'authorization_code',
        }, timeout=10)
        token_resp.raise_for_status()
        access_token = token_resp.json().get('access_token')

        info_resp = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        info_resp.raise_for_status()
        info = info_resp.json()
    except requests.RequestException as e:
        logger.error('Error en el intercambio OAuth con Google: %s', e)
        return redirect(url_for('auth.login'))

    google_id = info.get('sub')
    email = (info.get('email') or '').strip().lower()
    name = info.get('name') or (email.split('@')[0] if email else 'Usuario')

    if not google_id or not email:
        logger.error('Respuesta de Google sin sub/email, no se puede iniciar sesión.')
        return redirect(url_for('auth.login'))

    user = db.get_user_by_google_id(google_id)
    if not user:
        # Puede que ya tenga cuenta por registro normal con el mismo correo:
        # se enlaza en vez de crear un usuario duplicado.
        user = db.get_user_by_email(email)
        if user:
            db.link_google_id(user['id'], google_id)
        else:
            user_id = db.create_user(email, name, google_id=google_id)
            user = db.get_user_by_id(user_id)

    # Hay que leer oauth_next ANTES de _log_in_as: ese helper hace
    # session.clear() para arrancar la sesión limpia, y se llevaría la
    # clave por delante si se leyera después.
    next_url = session.get('oauth_next') or url_for('welcome')
    db.touch_admin_status(user)
    _log_in_as(user['id'])
    return redirect(next_url)
