import os
import json
from datetime import datetime

import streamlit as st
import openai
from supabase import create_client, Client

from PyPDF2 import PdfReader
import pytesseract
from PIL import Image

# --- Page Configuration ---
st.set_page_config(
    page_title="Greenwashing Radar Rover",
    page_icon="♻️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- Custom CSS ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@300;400;500;600;700&display=swap');

    * {
        font-family: 'Fira Code', monospace !important;
    }
    body {
        background-color: #ADD8E6;
        color: #000000;
        margin: 0; 
        padding: 0;
    }
    input[type="checkbox"] {
        accent-color: #3498db;
    }
    .title-container {
        text-align: center;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .title-container h1 {
        font-size: 3rem;
        margin: 0;
        color: #000000;
    }
    .chat-container {
        max-width: 800px;
        margin: 2rem auto;
        background: #D3D3D3;
        border-radius: 12px;
        padding: 2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .chat-message {
        display: flex;
        align-items: flex-start;
        margin-bottom: 1.5rem;
    }
    .chat-message:last-child {
        margin-bottom: 0;
    }
    .user-icon, .assistant-icon {
        width: 50px;
        height: 50px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        border-radius: 50%;
        margin-right: 1rem;
        color: #000;
    }
    .user-icon {
        background-color: #E0FFFF;  /* user color */
    }
    .assistant-icon {
        background-color: #E0FFFF;  /* assistant color */
    }
    .chat-content {
        background: #FFFFFF;
        padding: 1rem;
        border-radius: 8px;
        width: 100%;
    }
    /* Make user messages appear E0FFFF (blue-ish) */
    .chat-message.user .chat-content {
        background-color: #E0FFFF;
        color: #000000;
        padding: 1rem;
        border-radius: 8px;
    }
    .suggestion-buttons {
        margin-top: 0.5rem;
    }
    .suggestion-buttons button {
        margin-right: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Supabase & OpenAI Credentials ---
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]
SUPABASE_EMAIL = st.secrets["supabase"]["email"]
SUPABASE_PASSWORD = st.secrets["supabase"]["password"]

OPENAI_API_KEY = st.secrets["openai"]["api_key"]
OPENAI_MODEL = "gpt-4o-mini"  # Keep your requested model

# --- Create Supabase client ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Configure OpenAI ---
openai.api_key = OPENAI_API_KEY

# --------------------- Authentication & Setup ----------------------- #
def authenticate_user():
    """Prompt user for password before accessing the app."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.header("🔒 Access Restricted")
        st.write(
            "Conversations are stored in the database, but we collect no personal data. "
            "Any files uploaded are deleted right after analysis."
            "This is a Beta version, so please verify important information."
        )
        agree = st.checkbox("I agree to the terms above.")
        password = st.text_input("Enter password to continue", type="password")
        if password == "SpaceCrew2025" and agree:
            st.session_state.authenticated = True
            st.rerun()
        elif password and agree:
            st.error("Incorrect password. Please try again.")
        st.stop()

def auto_login():
    """Attempt Supabase login."""
    if "session" not in st.session_state:
        try:
            res = supabase.auth.sign_in_with_password({
                "email": SUPABASE_EMAIL,
                "password": SUPABASE_PASSWORD
            })
            if res.user:
                st.session_state.session = res.session
            else:
                st.error("Supabase login failed. Check your credentials.")
        except Exception as e:
            st.error("An error occurred during Supabase login.")
            print(f"Login error: {str(e)}")

def initialise_chat():
    """Initial chat messages."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Hello! 😊\n"
                    "I’m Greenwashing Radar Rover, a friendly AI designed to help you avoid greenwashing "
                    "and adopt genuine, ethical sustainability practices. How can I assist you today?\n\n"
                    "You can ask me to:\n"
                    "- Explain greenwashing and how to avoid it.\n"
                    "- Assess your sustainability efforts or marketing content.\n"
                    "- Help plan ethical, impactful sustainability strategies.\n"
                    "- Help with marketing and communication messaging.\n\n"
                    "What would you like to explore? 🌱"
                )
            }
        ]

# ---------------------- File Parsing --------------------------- #
MAX_SIZE_MB = 5

def parse_pdf(file_obj) -> str:
    """Extract text from PDF."""
    reader = PdfReader(file_obj)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)

def parse_text_file(file_obj) -> str:
    """Read a text file."""
    return file_obj.read().decode("utf-8", errors="ignore")

def parse_image(file_obj) -> str:
    """Attempt OCR on an image. Tesseract must be installed on the system."""
    try:
        image = Image.open(file_obj)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        st.warning(
            "Sorry, we couldn't process this image with OCR. "
            "Please ensure Tesseract is installed or upload a different format."
        )
        return ""

def get_file_content(uploaded_file) -> str:
    """
    Extract textual content from file for analysis,
    but show only "File: <filename>" to the user.
    """
    if uploaded_file.size > MAX_SIZE_MB * 1024 * 1024:
        st.error(
            f"**{uploaded_file.name}** is **too large** (limit: {MAX_SIZE_MB} MB). "
            "Try a smaller file."
        )
        return ""

    name_lower = uploaded_file.name.lower()
    if name_lower.endswith(".pdf"):
        return parse_pdf(uploaded_file)
    elif name_lower.endswith(".txt"):
        return parse_text_file(uploaded_file)
    elif any(name_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".bmp"]):
        return parse_image(uploaded_file)
    else:
        st.warning(
            f"**{uploaded_file.name}** is not a PDF, TXT, or common image type. "
            "Please convert it or upload only the relevant portion."
        )
        return ""

