import streamlit as st
st.set_page_config(page_title="User Management", layout="wide", page_icon="👤")

# Add CSS to hide sidebar initially
st.markdown("""
    <style>
        section[data-testid="stSidebar"] {
            display: none;
        }
    </style>
""", unsafe_allow_html=True)

import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import os
import base64
import pandas as pd
import bcrypt
import sys
# Add the project root to the Python path to allow importing from 'app'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from app.authentication import get_authenticator, save_config, CONFIG_FILE

# --- Authentication ---
authenticator, _ = get_authenticator()
name, authentication_status, username = authenticator.login(
    fields={'form_name': 'User Management Login', 'location': 'main'}
)

if authentication_status == False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status == None:
    st.warning('Please enter your username and password')
    st.stop()
else:
    # Show the sidebar after successful authentication
    st.markdown("""
        <style>
            section[data-testid="stSidebar"] {
                display: block;
            }
        </style>
    """, unsafe_allow_html=True)
    
    if authenticator.logout(button_name='Logout', location='sidebar', key='logout-user-management'):
        st.rerun()
    st.sidebar.write(f'Welcome *{name}*')

    # Only an admin can add users
    with open(CONFIG_FILE, 'r') as file:
        config = yaml.load(file, Loader=SafeLoader)
    if not config['credentials']['usernames'][username].get('is_admin', False):
        st.warning("Only admin users can manage other users.")
        st.stop()

    st.title("User Management")

    # Always reload config from disk to get the latest users
    with open(CONFIG_FILE, 'r') as file:
        config = yaml.load(file, Loader=SafeLoader)

    # Display current users with admin status
    st.subheader("Current Users")
    users_df = []
    for uname, user_data in config['credentials']['usernames'].items():
        users_df.append({
            'Username': uname,
            'Name': user_data['name'],
            'Email': user_data.get('email', ''),
            'Admin': user_data.get('is_admin', False)
        })
    if users_df:
        st.dataframe(pd.DataFrame(users_df))

    # Toggle admin status for users (except yourself)
    st.subheader("Toggle Admin Status")
    toggle_usernames = [u for u in config['credentials']['usernames'].keys() if u != username]
    if toggle_usernames:
        user_to_toggle = st.selectbox("Select user to toggle admin status", toggle_usernames, key="toggle_admin_user")
        current_status = config['credentials']['usernames'][user_to_toggle].get('is_admin', False)
        if st.button(f"{'Revoke' if current_status else 'Grant'} Admin", key="toggle_admin_btn"):
            config['credentials']['usernames'][user_to_toggle]['is_admin'] = not current_status
            save_config(config)
            st.success(f"{'Granted' if not current_status else 'Revoked'} admin rights for '{user_to_toggle}'")

    # Add new user form
    st.subheader("Add New User")
    with st.form("add_user_form"):
        new_username = st.text_input("Username")
        new_name = st.text_input("Full Name")
        new_email = st.text_input("Email")
        new_password = st.text_input("Password", type="password")
        new_password_confirm = st.text_input("Confirm Password", type="password")
        new_is_admin = st.checkbox("Grant admin rights to this user?")
        submitted = st.form_submit_button("Add User")
        if submitted:
            if not new_username or not new_password:
                st.error("Username and password are required")
            elif new_username in config['credentials']['usernames']:
                st.error(f"Username '{new_username}' already exists")
            elif new_password != new_password_confirm:
                st.error("Passwords do not match")
            else:
                config['credentials']['usernames'][new_username] = {
                    'name': new_name,
                    'email': new_email,
                    'password': stauth.Hasher([new_password]).generate()[0],
                    'is_admin': new_is_admin
                }
                try:
                    save_config(config)
                    st.success(f"User '{new_username}' added successfully!")
                except Exception as e:
                    st.error(f"Failed to save config: {e}")

    # Remove user
    st.subheader("Remove User")
    usernames = list(config['credentials']['usernames'].keys())
    usernames = [u for u in usernames if u != 'admin']  # Cannot remove admin
    if usernames:
        username_to_remove = st.selectbox("Select user to remove", usernames)
        if st.button("Remove User"):
            if username_to_remove == 'admin':
                st.error("Cannot remove the admin user")
            else:
                del config['credentials']['usernames'][username_to_remove]
                save_config(config)
                st.success(f"User '{username_to_remove}' removed successfully")
    else:
        st.info("No users to remove")

    # Reset password for any user (except yourself)
    st.subheader("Reset User Password")
    reset_usernames = [u for u in config['credentials']['usernames'].keys() if u != username]
    if reset_usernames:
        user_to_reset = st.selectbox("Select user to reset password", reset_usernames, key="reset_pw_user")
        with st.form("reset_user_password_form"):
            new_pw = st.text_input("New Password", type="password", key="reset_pw")
            new_pw_confirm = st.text_input("Confirm New Password", type="password", key="reset_pw_confirm")
            reset_submitted = st.form_submit_button("Reset Password")
            if reset_submitted:
                if not new_pw:
                    st.error("New password is required")
                elif new_pw != new_pw_confirm:
                    st.error("Passwords do not match")
                else:
                    config['credentials']['usernames'][user_to_reset]['password'] = stauth.Hasher([new_pw]).generate()[0]
                    try:
                        save_config(config)
                        st.success(f"Password for '{user_to_reset}' has been reset.")
                    except Exception as e:
                        st.error(f"Failed to save config: {e}")
    else:
        st.info("No users available for password reset.")

    # Change password for admin
    st.subheader("Change Admin Password")
    with st.form("change_admin_password"):
        current_password = st.text_input("Current Password", type="password")
        new_admin_password = st.text_input("New Password", type="password")
        new_admin_password_confirm = st.text_input("Confirm New Password", type="password")
        password_submitted = st.form_submit_button("Change Password")
        if password_submitted:
            st.write("DEBUG: Entered password change block")
            st.write("DEBUG: Current hash in config:", config['credentials']['usernames']['admin']['password'])
            try:
                check_result = bcrypt.checkpw(current_password.encode(), config['credentials']['usernames']['admin']['password'].encode())
            except Exception as e:
                st.write("DEBUG: bcrypt error:", e)
                check_result = False
            st.write("DEBUG: bcrypt check result:", check_result)
            if not check_result:
                st.error("Current password is incorrect")
            elif new_admin_password != new_admin_password_confirm:
                st.error("New passwords do not match")
            else:
                new_hash = stauth.Hasher([new_admin_password]).generate()[0]
                st.write("DEBUG: New hash to be saved:", new_hash)
                config['credentials']['usernames']['admin']['password'] = new_hash
                try:
                    save_config(config)
                    st.success("Admin password changed successfully! Please log in again with your new password.")
                    st.session_state.clear()
                except Exception as e:
                    st.error(f"Failed to save config: {e}") 