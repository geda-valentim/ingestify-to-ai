"""English texts of the engine-control / access / IAM / jobs entries of ``error_catalog``.

The Portuguese originals live in ``error_catalog._PT`` (unchanged wording). Every
catalog code has an entry (``tests/test_error_catalog.py`` asserts it). ``{params}`` must match the Portuguese
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
    "AUDIO_DURATION_LIMIT_EXCEEDED": (
        "The decoded audio is longer than the {max_minutes}-minute limit, so the transcription was "
        "refused. Duration is measured on the decoded samples, not on the file's metadata. "
        "Split the audio into shorter parts and upload each one."
    ),
    "AUDIO_SAMPLE_RATE_UNSUPPORTED": (
        "The audio's sample rate is too low (under 8 kHz) to be transcribed. Export the audio "
        "again with a rate of at least 8 kHz and upload the new version."
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
    # --- P-13 slice 4: engine-control / profiles / host agent -------------------
    "ACTION_OR_TARGET_NOT_REGISTERED": "The host does not have this action or service registered.",
    "ADAPTER_NOT_REGISTERED": "The adapter for this model is not registered on this installation.",
    "ADMISSION_AUTHORITY_UNAVAILABLE": "The effect's authorization could not be verified right now. Try again.",
    "BOOTSTRAP_ACTOR_REQUIRED": "Only root (or another active bootstrap admin) can seed the default execution profiles.",
    "BOUND_TO_LIBRARY_PROFILE": "The engine already uses a library profile for this feature; the default profile is not bound on top of it.",
    "BUDGET_INSUFFICIENT": "The engine's remaining budget does not cover the cap reserved for this operation.",
    "BUDGET_STOP_UNCONFIRMED": "It could not be confirmed that the paid containers stopped. Check with the provider.",
    "CLEANUP_CREDENTIAL_REQUIRED": "Some paid containers still need to be released. Run “Release model” and confirm the release before replacing or removing the credentials.",
    "CLEANUP_WATCHDOG_NOT_READY": "The control plane's cleanup watchdog is not active; operations that may incur costs stay blocked until it is back.",
    "CLI_ADMISSION_LOST": "The command-line authorization was lost.",
    "CONSUMER_NOT_CLASSIFIED": "A consumer of this engine's resources has no classified environment yet. Classify it in Admin → Access.",
    "CONTROL_REDEPLOY_REQUIRED": "The current deployment does not have the control protocol. Run “Deploy” or “Apply profile” before scaling, warming or releasing.",
    "COOLDOWN_NOT_VERIFIED": "The containers were not released within the observed time. Check with the provider.",
    "CREDENTIALS_NOT_ALLOWED_IN_PROFILE": "Execution profiles do not store credentials. Remove them from the profile; credentials live on the engine.",
    "CREDENTIALS_REQUIRED": "Save the provider credentials on this engine (Configuration tab), then test the connection.",
    "ENGINE_ENVIRONMENT_REQUIRED": "Classify this engine's environment in Admin → Access before binding a profile.",
    "ENVIRONMENT_UNKNOWN": "The server's ENVIRONMENT is not a known environment (development/dev/local, staging, production/prod); no default profile is created and no engine is classified. Fix ENVIRONMENT or classify the engines in Admin → Access.",
    "EXECUTOR_NOT_NEUTRALIZED": "The previous executor may still be active; recovery has to wait.",
    "GPU_NOT_REGISTERED": "The requested GPU is not registered on this host. Register the host with --gpu-uuid.",
    "GPU_UUID_NOT_REGISTERED": "The chosen GPU is not in the host's registered inventory{host}. Add the GPU UUID to the engine and register the host with --gpu-uuid.",
    "HASHED_MODEL_LOCK_REQUIRED": "This installation's model lock has no hashes; the deployment cannot be reproduced safely.",
    "HOST_AMBIGUOUS": "More than one registered host serves this feature (and GPU); the default local profile needs a specific host. Create the profile and choose the host.",
    "HOST_APPLY_FAILED": "The host agent could not apply the operation. See the operation events and journalctl -u ingestify-engine-host-agent.",
    "HOST_AUTHORITY_UNAVAILABLE": "The host agent lost contact with the API during the operation. Check the ingestify-engine-host-agent service on the server (journalctl -u ingestify-engine-host-agent).",
    "HOST_COMMAND_FAILED": "A docker compose command failed on the host. See the operation events and journalctl -u ingestify-engine-host-agent.",
    "HOST_EFFECT_UNCERTAIN": "The host agent restarted in the middle of an operation; the effect is uncertain. Review it and use Recover.",
    "HOST_IDENTITY_REQUIRED": "The host agent did not present a registered identity. Register the host again with scripts/register_engine_host.py.",
    "IDEMPOTENCY_CONFLICT": "This idempotency key was already used with a different plan. Review the operation again.",
    "IMAGE_MISMATCH": "The running image differs from the registered one. Register the host again after updating the images.",
    "INVALID_SETTINGS": "The engine's current configuration does not form a valid RuntimeSettings; review the feature binding.",
    "INVALID_WARM_DEADLINE": "The warm-up deadline is not valid (in the past or beyond what the profile allows).",
    "MANIFEST_STALE": "The plan was made with a different version of the host manifests. Review it and plan again.",
    "MODEL_FOOTPRINT_NOT_QUALIFIED": "The model does not have a qualified memory footprint yet; it cannot be used in an operation.",
    "MODEL_METADATA_CHANGED": "The model metadata changed since the profile revision. Create and publish a new compatible revision.",
    "MODEL_NOT_APPROVED": "This model is not approved in the catalog with the installation's current configuration; no default profile is created for it.",
    "NOTHING_TO_COOL_DOWN": "Nothing to release{for_feature}: with no execution profile bound, the control plane never warmed containers on this engine, and the default deployment already scales to zero by itself when idle.",
    "NO_REGISTERED_HOST": "No host agent is registered: local profiles need the host. They are created and bound on the agent's first heartbeat.",
    "PAID_BUDGET_REQUIRED": "This operation may incur costs: provide a reserved cap greater than US$ 0.",
    "PAID_CONFIRMATION_REQUIRED": "This operation may incur costs: confirm the paid operation to continue.",
    "PLAN_STALE": "The plan is out of date (the engine, profile or credentials changed). Review it again.",
    "POOL_OBSERVATION_UNAVAILABLE": "The provider did not report how many containers are alive.",
    "PROFILE_CONTENT_MISMATCH": "The submitted content differs from the published revision. Reload and bind again.",
    "PROFILE_INCOMPATIBLE": "The chosen profile is not compatible with this engine (adapter, feature or environment). Choose another one or create a compatible one.",
    "PROFILE_INVENTORY_CHANGED": "The host inventory changed since the binding (GPU or manifests). Bind the profile again.",
    "PROVIDER_SETTINGS_REQUIRED": "The adapter requires provider parameters that the current configuration does not define.",
    "RECOVERY_STATE_UNCONFIRMED": "The real state could not be confirmed to recover the operation.",
    "REGISTERED_COMMAND_NOT_SUPPORTED": "The service's registered command is not supported by the host agent.",
    "REGISTERED_MANIFEST_CHANGED": "The registered docker compose files changed, and the host agent refuses to operate. Register the host again (scripts/register_engine_host.py).",
    "RESOURCE_OWNED_BY_ANOTHER_ENGINE": "This profile's resource already belongs to another engine.",
    "RESOURCE_OWNERSHIP_CONFLICT": "Another engine claimed the same resource at the same time. Reload.",
    "RUNTIME_OPERATION_REQUIRED": "This engine is managed by the control plane: runtime changes go through an execution profile and a reviewed operation, not through direct editing.",
    "RUNTIME_PROFILE_EXISTS": "The engine already has a desired profile{for_feature}; the automatic binding does not replace it.",
    "RUNTIME_PROFILE_NOT_FOUND": "There is no desired execution profile{for_feature} on this engine (or it is outside your scope).",
    "RUNTIME_PROFILE_REQUIRED": "This engine has no bound execution profile yet{for_feature}. Bind a published profile in Admin → Execution profiles (or create one) before operating.",
    "SDK_AUTOSCALER_UNAVAILABLE": "The provider SDK does not expose the autoscaler. Update the SDK and deploy again.",
    "SEEDED_PROFILE_STALE": "The engine configuration changed since the default profile was created, and an administrator has already edited the profile; the automatic binding does not overwrite it. Review it, publish a profile revision with the current configuration and bind it to the engine.",
    "SERVICE_NOT_REGISTERED": "This feature's service is not registered on the host{host}. Register the host again including the service (--service).",
    "TEST_CONNECTION_FIRST": "The connection to the provider has not been verified yet. Use “Test connection” on this engine, then bind an execution profile.",
    "TEST_FAILED": "The connection test with the provider failed. Check the credentials and try again.",
    "USE_WARM_DURATION": "Published profiles use a warm-up duration (warm_for_seconds), not a fixed time of day.",
    "WARM_EXPIRATION_REQUIRED": "Set how long to keep the pool warm (or bind a profile with a warm-up period) before starting or warming.",
    "WARM_POOL_NOT_VERIFIED": "The warmed containers did not confirm the model was loaded.",
    "WHISPERX_CONTROL_PROFILE_NOT_QUALIFIED": "Engines with a WhisperX manifest cannot be operated by the control plane yet.",
}
