import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import os
import base64

# Configuration file path
CONFIG_DIR = "config"
CONFIG_FILE = os.path.abspath(os.path.join('config', 'config.yaml'))

print(f"[DEBUG] CONFIG FILE PATH: {CONFIG_FILE}")
print(f"[DEBUG] Current working directory: {os.getcwd()}")
print(f"[DEBUG] Config exists: {os.path.exists(CONFIG_FILE)}")
print(f"[DEBUG] Config writable: {os.access(CONFIG_FILE, os.W_OK)}")

def initialize_auth():
    """Initialize authentication configuration if it doesn't exist"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    
    if not os.path.exists(CONFIG_FILE):
        # Create a default configuration with one admin user
        default_config = {
            'credentials': {
                'usernames': {
                    'admin': {
                        'name': 'Admin User',
                        'email': 'admin@example.com',
                        'password': stauth.Hasher(['password']).generate()[0],  # Default password: 'password'
                        'is_admin': True
                    }
                }
            },
            'cookie': {
                'expiry_days': 30,
                'key': base64.b64encode(os.urandom(16)).decode(),  # Generate a random key
                'name': 'orionx_podcast_trends_auth'
            },
            'preauthorized': {
                'emails': []
            }
        }
        
        with open(CONFIG_FILE, 'w') as file:
            yaml.dump(default_config, file)
        
        print(f"Created default authentication configuration at {CONFIG_FILE}")
        print("Default username: admin")
        print("Default password: password")
        print("IMPORTANT: Change the default credentials immediately after first login!")

def get_authenticator():
    """Return an authenticator object from the configuration"""
    initialize_auth()
    
    # Initialize session state for authentication if not exists
    if 'auth_initialized' not in st.session_state:
        st.session_state.auth_initialized = False
        st.session_state.authenticator = None
        st.session_state.config = None
        st.session_state.authentication_status = None
        st.session_state.name = None
        st.session_state.username = None
    
    if not st.session_state.auth_initialized:
        # Load config
        with open(CONFIG_FILE, 'r') as file:
            config = yaml.load(file, Loader=SafeLoader)
        
        # Make sure config has the preauthorized key
        if 'preauthorized' not in config:
            config['preauthorized'] = {'emails': []}
        
        # Create authenticator with updated API
        authenticator = stauth.Authenticate(
            credentials=config['credentials'],
            cookie_name=config['cookie']['name'],
            key=config['cookie']['key'],
            cookie_expiry_days=config['cookie']['expiry_days'],
            preauthorized=config['preauthorized']['emails']
        )
        
        # Store in session state
        st.session_state.authenticator = authenticator
        st.session_state.config = config
        st.session_state.auth_initialized = True
    
    return st.session_state.authenticator, st.session_state.config

def save_config(config):
    """Save updated configuration back to file"""
    with open(CONFIG_FILE, 'w') as file:
        yaml.dump(config, file)
    # Reset authentication state to force reload
    st.session_state.auth_initialized = False
    st.session_state.authenticator = None
    st.session_state.config = None
    st.session_state.authentication_status = None
    st.session_state.name = None
    st.session_state.username = None

def display_user_management():
    """Display UI for managing users (admin only)"""
    import os
    st.write("DEBUG: CWD is", os.getcwd())
    st.write("DEBUG session_state:", dict(st.session_state))
    # Show debug and success messages after rerun
    if st.session_state.get('debug_message'):
        st.info(st.session_state['debug_message'])
        del st.session_state['debug_message']
    if st.session_state.get('user_added'):
        st.success("User added successfully!")
        del st.session_state['user_added']
    if st.session_state.get('admin_pw_changed'):
        st.success("Admin password changed successfully!")
        del st.session_state['admin_pw_changed']

    st.title("User Management")
    
    authenticator, _ = get_authenticator()
    # Always reload config from disk to get the latest users
    with open(CONFIG_FILE, 'r') as file:
        config = yaml.load(file, Loader=SafeLoader)
    
    # Only an admin can add users
    if st.session_state.get('username') != 'admin':
        st.warning("Only admin users can manage other users.")
        return
    
    # Display current users
    st.subheader("Current Users")
    
    users_df = []
    for username, user_data in config['credentials']['usernames'].items():
        users_df.append({
            'Username': username,
            'Name': user_data['name'],
            'Email': user_data.get('email', '')
        })
    
    import pandas as pd
    if users_df:
        st.dataframe(pd.DataFrame(users_df))
    
    # Add new user form
    st.subheader("Add New User")
    
    with st.form("add_user_form"):
        new_username = st.text_input("Username")
        new_name = st.text_input("Full Name")
        new_email = st.text_input("Email")
        new_password = st.text_input("Password", type="password")
        new_password_confirm = st.text_input("Confirm Password", type="password")
        
        submitted = st.form_submit_button("Add User")
        
        if submitted:
            with open('debug_user_add.log', 'a') as f:
                f.write(f"User add attempted: {new_username}\n")
            st.write("DEBUG: User add logic reached for", new_username)
            if not new_username or not new_password:
                st.error("Username and password are required")
            elif new_username in config['credentials']['usernames']:
                st.error(f"Username '{new_username}' already exists")
            elif new_password != new_password_confirm:
                st.error("Passwords do not match")
            else:
                # Add the new user
                config['credentials']['usernames'][new_username] = {
                    'name': new_name,
                    'email': new_email,
                    'password': stauth.Hasher([new_password]).generate()[0]
                }
                try:
                    save_config(config)
                    st.session_state['debug_message'] = f"Config saved to: {CONFIG_FILE}"
                except Exception as e:
                    st.session_state['debug_message'] = f"Failed to save config: {e}"
                if 'authenticator' in st.session_state:
                    del st.session_state['authenticator']
                if 'auth_config' in st.session_state:
                    del st.session_state['auth_config']
                st.session_state['user_added'] = True
                st.session_state['show_user_management'] = True
                st.rerun()
    
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
                st.rerun()
    else:
        st.info("No users to remove")
    
    # Change password for admin
    st.subheader("Change Admin Password")
    
    with st.form("change_admin_password"):
        current_password = st.text_input("Current Password", type="password")
        new_admin_password = st.text_input("New Password", type="password")
        new_admin_password_confirm = st.text_input("Confirm New Password", type="password")
        
        password_submitted = st.form_submit_button("Change Password")
        
        if password_submitted:
            with open('debug_user_add.log', 'a') as f:
                f.write(f"Admin password change attempted\n")
            st.write("DEBUG: Admin password change logic reached")
            if not stauth.Hasher([current_password]).verify(config['credentials']['usernames']['admin']['password']):
                st.error("Current password is incorrect")
            elif new_admin_password != new_admin_password_confirm:
                st.error("New passwords do not match")
            else:
                config['credentials']['usernames']['admin']['password'] = stauth.Hasher([new_admin_password]).generate()[0]
                try:
                    save_config(config)
                    st.session_state['debug_message'] = f"Config saved to: {CONFIG_FILE}"
                except Exception as e:
                    st.session_state['debug_message'] = f"Failed to save config: {e}"
                if 'authenticator' in st.session_state:
                    del st.session_state['authenticator']
                if 'auth_config' in st.session_state:
                    del st.session_state['auth_config']
                st.session_state['admin_pw_changed'] = True
                st.session_state['show_user_management'] = True
                st.rerun()
