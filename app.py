import streamlit as st
import time

# --- 1. SESSION STATE INITIALIZATION ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# State for the Phase 3 Setup Wizard
if 'setup_step' not in st.session_state:
    st.session_state.setup_step = 1
if 'setup_data' not in st.session_state:
    st.session_state.setup_data = {
        "brand": "", "region": "", "location": "", "platform": "Google Business Profile", "external_id": ""
    }

def handle_login():
    st.session_state.logged_in = True

def handle_logout():
    st.session_state.logged_in = False
    st.session_state.setup_step = 1 # Reset setup if they log out

# Wizard Navigation Helpers
def next_step(): st.session_state.setup_step += 1
def prev_step(): st.session_state.setup_step -= 1

# --- 2. THE LOGIN PAGE (Phase 2) ---
if not st.session_state.logged_in:
    st.title("Sign in to your tenant")
    
    with st.form("login_form"):
        tenant = st.text_input("Tenant Slug")
        email = st.text_input("Email address")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)
        
        if submitted:
            if email and password:
                handle_login()
                st.rerun()
            else:
                st.error("Please fill out all fields.")

# --- 3. PROTECTED LAYOUT & SETUP WIZARD (Phase 1 & 3) ---
if st.session_state.logged_in:
    # Sidebar
    st.sidebar.title("Reputation App")
    page = st.sidebar.radio("Navigation", ["Dashboard", "Setup Wizard", "Connectors", "Reviews", "Reports"])
    
    st.sidebar.divider()
    st.sidebar.button("Logout", on_click=handle_logout)
    
    # --- PHASE 3: SETUP WIZARD VIEW ---
    if page == "Setup Wizard":
        st.header("Set up your workspace")
        st.caption("Create your organizational hierarchy to start syncing reviews.")
        
        # Custom Progress Bar logic
        steps = ["1. Brand", "2. Region", "3. Location", "4. Connector"]
        step = st.session_state.setup_step
        
        cols = st.columns(4)
        for i, col in enumerate(cols):
            if i + 1 == step:
                col.markdown(f"**🔵 {steps[i]}**")
            elif i + 1 < step:
                col.markdown(f"✅ {steps[i]}")
            else:
                col.markdown(f"⚪ {steps[i]}")
        st.divider()

        # Step 1: Brand
        if step == 1:
            st.subheader("Create your first Brand")
            st.session_state.setup_data["brand"] = st.text_input("Brand Name", value=st.session_state.setup_data["brand"], placeholder="e.g., Starbucks")
            if st.button("Next ➡️", type="primary"):
                if st.session_state.setup_data["brand"]:
                    next_step()
                    st.rerun()
                else:
                    st.error("Please enter a brand name.")

        # Step 2: Region
        elif step == 2:
            st.subheader("Create a Region")
            st.session_state.setup_data["region"] = st.text_input("Region Name", value=st.session_state.setup_data["region"], placeholder="e.g., North America")
            col1, col2 = st.columns([1, 6])
            with col1: st.button("⬅️ Back", on_click=prev_step)
            with col2: 
                if st.button("Next ➡️", type="primary"):
                    next_step()
                    st.rerun()

        # Step 3: Location
        elif step == 3:
            st.subheader("Add a Location")
            st.session_state.setup_data["location"] = st.text_input("Location Name / Identifier", value=st.session_state.setup_data["location"], placeholder="e.g., Store #1402 - Times Square")
            col1, col2 = st.columns([1, 6])
            with col1: st.button("⬅️ Back", on_click=prev_step)
            with col2: 
                if st.button("Next ➡️", type="primary"):
                    next_step()
                    st.rerun()

        # Step 4: Connector
        elif step == 4:
            st.subheader("Attach a Review Connector")
            st.session_state.setup_data["platform"] = st.selectbox("Platform", ["Google Business Profile", "Trustpilot", "Google Play Store", "Glassdoor"])
            st.session_state.setup_data["external_id"] = st.text_input("External Platform ID", value=st.session_state.setup_data["external_id"], placeholder="e.g., ChIJN1t_tDeuEmsRUsoyG83frY4")
            
            col1, col2 = st.columns([1, 6])
            with col1: st.button("⬅️ Back", on_click=prev_step)
            with col2: 
                if st.button("✅ Complete Setup", type="primary"):
                    # Mocking an API call delay
                    with st.spinner("Provisioning workspace..."):
                        time.sleep(1.5)
                        st.success(f"Success! {st.session_state.setup_data['brand']} is now configured.")
                        # In a real app, you'd send st.session_state.setup_data to your FastApi backend here
                        st.session_state.setup_step = 1 # Reset wizard
                        st.balloons()

    # Placeholder Views for the other sidebar tabs
    elif page == "Dashboard":
        st.header("Analytics Dashboard")
        st.info("KPI widgets and charts will go here.")
    elif page == "Connectors":
        st.header("Connector Management")
        st.info("Table of active data syncs will go here.")
    elif page == "Reviews":
        st.header("Review Browser")
        st.info("Filterable list of all reviews will go here.")
    elif page == "Reports":
        st.header("Data Export")
        st.info("Excel download buttons will go here.")