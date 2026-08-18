import json
import os
from pathlib import Path
import base64
from groq import Groq
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from backend.prompts import EMAIL_ANALYSIS_PROMPT, EMAIL_REPLY_PROMPT
from html.parser import HTMLParser
import chromadb
from sentence_transformers import SentenceTransformer
import re
from html import unescape
from html.parser import HTMLParser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL")
RAG_INDEX_LIMIT = int(
    os.getenv("RAG_INDEX_LIMIT", "100")
)

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing from .env")

if not GROQ_MODEL:
    raise RuntimeError("GROQ_MODEL is missing from .env")

groq_client = Groq(api_key=GROQ_API_KEY)

BASE_DIR =  Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / "data" / "token.json"

CHROMA_PATH = BASE_DIR / "data" / "chroma"

chroma_client = chromadb.PersistentClient(
    path=str(CHROMA_PATH)
)

email_collection = chroma_client.get_or_create_collection(
    name="emails"
)

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

def store_email_in_chromadb(email):
    email_id = email["id"]
    email_text = email.get("body", "")

    if not email_text.strip():
        return False

    embedding = embedding_model.encode(
        email_text
    ).tolist()

    email_collection.upsert(
        ids=[email_id],
        documents=[email_text],
        embeddings=[embedding],
        metadatas=[
            {
                "sender": email.get("sender", ""),
                "subject": email.get("subject", ""),
                "date": email.get("date", ""),
                "thread_id": email.get("thread_id", "")
            }
        ]
    )

    return True

def index_recent_emails(max_results=None):
    if max_results is None:
        max_results = RAG_INDEX_LIMIT

    credentials = get_gmail_credentials()

    gmail_service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    indexed_count = 0
    skipped_count = 0
    next_page_token = None

    while indexed_count + skipped_count < max_results:

        remaining = max_results - (
            indexed_count + skipped_count
        )

        page_size = min(50, remaining)

        response = (
            gmail_service.users()
            .messages()
            .list(
                userId="me",
                maxResults=page_size,
                pageToken=next_page_token
            )
            .execute()
        )

        messages = response.get("messages", [])

        if not messages:
            break

        email_ids = [
            message["id"]
            for message in messages
        ]

        existing = email_collection.get(
            ids=email_ids
        )

        existing_ids = set(
            existing.get("ids", [])
        )

        for message in messages:

            email_id = message["id"]

            if email_id in existing_ids:
                skipped_count += 1
                continue

            full_email = get_email_by_id(
                email_id
            )

            if store_email_in_chromadb(
                full_email
            ):
                indexed_count += 1
            else:
                skipped_count += 1

        next_page_token = response.get(
            "nextPageToken"
        )

        if not next_page_token:
            break

    return {
        "indexed": indexed_count,
        "skipped": skipped_count
    }

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

def get_gmail_credentials():
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError("Gmail OAuth credentials are missing from .env")

    credentials = None

    # Reuse existing token if available
    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            GMAIL_SCOPES,
        )

    # Refresh expired token when possible
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

# First-time authentication
    if not credentials or not credentials.valid:
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

        flow = InstalledAppFlow.from_client_config(
            client_config,
            GMAIL_SCOPES,
        )

        credentials = flow.run_local_server(port=0)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    return credentials


