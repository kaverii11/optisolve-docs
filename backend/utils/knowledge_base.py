import logging
import os
from hashlib import sha256

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# CHROMA_DB_PATH lets tests use a throwaway store instead of the demo's chroma_db
client = chromadb.PersistentClient(
    path=os.getenv("CHROMA_DB_PATH") or os.path.join(BASE_DIR, "chroma_db")
)

# Use a local embedding model (no API cost for embedding)
embedding_model = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

collection = client.get_or_create_collection(
    name="support_tickets_v2",
    embedding_function=embedding_model,
    metadata={"hnsw:space": "cosine"}
)

def seed_knowledge_base():
    # Check if already seeded to avoid duplicates
    if collection.count() > 0:
        return

    seeds = [
    {"ticket": "How do I reset my password?", "reply": "Go to Settings > Security > Reset Password. You'll receive an email with a reset link within 2 minutes.", "cat": "Password reset"},
    {"ticket": "VPN is not connecting on Mac", "reply": "Ensure Tunnelblick is updated and re-import the config file. If the issue persists, restart the VPN service.", "cat": "VPN"},
    {"ticket": "My account is locked", "reply": "Accounts lock after 5 failed attempts. Please wait 30 minutes or contact support to unlock immediately.", "cat": "Account locked"},
    {"ticket": "Where can I find my latest invoice?", "reply": "Invoices are under Billing > History in your dashboard. You can download PDF copies from there.", "cat": "Billing"},
    {"ticket": "How do I install the software on Windows?", "reply": "Download the installer from our website, run it as administrator, and follow the setup wizard. Restart your machine after installation.", "cat": "Software installation"},
    {"ticket": "My computer is running very slowly", "reply": "Try restarting your machine first. If the issue persists, clear your cache, close unused applications, and check for pending system updates.", "cat": "Slow performance"},
    {"ticket": "I am not receiving any emails", "reply": "Check your spam/junk folder first. If emails are missing, verify your email settings under Account > Email Preferences and ensure your inbox is not full.", "cat": "Email not working"},
    {"ticket": "I need help with something not listed here", "reply": "Thank you for reaching out. Could you please describe your issue in more detail? Our support team will get back to you as soon as possible.", "cat": "General"},
    {"ticket": "How do I update my billing information?", "reply": "Go to Account > Billing > Payment Methods. You can add, remove or update your card details there.", "cat": "Billing"},
    {"ticket": "VPN keeps disconnecting frequently", "reply": "Try switching VPN servers, check your internet connection stability, and ensure your firewall isn't blocking the VPN client.", "cat": "VPN"},
    {"ticket": "How do I enable two-factor authentication?", "reply": "Go to Settings > Security > Two-Factor Authentication and choose an authenticator app or SMS. Scan the QR code, enter the 6-digit code to confirm, and save your backup codes somewhere safe.", "cat": "Account security"},
    {"ticket": "How do I change the email address on my account?", "reply": "Go to Settings > Profile > Email and enter your new address. We'll send a verification link to the new email; the change takes effect once you click it.", "cat": "Account"},
    {"ticket": "How do I cancel my subscription?", "reply": "Go to Billing > Subscription > Cancel Plan. You keep access until the end of your current billing period and won't be charged again.", "cat": "Billing"},
    {"ticket": "How do I get a refund?", "reply": "Refunds are available within 30 days of payment. Go to Billing > History, select the invoice, and click Request Refund. Refunds reach your card in 5-7 business days.", "cat": "Billing"},
    {"ticket": "How do I add a new user to my team?", "reply": "Go to Admin > Team > Invite Member, enter their email, and choose a role (Viewer, Editor or Admin). They'll get an invite link that's valid for 7 days.", "cat": "Team management"},
    {"ticket": "How do I export my data?", "reply": "Go to Settings > Data > Export and choose CSV or JSON. We'll email you a download link within 10 minutes.", "cat": "Data"},
    {"ticket": "How do I connect to the office Wi-Fi?", "reply": "Select the network Corp-WiFi and sign in with your company email and password. If it fails, choose Forget This Network, then reconnect and sign in again.", "cat": "Network"},
    {"ticket": "How do I set up work email on my phone?", "reply": "Install the Outlook app, sign in with your work email, and approve the sign-in request on your authenticator. Your mail, calendar and contacts will sync automatically.", "cat": "Email"},
    {"ticket": "How do I update the software to the latest version?", "reply": "Open the app and go to Help > Check for Updates. Install the update, then restart the app to finish.", "cat": "Software installation"},
    {"ticket": "How do I share a file with a colleague?", "reply": "Open the file, click Share, and add your colleague's email. Choose View or Edit access, then click Send.", "cat": "Collaboration"},
]

    collection.add(
        documents=[s["ticket"] for s in seeds],
        metadatas=[{"reply": s["reply"], "source": "static"} for s in seeds],
        ids=[f"seed_{i}" for i in range(len(seeds))]
    )
    logger.info("Knowledge base seeded with %d entries", len(seeds))

DOCUMENT_SOURCE = "document"


def add_document_chunks(filename: str, chunks: list[str]) -> list[str]:
    """
    Embed and store parsed document chunks in the same collection as the seeds,
    so analyze_ticket retrieves them with no changes. The chunk text is stored as
    the embedded document and as "reply", because analyze_ticket only passes
    metadata reply/resolution to the LLM as context.

    Re-uploading a file with the same name replaces its previous chunks.
    """
    collection.delete(where={"$and": [{"source": DOCUMENT_SOURCE}, {"filename": filename}]})
    if not chunks:
        return []

    file_key = sha256(filename.encode("utf-8")).hexdigest()[:12]
    ids = [f"doc_{file_key}_{i}" for i in range(len(chunks))]
    collection.add(
        documents=chunks,
        metadatas=[
            {
                "reply": chunk,
                "source": DOCUMENT_SOURCE,
                "filename": filename,
                "chunk_index": i,
            }
            for i, chunk in enumerate(chunks)
        ],
        ids=ids,
    )
    logger.info("Added %d chunks from %s to the knowledge base", len(chunks), filename)
    return ids

def get_collection():
    return collection