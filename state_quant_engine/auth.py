"""Authentication gate for STATE Quant Engine."""
from __future__ import annotations
import streamlit as st


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
                from state_quant_engine.database.connection import get_session
                from state_quant_engine.repositories.user_repository import UserRepository
                session = get_session()
                try:
                    user = UserRepository(session).verify(username.strip(), password)
                    if user:
                        st.session_state["authenticated"] = True
                        st.session_state["username"]      = user.username
                        st.session_state["is_admin"]      = user.is_admin
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
                finally:
                    session.close()

    return False
