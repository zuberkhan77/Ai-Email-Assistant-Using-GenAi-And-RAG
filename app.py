import requests
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="AI Email Assistant",
    page_icon="📧",
    layout="wide"
)


BACKEND_URL = "http://127.0.0.1:8000"


# ==================================================
# SESSION STATE
# ==================================================

if "emails" not in st.session_state:
    st.session_state.emails = []

if "email_details" not in st.session_state:
    st.session_state.email_details = None

if "analysis" not in st.session_state:
    st.session_state.analysis = None

if "reply" not in st.session_state:
    st.session_state.reply = None


# ==================================================
# BACKEND FUNCTIONS
# ==================================================

def fetch_emails():
    try:
        response = requests.get(
            f"{BACKEND_URL}/emails",
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()

            st.session_state.emails = data["emails"]
            st.session_state.email_details = None
            st.session_state.analysis = None
            st.session_state.reply = None

            return True, f"Fetched {data['count']} emails."

        return False, "Failed to fetch emails."

    except requests.RequestException:
        return False, "Could not connect to FastAPI."


def search_emails(query):
    try:
        response = requests.get(
            f"{BACKEND_URL}/search-emails",
            params={"query": query},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()

            st.session_state.emails = data.get(
                "emails",
                []
            )

            st.session_state.email_details = None
            st.session_state.analysis = None
            st.session_state.reply = None

            return True, data

        return False, response.text

    except requests.RequestException as error:
        return False, str(error)


def open_email(email_id):
    try:
        response = requests.get(
            f"{BACKEND_URL}/emails/{email_id}",
            timeout=10
        )

        if response.status_code == 200:
            st.session_state.email_details = response.json()
            st.session_state.analysis = None
            st.session_state.reply = None

            return True

        return False

    except requests.RequestException:
        return False


def analyze_email(email_id):
    try:
        response = requests.get(
            f"{BACKEND_URL}/emails/{email_id}/analyze",
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()

            st.session_state.analysis = data["analysis"]

            return True, ""

        return False, response.text

    except requests.RequestException as error:
        return False, str(error)


def generate_reply(
    email_id,
    analysis,
    human_guidance=None
):
    try:
        response = requests.post(
            f"{BACKEND_URL}/emails/{email_id}/generate-reply",
            json={
                "analysis": analysis,
                "human_guidance": human_guidance
            },
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()

            st.session_state.reply = data["reply"]

            return True, ""

        return False, response.text

    except requests.RequestException as error:
        return False, str(error)


def send_reply(email_id, reply):
    try:
        response = requests.post(
            f"{BACKEND_URL}/emails/{email_id}/send-reply",
            json={
                "reply": reply
            },
            timeout=30
        )

        if response.status_code == 200:
            return True, response.json()

        return False, response.text

    except requests.RequestException as error:
        return False, str(error)


# ==================================================
# PAGE TITLE
# ==================================================

st.title("AI Email Assistant")


# ==================================================
# THREE-COLUMN LAYOUT
# ==================================================

inbox_col, email_col, analysis_col = st.columns(
    [1.1, 2.5, 1.5],
    gap="medium"
)


# ==================================================
# LEFT COLUMN — INBOX
# ==================================================

with inbox_col:

    st.header("📧 Inbox")

    if st.button(
        "🔄 Fetch Emails",
        use_container_width=True
    ):
        success, message = fetch_emails()

        if success:
            st.success(message)
        else:
            st.error(message)

    st.divider()

    # Search
    search_query = st.text_input(
        "🔎 Search Emails",
        placeholder="e.g. internship, interview, subject:offer"
    )

    if st.button(
        "Search",
        use_container_width=True
    ):
        if not search_query.strip():

            st.warning(
                "Enter something to search."
            )

        else:

            success, result = search_emails(
                search_query.strip()
            )

            if success:

                count = result.get(
                    "count",
                    len(result.get("emails", []))
                )

                source = result.get(
                    "source",
                    ""
                )

                if source == "chroma":

                    st.success(
                        f"Found {count} emails from local history."
                    )

                elif source == "gmail":

                    st.success(
                        f"Found {count} emails from Gmail."
                    )

                else:

                    st.success(
                        f"Found {count} emails."
                    )

            else:

                st.error(
                    "Email search failed."
                )

    st.divider()

    # Email list
    if not st.session_state.emails:

        st.caption(
            "No emails loaded."
        )

    else:

        for email in st.session_state.emails:

            subject = email.get(
                "subject",
                "(No Subject)"
            )

            if not subject:
                subject = "(No Subject)"

            if len(subject) > 35:
                subject = subject[:35] + "..."

            if st.button(
                subject,
                key=f"email_{email['id']}",
                use_container_width=True
            ):

                success = open_email(
                    email["id"]
                )

                if not success:

                    st.error(
                        "Failed to open email."
                    )


# ==================================================
# CENTER COLUMN — EMAIL PREVIEW
# ==================================================

with email_col:

    st.header("Email")

    if not st.session_state.email_details:

        st.info(
            "Select an email from the inbox."
        )

    else:

        email = st.session_state.email_details

        st.subheader(
            email.get(
                "subject",
                "(No Subject)"
            ) or "(No Subject)"
        )

        st.caption(
            f"From: {email.get('sender', '')}"
        )

        st.caption(
            f"Date: {email.get('date', '')}"
        )

        st.divider()

        email_html = email.get(
            "html_body",
            ""
        ).strip()

        email_body = email.get(
            "body",
            ""
        ).strip()

        # Original HTML email
        if email_html:

            components.html(
                email_html,
                height=500,
                scrolling=True
            )

        # Plain-text email
        elif email_body:

            st.text(email_body)

        else:

            st.info(
                "No email body available."
            )


# ==================================================
# RIGHT COLUMN — AI ANALYSIS + REPLY
# ==================================================

with analysis_col:

    st.header("🤖 AI Analysis")

    if not st.session_state.email_details:

        st.info(
            "Select an email to analyze."
        )

    else:

        email = st.session_state.email_details

        # ==================================================
        # ANALYSIS
        # ==================================================

        if not st.session_state.analysis:

            st.caption(
                "This email has not been analyzed."
            )

            if st.button(
                "Analyze Email",
                use_container_width=True
            ):

                with st.spinner(
                    "Analyzing email..."
                ):

                    success, error = analyze_email(
                        email["id"]
                    )

                if not success:

                    st.error(
                        "Email analysis failed."
                    )

                    if error:

                        st.code(
                            error,
                            language="text"
                        )

                else:

                    st.rerun()

        else:

            analysis = st.session_state.analysis

            st.markdown("### Summary")

            st.write(
                analysis.get(
                    "summary",
                    "No summary available."
                )
            )

            st.markdown("### Details")

            st.markdown(
                f"- **Intent:** "
                f"{analysis.get('intent', 'Unknown')}"
            )

            st.markdown(
                f"- **Topic:** "
                f"{analysis.get('topic', 'Unknown')}"
            )

            st.markdown(
                f"- **Urgency:** "
                f"{analysis.get('urgency', 'Unknown')}"
            )

            st.markdown(
                f"- **Sentiment:** "
                f"{analysis.get('sentiment', 'Unknown')}"
            )

            st.markdown(
                f"- **Safety:** "
                f"{analysis.get('safety', 'Unknown')}"
            )

            st.markdown(
                f"- **Priority:** "
                f"{analysis.get('priority', 'Unknown')}"
            )

            requires_guidance = analysis.get(
                "requires_human_guidance",
                False
            )

            st.markdown(
                f"- **Human guidance required:** "
                f"{requires_guidance}"
            )

            # ==================================================
            # AI REPLY
            # ==================================================

            st.divider()

            st.markdown("### ✨ AI Reply")

            if not st.session_state.reply:

                human_guidance = None

                if requires_guidance:

                    st.warning(
                        "This email requires your direction "
                        "before a reply can be generated."
                    )

                    human_guidance = st.text_area(
                        "How would you like to reply?",
                        placeholder=(
                            "Example: Approve the request and "
                            "tell them I will complete it by Friday."
                        ),
                        height=150,
                        key=f"guidance_{email['id']}"
                    )

                if st.button(
                    "Generate AI Reply",
                    use_container_width=True
                ):

                    if (
                        requires_guidance
                        and not human_guidance
                    ):

                        st.warning(
                            "Please provide your direction "
                            "before generating the reply."
                        )

                    else:

                        with st.spinner(
                            "Generating reply..."
                        ):

                            success, error = generate_reply(
                                email["id"],
                                analysis,
                                human_guidance
                            )

                        if not success:

                            st.error(
                                "Reply generation failed."
                            )

                            if error:

                                st.code(
                                    error,
                                    language="text"
                                )

                        else:

                            st.rerun()

            else:

                # ==================================================
                # REPLY REVIEW
                # ==================================================

                edited_reply = st.text_area(
                    "Review your AI-generated reply",
                    value=st.session_state.reply,
                    height=250,
                    key="reply_editor"
                )

                st.caption(
                    "Review and edit the draft before sending."
                )

                # ==================================================
                # SEND EMAIL
                # ==================================================

                if st.button(
                    "📤 Send Email",
                    use_container_width=True
                ):

                    if not edited_reply.strip():

                        st.warning(
                            "The reply cannot be empty."
                        )

                    else:

                        with st.spinner(
                            "Sending email..."
                        ):

                            success, result = send_reply(
                                email["id"],
                                edited_reply
                            )

                        if success:

                            st.success(
                                "Email sent successfully."
                            )

                            st.session_state.reply = None

                        else:

                            st.error(
                                "Failed to send email."
                            )

                            st.code(
                                result,
                                language="text"
                            )