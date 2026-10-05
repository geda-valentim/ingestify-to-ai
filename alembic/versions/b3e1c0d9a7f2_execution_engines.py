"""execution engines: engines, routes, ledger, backlog, dispatcher lease, audit (spec 0003)

Revision ID: b3e1c0d9a7f2
Revises: 7c2f4a1d9b30
Create Date: 2026-10-04 23:00:00.000000

Mirrors the SQLAlchemy models in backend/shared/models.py; on installs that rely
on create_all at startup these tables appear on their own.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = 'b3e1c0d9a7f2'
down_revision: Union[str, Sequence[str], None] = '7c2f4a1d9b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('admin_audit',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('actor_user_id', sa.String(length=36), nullable=True),
    sa.Column('auth_method', sa.Enum('jwt', 'cli', name='audit_auth_method'), nullable=False),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target_type', sa.String(length=32), nullable=False),
    sa.Column('target_id', sa.String(length=64), nullable=False),
    sa.Column('before', sa.JSON(), nullable=True),
    sa.Column('after', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_target', 'admin_audit', ['target_type', 'target_id', 'created_at'], unique=False)
    op.create_table('dispatcher_lease',
    sa.Column('id', sa.SmallInteger(), nullable=False),
    sa.Column('epoch', sa.BigInteger(), nullable=False),
    sa.Column('holder', sa.String(length=128), nullable=True),
    sa.Column('holder_kind', sa.Enum('dispatcher', 'watchdog', name='lease_holder_kind'), nullable=True),
    sa.Column('renewed_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('dispatcher_seen_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('engines',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('adapter_type', sa.String(length=32), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('deployments', sa.JSON(), nullable=False),
    sa.Column('status', sa.Enum('active', 'paused', 'disabled', name='engine_status'), nullable=False),
    sa.Column('health', sa.Enum('unknown', 'healthy', 'degraded', 'unhealthy', 'exhausted', name='engine_health'), nullable=False),
    sa.Column('health_reason', sa.Text(), nullable=True),
    sa.Column('health_until', sa.DateTime(), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('limit_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('min_remaining_usd', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('soft_pct', sa.SmallInteger(), nullable=False),
    sa.Column('period_tz', sa.String(length=64), server_default='UTC', nullable=False),
    sa.Column('period_anchor_day', sa.SmallInteger(), server_default='1', nullable=False),
    sa.Column('alerted_soft_period', sa.Date(), nullable=True),
    sa.Column('alerted_hard_period', sa.Date(), nullable=True),
    sa.Column('provider_reported_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('provider_reported_period', sa.Date(), nullable=True),
    sa.Column('provider_reported_at', sa.DateTime(), nullable=True),
    sa.Column('credentials_sealed', sa.LargeBinary(), nullable=True),
    sa.Column('credentials_key_id', sa.String(length=16), nullable=True),
    sa.Column('credentials_masked', sa.JSON(), nullable=False),
    sa.Column('credentials_updated_at', sa.DateTime(), nullable=True),
    sa.Column('credentials_updated_by', sa.String(length=36), nullable=True),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('feature_routes',
    sa.Column('feature', sa.String(length=40), nullable=False),
    sa.Column('state', sa.Enum('active', 'draining', name='route_state'), nullable=False),
    sa.Column('steps', sa.JSON(), nullable=False),
    sa.Column('on_no_engine', sa.Enum('hold', 'fail', name='route_on_no_engine'), nullable=False),
    sa.Column('fail_after_seconds', sa.Integer(), nullable=True),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('remote_allowed_for', sa.Enum('admins', 'all', name='route_remote_allowed_for'), nullable=False),
    sa.Column('user_period_limit_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('remote_data_notice', sa.Text(), nullable=True),
    sa.Column('dispatcher_fallback', sa.Enum('local_direct', 'hold', name='route_dispatcher_fallback'), nullable=False),
    sa.Column('dispatcher_down_seconds', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('updated_by', sa.String(length=36), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('feature')
    )
    op.create_table('job_dispatches',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('feature', sa.String(length=40), nullable=False),
    sa.Column('subject_type', sa.Enum('job', 'page', 'vision_request', name='dispatch_subject_type'), nullable=False),
    sa.Column('subject_id', sa.String(length=64), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=True),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('remote_allowed', sa.Boolean(), nullable=False),
    sa.Column('state', sa.Enum('probing', 'waiting', 'assigned', 'running', 'done', 'failed', 'bypassed', name='dispatch_state'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('priority', sa.SmallInteger(), nullable=False),
    sa.Column('not_before', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('placements', sa.Integer(), nullable=False),
    sa.Column('job_failures', sa.Integer(), nullable=False),
    sa.Column('skip_count', sa.Integer(), nullable=False),
    sa.Column('blocked_engine_id', sa.String(length=36), nullable=True),
    sa.Column('solo', sa.Boolean(), nullable=False),
    sa.Column('exclude_engines', sa.JSON(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('media_seconds', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('media_bytes', sa.BigInteger(), nullable=True),
    sa.Column('usage_id', sa.BigInteger(), nullable=True),
    sa.Column('engine_id', sa.String(length=36), nullable=True),
    sa.Column('placed_step', sa.SmallInteger(), nullable=True),
    sa.Column('place_reason', sa.String(length=64), nullable=True),
    sa.Column('enqueued_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('unplaceable_since', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('assigned_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('error_code', sa.String(length=32), nullable=True),
    sa.Column('updated_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('subject_type', 'subject_id', name='uq_dispatch_subject')
    )
    op.create_index('ix_dispatch_feature_state_order', 'job_dispatches', ['feature', 'state', 'priority', 'enqueued_at'], unique=False)
    op.create_index('ix_dispatch_feature_state_remote_order', 'job_dispatches', ['feature', 'state', 'remote_allowed', 'priority', 'enqueued_at'], unique=False)
    op.create_table('engine_feature_state',
    sa.Column('engine_id', sa.String(length=36), nullable=False),
    sa.Column('feature', sa.String(length=40), nullable=False),
    sa.Column('full_since', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('capacity_penalty', sa.Integer(), nullable=False),
    sa.Column('penalty_until', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('alive_below_configured_since', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('updated_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.ForeignKeyConstraint(['engine_id'], ['engines.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('engine_id', 'feature')
    )
    op.create_table('engine_usage',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('kind', sa.Enum('job', 'idle_tail', 'probe', 'benchmark', name='usage_kind'), nullable=False),
    sa.Column('engine_id', sa.String(length=36), nullable=False),
    sa.Column('feature', sa.String(length=40), nullable=False),
    sa.Column('subject_type', sa.Enum('job', 'page', 'vision_request', name='usage_subject_type'), nullable=True),
    sa.Column('subject_id', sa.String(length=64), nullable=True),
    sa.Column('attempt', sa.Integer(), nullable=True),
    sa.Column('job_id', sa.String(length=36), nullable=True),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('reserved', 'spawning', 'running', 'settled', 'released', name='usage_status'), nullable=False),
    sa.Column('outcome', sa.Enum('succeeded', 'failed', 'cancelled', 'lost', name='usage_outcome'), nullable=True),
    sa.Column('counts_toward_attempts', sa.Boolean(), nullable=False),
    sa.Column('placed_by', sa.Enum('dispatcher', 'watchdog', 'fallback', 'cli', name='usage_placed_by'), nullable=True),
    sa.Column('dispatch_epoch', sa.BigInteger(), nullable=True),
    sa.Column('gpu_type', sa.String(length=32), nullable=True),
    sa.Column('executions_per_worker', sa.SmallInteger(), nullable=True),
    sa.Column('container_id', sa.String(length=128), nullable=True),
    sa.Column('segment_start', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('exec_started_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('exec_ended_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('shared_seconds', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('cold_start_seconds', sa.Numeric(precision=9, scale=3), nullable=True),
    sa.Column('estimated_usd', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('reserved_usd', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('actual_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('cost_basis', sa.Enum('measured', 'reported', 'shared', 'reserved', name='usage_cost_basis'), nullable=True),
    sa.Column('reported_seconds', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('measured_seconds', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('rate_usd_per_s', sa.Numeric(precision=14, scale=10), nullable=False),
    sa.Column('price_snapshot', sa.JSON(), nullable=True),
    sa.Column('units', sa.JSON(), nullable=True),
    sa.Column('fingerprint', sa.String(length=64), nullable=True),
    sa.Column('attempt_key', sa.String(length=36), nullable=True),
    sa.Column('provider_call_id', sa.String(length=128), nullable=True),
    sa.Column('holder', sa.String(length=128), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('published_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('spawned_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('deadline_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('output_persisted_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('republish_count', sa.Integer(), nullable=False),
    sa.Column('error_code', sa.String(length=32), nullable=True),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('finished_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.ForeignKeyConstraint(['engine_id'], ['engines.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('container_id', 'kind', 'segment_start', name='uq_usage_container_segment'),
    sa.UniqueConstraint('subject_type', 'subject_id', 'attempt', name='uq_usage_subject_attempt')
    )
    op.create_index('ix_usage_container', 'engine_usage', ['container_id'], unique=False)
    op.create_index('ix_usage_engine_feature_kind_status', 'engine_usage', ['engine_id', 'feature', 'kind', 'status'], unique=False)
    op.create_index('ix_usage_engine_period_status', 'engine_usage', ['engine_id', 'period_start', 'status'], unique=False)
    op.create_index('ix_usage_job', 'engine_usage', ['job_id'], unique=False)
    op.create_index('ix_usage_speed_key', 'engine_usage', ['engine_id', 'feature', 'gpu_type', 'executions_per_worker', 'status', 'finished_at'], unique=False)
    op.create_index('ix_usage_status_heartbeat', 'engine_usage', ['status', 'heartbeat_at'], unique=False)
    op.create_index('ix_usage_user_period', 'engine_usage', ['user_id', 'period_start'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_usage_user_period', table_name='engine_usage')
    op.drop_index('ix_usage_status_heartbeat', table_name='engine_usage')
    op.drop_index('ix_usage_speed_key', table_name='engine_usage')
    op.drop_index('ix_usage_job', table_name='engine_usage')
    op.drop_index('ix_usage_engine_period_status', table_name='engine_usage')
    op.drop_index('ix_usage_engine_feature_kind_status', table_name='engine_usage')
    op.drop_index('ix_usage_container', table_name='engine_usage')
    op.drop_table('engine_usage')
    op.drop_table('engine_feature_state')
    op.drop_index('ix_dispatch_feature_state_remote_order', table_name='job_dispatches')
    op.drop_index('ix_dispatch_feature_state_order', table_name='job_dispatches')
    op.drop_table('job_dispatches')
    op.drop_table('feature_routes')
    op.drop_table('engines')
    op.drop_table('dispatcher_lease')
    op.drop_index('ix_audit_target', table_name='admin_audit')
    op.drop_table('admin_audit')
