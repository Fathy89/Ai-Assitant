import os

from typing import Optional

from dotenv import load_dotenv

from sqlalchemy.orm import Session

from langchain_cohere import ChatCohere

from database.models import (
    Candidate,
    CVChunk,
    HRConversation,
    HRMessage
)

from Services.fiass_service import (
    search_faiss
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


COHERE_API_KEY = os.getenv(
    "COHERE_API_KEY"
)


if not COHERE_API_KEY:

    raise ValueError(
        "COHERE_API_KEY is not set in .env"
    )


LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "command-a-03-2025"
)


# ============================================================
# LLM
# ============================================================

llm = ChatCohere(

    model=LLM_MODEL,

    temperature=0,

    cohere_api_key=COHERE_API_KEY
)


# ============================================================
# RETRIEVE CV CHUNKS
# ============================================================

def retrieve_cv_chunks(

    db: Session,

    question: str,

    candidate_id: Optional[int] = None,

    top_k: int = 8
):

    # --------------------------------------------------------
    # Search FAISS
    # --------------------------------------------------------

    results = search_faiss(

        query=question,

        k=top_k * 3
    )


    if not results:

        return []


    retrieved = []


    # --------------------------------------------------------
    # Process FAISS results
    # --------------------------------------------------------

    for document, score in results:

        metadata = document.metadata


        chunk_id = metadata.get(
            "chunk_id"
        )


        document_candidate_id = metadata.get(
            "candidate_id"
        )


        # ----------------------------------------------------
        # Candidate filtering
        # ----------------------------------------------------

        if (

            candidate_id is not None

            and document_candidate_id != candidate_id

        ):

            continue


        if chunk_id is None:

            continue


        # ----------------------------------------------------
        # Get PostgreSQL chunk
        # ----------------------------------------------------

        chunk = (

            db.query(CVChunk)

            .filter(
                CVChunk.id == chunk_id
            )

            .first()
        )


        if not chunk:

            continue


        # ----------------------------------------------------
        # Candidate
        # ----------------------------------------------------

        candidate = (

            db.query(Candidate)

            .filter(
                Candidate.id
                == chunk.candidate_id
            )

            .first()
        )


        if not candidate:

            continue


        retrieved.append({

            "candidate_id":
                candidate.id,

            "candidate_name":
                candidate.name,

            "chunk_id":
                chunk.id,

            "section":
                chunk.section,

            "content":
                chunk.content,

            "score":
                float(score)
        })


        if len(retrieved) >= top_k:

            break


    return retrieved


# ============================================================
# CONVERSATION
# ============================================================

def get_or_create_conversation(

    db: Session,

    conversation_id: Optional[int] = None

):

    if conversation_id is not None:

        conversation = (

            db.query(
                HRConversation
            )

            .filter(
                HRConversation.id
                == conversation_id
            )

            .first()
        )


        if conversation:

            return conversation


    conversation = HRConversation()


    db.add(
        conversation
    )


    db.commit()


    db.refresh(
        conversation
    )


    return conversation


# ============================================================
# HISTORY
# ============================================================

def get_conversation_history(

    db: Session,

    conversation_id: int,

    limit: int = 10

):

    messages = (

        db.query(
            HRMessage
        )

        .filter(
            HRMessage.conversation_id
            == conversation_id
        )

        .order_by(
            HRMessage.created_at.desc()
        )

        .limit(limit)

        .all()
    )


    messages.reverse()


    return messages


# ============================================================
# CONTEXT
# ============================================================

def build_context(
    sources
):

    if not sources:

        return (
            "No relevant candidate information "
            "was found."
        )


    context = []


    for i, source in enumerate(
        sources,
        start=1
    ):

        context.append(

            f"""
SOURCE {i}

Candidate:
{source["candidate_name"]}

Candidate ID:
{source["candidate_id"]}

Section:
{source["section"] or "Unknown"}

CV Content:
{source["content"]}
"""
        )


    return "\n".join(
        context
    )


# ============================================================
# CONVERSATION TEXT
# ============================================================

def build_conversation(
    history
):

    if not history:

        return "No previous conversation."


    messages = []


    for message in history:

        messages.append(

            f"{message.role.upper()}: "
            f"{message.content}"
        )


    return "\n".join(
        messages
    )


# ============================================================
# GENERATE ANSWER
# ============================================================

def generate_answer(

    question: str,

    sources,

    history

):

    context = build_context(
        sources
    )


    conversation = build_conversation(
        history
    )


    prompt = f"""
You are an AI HR recruitment assistant.

Your task is to answer HR questions about candidates.

You MUST follow these rules:

1. Use ONLY the retrieved CV information.
2. Never invent candidate information.
3. Never assume information that is not present.
4. If the information is unavailable, say:
   "I couldn't find that information in the candidate CVs."
5. If multiple candidates are relevant, separate them clearly.
6. Always mention candidate names when appropriate.
7. Do not confuse information between candidates.
8. Previous conversation can be used only for conversational context.
9. The retrieved CV information is the source of truth.
10. Be concise and professional.

RETRIEVED CV INFORMATION:

{context}


PREVIOUS CONVERSATION:

{conversation}


HR QUESTION:

{question}


ANSWER:
"""


    response = llm.invoke(
        prompt
    )


    return response.content


# ============================================================
# HR RAG CHAT
# ============================================================

def hr_rag_chat(

    db: Session,

    question: str,

    candidate_id: Optional[int] = None,

    conversation_id: Optional[int] = None

):

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

    conversation = (
        get_or_create_conversation(

            db=db,

            conversation_id=conversation_id
        )
    )


    # --------------------------------------------------------
    # History
    # --------------------------------------------------------

    history = (
        get_conversation_history(

            db=db,

            conversation_id=conversation.id
        )
    )


    # --------------------------------------------------------
    # Retrieval
    # --------------------------------------------------------

    sources = retrieve_cv_chunks(

        db=db,

        question=question,

        candidate_id=candidate_id,

        top_k=8
    )


    # --------------------------------------------------------
    # Generate
    # --------------------------------------------------------

    answer = generate_answer(

        question=question,

        sources=sources,

        history=history
    )


    # --------------------------------------------------------
    # Save user message
    # --------------------------------------------------------

    user_message = HRMessage(

        conversation_id=conversation.id,

        role="user",

        content=question
    )


    db.add(
        user_message
    )


    # --------------------------------------------------------
    # Save assistant message
    # --------------------------------------------------------

    assistant_message = HRMessage(

        conversation_id=conversation.id,

        role="assistant",

        content=answer
    )


    db.add(
        assistant_message
    )


    db.commit()


    return {

        "answer":
            answer,

        "conversation_id":
            conversation.id,

        "sources":
            sources
    }