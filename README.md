# ComplianceOS

Internal prototype for Five Rise Consultancy — ISO 9001 / 14001 / 45001 compliance gap analysis tool.

## Stack
- **Backend:** FastAPI (Python), Azure OpenAI GPT-4.1-mini, ChromaDB
- **Frontend:** React + Vite + shadcn/ui
- **OCR:** Azure Document Intelligence

## Quick start
```powershell
# Backend
cd backend
..\venv-compliance\Scripts\Activate.ps1
uvicorn api_server:app --reload

# Frontend
cd frontend
npm run dev
```
