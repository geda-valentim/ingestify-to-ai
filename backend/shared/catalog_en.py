"""English texts of the engine-control / access / IAM / jobs entries of ``error_catalog``.

The Portuguese originals live in ``error_catalog._PT`` (unchanged wording). A code
without an entry here still answers in Portuguese when English is asked; the
allowlist ``PENDING_EN`` in ``tests/test_error_catalog.py`` names them, and it must
be empty when the last slice of P-13 lands. ``{params}`` must match the Portuguese
template exactly (a test compares them).
"""

EN = {
    # --- jobs ------------------------------------------------------------------
    "JOB_STILL_PROCESSING": (
        "The job (or one of its pages) is still queued, processing or waiting for a retry. "
        "Wait for it to finish before deleting the original file."
    ),
    "SOURCE_PURGED": (
        "The source files of this job (the uploaded file and the page PDFs) were deleted on "
        "{deleted_at}, on request (purge_source or deletion of the original). The conversion "
        "result is still available."
    ),
    "SOURCE_NOT_AVAILABLE": "The original file was deleted, so this page cannot be redone.",
    "PAGES_FAILED": (
        "{failed} of {total} pages failed. The others were converted; redo the failed pages "
        "to complete the document."
    ),
    "SPLIT_FAILED": (
        "The PDF could not be split into pages, with neither qpdf nor PyPDF2, even after the "
        "automatic retries. The file is probably corrupted or password-protected, so sending "
        "the same file again will not help. Regenerate the PDF (for example with \"print to "
        "PDF\") and upload the new version."
    ),
    "FIGURES_FAILED": (
        "The conversion finished, but the figure description/OCR step (describe_images / "
        "ocr_images) could not be completed after the automatic retries. Upload the file "
        "again, or without those options."
    ),
    "RETRY_NOT_QUEUED": (
        "The automatic retry could not be scheduled (queue unavailable), so processing ended "
        "with a failure. Upload the file again."
    ),
    "ASSETS_PURGED": (
        "The images extracted from this job (figures and rendered pages) were deleted on "
        "{deleted_at} (purge_source, after the retention period, or deletion of the original). "
        "The markdown is still available; convert the file again to get the images back."
    ),
    "ASSET_NOT_FOUND": (
        "This job has no image with that name. The valid names are in `assets` of "
        "GET /jobs/{{job_id}}/result (only after the job finishes)."
    ),
    "ASSET_STORAGE_UNAVAILABLE": "Image storage is unavailable right now. Try again in a moment.",
    "SOURCE_DELETE_FAILED": "The original file could not be deleted right now; it was kept. Try again in a moment.",
    "RESULT_FORMAT_INVALID": (
        "Invalid format: {format}. Use json or markdown; transcripts also accept vtt, srt and txt."
    ),
    "IMAGE_RESULT_FORMAT_UNSUPPORTED": (
        "This is a {kind} job and its result comes as format=json or format=markdown; "
        "'{format}' only applies to transcripts."
    ),
    # --- setup / configuration -------------------------------------------------
    "CONTROL_NOT_ENABLED": "The engine control plane is turned off on this installation (ENGINE_CONTROL_ENABLED).",
    "ACCESS_NOT_ENABLED": (
        "Execution profiles and access scopes are turned off on this installation "
        "(IAM_MODE is not enforce)."
    ),
    "ACCESS_SCHEMA_NOT_READY": "The access tables have not been migrated yet. Run the backend migrations and try again.",
    "FEATURE_NOT_SUPPORTED": "This adapter does not offer this feature.",
    "FEATURE_UNSUPPORTED": "This adapter does not offer this feature.",
    "INVALID_PROVIDER_VALUE": "A provider-specific value is not valid for this adapter.",
    "PROVIDER_FIELDS_REQUIRED": "Fill in the provider fields this adapter requires.",
    "INVALID_CONFIGURATION": "The submitted configuration was rejected.",
    "INVALID_OPERATION": "The operation cannot be planned with the current configuration.",
    "SLUG_IN_USE": "An engine with this identifier already exists. Choose another one.",
    "SYSTEM_ENGINE_ALREADY_EXISTS": "This system engine already exists and cannot be created again.",
    "ENGINE_NOT_FOUND": "Engine not found (or outside your scope).",
    "HOST_AGENT_NOT_READY": (
        "The local host agent{host} is not responding (no recent heartbeat){since}. Check the "
        "ingestify-engine-host-agent service on the server (journalctl -u ingestify-engine-host-agent)."
    ),
    "INVALID_INVENTORY": "The host agent sent an invalid inventory.",
    "HOST_COMMAND_TIMEOUT": "A docker compose command took too long on the host.",
    "MODEL_READINESS_TIMEOUT": "The workers did not confirm the model was loaded in time.",
    "LIVE_SINGLE_RESIDENT_REQUIRED": "Live transcription needs a single replica with one execution per worker.",
    "LIVE_REQUIRES_CUDA": "Live transcription needs a GPU (gpu_ref) in the profile.",
    "CANCELLED": "The operation was cancelled.",
    "MODEL_PROFILE_UNAVAILABLE": "The chosen model is not available for this adapter and feature.",
    "PUBLISHED_REVISION_REQUIRED": "Choose a published (not archived) revision of the execution profile.",
    "PROFILE_NOT_FOUND": "Execution profile not found (or outside your scope).",
    "SOURCE_PROFILE_NOT_FOUND": "The source profile of this binding no longer exists or left your scope.",
    "PROFILE_ARCHIVED": "This profile is archived and accepts no new bindings or revisions.",
    "REVISION_NOT_FOUND": "Profile revision not found.",
    "REVISION_NOT_PUBLISHABLE": "This revision cannot be published (already published or incomplete).",
    "POLICY_NOT_FOUND": "Access policy not found.",
    "WARM_DURATION_REQUIRED": "Say how long to keep the pool warm.",
    "WARM_DEADLINE": "The warm-up deadline ran out during the operation.",
    "ACTION_UNSUPPORTED": "This adapter does not offer this operation.",
    "VERSION_CONFLICT": "The data changed since the page was loaded. Reload and review before trying again.",
    "OPERATION_CONFLICT": "An operation is already running on this engine. Wait for it or cancel it.",
    "RESOURCE_LOCKED": "A resource of this engine is held by an active or uncertain operation.",
    "RESOURCE_NOT_FOUND": "Resource not found.",
    "PLAN_NOT_FOUND": "The plan does not exist or has expired. Review the operation again.",
    "OPERATION_NOT_FOUND": "Operation not found (or outside your scope).",
    "IDEMPOTENCY_KEY_REQUIRED": "The request needs an idempotency key.",
    "DEPLOYMENT_STOP_FAILED": "The provider refused to stop the deployment.",
    "DEPLOYMENT_STOP_NOT_VERIFIED": "The deployment is still active after the stop request.",
    "DRAIN_TIMEOUT": "The drain did not finish in time; work was still in progress.",
    "OPERATION_DEADLINE": "The operation ran past its deadline.",
    "PROCESS_DEADLINE": "A command of the operation ran past its deadline.",
    "OPERATION_ABORTED": "The operation was interrupted.",
    "LEASE_LOST": "The executor lost ownership of the operation.",
    "EXECUTOR_LOST": "The operation's executor stopped responding.",
    "RECOVERY_NOT_REQUIRED": "This operation does not need recovery.",
    "EFFECT_ALREADY_ADMITTED": "This effect was already admitted for this operation.",
    "ENGINE_MAINTENANCE": "The engine is under maintenance because of an operation in progress.",
    "ENGINE_NOT_RUNNING": "The engine is not running.",
    "INSTALLATION_PRINCIPAL_REQUIRED": "This action needs an installation user (not an API key).",
    "LEGACY_CONTEXT_INVALID": "The legacy request context is not valid.",
    # --- access / IAM / root ---------------------------------------------------
    "ACCESS_DENIED": "Your access does not allow this action here.",
    "ACCESS_REVOKED": "Your access was revoked during the operation.",
    "LOGIN_SESSION_REQUIRED": "This action needs a login session (not an API key).",
    "DELEGATION_EXCEEDED": "You cannot grant more than your own delegation allows.",
    "DELEGATION_INVALID": "The delegation provided is not valid.",
    "SELF_GRANT": "Nobody can grant roles to themselves.",
    "ROLE_ABOVE_GRANTOR": "You cannot grant a role above your own.",
    "ROLE_UNKNOWN": "Unknown role.",
    "UNKNOWN_ROLE": "Unknown role.",
    "PERMISSIONS_OUTSIDE_ROLE": "Some permissions go beyond what the role allows.",
    "FIELD_NOT_ALLOWED_FOR_ROLE": "A submitted field does not apply to this role.",
    "BINDING_EXISTS": "This user already has this role.",
    "BINDING_NOT_FOUND": "Grant not found.",
    "GRANT_NOT_FOUND": "Grant not found.",
    "PROJECT_NOT_FOUND": "Project not found (or outside your access).",
    "FOLDER_NOT_FOUND": "Folder not found (or outside your access).",
    "ALREADY_REVOKED": "This grant was already revoked.",
    "GRANT_EXPIRY_INVALID": "The grant's validity is not valid.",
    "INVALID_EXPIRES_AT": "The expiry date is not valid (use an ISO-8601 date and time in the future).",
    "GRANT_TARGET_NOT_FOUND": "The grant target does not exist.",
    "INVALID_SUBJECT": "The user or key provided is not valid.",
    "SUBJECT_NOT_FOUND": "User not found.",
    "PRINCIPAL_EXISTS": "This principal already exists.",
    "PRINCIPAL_NOT_FOUND": "Principal not found.",
    "TOO_MANY_CHECKS": "Too many checks in a single request.",
    "UNSUPPORTED_PERMISSION": "Unknown permission.",
    "ROOT_SETUP_TOKEN_REQUIRED": (
        "This installation has no root user yet. Set ROOT_SETUP_TOKEN on the server to create one."
    ),
    "ROOT_SETUP_TOKEN_INVALID": "The setup token is missing or not valid.",
    "ROOT_IMMUTABLE": "The root user cannot be deactivated or lose administrator access.",
}
