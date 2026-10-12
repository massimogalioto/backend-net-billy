# estrai-testo-pdf.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile
from pdf2image import convert_from_path  # 🆕 #modificato (2025-06-03)
import pytesseract  # 🆕 #modificato (2025-06-03)
import os

router = APIRouter()

@router.post("/estrai-testo-pdf", summary="Estrai testo da un PDF con OCR", tags=["Utility"])  #modificato (2025-06-03)
async def estrai_testo_pdf(file: UploadFile = File(...)):
    #if not file.filename.endswith(".pdf"):
    #   raise HTTPException(status_code=400, detail="Il file deve essere un PDF")

    try:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp:
            file.file.seek(0)
            temp.write(file.file.read())
            temp_path = temp.name

        # 🆕 Converti tutte le pagine PDF in immagini
        immagini = convert_from_path(temp_path, dpi=300)  #modificato (2025-06-03)

        testo_estratto = ""
        for img in immagini:
            testo_estratto += pytesseract.image_to_string(img, lang="ita") + "\n"  #modificato (2025-06-03)

        os.remove(temp_path)

        if not testo_estratto.strip():
            raise HTTPException(status_code=422, detail="OCR non ha estratto testo utile")

        return JSONResponse({
            "filename": file.filename,
            "contenuto_testo": testo_estratto[:20000]  #modificato (2026-10-12)
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore: {str(e)}")
