"""Memory export routes."""

from __future__ import annotations

import tempfile
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from ...utils import validate_safe_path
from ..errors import error_response


def register_memory_export_routes(router: APIRouter, memos, kg_bridge) -> None:
    """Register markdown and parquet export endpoints."""

    @router.get("/api/v1/export/markdown", response_model=None)
    async def api_export_markdown(
        output_dir: str | None = None, update: bool = False, wiki_dir: str | None = None
    ) -> FileResponse:
        import asyncio

        from ...export_markdown import MarkdownExporter

        if output_dir is not None:
            try:
                output_dir = validate_safe_path(output_dir)
            except ValueError:
                return error_response("Invalid output_dir: path traversal rejected", status_code=400)
        if wiki_dir is not None:
            try:
                wiki_dir = validate_safe_path(wiki_dir)
            except ValueError:
                return error_response("Invalid wiki_dir: path traversal rejected", status_code=400)

        kg = kg_bridge.kg if hasattr(kg_bridge, "kg") else None
        export_dir = output_dir
        wiki_export_dir = wiki_dir

        def _blocking_export() -> str:
            export_root = Path(export_dir) if export_dir else Path(tempfile.mkdtemp(prefix="memos-markdown-export-"))
            MarkdownExporter(memos, kg=kg, wiki_dir=wiki_export_dir).export(str(export_root), update=update)
            zip_path = export_root.parent / f"{export_root.name}.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for file_path in sorted(export_root.rglob("*")):
                    if file_path.is_file():
                        bundle.write(file_path, arcname=str(file_path.relative_to(export_root)))
            return str(zip_path)

        zip_path = await asyncio.to_thread(_blocking_export)
        return FileResponse(
            zip_path, media_type="application/zip", filename=f"memos-markdown-export-{int(time.time())}.zip"
        )

    @router.get("/api/v1/export/parquet", response_model=None)
    async def api_export_parquet(include_metadata: bool = True, compression: str = "zstd") -> FileResponse:
        import asyncio

        def _blocking_export() -> tuple[str, dict]:
            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                result = memos.export_parquet(tmp.name, include_metadata=include_metadata, compression=compression)
                return tmp.name, result

        try:
            tmp_name, result = await asyncio.to_thread(_blocking_export)
            return FileResponse(
                tmp_name,
                media_type="application/octet-stream",
                filename=f"memos-export-{int(time.time())}.parquet",
                headers={"X-Memos-Total": str(result["total"]), "X-Memos-Size": str(result["size_bytes"])},
            )
        except ImportError as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "message": str(exc),
                    "hint": "Install with: pip install memos-os[parquet]",
                },
            )
