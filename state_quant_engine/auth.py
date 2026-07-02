"""Authentication gate for STATE Quant Engine."""
from __future__ import annotations
import hashlib
import streamlit as st

# Hardcoded fallback — works even when DB is empty or unreachable
_FALLBACK_USERS = {
    "admin": hashlib.sha256("sqe@2024".encode()).hexdigest(),
}


def _try_db_verify(username: str, password: str):
    """Try DB lookup; return user object or None. Never raises."""
    try:
        from state_quant_engine.database.connection import get_session
        from state_quant_engine.repositories.user_repository import UserRepository
        session = get_session()
        try:
            return UserRepository(session).verify(username, password)
        finally:
            session.close()
    except Exception:
        return None


def _fallback_verify(username: str, password: str) -> bool:
    """Verify against hardcoded fallback credentials."""
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    return _FALLBACK_USERS.get(username) == pw_hash


def check_auth() -> bool:
    """Return True if the user is authenticated. Show login form if not."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <div style='text-align:center;padding:40px 0 20px'>
          <span style='font-size:2.5em'>📈</span>
          <h2 style='margin:8px 0 4px'>STATE Quant Engine</h2>
          <p style='color:#888;font-size:0.9em'>Please sign in to continue</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col = st.columns([1, 2, 1])[1]
    with col:
        with st.form("login_form"):
            username  = st.text_input("Username")
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", type="primary",
                                               use_container_width=True)
            if submitted:
                uname = username.strip()
                # Try DB first, fall back to hardcoded credentials
                db_user  = _try_db_verify(uname, password)
                fallback = _fallback_verify(uname, password)

                if db_user or fallback:
                    st.session_state["authenticated"] = True
                    st.session_state["username"]      = uname
                    st.session_state["is_admin"]      = getattr(db_user, "is_admin", True) if db_user else True
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    return False
