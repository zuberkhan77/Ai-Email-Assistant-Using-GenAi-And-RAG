# AI Email Assistant Using Generative AI and RAG

An AI-powered email assistant that uses Generative AI and Retrieval-Augmented Generation (RAG) to understand emails, summarize them, classify them, retrieve relevant historical emails, generate context-aware replies, and send approved replies through Gmail.

The system is designed to minimize unnecessary LLM API calls and keeps the user in control of email sending.

---

## Features

- Gmail OAuth 2.0 authentication
- Fetch recent emails from Gmail
- View emails in an email-style preview
- Generate email summaries
- Classify emails by:
  - Intent
  - Topic
  - Urgency
  - Sentiment
  - Safety
- Local email embeddings using Sentence Transformers
- Persistent vector storage using ChromaDB
- Semantic search over historical emails
- RAG-based reply generation
- AI-generated reply drafts
- User review and editing before sending
- Send approved replies through Gmail
- FastAPI backend
- Streamlit frontend
- Controlled Groq API usage
- Secrets managed through `.env`

---

## Architecture

```text
                    Gmail
                      |
                      v
                FastAPI Backend
                      |
          +-----------+-----------+
          |                       |
          v                       v
    Email Processing         Groq API
          |                       |
          v                       v
  Sentence Transformers     AI Analysis
          |
          v
      ChromaDB
          |
          v
   Semantic Retrieval
          |
          v
     RAG Context
          |
          v
      Groq API
          |
          v
    AI Reply Draft
          |
          v
      User Review
          |
          v
      Gmail Send


        Streamlit Frontend
                |
                v
          FastAPI Backend