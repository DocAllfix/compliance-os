"""
Modulo Auth Manager per Amisys QHSE
Gestisce autenticazione multi-utente con ruoli admin/auditor
Sicurezza: bcrypt per hashing password (resistente a rainbow tables)
"""

import hashlib
import json
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from pathlib import Path

# Path del file utenti
CONFIG_DIR = Path(__file__).parent.parent / "config"
USERS_FILE = CONFIG_DIR / "users.json"
SESSIONS_FILE = CONFIG_DIR / "sessions.json"  # Nuovo: file per sessioni persistenti

# Marker per identificare hash bcrypt vs SHA-256 legacy
BCRYPT_PREFIX = "$2b$"

# Durata sessione (24 ore)
SESSION_DURATION_HOURS = 24


def hash_password(password: str) -> str:
    """Hash password con bcrypt (sicuro, include salt automatico)."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=10)  # 10 rounds = ~100ms, buon compromesso sicurezza/velocità
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifica password contro hash.
    Supporta sia bcrypt (nuovo) che SHA-256 (legacy per migrazione).
    """
    if hashed.startswith(BCRYPT_PREFIX):
        # Nuovo formato bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    else:
        # Legacy SHA-256 (per migrazione password esistenti)
        salt = "AUDITOS_SECURE_SALT_2026"
        legacy_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return legacy_hash == hashed


def hash_password_legacy(password: str) -> str:
    """Hash legacy SHA-256 (solo per confronto durante migrazione)."""
    salt = "AUDITOS_SECURE_SALT_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def load_users() -> Dict:
    """Carica utenti dal file JSON."""
    if not USERS_FILE.exists():
        # Crea file utenti default se non esiste
        create_default_users()
    
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(users: Dict):
    """Salva utenti nel file JSON."""
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def create_default_users():
    """Bootstrap del primo utente admin (eseguito SOLO se users.json non esiste).

    Fase 3 consolidamento: rimosse le 6 password hardcoded nel sorgente.
    La password admin iniziale viene da COMPLIANCE_ADMIN_PASSWORD (env);
    in assenza, ne viene generata una casuale e STAMPATA UNA SOLA VOLTA
    all'avvio — va cambiata o annotata subito. Gli utenti aggiuntivi si
    creano cambiando users.json o via strumenti admin.
    """
    import secrets

    admin_password = os.environ.get("COMPLIANCE_ADMIN_PASSWORD", "").strip()
    generated = False
    if not admin_password:
        admin_password = secrets.token_urlsafe(9)
        generated = True

    users = {
        "admin": {
            "name": "Administrator",
            "password": hash_password(admin_password),
            "role": "admin",
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "active": True,
        },
    }
    save_users(users)

    if generated:
        print("=" * 62)
        print("  Amisys QHSE — primo avvio: creato l'utente 'admin'.")
        print(f"  Password generata (NON verrà più mostrata): {admin_password}")
        print("  Impostare COMPLIANCE_ADMIN_PASSWORD in .env per controllarla.")
        print("=" * 62)
    return users


def authenticate(username: str, password: str) -> Tuple[bool, Optional[str]]:
    """
    Verifica le credenziali utente.
    Migra automaticamente password legacy SHA-256 a bcrypt al primo login.
    
    Returns:
        (success, error_message)
    """
    users = load_users()
    
    username_lower = username.lower().strip()
    
    if username_lower not in users:
        return False, "Username non trovato"
    
    user = users[username_lower]
    
    if not user.get("active", True):
        return False, "Account disabilitato"
    
    # Usa verify_password che supporta sia bcrypt che SHA-256 legacy
    if not verify_password(password, user["password"]):
        return False, "Password errata"
    
    # MIGRAZIONE AUTOMATICA: se la password è ancora SHA-256, aggiornala a bcrypt
    if not user["password"].startswith(BCRYPT_PREFIX):
        users[username_lower]["password"] = hash_password(password)
        # Salva subito la password migrata
    
    # Aggiorna last_login
    users[username_lower]["last_login"] = datetime.now().isoformat()
    save_users(users)
    
    return True, None


# Fase 1 consolidamento: rimosso il blocco sessione Streamlit (get_current_user,
# is_logged_in, is_admin, get_user_display_name) — era l'UI dell'app legacy
# AUDITORSEMI. L'identità utente nell'API REST viene dal Bearer token
# (api_server._get_current_user), non da st.session_state.


