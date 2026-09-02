from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.connection import get_db

from database.models import (
    Interview,
    InterviewQuestion,
    CandidateAnswer,
    Evaluation
)

from Services.llm_handel import eval_answer


router = APIRouter()


# ============================================================
# REQUEST SCHEMA
# ============================================================

class AnswerRequest(BaseModel):
    answer: str


# ============================================================
# GET INTERVIEW
# ============================================================

@router.get("/interview/{token}")
def get_interview(
    token: str,
    db: Session = Depends(get_db)
):

    interview = (
        db.query(Interview)
        .filter(
            Interview.token == token
        )
        .first()
    )

    if not interview:
        raise HTTPException(
            status_code=404,
            detail="Interview not found."
        )

    if interview.status == "completed":
        raise HTTPException(
            status_code=400,
            detail="This interview has already been completed."
        )

    question = (
        db.query(InterviewQuestion)
        .filter(
            InterviewQuestion.interview_id
            == interview.id
        )
        .order_by(
            InterviewQuestion.question_order
        )
        .first()
    )

    if not question:
        raise HTTPException(
            status_code=404,
            detail="Interview question not found."
        )

    # Mark interview as started
    if interview.started_at is None:

        interview.started_at = datetime.utcnow()
        interview.status = "in_progress"

        db.commit()

    return {
        "candidate_id": interview.candidate.id,
        "candidate_name": interview.candidate.name,
        "interview_id": interview.id,
        "question_id": question.id,
        "question": question.question,
        "status": interview.status
    }


# ============================================================
# SUBMIT ANSWER
# ============================================================

@router.post("/interview/{token}/answer")
def submit_answer(
    token: str,
    request: AnswerRequest,
    db: Session = Depends(get_db)
):

    if not request.answer.strip():

        raise HTTPException(
            status_code=400,
            detail="Answer cannot be empty."
        )

    # ========================================================
    # Find interview
    # ========================================================

    interview = (
        db.query(Interview)
        .filter(
            Interview.token == token
        )
        .first()
    )

    if not interview:

        raise HTTPException(
            status_code=404,
            detail="Interview not found."
        )

    if interview.status == "completed":

        raise HTTPException(
            status_code=400,
            detail="This interview has already been completed."
        )

    # ========================================================
    # Find question
    # ========================================================

    question = (
        db.query(InterviewQuestion)
        .filter(
            InterviewQuestion.interview_id
            == interview.id
        )
        .order_by(
            InterviewQuestion.question_order
        )
        .first()
    )

    if not question:

        raise HTTPException(
            status_code=404,
            detail="Interview question not found."
        )

    # ========================================================
    # Evaluate answer
    # ========================================================

    evaluation = eval_answer(
        question=question.question,
        answer=request.answer
    )

    # ========================================================
    # Save candidate answer
    # ========================================================

    candidate_answer = CandidateAnswer(
        question_id=question.id,
        answer=request.answer
    )

    db.add(candidate_answer)

    db.flush()

    # ========================================================
    # Save evaluation
    # ========================================================

    evaluation_record = Evaluation(
        answer_id=candidate_answer.id,

        overall_score=str(
            evaluation.score
        ),

        feedback=evaluation.overall_feedback,

        strengths=evaluation.strengths,

        weaknesses=(
            evaluation.missing_points
            + evaluation.mistakes
        )
    )

    db.add(evaluation_record)

    # ========================================================
    # Complete interview
    # ========================================================

    interview.status = "completed"

    interview.finished_at = datetime.utcnow()

    interview.overall_score = str(
        evaluation.score
    )

    db.commit()

    return {
        "message": "Answer submitted successfully.",

        "score": evaluation.score,

        "technical_correctness":
            evaluation.technical_correctness,

        "relevance":
            evaluation.relevance,

        "depth":
            evaluation.depth,

        "strengths":
            evaluation.strengths,

        "missing_points":
            evaluation.missing_points,

        "mistakes":
            evaluation.mistakes,

        "overall_feedback":
            evaluation.overall_feedback
    }