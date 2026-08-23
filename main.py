from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.services import (
    get_gmail_credentials,
    fetch_emails,
    get_email_by_id,
    analyze_email,
    generate_reply,
    index_recent_emails,
    send_email_reply,
    search_emails,
)


app = FastAPI(title="AI Email Assistant")


class ReplyRequest(BaseModel):
    analysis: dict
    human_guidance: str | None = None


class SendReplyRequest(BaseModel):
    reply: str


@app.get("/")
def root():
    return {
        "message": "AI Email Assistant backend is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.get("/auth/gmail")
def authenticate_gmail():
    try:
        get_gmail_credentials()

        return {
            "status": "success",
            "message": "Gmail authentication successful",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gmail authentication failed: {str(e)}",
        )


@app.get("/emails")
def get_emails():
    try:
        emails = fetch_emails(
            max_results=10
        )

        return {
            "count": len(emails),
            "emails": emails,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch emails: {str(e)}",
        )


@app.get("/emails/{email_id}")
def get_email(email_id: str):
    try:
        email = get_email_by_id(
            email_id
        )

        return email

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch email: {str(e)}",
        )


@app.get("/emails/{email_id}/analyze")
def analyze_email_endpoint(email_id: str):
    try:
        email = get_email_by_id(
            email_id
        )

        result = analyze_email(
            email["body"]
        )

        return {
            "email_id": email_id,
            "analysis": result,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Email analysis failed: {str(e)}",
        )


@app.post("/emails/{email_id}/generate-reply")
def generate_email_reply(
    email_id: str,
    request: ReplyRequest,
):
    try:
        email = get_email_by_id(
            email_id
        )

        reply = generate_reply(
            email["body"],
            request.analysis,
            email_id,
            request.human_guidance,
        )

        return {
            "email_id": email_id,
            "reply": reply,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Reply generation failed: {str(e)}",
        )


@app.post("/index-emails")
def index_emails():
    try:
        result = index_recent_emails()

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Email indexing failed: {str(e)}",
        )


@app.post("/emails/{email_id}/send-reply")
def send_reply(
    email_id: str,
    request: SendReplyRequest,
):
    if not request.reply.strip():
        raise HTTPException(
            status_code=400,
            detail="Reply cannot be empty.",
        )

    try:
        result = send_email_reply(
            email_id,
            request.reply,
        )

        return {
            "status": "success",
            "message": "Email sent successfully.",
            "message_id": result.get("id"),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {str(e)}",
        )


@app.get("/search-emails")
def search_emails_endpoint(query: str):
    if not query.strip():
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty.",
        )

    try:
        result = search_emails(
            query=query,
            top_k=10,
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Email search failed: {str(e)}",
        )