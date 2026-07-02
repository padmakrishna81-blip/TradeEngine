"""Authentication gate for STATE Quant Engine."""
from __future__ import annotations
import hashlib
import streamlit as st


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _load_users() -> dict:
    """Load users from Streamlit secrets or fall back to a default."""
    try:
        users = dict(st.secrets.get("users", {}))
        if users:
            return users
    except Exception:
        pass
    # Default credential when no secrets are configured
    # username: admin  password: sqe@2024
    return {
        "admin": "62a58963e94473ed83020b67aff0acf76338c53839185d31ee1ee6dd306dc79b"
    }


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
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", type="primary",
                                               use_container_width=True)
            if submitted:
                users = _load_users()
                pw_hash = _hash(password)
                if username in users and users[username] == pw_hash:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = username
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    return False