def fetch_emails(max_results=10):
    credentials = get_gmail_credentials()

    gmail_service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    response = (
        gmail_service.users()
        .messages()
        .list(
            userId="me",
            maxResults=max_results
        )
        .execute()
    )

    messages = response.get("messages", [])

    emails = []

    for message in messages:
        email_data = (
            gmail_service.users()
            .messages()
            .get(
                userId="me",
                id=message["id"],
                format="metadata",
                metadataHeaders=[
                    "From",
                    "Subject",
                    "Date"
                ]
            )
            .execute()
        )

        headers = email_data.get("payload", {}).get("headers", [])

        email_headers = {
            header["name"]: header["value"]
            for header in headers
        }

        emails.append({
            "id": email_data["id"],
            "thread_id": email_data.get("threadId"),
            "sender": email_headers.get("From", ""),
            "subject": email_headers.get("Subject", ""),
            "date": email_headers.get("Date", "")
        })

    return emails

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()

        self.text = []
        self.skip_content = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"style", "script", "head", "noscript"}:
            self.skip_content = True

    def handle_endtag(self, tag):
        if tag.lower() in {"style", "script", "head", "noscript"}:
            self.skip_content = False

    def handle_data(self, data):
        if not self.skip_content:
            text = data.strip()

            if text:
                self.text.append(text)

    def get_text(self):
        return "\n".join(self.text)


def decode_body(data):
    padding = "=" * (-len(data) % 4)

    return base64.urlsafe_b64decode(
        data + padding
    ).decode("utf-8", errors="replace")


