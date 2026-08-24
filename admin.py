# admin.py
"""Panel admin sencillo: usuarios, tokens de Gemini usados y documentos
generados. Sólo lectura — no hay edición de usuarios ni de planes desde
aquí todavía."""

from flask import Blueprint, render_template

import db
from auth import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
@admin_required
def dashboard():
    return render_template(
        'admin.html',
        stats=db.get_stats(),
        users=db.list_users(),
        documents=db.list_documents(limit=100),
    )
