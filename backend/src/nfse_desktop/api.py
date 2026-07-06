from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread

from fastapi.background import BackgroundTasks
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .certificates import inspect_pfx
from .config import Settings
from .database import Database
from .exporter import DocumentExporter
from .repository import Repository
from .sync import SyncService


class WindowsCompanyPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cnpj: str
    legal_name: str = Field(alias="legalName")
    thumbprint: str
    expires_at: str = Field(alias="expiresAt")


class WindowsBatchPayload(BaseModel):
    requested_nsu: int
    response: dict[str, object]


class SyncLogPayload(BaseModel):
    level: str
    message: str


class SettingsPayload(BaseModel):
    notes_directory: str
    notifications_enabled: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or Settings.from_environment()
    database = Database(current_settings.data_dir / "nfse-desktop.db")
    repository = Repository(database)
    sync_service = SyncService(repository, current_settings.data_dir)
    exporter = DocumentExporter(repository)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        database.initialize()
        repository.initialize_settings(str(current_settings.default_notes_dir))
        Thread(
            target=database.backfill_note_numbers,
            name="nfse-note-number-backfill",
            daemon=True,
        ).start()
        yield

    app = FastAPI(title="NFS-e Desktop API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5174"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def authorize(x_nfse_token: str = Header(default="")) -> None:
        if current_settings.api_token and x_nfse_token != current_settings.api_token:
            raise HTTPException(status_code=401, detail="Token local invalido.")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/companies", dependencies=[Depends(authorize)])
    def list_companies():
        return repository.list_companies()

    @app.get("/settings", dependencies=[Depends(authorize)])
    def get_settings():
        return repository.get_settings()

    @app.put("/settings", dependencies=[Depends(authorize)])
    def update_settings(payload: SettingsPayload):
        notes_directory = payload.notes_directory.strip()
        if not notes_directory:
            raise HTTPException(status_code=422, detail="Selecione uma pasta para as notas.")
        return repository.update_settings(notes_directory, payload.notifications_enabled)

    @app.post("/companies/pfx", dependencies=[Depends(authorize)])
    async def create_pfx_company(
        certificate: UploadFile = File(...),
        password: str = Form(...),
        remember_certificate: bool = Form(False),
        credential_reference: str | None = Form(None),
    ):
        content = await certificate.read()
        info = inspect_pfx(content, password)
        repository.save_company(
            {
                "cnpj": info.cnpj,
                "legal_name": info.legal_name,
                "certificate_source": "pfx",
                "remember_certificate": remember_certificate,
                "certificate_reference": credential_reference if remember_certificate else None,
                "certificate_expires_at": info.expires_at,
            }
        )
        return repository.get_company(info.cnpj)

    @app.post("/companies/windows", dependencies=[Depends(authorize)])
    def create_windows_company(payload: WindowsCompanyPayload):
        cnpj = "".join(character for character in payload.cnpj if character.isdigit())
        if len(cnpj) != 14:
            raise HTTPException(status_code=422, detail="CNPJ do certificado invalido.")
        repository.save_company(
            {
                "cnpj": cnpj,
                "legal_name": payload.legal_name,
                "certificate_source": "windows",
                "remember_certificate": True,
                "certificate_reference": payload.thumbprint,
                "certificate_expires_at": payload.expires_at,
            }
        )
        return repository.get_company(cnpj)

    @app.get("/companies/{cnpj}/documents", dependencies=[Depends(authorize)])
    def list_documents(
        cnpj: str,
        data_inicial: str | None = None,
        data_final: str | None = None,
        tipo: str | None = None,
        busca: str | None = None,
        situacao: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ):
        if data_inicial and data_final and data_inicial > data_final:
            raise HTTPException(
                status_code=422,
                detail="A data inicial nao pode ser posterior a data final.",
            )
        if tipo not in (None, "emitida", "recebida"):
            raise HTTPException(status_code=422, detail="Tipo de nota invalido.")
        if situacao not in (None, "todas", "autorizada", "cancelada"):
            raise HTTPException(status_code=422, detail="Situacao da nota invalida.")
        return repository.list_documents(
            cnpj,
            start_date=data_inicial,
            end_date=data_final,
            direction=tipo,
            search=busca,
            status=None if situacao == "todas" else situacao,
            page=max(page, 1),
            per_page=min(max(per_page, 1), 100),
        )

    @app.get("/companies/{cnpj}/sync/logs", dependencies=[Depends(authorize)])
    def list_sync_logs(cnpj: str, limit: int = 20):
        return repository.list_sync_logs(cnpj, min(max(limit, 1), 20))

    @app.get("/companies/{cnpj}/documents.zip", dependencies=[Depends(authorize)])
    def download_documents_zip(
        cnpj: str,
        background_tasks: BackgroundTasks,
        data_inicial: str,
        data_final: str,
        tipo: str,
    ):
        if tipo not in ("emitida", "recebida"):
            raise HTTPException(status_code=422, detail="Tipo de nota inválido.")
        if data_inicial > data_final:
            raise HTTPException(
                status_code=422,
                detail="A data inicial não pode ser posterior à data final.",
            )
        if not repository.get_company(cnpj):
            raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        try:
            zip_path, count = exporter.create_zip(
                cnpj,
                start_date=data_inicial,
                end_date=data_final,
                direction=tipo,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Não foi possível gerar os PDFs: {str(exc)[:300]}",
            ) from exc
        if count == 0:
            zip_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=404,
                detail="Nenhuma nota encontrada no período selecionado.",
            )
        background_tasks.add_task(Path(zip_path).unlink, missing_ok=True)
        filename = f"{cnpj}-{tipo}s-{data_inicial}-{data_final}.zip"
        return FileResponse(zip_path, media_type="application/zip", filename=filename)

    @app.post("/companies/{cnpj}/sync/logs", dependencies=[Depends(authorize)])
    def add_sync_log(cnpj: str, payload: SyncLogPayload):
        level = payload.level if payload.level in ("info", "warning", "error") else "info"
        if level == "error":
            repository.set_sync_state(
                cnpj,
                status="error",
                diagnostic=payload.message,
            )
        elif level == "warning":
            repository.set_sync_state(
                cnpj,
                status="waiting",
                diagnostic=payload.message,
            )
        else:
            repository.add_sync_log(cnpj, level, payload.message)
        return {"saved": True}

    @app.post("/companies/{cnpj}/sync/pfx", dependencies=[Depends(authorize)])
    async def sync_pfx_company(
        cnpj: str,
        certificate: UploadFile = File(...),
        password: str = Form(...),
    ):
        return sync_service.synchronize_pfx(cnpj, await certificate.read(), password)

    @app.post("/companies/{cnpj}/sync/windows/batch", dependencies=[Depends(authorize)])
    def sync_windows_batch(cnpj: str, payload: WindowsBatchPayload):
        return sync_service.process_windows_batch(
            cnpj,
            payload.requested_nsu,
            payload.response,
        )

    return app


app = create_app()