def extract_html_text(html):
    # Remove style/script blocks completely
    html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    html = re.sub(
        r"<head\b[^>]*>.*?</head>",
        "",
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    parser = HTMLTextExtractor()
    parser.feed(html)

    text = parser.get_text()

    text = unescape(text)

    # Remove excessive whitespace
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


def extract_email_body(payload):
    if not payload:
        return ""

    plain_text_parts = []
    html_parts = []

    body_data = payload.get(
        "body",
        {}
    ).get("data")

    mime_type = payload.get(
        "mimeType",
        ""
    )

    if body_data:

        decoded_body = decode_body(
            body_data
        )

        if mime_type == "text/plain":
            plain_text_parts.append(
                decoded_body
            )

        elif mime_type == "text/html":
            html_parts.append(
                decoded_body
            )

    for part in payload.get("parts", []):

        part_type = part.get(
            "mimeType",
            ""
        )

        part_data = part.get(
            "body",
            {}
        ).get("data")

        if part_data:

            decoded_part = decode_body(
                part_data
            )

            if part_type == "text/plain":
                plain_text_parts.append(
                    decoded_part
                )

            elif part_type == "text/html":
                html_parts.append(
                    decoded_part
                )

        nested_body = extract_email_body(
            part
        )

        if nested_body:
            plain_text_parts.append(
                nested_body
            )

    # Prefer real plain text
    if plain_text_parts:

        clean_text = "\n\n".join(
            plain_text_parts
        ).strip()

        return clean_text

    # Convert HTML to clean text
    if html_parts:

        return extract_html_text(
            html_parts[0]
        )

    return ""

def extract_email_html(payload):
    if not payload:
        return ""

    body_data = payload.get("body", {}).get("data")
    mime_type = payload.get("mimeType", "")

    if body_data and mime_type == "text/html":
        return decode_body(body_data)

    for part in payload.get("parts", []):
        html = extract_email_html(part)

        if html:
            return html

    return ""

def get_email_by_id(email_id):
    credentials = get_gmail_credentials()

    gmail_service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    email_data = (
        gmail_service.users()
        .messages()
        .get(
            userId="me",
            id=email_id,
            format="full"
        )
        .execute()
    )

    headers = email_data.get("payload", {}).get("headers", [])

    email_headers = {
        header["name"]: header["value"]
        for header in headers
    }

    body = extract_email_body(
        email_data.get("payload", {})
    )

    return {
        "id": email_data["id"],
        "thread_id": email_data.get("threadId"),
        "sender": email_headers.get("From", ""),
        "subject": email_headers.get("Subject", ""),
        "date": email_headers.get("Date", ""),
        "body": body,
        "html_body": extract_email_html(
            email_data.get("payload", {})
        )
    }

def analyze_email(email):
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": """
You are an email analysis assistant.

Analyze the email and return:
- a concise summary
- the email's intent
- the main topic
- urgency
- sentiment
- whether it contains unsafe, abusive, or profane content

Keep all responses concise.
"""
            },
            {
                "role": "user",
                "content": email
            }
        ],
        temperature=0.2,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "email_analysis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string"
                        },
                        "intent": {
                            "type": "string"
                        },
                        "topic": {
                            "type": "string"
                        },
                        "urgency": {
                            "type": "string",
                            "enum": [
                                "low",
                                "medium",
                                "high"
                            ]
                        },
                        "sentiment": {
                            "type": "string",
                            "enum": [
                                "positive",
                                "neutral",
                                "negative"
                            ]
                        },
                        "safety": {
                            "type": "string",
                            "enum": [
                                "safe",
                                "unsafe"
                            ]
                        }
                    },
                    "required": [
                        "summary",
                        "intent",
                        "topic",
                        "urgency",
                        "sentiment",
                        "safety"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    return json.loads(
        response.choices[0].message.content
    )


def generate_reply(email, analysis, email_id):
    retrieved_emails = search_similar_emails(
        email,
        top_k=2,
        exclude_email_id=email_id
    )

    # Keep the current email reasonably small
    email_for_prompt = email[:5000]

    context_parts = []

    for result in retrieved_emails:
        metadata = result.get("metadata", {})

        historical_email = result.get(
            "document",
            ""
        )

        # Keep each retrieved email small
        historical_email = historical_email[:1000]

        context_parts.append(
            f"Subject: {metadata.get('subject', '')}\n"
            f"Sender: {metadata.get('sender', '')}\n"
            f"Email:\n{historical_email}"
        )

    retrieved_context = "\n\n---\n\n".join(
        context_parts
    )

    prompt = EMAIL_REPLY_PROMPT.format(
        email=email_for_prompt,
        analysis=json.dumps(
            analysis,
            ensure_ascii=False
        ),
        retrieved_context=retrieved_context
    )

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
        max_completion_tokens=500
    )

    return response.choices[0].message.content.strip()


def search_similar_emails(query, top_k=3, exclude_email_id=None):
    if not query.strip():
        return []

    query_embedding = embedding_model.encode(
        query
    ).tolist()

    search_count = top_k + 1 if exclude_email_id else top_k

    results = email_collection.query(
        query_embeddings=[query_embedding],
        n_results=search_count
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    result_ids = results.get("ids", [[]])[0]

    matches = []

    for result_id, document, metadata, distance in zip(
        result_ids,
        documents,
        metadatas,
        distances
    ):
        if (
            exclude_email_id
            and result_id == exclude_email_id
        ):
            continue

        matches.append({
            "id": result_id,
            "document": document,
            "metadata": metadata,
            "distance": distance
        })

        if len(matches) >= top_k:
            break

    return matches

def reset_email_collection():
    global email_collection

    try:
        chroma_client.delete_collection(
            name="emails"
        )
    except Exception:
        pass

    email_collection = chroma_client.get_or_create_collection(
        name="emails"
    )

    return True

def send_email_reply(email_id, reply_body):
    credentials = get_gmail_credentials()

    gmail_service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    original_email = (
        gmail_service.users()
        .messages()
        .get(
            userId="me",
            id=email_id,
            format="metadata",
            metadataHeaders=[
                "From",
                "Subject"
            ]
        )
        .execute()
    )

    headers = original_email.get(
        "payload",
        {}
    ).get(
        "headers",
        []
    )

    email_headers = {
        header["name"]: header["value"]
        for header in headers
    }

    recipient = email_headers.get("From")

    subject = email_headers.get(
        "Subject",
        ""
    )

    if not recipient:
        raise ValueError(
            "Recipient email address could not be determined."
        )

    if subject and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message = MIMEText(
        reply_body,
        "plain",
        "utf-8"
    )

    message["To"] = recipient
    message["Subject"] = subject

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    sent_message = (
        gmail_service.users()
        .messages()
        .send(
            userId="me",
            body={
                "raw": raw_message,
                "threadId": original_email.get("threadId")
            }
        )
        .execute()
    )

    return sent_message