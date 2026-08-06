from fastapi import APIRouter

from .. import rag_pipeline
from ..models import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = rag_pipeline.answer_query(req.query, top_k=req.top_k)
    return result