# ---------------------- AI Interaction ----------------------------- #
def get_ai_response(messages):
    """Stream response from OpenAI."""
    response_stream = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=messages,
        stream=True,
        temperature=0.7
    )
    accumulated = ""
    for chunk in response_stream:
        portion = chunk.choices[0].delta.get("content", "")
        accumulated += portion
        yield accumulated

def save_conversation():
    """Save conversation to Supabase if session is present."""
    if "session" not in st.session_state:
        return
    conv_id = datetime.now().strftime('%Y%m%d%H%M%S')
    data = {
        "conversation_id": conv_id,
        "messages": json.dumps(st.session_state.messages, indent=2),
        "created_at": datetime.now().isoformat(),
        "user_id": "anonymous_user"
    }
    try:
        supabase.auth.set_session(
            st.session_state.session.access_token,
            st.session_state.session.refresh_token
        )
        resp = supabase.table("conversations").insert(data).execute()
        if not resp.data:
            st.error("Could not save conversation.")
    except Exception as ex:
        st.error("An error occurred while saving. Please try again.")
        print(f"Save error: {ex}")

# ------------------ Display + Suggestions ----------------------- #
def display_chat_messages():
    """
    Show each message with user or assistant background.
    If user message starts with 'File: <filename>\n<extracted text>',
    only show 'File: <filename>' to the user.
    """
    # st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    for idx, msg in enumerate(st.session_state.messages):
        # Determine role-based styling
        if msg["role"] == "assistant":
            message_class = "assistant"
            icon_class = "assistant-icon"
            icon_emoji = "♻️"
        else:
            message_class = "user"
            icon_class = "user-icon"
            icon_emoji = "🕵️"

        # By default, we show the entire message
        display_text = msg["content"]

        # If it's a user message containing file content, only show "File: <filename>"
        if msg["role"] == "user" and display_text.startswith("File: "):
            # If there's a newline, only display the first line
            # so the OCR text is hidden from the UI
            first_line, _, _ = display_text.partition("\n")
            display_text = first_line

        st.markdown(
            f"""
            <div class="chat-message {message_class}">
                <div class="{icon_class}">{icon_emoji}</div>
                <div class="chat-content">{display_text}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # If assistant message, add optional suggestions
        if msg["role"] == "assistant":
            # Some example hints
            suggestions = [
                "Ask about deeper analysis of marketing claims",
                "Inquire about alternative sustainable approaches",
                "Request a bullet-point list of green strategies"
            ]
            st.write('<div class="suggestion-buttons">', unsafe_allow_html=True)
            for s_idx, hint in enumerate(suggestions):
                if st.button(hint, key=f"suggestion_{idx}_{s_idx}"):
                    # Put the hint in the user input box
                    st.session_state.draft_input = hint
                    st.rerun()
            st.write('</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------- Main App ------------------------------- #
def main():
    authenticate_user()
    auto_login()

    # If we want to preserve a "draft" input for the user after hint clicks
    if "draft_input" not in st.session_state:
        st.session_state.draft_input = ""

    st.markdown('<div class="title-container">', unsafe_allow_html=True)
    st.write("# ♻️ Greenwashing Radar Rover")
    st.write("### Unmasking questionable sustainability claims in your projects or products")
    st.markdown('</div>', unsafe_allow_html=True)
    st.write("Built with 💚  by Spaceship AI.")
    st.write("---")

    initialise_chat()
    # Display the conversation first
    display_chat_messages()

    # Then the user input form
    with st.form("user_input_form", clear_on_submit=True):
        user_input = st.text_input(" ", 
                                   placeholder="lets discuss greenwashing ...",
                                   value=st.session_state.draft_input)
        uploaded_files = st.file_uploader("Attach files (optional)", 
                                          accept_multiple_files=True)
        submit_button = st.form_submit_button("Send")

    if submit_button:
        # Clear the draft after they send
        st.session_state.draft_input = ""

        content_blocks = []
        if user_input.strip():
            content_blocks.append(user_input)

        # Parse each uploaded file
        for uf in uploaded_files:
            extracted_text = get_file_content(uf)
            if extracted_text:
                # Add "File: <filename>\n<extracted text>" so AI can see the text
                content_blocks.append(f"File: {uf.name}\n{extracted_text}")
            else:
                # Show user that they attempted to upload something
                content_blocks.append(f"File: {uf.name}")

        # If there's any user input to add
        if content_blocks:
            final_user_msg = "\n\n".join(content_blocks)
            st.session_state.messages.append(
                {"role": "user", "content": final_user_msg}
            )

            # Generate AI response
            with st.spinner("♻️ Thinking..."):
                full_resp = ""
                response_stream = openai.ChatCompletion.create(
                    model=OPENAI_MODEL,
                    messages=st.session_state.messages,
                    stream=True,
                    temperature=0.7
                )
                for chunk in response_stream:
                    part = chunk.choices[0].delta.get("content", "")
                    full_resp += part

            st.session_state.messages.append({"role": "assistant", "content": full_resp})

            # Save conversation automatically
            save_conversation()

            # Rerun to refresh chat above
            st.rerun()

if __name__ == "__main__":
    main()

