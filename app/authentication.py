import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import os
import base64

# Configuration file path
CONFIG_DIR = "config"
CONFIG_FILE = os.path.abspath(os.path.join('config', 'config.yaml'))

print(f"[DEBUG] AUTH: CONFIG_FILE path: {CONFIG_FILE}")
print(f"[DEBUG] AUTH: Current working directory: {os.getcwd()}")
print(f"[DEBUG] AUTH: Config exists: {os.path.exists(CONFIG_FILE)}")

def initialize_auth():
    """Initialize authentication configuration if it doesn't exist"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            'credentials': {
                'usernames': {
                    'admin': {
                        'name': 'Admin User',
                        'email': 'admin@example.com',
                        'password': stauth.Hasher(['password']).generate()[0],
                        'is_admin': True
                    }
                }
            },
            'cookie': {
                'expiry_days': 30,
                'key': base64.b64encode(os.urandom(16)).decode(),
                'name': 'orionx_podcast_trends_auth'
            },
            'preauthorized': {'emails': []}
        }
        with open(CONFIG_FILE, 'w') as file:
            yaml.dump(default_config, file)
        print(f"[DEBUG] AUTH: Created default config at {CONFIG_FILE}")
        print("IMPORTANT: Default admin/password created. Change immediately!")

def get_authenticator():
    """Return an authenticator object, aggressively re-initializing if necessary."""
    initialize_auth()

    # Determine if a full re-initialization is needed
    if not st.session_state.get('auth_initialized', False) or \
       st.session_state.get('authenticator') is None:
        
        print("[DEBUG] AUTH: Forcing full reset and re-creation of authenticator.")
        
        # Explicitly delete all known auth-related keys from session state
        keys_to_delete = ['authenticator', 'config', 'authentication_status', 'name', 'username', 'auth_initialized']
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
        
        print(f"[DEBUG] AUTH: Loading config from {CONFIG_FILE} for re-initialization.")
        try:
            with open(CONFIG_FILE, 'r') as file:
                config_data = yaml.load(file, Loader=SafeLoader)
            if not config_data or 'credentials' not in config_data or 'cookie' not in config_data:
                print("[DEBUG] AUTH: Config file is invalid or missing crucial keys during re-init.")
                st.error("Authentication configuration is invalid. Please check config.yaml.")
                st.stop()
            print(f"[DEBUG] AUTH: Config loaded for re-init. Users: {list(config_data.get('credentials', {}).get('usernames', {}).keys())}")
        except Exception as e:
            print(f"[DEBUG] AUTH: Critical error loading config during re-init: {e}")
            st.error(f"Fatal error: Could not load authentication configuration: {e}")
            st.stop()

        if 'preauthorized' not in config_data:
            config_data['preauthorized'] = {'emails': []}

        try:
            auth_obj = stauth.Authenticate(
                credentials=config_data['credentials'],
                cookie_name=config_data['cookie']['name'],
                key=config_data['cookie']['key'],
                cookie_expiry_days=config_data['cookie']['expiry_days'],
                preauthorized=config_data['preauthorized']['emails']
            )
            print("[DEBUG] AUTH: Authenticator object re-created successfully.")
        except Exception as e:
            print(f"[DEBUG] AUTH: Critical error re-creating authenticator: {e}")
            st.error(f"Fatal error: Could not initialize authenticator: {e}")
            st.stop()

        st.session_state.authenticator = auth_obj
        st.session_state.config = config_data
        st.session_state.auth_initialized = True # Mark as initialized *after* successful creation
        print("[DEBUG] AUTH: Authentication fully re-initialized and stored in session state.")
    else:
        print("[DEBUG] AUTH: Using existing authenticator from session state.")
            
    return st.session_state.authenticator, st.session_state.config

def save_config(config_to_save):
    """Save updated configuration and force a full auth reset for the next load."""
    try:
        with open(CONFIG_FILE, 'w') as file:
            yaml.dump(config_to_save, file)
        print(f"[DEBUG] AUTH: Config saved to {CONFIG_FILE}.")
    except Exception as e:
        print(f"[DEBUG] AUTH: Error saving config: {e}")
        st.error(f"Error saving configuration: {e}")
        return

    print("[DEBUG] AUTH: Config saved. Forcing full auth reset for next interaction.")
    # Explicitly delete all known auth-related keys to force re-creation by get_authenticator
    keys_to_delete = ['authenticator', 'config', 'authentication_status', 'name', 'username', 'auth_initialized']
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
    # Setting auth_initialized to False here is also an option, but deleting ensures it.
    # st.session_state.auth_initialized = False

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