# ==============================================================================
# SESSIONI PERSISTENTI - Mantiene login dopo refresh
# ==============================================================================

def generate_session_token() -> str:
    """Genera un token di sessione univoco."""
    import secrets
    return secrets.token_urlsafe(32)


def load_sessions() -> Dict:
    """Carica sessioni dal file JSON."""
    if not SESSIONS_FILE.exists():
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_sessions(sessions: Dict):
    """Salva sessioni nel file JSON."""
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)


def create_persistent_session(username: str) -> str:
    """
    Crea una sessione persistente per l'utente.
    Ritorna il token da salvare nei query params.
    """
    token = generate_session_token()
    sessions = load_sessions()
    
    # Pulisci sessioni scadute
    now = datetime.now()
    sessions = {
        t: s for t, s in sessions.items()
        if datetime.fromisoformat(s["expires"]) > now
    }
    
    # Aggiungi nuova sessione
    sessions[token] = {
        "username": username,
        "created": now.isoformat(),
        "expires": (now + timedelta(hours=SESSION_DURATION_HOURS)).isoformat()
    }
    
    save_sessions(sessions)
    return token


def validate_session_token(token: str) -> Optional[str]:
    """
    Verifica se un token di sessione è valido.
    Ritorna lo username se valido, None altrimenti.
    """
    if not token:
        return None
    
    sessions = load_sessions()
    
    if token not in sessions:
        return None
    
    session = sessions[token]
    expires = datetime.fromisoformat(session["expires"])
    
    if datetime.now() > expires:
        # Sessione scaduta, rimuovi
        del sessions[token]
        save_sessions(sessions)
        return None
    
    return session["username"]


def invalidate_session_token(token: str):
    """Invalida un token di sessione (per logout)."""
    sessions = load_sessions()
    if token in sessions:
        del sessions[token]
        save_sessions(sessions)


# Fase 1 consolidamento: rimosse restore_session_from_token / logout / login —
# funzioni di sessione Streamlit dell'app legacy. Il flusso REST equivalente è
# authenticate + create_persistent_session (login) e invalidate_session_token
# (logout), già usati da api_server.


def change_password(username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
    """Cambia la password di un utente."""
    users = load_users()
    username_lower = username.lower().strip()

    if username_lower not in users:
        return False, "Utente non trovato"

    # Fase 1 consolidamento: hash_password() genera un salt bcrypt nuovo a ogni
    # chiamata, quindi il confronto diretto fra hash falliva SEMPRE. La verifica
    # corretta passa da verify_password (gestisce anche gli hash legacy SHA-256).
    if not verify_password(old_password, users[username_lower]["password"]):
        return False, "Password attuale errata"
    
    if len(new_password) < 6:
        return False, "La nuova password deve avere almeno 6 caratteri"
    
    users[username_lower]["password"] = hash_password(new_password)
    save_users(users)
    
    return True, "Password cambiata con successo"


def admin_reset_password(username: str, new_password: str,
                          caller_role: str = "") -> Tuple[bool, str]:
    """Admin resetta la password di un utente.

    Fase 1 consolidamento: il check ruolo ora arriva dal chiamante (l'identità
    nell'API REST viene dal Bearer token), non più da st.session_state.
    """
    if caller_role != "admin":
        return False, "Solo l'admin può resettare le password"

    users = load_users()
    username_lower = username.lower().strip()
    
    if username_lower not in users:
        return False, "Utente non trovato"
    
    if len(new_password) < 6:
        return False, "La password deve avere almeno 6 caratteri"
    
    users[username_lower]["password"] = hash_password(new_password)
    save_users(users)
    
    return True, f"Password di {username} resettata"


def get_all_users() -> Dict:
    """Ritorna tutti gli utenti (solo per admin)."""
    return load_users()


# Fase 1 consolidamento: rimosse render_login_page / render_user_menu — UI
# Streamlit dell'app legacy. Il login Amisys QHSE vive nel frontend React
# (frontend/src/pages/Login.tsx) via POST /api/auth/login.


# Inizializza file utenti se necessario
if not USERS_FILE.exists():
    create_default_users()
