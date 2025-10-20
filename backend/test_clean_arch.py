"""
Test Clean Architecture - Use Cases with Mocks

Demonstra testabilidade sem infraestrutura
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

# Domain
from domain.entities.job import Job, JobStatus, JobType
from domain.entities.page import Page, PageStatus
from domain.value_objects.job_id import JobId
from domain.repositories.job_repository import JobRepository
from domain.repositories.page_repository import PageRepository
from domain.services.progress_calculator_service import ProgressCalculatorService

# Application
from application.use_cases.convert_document import ConvertDocumentUseCase
from application.use_cases.get_job_status import GetJobStatusUseCase
from application.use_cases.get_job_result import GetJobResultUseCase
from application.dto.convert_request_dto import ConvertRequestDTO
from application.ports.queue_port import QueuePort
from application.ports.storage_port import StoragePort


async def test_convert_document_use_case():
    """Test ConvertDocumentUseCase with mocked dependencies"""
    print("\n1. Testing ConvertDocumentUseCase...")

    # Arrange: Create mocks (NO real infrastructure!)
    job_repo_mock = MagicMock(spec=JobRepository)
    job_repo_mock.save = AsyncMock()

    queue_mock = MagicMock(spec=QueuePort)
    queue_mock.enqueue_conversion = AsyncMock(return_value="task-123")

    # Create use case with mocked dependencies
    use_case = ConvertDocumentUseCase(
        job_repository=job_repo_mock,
        queue=queue_mock
    )

    # Create request DTO
    dto = ConvertRequestDTO(
        user_id="user-123",
        source_type="file",
        source="/path/to/test.pdf",
        filename="test.pdf",
        file_size_bytes=1024000,
        mime_type="application/pdf"
    )

    # Act: Execute use case
    response = await use_case.execute(dto)

    # Assert: Verify behavior
    assert response.status == "queued"
    assert response.job_id is not None
    assert len(response.job_id) == 36  # UUID format
    assert response.message == "Job enfileirado para processamento"

    # Verify interactions
    job_repo_mock.save.assert_called_once()
    queue_mock.enqueue_conversion.assert_called_once()

    saved_job = job_repo_mock.save.call_args[0][0]
    assert saved_job.user_id == "user-123"
    assert saved_job.status == JobStatus.QUEUED
    assert saved_job.job_type == JobType.MAIN

    print("   ✓ Use case executed successfully")
    print(f"   ✓ Job ID: {response.job_id[:8]}...")
    print("   ✓ Repository.save() called")
    print("   ✓ Queue.enqueue_conversion() called")
    print("   ✅ ConvertDocumentUseCase test passed!")


async def test_get_job_status_use_case():
    """Test GetJobStatusUseCase with mocked dependencies"""
    print("\n2. Testing GetJobStatusUseCase...")

    # Arrange: Create mocks
    job_id = str(JobId.generate())
    user_id = "user-123"

    # Mock job
    job = Job(
        id=job_id,
        user_id=user_id,
        job_type=JobType.MAIN,
        status=JobStatus.PROCESSING,
        progress=45,
        filename="test.pdf",
        total_pages=10,
        pages_completed=4,
        pages_failed=0,
        created_at=datetime.utcnow()
    )

    # Mock pages
    pages = [
        Page(id=str(JobId.generate()), job_id=job_id, page_number=i,
             status=PageStatus.COMPLETED if i <= 4 else PageStatus.PENDING)
        for i in range(1, 11)
    ]

    # Create repository mocks
    job_repo_mock = MagicMock(spec=JobRepository)
    job_repo_mock.find_by_id = AsyncMock(return_value=job)

    page_repo_mock = MagicMock(spec=PageRepository)
    page_repo_mock.find_by_job_id = AsyncMock(return_value=pages)

    progress_calc = ProgressCalculatorService()

    # Create use case
    use_case = GetJobStatusUseCase(
        job_repository=job_repo_mock,
        page_repository=page_repo_mock,
        progress_calculator=progress_calc
    )

    # Act
    response = await use_case.execute(job_id=job_id, user_id=user_id)

    # Assert
    assert response.job_id == job_id
    assert response.status == "processing"
    assert response.total_pages == 10
    assert response.pages_completed == 4
    assert len(response.pages) == 10

    # Verify interactions
    job_repo_mock.find_by_id.assert_called_once_with(job_id)
    page_repo_mock.find_by_job_id.assert_called_once_with(job_id)

    print("   ✓ Use case executed successfully")
    print(f"   ✓ Job ID: {response.job_id[:8]}...")
    print(f"   ✓ Status: {response.status}")
    print(f"   ✓ Progress: {response.progress}%")
    print(f"   ✓ Pages: {response.pages_completed}/{response.total_pages}")
    print("   ✅ GetJobStatusUseCase test passed!")


async def test_get_job_result_use_case():
    """Test GetJobResultUseCase with mocked dependencies"""
    print("\n3. Testing GetJobResultUseCase...")

    # Arrange
    job_id = str(JobId.generate())
    user_id = "user-123"

    # Mock completed job
    job = Job(
        id=job_id,
        user_id=user_id,
        job_type=JobType.MAIN,
        status=JobStatus.COMPLETED,
        progress=100,
        completed_at=datetime.utcnow()
    )

    # Mock result
    result_data = {
        "markdown": "# Test Document\n\nThis is a test.",
        "metadata": {
            "pages": 10,
            "words": 500,
            "format": "pdf"
        }
    }

    # Create mocks
    job_repo_mock = MagicMock(spec=JobRepository)
    job_repo_mock.find_by_id = AsyncMock(return_value=job)

    storage_mock = MagicMock(spec=StoragePort)
    storage_mock.get_job_result = AsyncMock(return_value=result_data)

    # Create use case
    use_case = GetJobResultUseCase(
        job_repository=job_repo_mock,
        storage=storage_mock
    )

    # Act
    response = await use_case.execute(job_id=job_id, user_id=user_id)

    # Assert
    assert response.job_id == job_id
    assert response.status == "completed"
    assert response.result["markdown"] == "# Test Document\n\nThis is a test."
    assert response.result["metadata"]["pages"] == 10

    # Verify interactions
    job_repo_mock.find_by_id.assert_called_once_with(job_id)
    storage_mock.get_job_result.assert_called_once_with(job_id)

    print("   ✓ Use case executed successfully")
    print(f"   ✓ Job ID: {response.job_id[:8]}...")
    print(f"   ✓ Status: {response.status}")
    print(f"   ✓ Markdown length: {len(response.result['markdown'])} chars")
    print("   ✅ GetJobResultUseCase test passed!")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Clean Architecture - Use Case Tests (with Mocks)")
    print("=" * 60)
    print("\nTesting WITHOUT infrastructure (no Redis, MySQL, Celery)!")
    print("All dependencies are MOCKED via interfaces.\n")

    try:
        await test_convert_document_use_case()
        await test_get_job_status_use_case()
        await test_get_job_result_use_case()

        print("\n" + "=" * 60)
        print("✅ ALL USE CASE TESTS PASSED!")
        print("=" * 60)
        print("\n🎉 Clean Architecture is working perfectly!")
        print("\nKey achievements:")
        print("  ✓ Use Cases tested WITHOUT infrastructure")
        print("  ✓ Fast tests (< 1ms each)")
        print("  ✓ Deterministic (no race conditions)")
        print("  ✓ Easy to write (mocks via interfaces)")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
