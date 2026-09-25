"""
MinIO Crawler Storage Adapter

Adapter especializado para armazenamento de arquivos crawler no MinIO
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import timedelta

from shared.minio_client import MinIOClient
from domain.value_objects.crawler_enums import AssetType

logger = logging.getLogger(__name__)


class MinioCrawlerStorageAdapter:
    """
    Adapter para storage de crawler usando MinIO

    Estrutura de pastas padronizada:
    - crawled/{execution_id}/files/         → Arquivos baixados (PDFs, etc.)
    - crawled/{execution_id}/pages/         → HTML pages
    - crawled/{execution_id}/assets/css/    → CSS files
    - crawled/{execution_id}/assets/js/     → JavaScript files
    - crawled/{execution_id}/assets/images/ → Imagens
    - crawled/{execution_id}/assets/fonts/  → Fontes
    - crawled/{execution_id}/assets/videos/ → Vídeos
    - crawled/{execution_id}/merged/        → PDFs merged

    Características:
    - Paths consistentes e organizados
    - Metadados automáticos (timestamp, source_url, etc.)
    - Cleanup de execuções antigas
    - Pre-signed URLs para download
    """

    def __init__(self, minio_client: MinIOClient):
        """
        Inicializa adapter

        Args:
            minio_client: Cliente MinIO configurado
        """
        self.client = minio_client
        self.bucket = minio_client.bucket_crawled

    async def upload_crawled_file(
        self,
        execution_id: str,
        file_path: Path,
        source_url: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload arquivo baixado pelo crawler

        Args:
            execution_id: ID da execução do crawler
            file_path: Caminho local do arquivo
            source_url: URL original do arquivo
            content_type: MIME type (opcional)

        Returns:
            Object name no MinIO
        """
        object_name = f"crawled/{execution_id}/files/{file_path.name}"

        metadata = {
            "source-url": source_url,
            "execution-id": execution_id,
            "original-filename": file_path.name,
        }

        self.client.upload_file(
            file_path=str(file_path),
            object_name=object_name,
            bucket_name=self.bucket,
            content_type=content_type,
            metadata=metadata,
        )

        logger.info(f"Uploaded crawled file: {object_name}")
        return object_name

    async def upload_html_page(
        self,
        execution_id: str,
        url: str,
        html_content: str,
        page_number: Optional[int] = None
    ) -> str:
        """
        Upload HTML page content

        Args:
            execution_id: ID da execução
            url: URL da página
            html_content: HTML content
            page_number: Número da página (opcional)

        Returns:
            Object name no MinIO
        """
        # Sanitize URL para criar nome de arquivo
        from urllib.parse import urlparse
        parsed = urlparse(url)
        filename = parsed.path.replace("/", "_") or "index"
        if page_number is not None:
            filename = f"page_{page_number}_{filename}"
        filename = f"{filename}.html"

        object_name = f"crawled/{execution_id}/pages/{filename}"

        metadata = {
            "source-url": url,
            "execution-id": execution_id,
            "content-type": "text/html",
        }
        if page_number is not None:
            metadata["page-number"] = str(page_number)

        self.client.upload_content(
            content=html_content,
            object_name=object_name,
            bucket_name=self.bucket,
            content_type="text/html; charset=utf-8",
            metadata=metadata,
        )

        logger.info(f"Uploaded HTML page: {object_name}")
        return object_name

    async def upload_asset(
        self,
        execution_id: str,
        asset_type: AssetType,
        file_path: Path,
        source_url: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload asset (CSS, JS, image, font, video)

        Args:
            execution_id: ID da execução
            asset_type: Tipo do asset (CSS, JS, IMAGES, etc.)
            file_path: Caminho local do asset
            source_url: URL original
            content_type: MIME type

        Returns:
            Object name no MinIO
        """
        # Subpasta por tipo de asset
        type_folder = asset_type.value.lower()
        object_name = f"crawled/{execution_id}/assets/{type_folder}/{file_path.name}"

        metadata = {
            "source-url": source_url,
            "execution-id": execution_id,
            "asset-type": asset_type.value,
            "original-filename": file_path.name,
        }

        self.client.upload_file(
            file_path=str(file_path),
            object_name=object_name,
            bucket_name=self.bucket,
            content_type=content_type,
            metadata=metadata,
        )

        logger.debug(f"Uploaded {asset_type.value} asset: {object_name}")
        return object_name

    async def upload_merged_pdf(
        self,
        execution_id: str,
        file_path: Path,
        source_urls: List[str],
        total_pages: int
    ) -> str:
        """
        Upload PDF merged (resultado final do crawler)

        Args:
            execution_id: ID da execução
            file_path: Caminho do PDF merged
            source_urls: URLs dos PDFs originais
            total_pages: Total de páginas no PDF merged

        Returns:
            Object name no MinIO
        """
        object_name = f"crawled/{execution_id}/merged/{file_path.name}"

        metadata = {
            "execution-id": execution_id,
            "source-urls": ",".join(source_urls),
            "total-pages": str(total_pages),
            "file-type": "merged-pdf",
        }

        self.client.upload_file(
            file_path=str(file_path),
            object_name=object_name,
            bucket_name=self.bucket,
            content_type="application/pdf",
            metadata=metadata,
        )

        logger.info(f"Uploaded merged PDF: {object_name} ({total_pages} pages)")
        return object_name

    def list_execution_files(
        self,
        execution_id: str,
        file_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Lista arquivos de uma execução

        Args:
            execution_id: ID da execução
            file_type: Filtrar por tipo (files, pages, assets, merged)

        Returns:
            Lista de dicts com informações dos arquivos
        """
        prefix = f"crawled/{execution_id}/"
        if file_type:
            prefix = f"{prefix}{file_type}/"

        files = self.client.list_objects(
            bucket_name=self.bucket,
            prefix=prefix
        )

        result = []
        for obj in files:
            result.append({
                "object_name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified,
                "etag": obj.etag,
            })

        logger.info(f"Listed {len(result)} files for execution {execution_id}")
        return result

    async def delete_execution_folder(self, execution_id: str) -> int:
        """
        Deleta todos os arquivos de uma execução (cleanup)

        Args:
            execution_id: ID da execução

        Returns:
            Número de arquivos deletados
        """
        prefix = f"crawled/{execution_id}/"

        deleted_count = self.client.delete_folder(
            bucket_name=self.bucket,
            prefix=prefix
        )

        logger.info(f"Deleted {deleted_count} files for execution {execution_id}")
        return deleted_count

    def get_download_url(
        self,
        object_name: str,
        expiry_hours: int = 24
    ) -> str:
        """
        Gera URL pre-signed para download

        Args:
            object_name: Nome do objeto no MinIO
            expiry_hours: Validade da URL em horas

        Returns:
            URL pre-signed
        """
        url = self.client.get_presigned_url(
            object_name=object_name,
            bucket_name=self.bucket,
            expiry=timedelta(hours=expiry_hours)
        )

        logger.debug(f"Generated download URL for {object_name} (expires in {expiry_hours}h)")
        return url

    def get_execution_summary(self, execution_id: str) -> Dict:
        """
        Retorna sumário de uma execução

        Args:
            execution_id: ID da execução

        Returns:
            Dict com estatísticas da execução
        """
        files = self.list_execution_files(execution_id)

        # Calcular estatísticas
        total_size = sum(f["size"] for f in files)
        file_types = {}

        for f in files:
            # Extrair tipo do path
            parts = f["object_name"].split("/")
            if len(parts) >= 3:
                ftype = parts[2]  # files, pages, assets, merged
                file_types[ftype] = file_types.get(ftype, 0) + 1

        return {
            "execution_id": execution_id,
            "total_files": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "file_types": file_types,
        }
