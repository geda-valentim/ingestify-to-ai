"""
MySQL implementation of CrawledFile Repository
"""
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from domain.entities.crawled_file import CrawledFile as CrawledFileEntity, FileStatus
from shared.models import CrawledFile as CrawledFileModel


class MySQLCrawledFileRepository:
    """
    Repository para persistência de CrawledFile no MySQL

    Responsabilidades:
    - Salvar arquivos crawleados no banco
    - Buscar arquivos por execução
    - Contar arquivos por tipo/status
    - Buscar arquivos com falha
    """

    def __init__(self, session: Session):
        """
        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def save(self, file: CrawledFileEntity) -> None:
        """
        Salva ou atualiza um arquivo crawleado

        Args:
            file: Entidade CrawledFile
        """
        try:
            # Verificar se já existe
            existing = self.session.query(CrawledFileModel).filter_by(id=file.id).first()

            if existing:
                # Update
                self._update_model_from_entity(existing, file)
            else:
                # Insert
                model = self._entity_to_model(file)
                self.session.add(model)

            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise Exception(f"Failed to save crawled file: {str(e)}")

    def find_by_id(self, file_id: str) -> Optional[CrawledFileEntity]:
        """
        Busca arquivo por ID

        Args:
            file_id: ID do arquivo

        Returns:
            CrawledFile entity ou None
        """
        model = self.session.query(CrawledFileModel).filter_by(id=file_id).first()
        if model:
            return self._model_to_entity(model)
        return None

    def find_by_execution_id(self, execution_id: str) -> List[CrawledFileEntity]:
        """
        Busca todos os arquivos de uma execução

        Args:
            execution_id: ID da execução (Job)

        Returns:
            Lista de CrawledFile entities
        """
        models = (
            self.session.query(CrawledFileModel)
            .filter_by(execution_id=execution_id)
            .order_by(CrawledFileModel.created_at)
            .all()
        )

        return [self._model_to_entity(model) for model in models]

    def find_by_status(self, execution_id: str, status: FileStatus) -> List[CrawledFileEntity]:
        """
        Busca arquivos por status

        Args:
            execution_id: ID da execução
            status: Status do arquivo

        Returns:
            Lista de CrawledFile entities
        """
        models = (
            self.session.query(CrawledFileModel)
            .filter_by(execution_id=execution_id, status=status)
            .order_by(CrawledFileModel.created_at)
            .all()
        )

        return [self._model_to_entity(model) for model in models]

    def find_failed(self, execution_id: str) -> List[CrawledFileEntity]:
        """
        Busca arquivos com falha

        Args:
            execution_id: ID da execução

        Returns:
            Lista de arquivos que falharam
        """
        return self.find_by_status(execution_id, FileStatus.FAILED)

    def count_by_status(self, execution_id: str) -> Dict[str, int]:
        """
        Conta arquivos agrupados por status

        Args:
            execution_id: ID da execução

        Returns:
            Dict com contagem por status: {"pending": 5, "completed": 10, ...}
        """
        results = (
            self.session.query(
                CrawledFileModel.status,
                func.count(CrawledFileModel.id).label('count')
            )
            .filter_by(execution_id=execution_id)
            .group_by(CrawledFileModel.status)
            .all()
        )

        return {str(status.value): count for status, count in results}

    def count_by_type(self, execution_id: str) -> Dict[str, int]:
        """
        Conta arquivos agrupados por tipo

        Args:
            execution_id: ID da execução

        Returns:
            Dict com contagem por tipo: {"pdf": 5, "jpg": 10, ...}
        """
        results = (
            self.session.query(
                CrawledFileModel.file_type,
                func.count(CrawledFileModel.id).label('count')
            )
            .filter_by(execution_id=execution_id)
            .filter(CrawledFileModel.file_type.isnot(None))
            .group_by(CrawledFileModel.file_type)
            .all()
        )

        return {file_type: count for file_type, count in results}

    def get_total_size(self, execution_id: str) -> int:
        """
        Calcula tamanho total de arquivos completados

        Args:
            execution_id: ID da execução

        Returns:
            Tamanho total em bytes
        """
        result = (
            self.session.query(func.sum(CrawledFileModel.size_bytes))
            .filter_by(execution_id=execution_id, status=FileStatus.COMPLETED)
            .scalar()
        )

        return result or 0

    def delete_by_execution_id(self, execution_id: str) -> int:
        """
        Deleta todos os arquivos de uma execução

        Args:
            execution_id: ID da execução

        Returns:
            Número de arquivos deletados
        """
        try:
            count = (
                self.session.query(CrawledFileModel)
                .filter_by(execution_id=execution_id)
                .delete()
            )
            self.session.commit()
            return count
        except Exception as e:
            self.session.rollback()
            raise Exception(f"Failed to delete crawled files: {str(e)}")

    # === Private Methods: Entity <-> Model Conversion ===

    def _entity_to_model(self, entity: CrawledFileEntity) -> CrawledFileModel:
        """Converte Entity para ORM Model"""
        return CrawledFileModel(
            id=entity.id,
            execution_id=entity.execution_id,
            url=entity.url,
            filename=entity.filename,
            file_type=entity.file_type,
            mime_type=entity.mime_type,
            size_bytes=entity.size_bytes,
            minio_path=entity.minio_path,
            minio_bucket=entity.minio_bucket,
            public_url=entity.public_url,
            status=entity.status,
            error_message=entity.error_message,
            downloaded_at=entity.downloaded_at,
            created_at=entity.created_at,
        )

    def _model_to_entity(self, model: CrawledFileModel) -> CrawledFileEntity:
        """Converte ORM Model para Entity"""
        return CrawledFileEntity(
            id=model.id,
            execution_id=model.execution_id,
            url=model.url,
            filename=model.filename,
            file_type=model.file_type,
            mime_type=model.mime_type,
            size_bytes=model.size_bytes,
            minio_path=model.minio_path,
            minio_bucket=model.minio_bucket,
            public_url=model.public_url,
            status=model.status,
            error_message=model.error_message,
            downloaded_at=model.downloaded_at,
            created_at=model.created_at,
        )

    def _update_model_from_entity(self, model: CrawledFileModel, entity: CrawledFileEntity) -> None:
        """Atualiza ORM Model com dados da Entity"""
        model.execution_id = entity.execution_id
        model.url = entity.url
        model.filename = entity.filename
        model.file_type = entity.file_type
        model.mime_type = entity.mime_type
        model.size_bytes = entity.size_bytes
        model.minio_path = entity.minio_path
        model.minio_bucket = entity.minio_bucket
        model.public_url = entity.public_url
        model.status = entity.status
        model.error_message = entity.error_message
        model.downloaded_at = entity.downloaded_at
        model.created_at = entity.created_at
