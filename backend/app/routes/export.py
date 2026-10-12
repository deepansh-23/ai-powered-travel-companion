import re
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from app.services.pdf_service import pdf_service
from app.services.tts_service import tts_service

router = APIRouter(prefix="/api/export", tags=["Export"])


class ExportPDFRequest(BaseModel):
    title: str
    content: Dict[str, Any] = {}


class ExportAudioRequest(BaseModel):
    text: str


@router.post("/pdf")
async def export_pdf(req: ExportPDFRequest):
    """Generate and return actual binary PDF (Section 23)."""
    try:
        pdf_bytes = pdf_service.generate_itinerary_pdf_bytes(req.title, req.content)
        safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', req.title or "Itinerary")[:50]
        if not safe_filename.endswith(".pdf"):
            safe_filename += ".pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "Content-Length": str(len(pdf_bytes))
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(exc)}")



@router.post("/audio")
async def export_audio(req: ExportAudioRequest):
    """Generate audio TTS synthesis payload."""
    return tts_service.synthesize_audio_payload(req.text)
