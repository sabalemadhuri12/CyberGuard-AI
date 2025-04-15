import streamlit as st
import google.generativeai as genai
import speech_recognition as sr
import pyaudio
import datetime
import uuid
import io
import base64
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from streamlit_option_menu import option_menu
import os
import tempfile
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from supabase import create_client, Client
from pydub import AudioSegment

# Supabase Configuration
supabase_url = # supabase_url#
supabase_key =  # supabase_key#
supabase: Client = create_client(supabase_url, supabase_key)

# SMTP Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = # smtp_port#
SMTP_EMAIL =# smtp_email#
SMTP_PASSWORD = # smtp_password#

# Initialize Gemini AI
genai.configure(api_key=# api_key#)
model = genai.GenerativeModel('gemini-1.5-flash')

# Function to generate 5 tips using Gemini based on the category
def generate_cybercrime_tips(category):
    prompt = f"""
    You are a cybersecurity expert tasked with providing practical and meaningful advice. Based on the cybercrime category '{category}', generate exactly 5 concise, actionable tips to help individuals avoid falling victim to this type of crime. Ensure the tips are specific to the category, easy to understand, and useful for the general public. Format the response as a numbered list (1-5) with no additional explanations or introductions beyond the tips themselves.

    Category: {category}
    """
    response = get_gemini_response(prompt)
    return response if response else "1. Be cautious online.\n2. Use strong passwords.\n3. Avoid suspicious links.\n4. Keep software updated.\n5. Report suspicious activity."

# Function to send confirmation email with tips
def send_confirmation_email(to_email, ticket_id, category):
    try:
        tips = generate_cybercrime_tips(category)
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"CyberGuard AI - Complaint Confirmation (Ticket ID: {ticket_id})"

        body = f"""
        Dear User,

        Thank you for submitting your complaint to CyberGuard AI - National Cyber Crime Reporting Portal.
        Your complaint has been successfully registered with the following details:

        Ticket ID: {ticket_id}
        Date Filed: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        Status: Under Investigation
        Category: {category}

        You can track the status of your complaint using the Ticket ID on our portal under 'Track Complaint'.
        For any further assistance, please contact us at cybercrime@nic.in or call 1930.

        **5 Tips to Avoid {category} Crimes:**
        {tips}

        Regards,
        CyberGuard AI Team
        National Cyber Crime Reporting Portal
        """
        msg.attach(MIMEText(body, 'plain'))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Failed to send confirmation email: {e}")
        return False

# TTS function
def speak_text(text, lang_code):
    try:
        js_code = f"""
        <script>
            var utterance = new SpeechSynthesisUtterance("{text}");
            utterance.lang = "{lang_code}";
            utterance.pitch = {st.session_state.voice_pitch};
            utterance.rate = {st.session_state.voice_rate};
            window.speechSynthesis.speak(utterance);
        </script>
        """
        st.components.v1.html(js_code, height=0)
    except Exception as e:
        st.error(f"Error in speech synthesis: {e}")

# Improved STT function with retries and fallback
def recognize_speech(language_code):
    recognizer = sr.Recognizer()
    retries = 3
    for attempt in range(retries):
        with sr.Microphone() as source:
            st.info(f"🎙️ Listening in {st.session_state.selected_language}... (Attempt {attempt + 1}/{retries})")
            recognizer.adjust_for_ambient_noise(source, duration=2)
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                    temp_file.write(audio.get_wav_data())
                    temp_path = temp_file.name
                try:
                    text = recognizer.recognize_google(audio, language=language_code)
                    os.unlink(temp_path)
                    return text

                except sr.UnknownValueError:
                    st.warning("Google STT failed, trying Gemini transcription...")
                    text = get_gemini_response("Transcribe this audio:", temp_path, "audio/wav")
                    os.unlink(temp_path)
                    return text if text else None
            except sr.WaitTimeoutError:
                st.error("🎙️ No speech detected. Please speak louder or closer to the mic.")
            except sr.RequestError as e:
                st.error(f"🎙️ Speech recognition error: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")
        if attempt < retries - 1:
            st.info("Retrying...")
    st.error("🎙️ Failed to recognize speech after multiple attempts. Please try typing or check your microphone.")
    return None

# Gemini response function with improved error handling
def get_gemini_response(prompt, file_path=None, mime_type=None):
    try:
        if file_path and mime_type:
            with open(file_path, "rb") as file:
                file_content = file.read()
            response = model.generate_content([prompt, {"mime_type": mime_type, "data": file_content}])
        else:
            response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        st.error(f"Gemini API error: {e}")
        return None

# Translation function with caching
@st.cache_data
def translate_text(text, source_lang, target_lang):
    if source_lang == target_lang or not text:
        return text
    try:
        prompt = f"""
        You are a precise language translator. Translate the following '{source_lang}' text into '{target_lang}' and return ONLY the translated text, nothing else—no explanations, no breakdowns, no notes. Use the appropriate script for the target language.
        Text to translate: {text}
        """
        response = get_gemini_response(prompt)
        return response
    except Exception as e:
        st.error(f"Translation error: {e}")
        return text

# Extract information using Gemini with improved prompting
def extract_info_from_response(question, response):
    prompt = f"""
    You are an advanced information extraction system. Given the following question and user response, extract ONLY the relevant information as a plain string. Do not use brackets, '[Not Provided]', or any extra text—just the extracted value. If the response is incomplete or unclear, return only what can be confidently extracted; otherwise, return an empty string ('').

    Question: {question}
    Response: {response}

    Extract:
    - For "What is your full name and contact phone number?": the full name and phone number as a single string (e.g., "pruthviraj 544434")
    - For "What is your email address?": the email address (e.g., "aakash@gmail.com")
    - For "When did the incident occur?": the date and time (e.g., "12-03-2025 14:30")
    - For "Can you describe what happened in detail?": the full description as provided
    - For "Do you have any evidence...?": the evidence description as provided
    - For yes/no questions: "yes" or "no" (lowercase); if unclear, return an empty string ('')
    """
    result = get_gemini_response(prompt)
    return result if result else ""

# Initialize session state
def init_session_state():
    defaults = {
        'chat_history': [],
        'form_data': {},
        'form_data_translated': {},
        'complaint_tickets': {},
        'questions_index': 0,
        'chatbot_active': False,
        'speech_input': '',
        'last_spoken_index': -1,
        'voice_enabled': True,
        'voice_pitch': 1.0,
        'voice_rate': 1.0,
        'selected_language': "English",
        'authenticated': False,
        'current_page': 'signin'
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# Language mappings
languages = {
    "Hindi": "hi-IN", "Konkani": "kok-IN", "Kannada": "kn-IN", "Dogri": "doi-IN",
    "Bodo": "brx-IN", "Urdu": "ur-IN", "Tamil": "ta-IN", "Kashmiri": "ks-IN",
    "Assamese": "as-IN", "Bengali": "bn-IN", "Marathi": "mr-IN", "Sindhi": "sd-IN",
    "Maithili": "mai-IN", "Punjabi": "pa-IN", "Malayalam": "ml-IN", "Manipuri": "mni-IN",
    "Telugu": "te-IN", "Sanskrit": "sa-IN", "Nepali": "ne-IN", "Santali": "sat-IN",
    "Gujarati": "gu-IN", "Odia": "or-IN", "English": "en-IN"
}
tts_lang_codes = {k: v.split('-')[0] + '-' + v.split('-')[1].upper() for k, v in languages.items()}
native_commands = {
    "English": {"next": "next", "back": "back", "submit": "submit", "repeat": "repeat"},
    "Hindi": {"next": "अगला", "back": "पीछे", "submit": "जमा करें", "repeat": "दोहराएं"},
    "Tamil": {"next": "அடுத்து", "back": "பின்னால்", "submit": "சமர்ப்பி", "repeat": "மீண்டும்"},
    "Telugu": {"next": "తదుపరి", "back": "వెనక్కి", "submit": "సమర్పించు", "repeat": "పునరావృతం"},
    "Kannada": {"next": "ಮುಂದಿನ", "back": "ಹಿಂದೆ", "submit": "ಸಲ್ಲಿಸು", "repeat": "ಪುನರಾವರ್ತನೆ"},
    "Malayalam": {"next": "അടുത്തത്", "back": "പിന്നോട്ട്", "submit": "സമർപ്പിക്കുക", "repeat": "ആവർത്തിക്കുക"},
    "Marathi": {"next": "पुढील", "back": "मागे", "submit": "सादर करा", "repeat": "पुनरावृत्ती"},
    "Bengali": {"next": "পরবর্তী", "back": "পিছনে", "submit": "জমা দিন", "repeat": "পুনরাবৃত্তি"},
    "Gujarati": {"next": "આગળ", "back": "પાછળ", "submit": "સબમિટ કરો", "repeat": "પુનરાવર્તન"},
    "Punjabi": {"next": "ਅਗਲਾ", "back": "ਪਿੱਛੇ", "submit": "ਜਮ੍ਹਾ ਕਰੋ", "repeat": "ਦੁਹਰਾਓ"},
    "Dogri": {"next": "अगला", "back": "पिछे", "submit": "जमा करो", "repeat": "दुहराओ"},
}

# Updated Complaint Questionnaire
form_filling_questions = [
    {"field": "name_phone", "question": {"English": "What is your full name and contact phone number?"}, "required": True},
    {"field": "email", "question": {"English": "What is your email address?"}, "required": True},
    {"field": "incident_date", "question": {"English": "When did the incident occur? (Please provide the date and approximate time.)"}, "required": True},
    {"field": "threat_harass_women_children", "question": {"English": "Have you or someone you know received threatening or harassing messages online specifically targeting women or children? Please answer with yes or no."}, "required": False, "type": "yes_no"},
    {"field": "financial_scam", "question": {"English": "Have you experienced unauthorized financial transactions, phishing scams, or deceptive financial offers via online communications? Please answer with yes or no."}, "required": False, "type": "yes_no"},
    {"field": "malware_ransomware", "question": {"English": "Has your computer system or network been compromised by malware, ransomware, or unauthorized access? Please answer with yes or no."}, "required": False, "type": "yes_no"},
    {"field": "illegal_trafficking", "question": {"English": "Have you encountered online platforms or content facilitating illegal trafficking or sale of goods/services? Please answer with yes or no."}, "required": False, "type": "yes_no"},
    {"field": "incident_description", "question": {"English": "Can you describe what happened in detail?"}, "required": True},
    {"field": "evidence", "question": {"English": "Do you have any evidence such as screenshots, emails, or messages that support your report? Please describe and upload if available."}, "required": False, "type": "text_and_upload"},
]

# UI Config
st.set_page_config(
    page_title="CyberGuard AI - National Cyber Crime Reporting Portal",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS (unchanged)
st.markdown(
    """
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
    .stApp {
        background-color: #f5f7fa;
        margin: 0 !important;
        padding: 0 !important;
    }
    .header-home {
        background: linear-gradient(90deg, #0047AB 0%, #184C78 100%);
        color: white;
        padding: 1rem;
        text-align: center;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 0 0 20px 0 !important;
        font-size: 0.9em;
    }
    .content-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        margin: 0 0 20px 0 !important;
    }
    .dashboard-card {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        text-align: center;
        margin: 5px;
    }
    .stButton>button {
        background-color: #0047AB;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    .stButton>button:hover {
        background-color: #003087;
        border: none;
    }
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        border-radius: 5px;
        border: 1px solid #E0E0E0;
    }
    .status-badge {
        padding: 5px 10px;
        border-radius: 15px;
        font-weight: 500;
        display: inline-block;
    }
    .status-pending {
        background-color: #FFF9C4;
        color: #F57F17;
    }
    .status-active {
        background-color: #E3F2FD;
        color: #0D47A1;
    }
    .status-resolved {
        background-color: #E8F5E9;
        color: #1B5E20;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 15px;
        margin-bottom: 10px;
        max-width: 80%;
        display: inline-block;
    }
    .user-message {
        background-color: #E3F2FD;
        float: right;
        clear: both;
        border-bottom-right-radius: 5px;
    }
    .bot-message {
        background-color: #F5F5F5;
        float: left;
        clear: both;
        border-bottom-left-radius: 5px;
    }
    .chat-container {
        height: calc(80vh - 200px);
        overflow-y: auto;
        padding: 20px;
        display: flex;
        flex-direction: column;
    }
    .helpline-badge {
        background-color: #E91E63;
        color: white;
        padding: 5px 10px;
        border-radius: 30px;
        font-weight: bold;
        margin: 5px;
        display: inline-block;
    }
    .footer {
        text-align: center;
        padding: 20px;
        color: #666;
        font-size: 0.8rem;
        border-top: 1px solid #eee;
        margin-top: 30px;
    }
    .stat-counter {
        font-size: 2rem;
        font-weight: bold;
        color: #0047AB;
    }
    .big-icon {
        font-size: 100px;
        color: #0047AB;
        text-align: center;
        margin-bottom: 20px;
    }
    .auth-container {
        max-width: 400px;
        margin: 50px auto;
        text-align: center;
    }
    .auth-icon {
        font-size: 60px;
        color: #0047AB;
        margin-bottom: 20px;
    }
    .auth-button {
        width: 100%;
        margin-top: 10px;
    }
    @media (max-width: 768px) {
        .chat-message {
            max-width: 90%;
        }
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .progress-bar {
        background-color: #E0E0E0;
        border-radius: 5px;
        height: 20px;
    }
    .progress-fill {
        background-color: #0047AB;
        height: 100%;
        border-radius: 5px;
    }
    div[data-testid="stFileUploader"] {
        width: 100%;
        max-width: 500px;
        margin-top: 10px;
    }
    div[data-testid="stFileUploader"] > div > div {
        width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Authentication Functions
def register_user(username, password, email):
    response = supabase.table('users').select('username').eq('username', username).execute()
    if response.data:
        return False, "Username already exists."

    try:
        supabase.table('users').insert({
            'username': username,
            'password': password,  # In production, hash the password
            'email': email
        }).execute()
        return True, "Registered successfully! Please sign in."
    except Exception as e:
        return False, f"Registration failed: {str(e)}"

def sign_in_user(username, password):
    response = supabase.table('users').select('*').eq('username', username).eq('password', password).execute()
    if response.data:
        st.session_state.authenticated = True
        st.session_state.current_page = 'dashboard'
        return True, "Signed in successfully!"
    return False, "Invalid credentials."

# Sign In Page
def sign_in_page():
    st.markdown(
        """
        <div class="auth-container">
            <i class="fas fa-sign-in-alt auth-icon"></i>
            <h2>Sign In</h2>
        </div>
        """,
        unsafe_allow_html=True
    )
    with st.form(key='signin_form', clear_on_submit=True):
        username = st.text_input("Username", key="signin_username")
        password = st.text_input("Password", type="password", key="signin_password")
        submit_button = st.form_submit_button(label="Sign In")

        if submit_button:
            success, message = sign_in_user(username, password)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    st.markdown(
        """
        <div class="auth-container">
            <p>Not registered yet? <a href="#" id="register_link">Register here</a></p>
        </div>
        """,
        unsafe_allow_html=True
    )
    if st.button("Go to Register", key="to_register"):
        st.session_state.current_page = 'register'
        st.rerun()

# Register Page
def register_page():
    st.markdown(
        """
        <div class="auth-container">
            <i class="fas fa-user-plus auth-icon"></i>
            <h2>Register</h2>
        </div>
        """,
        unsafe_allow_html=True
    )
    with st.form(key='register_form', clear_on_submit=True):
        username = st.text_input("Username", key="register_username")
        password = st.text_input("Password", type="password", key="register_password")
        email = st.text_input("Email", key="register_email")
        submit_button = st.form_submit_button(label="Register")

        if submit_button:
            success, message = register_user(username, password, email)
            if success:
                st.success(message)
                st.session_state.current_page = 'signin'
                st.rerun()
            else:
                st.error(message)

    st.markdown(
        """
        <div class="auth-container">
            <p>Already registered? <a href="#" id="signin_link">Sign in here</a></p>
        </div>
        """,
        unsafe_allow_html=True
    )
    if st.button("Go to Sign In", key="to_signin"):
        st.session_state.current_page = 'signin'
        st.rerun()

# Supabase Integration for Complaint Storage
def save_to_supabase(data, translated_data):
    ticket_id = f"CYBER-{uuid.uuid4().hex[:8].upper()}"
    complaint_data = {
        "ticket_id": ticket_id,
        "data": data,
        "translated_data": translated_data,
        "status": "Under Investigation",
        "date_filed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        supabase.table('complaints').insert(complaint_data).execute()
        email = translated_data.get('email', '')
        category = translated_data.get('category', 'Other')
        if email and send_confirmation_email(email, ticket_id, category):
            st.success(f"✅ Confirmation email with safety tips sent to {email}!")
        else:
            st.warning("Complaint saved, but email confirmation failed.")
        return ticket_id
    except Exception as e:
        st.error(f"Failed to save to Supabase: {e}")
        return None

def fetch_complaint_from_supabase(ticket_id):
    try:
        response = supabase.table('complaints').select('*').eq('ticket_id', ticket_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"Failed to fetch from Supabase: {e}")
        return None

# Generate PDF
def generate_complaint_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, spaceAfter=12)
    story.append(Paragraph("CYBER CRIME COMPLAINT REPORT", title_style))
    story.append(Spacer(1, 12))

    complaint_data = [
        ["Ticket Number", data.get('ticket_id', '')],
        ["Date Filed", data.get('date_filed', '')],
        ["Name and Phone", data.get('name_phone', '')],
        ["Email Address", data.get('email', '')],
        ["Incident Date", data.get('incident_date', '')],
        ["Threat/Harassment to Women/Children", data.get('threat_harass_women_children', 'N/A')],
        ["Financial Scam", data.get('financial_scam', 'N/A')],
        ["Malware/Ransomware", data.get('malware_ransomware', 'N/A')],
        ["Illegal Trafficking", data.get('illegal_trafficking', 'N/A')],
        ["Incident Description", data.get('incident_description', '')],
        ["Evidence Description", data.get('evidence', '')],
        ["Category", data.get('category', 'N/A')],
        ["Category Explanation", data.get('category_explanation', 'N/A')],
        ["Status", data.get('status', '')],
    ]

    table = Table(complaint_data, colWidths=[150, 400])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=10, textColor=colors.grey, alignment=1)
    story.append(Paragraph("This is an auto-generated document from CyberGuard AI Portal", footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

# Get question text with caching
@st.cache_data
def get_question_text(question_dict, lang):
    if lang in question_dict:
        return question_dict[lang]
    english_text = question_dict.get("English", "")
    translated_text = translate_text(english_text, "English", lang)
    question_dict[lang] = translated_text
    return translated_text

# Analyze Image with Gemini
def analyze_image(image_path):
    prompt = "Analyze this image and describe its content relevant to a cybercrime complaint."
    analysis = get_gemini_response(prompt, image_path, "image/jpeg")
    return analysis if analysis else "No significant content detected in the image."

# Check if audio has sound
def has_sound(audio_path):
    try:
        audio = AudioSegment.from_file(audio_path)
        return audio.dBFS > -60  # Threshold for detecting sound
    except Exception as e:
        st.error(f"Audio analysis error: {e}")
        return False

# Enhanced Categorization with Advanced Prompting
def categorize_complaint(data):
    complaint_text = "\n".join([f"{k}: {v}" for k, v in data.items() if k not in ['evidence_files', 'category', 'category_explanation']])
    image_analyses = []
    if 'evidence_files' in data:
        for evidence in data['evidence_files']:
            if evidence['name'].endswith(('.jpg', '.jpeg', '.png')):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                    temp_file.write(base64.b64decode(evidence['content']))
                    temp_path = temp_file.name
                analysis = analyze_image(temp_path)
                image_analyses.append(f"Image {evidence['name']}: {analysis}")
                os.unlink(temp_path)

    prompt = f"""
    You are an expert cybercrime analyst with advanced knowledge in digital forensics, behavioral analysis, and legal frameworks. Your task is to categorize the following complaint into one of these categories:
    - Cyber Harassment
    - Financial Fraud
    - System Security
    - Illegal Activities
    - Other

    Provide a precise and detailed explanation (6-10 sentences) justifying the chosen category, adhering to these enhanced steps:
    1. Analyze each Yes/No response, assigning weighted relevance to potential categories based on severity and specificity.
    2. Perform a semantic analysis of the incident description, identifying key phrases, intent, and contextual clues with high accuracy.
    3. Integrate image analysis (if available) as corroborative evidence, assessing its relevance to the complaint narrative.
    4. Cross-reference the combined data against known cybercrime patterns and typologies for consistency.
    5. Resolve ambiguities by prioritizing the most specific and impactful evidence, avoiding generic assumptions.
    6. Conclude with a clear, evidence-based rationale for the selected category, ensuring alignment with legal definitions.

    Respond in this format:
    Category: [category name]
    Explanation: [detailed explanation]

    Complaint details:
    {complaint_text}

    Image Analysis (if any):
    {"; ".join(image_analyses) if image_analyses else "No images provided."}
    """
    response = get_gemini_response(prompt)
    try:
        category_line, explanation_line = response.split('\n', 1)
        category = category_line.split(": ")[1]
        explanation = explanation_line.split(": ")[1]
        valid_categories = ["Cyber Harassment", "Financial Fraud", "System Security", "Illegal Activities", "Other"]
        return category if category in valid_categories else "Other", explanation
    except Exception:
        return "Other", "Failed to categorize due to an error in processing the response. Please ensure all details are complete and retry."

# Process chatbot input with clean data storage
def process_chatbot_input(user_input, audio_file, current_question):
    lang = st.session_state.selected_language
    commands = native_commands.get(lang, native_commands["English"])
    question_text = get_question_text(current_question['question'], "English")

    if audio_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(audio_file.read())
            temp_path = temp_file.name
        if has_sound(temp_path):
            user_input = get_gemini_response("Transcribe this audio:", temp_path, "audio/wav")
            if not user_input:
                user_input = "No recognizable speech in audio."
        else:
            os.unlink(temp_path)
            st.warning("Uploaded audio has no sound. Please upload a valid audio file.")
            return "No sound detected in audio."
        os.unlink(temp_path)
        st.session_state.speech_input = user_input

    if user_input.lower() in [commands["next"], "next"]:
        st.session_state.questions_index += 1
        return None
    elif user_input.lower() in [commands["back"], "back"]:
        st.session_state.questions_index = max(0, st.session_state.questions_index - 1)
        return None
    elif user_input.lower() in [commands["submit"], "submit"]:
        st.session_state.chatbot_active = False
        category, explanation = categorize_complaint(st.session_state.form_data_translated)
        st.session_state.form_data['category'] = category
        st.session_state.form_data['category_explanation'] = explanation
        st.session_state.form_data_translated['category'] = category
        st.session_state.form_data_translated['category_explanation'] = explanation
        return f"All details collected. Complaint categorized as: {category}. Explanation: {explanation}"
    elif user_input.lower() in [commands["repeat"], "repeat"]:
        return get_question_text(current_question['question'], lang)

    extracted_value = extract_info_from_response(question_text, user_input)
    if current_question.get('type') == "yes_no":
        if extracted_value in ["yes", "no"]:
            st.session_state.form_data[current_question['field']] = extracted_value
            st.session_state.form_data_translated[current_question['field']] = extracted_value
            st.session_state.questions_index += 1
        else:
            return translate_text("Please respond with 'yes' or 'no'.", "English", lang)
    elif current_question.get('type') == "text_and_upload":
        st.session_state.form_data[current_question['field']] = extracted_value
        st.session_state.form_data_translated[current_question['field']] = translate_text(extracted_value, lang, "English")
        uploaded_files = st.file_uploader("Upload evidence here", accept_multiple_files=True, key=f"upload_{st.session_state.questions_index}")
        if uploaded_files:
            st.session_state.form_data['evidence_files'] = [{"name": f.name, "content": base64.b64encode(f.read()).decode('utf-8')} for f in uploaded_files]
        st.session_state.questions_index += 1
    else:
        st.session_state.form_data[current_question['field']] = extracted_value
        st.session_state.form_data_translated[current_question['field']] = translate_text(extracted_value, lang, "English")
        st.session_state.questions_index += 1

    if st.session_state.questions_index >= len(form_filling_questions):
        st.session_state.chatbot_active = False
        category, explanation = categorize_complaint(st.session_state.form_data_translated)
        st.session_state.form_data['category'] = category
        st.session_state.form_data['category_explanation'] = explanation
        st.session_state.form_data_translated['category'] = category
        st.session_state.form_data_translated['category_explanation'] = explanation
        return f"Thank you for providing all the information. Complaint categorized as: {category}. Explanation: {explanation}"
    return None

# Display chat message
def display_chat_message(message, is_user=False):
    message_class = "user-message" if is_user else "bot-message"
    st.markdown(f'<div class="chat-message {message_class}">{message}</div>', unsafe_allow_html=True)

# Main Dashboard
def dashboard():
    with st.sidebar:
        selected = option_menu(
            "Main Menu",
            ["Home", "Register Complaint", "Track Complaint", "Contact Us"],
            icons=['house', 'file-alt', 'search', 'envelope'],
            menu_icon="shield-lock",
            default_index=0,
            styles={
                "container": {"padding": "5px", "background-color": "#f5f7fa"},
                "icon": {"color": "#0047AB", "font-size": "25px"},
                "nav-link": {"font-size": "16px", "text-align": "left", "margin": "0px", "--hover-color": "#eee"},
                "nav-link-selected": {"background-color": "#0047AB"},
            }
        )
        if st.button("Sign Out", key="signout"):
            st.session_state.authenticated = False
            st.session_state.current_page = 'signin'
            st.rerun()

    language_code = languages.get(st.session_state.selected_language, languages["English"])
    tts_lang = tts_lang_codes.get(st.session_state.selected_language, tts_lang_codes["English"])

    if selected == "Home":
        st.markdown(
            """
            <div class="header-home">
                <h4>CyberGuard AI - National Cyber Crime Reporting Portal</h4>
                <p>File and Track Cyber Crime Complaints with Ease | Powered by AI</p>
                <div class="helpline-badge">National Cyber Crime Helpline: 1930</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown('<i class="fas fa-shield-alt big-icon"></i>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="content-card">
                <h2>Welcome to CyberGuard AI</h2>
                <p>India's premier portal for reporting and tracking cyber crimes, powered by Artificial Intelligence. Our mission is to provide a secure, efficient, and user-friendly platform to combat cyber threats.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                """
                <div class="dashboard-card">
                    <h4>Total Complaints</h4>
                    <div class="stat-counter">{}</div>
                </div>
                """.format(len(st.session_state.complaint_tickets)),
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(
                """
                <div class="dashboard-card">
                    <h4>Resolved Cases</h4>
                    <div class="stat-counter">{}</div>
                </div>
                """.format(sum(1 for ticket in st.session_state.complaint_tickets.values() if ticket.get('status') == "Resolved")),
                unsafe_allow_html=True
            )
        with col3:
            st.markdown(
                """
                <div class="dashboard-card">
                    <h3>Active Cases</h3>
                    <div class="stat-counter">{}</div>
                </div>
                """.format(sum(1 for ticket in st.session_state.complaint_tickets.values() if ticket.get('status') == "Under Investigation")),
                unsafe_allow_html=True
            )

    elif selected == "Register Complaint":
        st.session_state.selected_language = st.selectbox(
            "Select Language / भाषा चुनें",
            list(languages.keys()),
            index=list(languages.keys()).index("English"),
            key="language_selector"
        )
        language_code = languages[st.session_state.selected_language]
        tts_lang = tts_lang_codes[st.session_state.selected_language]

        st.markdown('<i class="fas fa-file-alt big-icon"></i>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="content-card">
                <h4>File a New Complaint</h4>
                <p>Please provide the necessary details to register your complaint. You can use the AI chatbot to fill the form automatically or fill it manually.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.expander("Voice Settings"):
            st.session_state.voice_enabled = st.checkbox("Enable Voice", value=True)
            st.session_state.voice_pitch = st.slider("Pitch", 0.5, 2.0, 1.0)
            st.session_state.voice_rate = st.slider("Speed", 0.5, 2.0, 1.0)

        use_chatbot = st.checkbox("Use AI Chatbot to Fill Form", value=False)
        if use_chatbot:
            st.session_state.chatbot_active = True
            st.markdown('<div class="chat-container">', unsafe_allow_html=True)

            progress = st.session_state.questions_index / len(form_filling_questions) * 100
            st.markdown(f'<div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>', unsafe_allow_html=True)

            for chat in st.session_state.chat_history:
                display_chat_message(chat['message'], chat['is_user'])

            if st.session_state.chatbot_active and st.session_state.questions_index < len(form_filling_questions):
                current_question = form_filling_questions[st.session_state.questions_index]
                with st.spinner("Loading question..."):
                    q_text = get_question_text(current_question['question'], st.session_state.selected_language)

                if st.session_state.voice_enabled and st.session_state.questions_index > st.session_state.last_spoken_index:
                    st.info(f"🔊 Speaking in {st.session_state.selected_language}...")
                    speak_text(q_text, tts_lang)
                    st.session_state.last_spoken_index = st.session_state.questions_index

                display_chat_message(q_text)

                col1, col2 = st.columns([4, 1])
                with col1:
                    user_input = st.text_input(
                        "Your response",
                        value=st.session_state.speech_input,
                        key=f"chat_input_{st.session_state.questions_index}"
                    )
                with col2:
                    if st.button("🎙️", key=f"mic_{st.session_state.questions_index}"):
                        with st.spinner("Processing speech..."):
                            speech_text = recognize_speech(language_code)
                        if speech_text:
                            st.session_state.speech_input = speech_text
                            st.rerun()

                audio_file = st.file_uploader(
                    "Upload Audio Response",
                    type=["wav", "mp3"],
                    key=f"audio_{st.session_state.questions_index}",
                    help="Upload an audio file as your response (max 5MB)",
                    label_visibility="visible"
                )

                if user_input or audio_file:
                    with st.spinner("Processing your response..."):
                        final_input = user_input if user_input else ""
                        if audio_file:
                            final_input = process_chatbot_input("", audio_file, current_question) or final_input
                        if final_input:
                            display_chat_message(final_input, is_user=True)
                            st.session_state.chat_history.append({"message": q_text, "is_user": False})
                            st.session_state.chat_history.append({"message": final_input, "is_user": True})
                            response = process_chatbot_input(final_input, None, current_question)
                            if response:
                                display_chat_message(response)
                            st.session_state.speech_input = ""
                            st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

            if not st.session_state.chatbot_active:
                st.success("✅ Complaint data collected successfully.")
                # Removed Collected Details display
                st.markdown(f"**Category Assigned:** {st.session_state.form_data.get('category', 'N/A')}")
                st.markdown(f"**Explanation:** {st.session_state.form_data.get('category_explanation', 'N/A')}")
                if st.button("Submit Complaint", key="chatbot_submit"):
                    with st.spinner("Submitting your complaint..."):
                        ticket_id = save_to_supabase(st.session_state.form_data, st.session_state.form_data_translated)
                        if ticket_id:
                            st.session_state.form_data['ticket_id'] = ticket_id
                            st.session_state.form_data_translated['ticket_id'] = ticket_id
                            st.session_state.form_data_translated.update({
                                "status": "Under Investigation",
                                "date_filed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            })
                            pdf_buffer = generate_complaint_pdf(st.session_state.form_data_translated)
                            st.success(f"✅ Complaint filed successfully! Your ticket ID is: {ticket_id}")
                            st.download_button(
                                label="Download Complaint PDF",
                                data=pdf_buffer,
                                file_name=f"Complaint_{ticket_id}.pdf",
                                mime="application/pdf"
                            )
                            st.session_state.form_data = {}
                            st.session_state.form_data_translated = {}
                            st.session_state.chat_history = []
                            st.session_state.questions_index = 0

        if not use_chatbot or not st.session_state.chatbot_active:
            with st.form(key='complaint_form'):
                col1, col2 = st.columns(2)
                with col1:
                    name_phone = st.text_input("Full Name and Phone Number", value=st.session_state.form_data.get('name_phone', ''))
                    email = st.text_input("Email Address", value=st.session_state.form_data.get('email', ''))
                    incident_date = st.text_input("Incident Date & Time (e.g., DD-MM-YYYY HH:MM)", value=st.session_state.form_data.get('incident_date', ''))
                    threat_harass = st.selectbox("Threat/Harassment to Women/Children", ["No", "Yes"],
                                                index=0 if st.session_state.form_data.get('threat_harass_women_children', 'no') == 'no' else 1)
                    financial_scam = st.selectbox("Financial Scam", ["No", "Yes"],
                                                 index=0 if st.session_state.form_data.get('financial_scam', 'no') == 'no' else 1)
                with col2:
                    malware = st.selectbox("Malware/Ransomware", ["No", "Yes"],
                                          index=0 if st.session_state.form_data.get('malware_ransomware', 'no') == 'no' else 1)
                    illegal_trafficking = st.selectbox("Illegal Trafficking", ["No", "Yes"],
                                                      index=0 if st.session_state.form_data.get('illegal_trafficking', 'no') == 'no' else 1)

                incident_description = st.text_area("Incident Description", value=st.session_state.form_data.get('incident_description', ''), height=200)
                evidence = st.text_area("Evidence Description (e.g., screenshots, emails, messages)", value=st.session_state.form_data.get('evidence', ''))
                evidence_files = st.file_uploader("Upload Evidence (Screenshots, Documents, etc.)", accept_multiple_files=True, type=['jpg', 'png', 'pdf', 'docx'])

                submit_button = st.form_submit_button(label='Submit Complaint')

            if submit_button:
                with st.spinner("Submitting your complaint..."):
                    required_fields = {q['field']: q['question']['English'] for q in form_filling_questions if q['required']}
                    form_values = {
                        "name_phone": name_phone,
                        "email": email,
                        "incident_date": incident_date,
                        "incident_description": incident_description
                    }
                    missing_fields = [field for field, value in form_values.items() if field in required_fields and not value]

                    if missing_fields:
                        st.error(f"Please fill in all required fields: {', '.join(required_fields[field] for field in missing_fields)}")
                    else:
                        complaint_data = {
                            "name_phone": name_phone,
                            "email": email,
                            "incident_date": incident_date,
                            "threat_harass_women_children": threat_harass.lower(),
                            "financial_scam": financial_scam.lower(),
                            "malware_ransomware": malware.lower(),
                            "illegal_trafficking": illegal_trafficking.lower(),
                            "incident_description": incident_description,
                            "evidence": evidence,
                            "evidence_files": []
                        }
                        if evidence_files:
                            complaint_data["evidence_files"] = [{"name": f.name, "content": base64.b64encode(f.read()).decode('utf-8')} for f in evidence_files]
                        category, explanation = categorize_complaint(complaint_data)
                        complaint_data["category"] = category
                        complaint_data["category_explanation"] = explanation
                        translated_data = {k: translate_text(v, st.session_state.selected_language, "English") for k, v in complaint_data.items()}
                        ticket_id = save_to_supabase(complaint_data, translated_data)
                        if ticket_id:
                            translated_data["ticket_id"] = ticket_id
                            translated_data.update({
                                "status": "Under Investigation",
                                "date_filed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            })
                            pdf_buffer = generate_complaint_pdf(translated_data)
                            st.success(f"✅ Complaint filed successfully! Your ticket ID is: {ticket_id}")
                            # Removed Collected Details display
                            st.markdown(f"**Category Assigned:** {category}")
                            st.markdown(f"**Explanation:** {explanation}")
                            st.download_button(
                                label="Download Complaint PDF",
                                data=pdf_buffer,
                                file_name=f"Complaint_{ticket_id}.pdf",
                                mime="application/pdf"
                            )
                            st.session_state.form_data = {}
                            st.session_state.form_data_translated = {}
                            st.session_state.chat_history = []
                            st.session_state.questions_index = 0

    elif selected == "Track Complaint":
        st.markdown('<i class="fas fa-search big-icon"></i>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="content-card">
                <h2>Track Your Complaint</h2>
                <p>Enter your ticket ID to check the status of your complaint.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        ticket_id = st.text_input("Enter Ticket ID (e.g., CYBER-XXXXXXXX)", "").upper()
        if ticket_id:
            ticket_data = fetch_complaint_from_supabase(ticket_id)
            if ticket_data:
                status_class = "status-pending" if ticket_data['status'] == "Under Investigation" else "status-resolved"
                st.markdown(
                    f"""
                    <div class="content-card">
                        <h3>Complaint Status</h3>
                        <p><strong>Ticket ID:</strong> {ticket_id}</p>
                        <p><strong>Status:</strong> <span class="status-badge {status_class}">{ticket_data['status']}</span></p>
                        <p><strong>Date Filed:</strong> {ticket_data['date_filed']}</p>
                        <p><strong>Last Updated:</strong> {ticket_data['last_updated']}</p>
                        <p><strong>Category:</strong> {ticket_data['translated_data'].get('category', 'N/A')}</p>
                        <p><strong>Category Explanation:</strong> {ticket_data['translated_data'].get('category_explanation', 'N/A')}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                pdf_buffer = generate_complaint_pdf(ticket_data['translated_data'])
                st.download_button(
                    label="Download Complaint PDF",
                    data=pdf_buffer,
                    file_name=f"Complaint_{ticket_id}.pdf",
                    mime="application/pdf"
                )
            else:
                st.error("❌ Invalid Ticket ID. Please check and try again.")

    elif selected == "Contact Us":
        st.markdown('<i class="fas fa-envelope big-icon"></i>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="content-card">
                <h2>Contact Us</h2>
                <p>For immediate assistance, please use the following contact information:</p>
                <div class="helpline-badge">National Cyber Crime Helpline: 1930</div>
                <p><strong>Email:</strong> cybercrime@nic.in</p>
                <p><strong>Website:</strong> <a href="https://cybercrime.gov.in" target="_blank">cybercrime.gov.in</a></p>
                <p><strong>Address:</strong> Ministry of Home Affairs, Cyber Crime Wing, North Block, New Delhi - 110001</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown(
        """
        <div class="footer">
            <p>© 2023 CyberGuard AI | All Rights Reserved | Powered by Streamlit & Google Gemini AI</p>
            <p>Disclaimer: This is a demo application. For actual complaints, please visit the official portal at cybercrime.gov.in</p>
        </div>
        """,
        unsafe_allow_html=True
    )

# Main App Logic
if not st.session_state.authenticated:
    if st.session_state.current_page == 'signin':
        sign_in_page()
    elif st.session_state.current_page == 'register':
        register_page()
else:
    dashboard()