from fastapi import APIRouter, HTTPException

from .. import sop_manager
from ..database import get_session, SOP
from ..models import SOPCreateRequest, SOPOut

router = APIRouter(prefix="/sops", tags=["sops"])


@router.get("", response_model=list[SOPOut])
def list_sops():
    session = get_session()
    try:
        sops = session.query(SOP).all()
        return sops
    finally:
        session.close()


@router.post("", response_model=SOPOut)
def create_sop(req: SOPCreateRequest):
    sop = sop_manager.create_sop(req.title, req.domain, req.content)
    return get_sop(sop.id)


@router.get("/{sop_id}", response_model=SOPOut)
def get_sop(sop_id: str):
    session = get_session()
    try:
        sop = session.query(SOP).filter(SOP.id == sop_id).first()
        if not sop:
            raise HTTPException(404, "SOP not found")
        return sop
    finally:
        session.close()


@router.post("/{sop_id}/approve/{version_id}", response_model=SOPOut)
def approve_version(sop_id: str, version_id: str):
    version = sop_manager.approve_version(sop_id, version_id)
    if not version:
        raise HTTPException(404, "SOP or version not found")
    return get_sop(sop_id)


@router.post("/{sop_id}/reject/{version_id}", response_model=SOPOut)
def reject_version(sop_id: str, version_id: str):
    version = sop_manager.reject_version(sop_id, version_id)
    if not version:
        raise HTTPException(404, "SOP or version not found")
    return get_sop(sop_id)
