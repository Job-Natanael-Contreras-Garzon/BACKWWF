"""0001 · Esquema canónico (FLUJOS_SISTEMA §3) — HU-02.

Revision ID: 0001
Revises: (ninguna; primera migración)

⚠️  DESTRUCTIVA: ``upgrade`` ELIMINA las 10 tablas del esquema legado del hackathon (users,
anon_sessions, camera_stations, projects, project_stations, media_files, videos, species,
individuals, reports) con todos sus datos, y crea el esquema canónico vacío. ``downgrade`` borra
el esquema canónico y NO restaura las tablas legadas. Antes de aplicarla en una base con datos
reales (p. ej. producción en Aiven), hacer un respaldo con pg_dump.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_TABLES = (
    "reports",
    "individuals",
    "species",
    "videos",
    "media_files",
    "project_stations",
    "projects",
    "camera_stations",
    "anon_sessions",
    "users",
)


def drop_legacy_schema() -> None:
    """Tablas y tipos ENUM nativos que creaba el esquema viejo con create_all."""
    for table in LEGACY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    # El esquema canónico no usa ENUM nativos (VARCHAR + CHECK): todo enum en public es legado.
    op.execute(
        """
        DO $$
        DECLARE t record;
        BEGIN
            FOR t IN SELECT typname FROM pg_type
                     JOIN pg_namespace ns ON ns.oid = typnamespace
                     WHERE typtype = 'e' AND ns.nspname = 'public'
            LOOP
                EXECUTE format('DROP TYPE IF EXISTS public.%I CASCADE', t.typname);
            END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    drop_legacy_schema()
    op.create_table('anon_purge_runs',
    sa.Column('run_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sessions', sa.Integer(), nullable=False),
    sa.Column('classifications', sa.Integer(), nullable=False),
    sa.Column('camera_stations', sa.Integer(), nullable=False),
    sa.Column('projects', sa.Integer(), nullable=False),
    sa.Column('frames', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_anon_purge_runs'))
    )
    op.create_table('email_log',
    sa.Column('type', sa.Enum('password_reset', name='email_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('to_hash', sa.String(length=128), nullable=False),
    sa.Column('status', sa.Enum('queued', 'sent', 'failed', 'skipped_limit', name='email_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('provider_id', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_log'))
    )
    op.create_index(op.f('ix_email_log_created_at'), 'email_log', ['created_at'], unique=False)
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('institution', sa.String(length=200), nullable=True),
    sa.Column('role', sa.Enum('user', 'admin', name='user_role', native_enum=False, create_constraint=True, length=32), server_default='user', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('admin_audit_log',
    sa.Column('admin_user_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.Enum('soft_delete', 'restore', 'deactivate_user', 'reactivate_user', 'export', 'update_setting', name='admin_action', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], name=op.f('fk_admin_audit_log_admin_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_audit_log'))
    )
    op.create_index(op.f('ix_admin_audit_log_admin_user_id'), 'admin_audit_log', ['admin_user_id'], unique=False)
    op.create_index(op.f('ix_admin_audit_log_created_at'), 'admin_audit_log', ['created_at'], unique=False)
    op.create_table('anon_sessions',
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('active', 'claimed', 'expired', name='anon_session_status', native_enum=False, create_constraint=True, length=32), server_default='active', nullable=False),
    sa.Column('claimed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['claimed_by_user_id'], ['users.id'], name=op.f('fk_anon_sessions_claimed_by_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_anon_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_anon_sessions_token_hash'))
    )
    op.create_index(op.f('ix_anon_sessions_expires_at'), 'anon_sessions', ['expires_at'], unique=False)
    op.create_table('password_reset_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('request_ip_hash', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_password_reset_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_password_reset_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_password_reset_tokens_token_hash'))
    )
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('system_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_system_settings_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_system_settings'))
    )
    op.create_table('camera_stations',
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('deployed_at', sa.DateTime(), nullable=False),
    sa.Column('retrieved_at', sa.DateTime(), nullable=True),
    sa.Column('still_installed', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('observations', sa.Text(), nullable=True),
    sa.Column('visibility', sa.Enum('public', 'private', name='camera_visibility', native_enum=False, create_constraint=True, length=32), server_default='private', nullable=False),
    sa.Column('previous_camera_station_id', sa.Uuid(), nullable=True),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('anon_session_id', sa.Uuid(), nullable=True),
    sa.Column('anon_retain', sa.Boolean(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('(owner_user_id IS NULL) <> (anon_session_id IS NULL)', name=op.f('ck_camera_stations_owner_xor')),
    sa.CheckConstraint('latitude BETWEEN -90 AND 90', name=op.f('ck_camera_stations_latitude_range')),
    sa.CheckConstraint('longitude BETWEEN -180 AND 180', name=op.f('ck_camera_stations_longitude_range')),
    sa.ForeignKeyConstraint(['anon_session_id'], ['anon_sessions.id'], name=op.f('fk_camera_stations_anon_session_id_anon_sessions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_camera_stations_owner_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['previous_camera_station_id'], ['camera_stations.id'], name=op.f('fk_camera_stations_previous_camera_station_id_camera_stations'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_camera_stations'))
    )
    op.create_index(op.f('ix_camera_stations_anon_session_id'), 'camera_stations', ['anon_session_id'], unique=False)
    op.create_index(op.f('ix_camera_stations_owner_user_id'), 'camera_stations', ['owner_user_id'], unique=False)
    op.create_index('ix_camera_stations_public', 'camera_stations', ['visibility'], unique=False, postgresql_where=sa.text('is_deleted = false'))
    op.create_index('uq_camera_stations_anon_code', 'camera_stations', ['anon_session_id', sa.literal_column('lower(code)')], unique=True, postgresql_where=sa.text('is_deleted = false AND anon_session_id IS NOT NULL'))
    op.create_index('uq_camera_stations_user_code', 'camera_stations', ['owner_user_id', sa.literal_column('lower(code)')], unique=True, postgresql_where=sa.text('is_deleted = false AND owner_user_id IS NOT NULL'))
    op.create_table('projects',
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('visibility', sa.Enum('public', 'private', name='project_visibility', native_enum=False, create_constraint=True, length=32), server_default='private', nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('anon_session_id', sa.Uuid(), nullable=True),
    sa.Column('anon_retain', sa.Boolean(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('(owner_user_id IS NULL) <> (anon_session_id IS NULL)', name=op.f('ck_projects_owner_xor')),
    sa.ForeignKeyConstraint(['anon_session_id'], ['anon_sessions.id'], name=op.f('fk_projects_anon_session_id_anon_sessions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_projects_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    op.create_index(op.f('ix_projects_anon_session_id'), 'projects', ['anon_session_id'], unique=False)
    op.create_index(op.f('ix_projects_owner_user_id'), 'projects', ['owner_user_id'], unique=False)
    op.create_table('classification_batches',
    sa.Column('camera_station_id', sa.Uuid(), nullable=False),
    sa.Column('source', sa.Enum('web', 'desktop_import', name='batch_source', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('open', 'processing', 'completed', 'completed_with_errors', 'cancelled', 'incomplete', name='batch_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('expected_files', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), server_default='0', nullable=False),
    sa.Column('done', sa.Integer(), server_default='0', nullable=False),
    sa.Column('failed', sa.Integer(), server_default='0', nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('anon_session_id', sa.Uuid(), nullable=True),
    sa.Column('anon_retain', sa.Boolean(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('(owner_user_id IS NULL) <> (anon_session_id IS NULL)', name=op.f('ck_classification_batches_owner_xor')),
    sa.CheckConstraint('expected_files BETWEEN 1 AND 500', name=op.f('ck_classification_batches_expected_files_range')),
    sa.ForeignKeyConstraint(['anon_session_id'], ['anon_sessions.id'], name=op.f('fk_classification_batches_anon_session_id_anon_sessions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['camera_station_id'], ['camera_stations.id'], name=op.f('fk_classification_batches_camera_station_id_camera_stations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_classification_batches_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_classification_batches'))
    )
    op.create_index(op.f('ix_classification_batches_anon_session_id'), 'classification_batches', ['anon_session_id'], unique=False)
    op.create_index(op.f('ix_classification_batches_camera_station_id'), 'classification_batches', ['camera_station_id'], unique=False)
    op.create_index(op.f('ix_classification_batches_owner_user_id'), 'classification_batches', ['owner_user_id'], unique=False)
    op.create_table('desktop_imports',
    sa.Column('owner_user_id', sa.Uuid(), nullable=False),
    sa.Column('camera_station_id', sa.Uuid(), nullable=True),
    sa.Column('package_sha256', sa.String(length=64), nullable=False),
    sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.Enum('preview', 'completed', 'cancelled', 'expired', name='import_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('counts', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('tmp_key', sa.String(length=255), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("package_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_desktop_imports_package_sha256_hex')),
    sa.ForeignKeyConstraint(['camera_station_id'], ['camera_stations.id'], name=op.f('fk_desktop_imports_camera_station_id_camera_stations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_desktop_imports_owner_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_desktop_imports'))
    )
    op.create_index(op.f('ix_desktop_imports_owner_user_id'), 'desktop_imports', ['owner_user_id'], unique=False)
    op.create_index('uq_desktop_imports_camera_package_completed', 'desktop_imports', ['camera_station_id', 'package_sha256'], unique=True, postgresql_where=sa.text("status = 'completed' AND is_deleted = false"))
    op.create_table('project_camera_stations',
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('camera_station_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['camera_station_id'], ['camera_stations.id'], name=op.f('fk_project_camera_stations_camera_station_id_camera_stations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_camera_stations_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('project_id', 'camera_station_id', name=op.f('pk_project_camera_stations'))
    )
    op.create_index(op.f('ix_project_camera_stations_camera_station_id'), 'project_camera_stations', ['camera_station_id'], unique=False)
    op.create_table('classifications',
    sa.Column('batch_id', sa.Uuid(), nullable=True),
    sa.Column('client_index', sa.Integer(), nullable=True),
    sa.Column('camera_station_id', sa.Uuid(), nullable=False),
    sa.Column('source', sa.Enum('web', 'desktop', name='classification_source', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('media_type', sa.Enum('image', 'video', name='media_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('duration_seconds', sa.Float(), nullable=True),
    sa.Column('captured_at', sa.DateTime(), nullable=True),
    sa.Column('captured_at_source', sa.Enum('exif', 'container', 'filename', 'client_mtime', 'upload_time', name='capture_source', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('category', sa.Enum('animal', 'person', 'vehicle', 'blank', name='category', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('label_id', sa.String(length=64), nullable=True),
    sa.Column('class', sa.String(length=100), nullable=True),
    sa.Column('order', sa.String(length=100), nullable=True),
    sa.Column('family', sa.String(length=100), nullable=True),
    sa.Column('genus', sa.String(length=100), nullable=True),
    sa.Column('species', sa.String(length=100), nullable=True),
    sa.Column('scientific_name', sa.String(length=200), nullable=True),
    sa.Column('common_name', sa.String(length=200), nullable=True),
    sa.Column('rank', sa.Enum('class', 'order', 'family', 'genus', 'species', name='rank', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=True),
    sa.Column('label_raw', sa.Text(), nullable=True),
    sa.Column('alternatives', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('frames_analyzed', sa.Integer(), nullable=True),
    sa.Column('evidence_key', sa.String(length=255), nullable=True),
    sa.Column('evidence_frame_index', sa.Integer(), nullable=True),
    sa.Column('evidence_timestamp_seconds', sa.Float(), nullable=True),
    sa.Column('evidence_bbox', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('evidence_width', sa.Integer(), nullable=True),
    sa.Column('evidence_height', sa.Integer(), nullable=True),
    sa.Column('model_detector', sa.String(length=64), nullable=True),
    sa.Column('model_classifier', sa.String(length=64), nullable=True),
    sa.Column('model_sampling', sa.String(length=128), nullable=True),
    sa.Column('pipeline_version', sa.String(length=32), nullable=True),
    sa.Column('low_evidence', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('truncated_at_seconds', sa.Float(), nullable=True),
    sa.Column('status', sa.Enum('queued', 'processing', 'done', 'error', 'cancelled', name='classification_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('tmp_key', sa.String(length=255), nullable=True),
    sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('validation_status', sa.Enum('unvalidated', 'confirmed', 'corrected', 'corrected_unlisted', 'rejected', 'discarded_repeat', name='validation_status', native_enum=False, create_constraint=True, length=32), server_default='unvalidated', nullable=False),
    sa.Column('repeat_of', sa.Uuid(), nullable=True),
    sa.Column('burst_reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('correction_source', sa.Enum('alternative', 'catalog', 'unlisted', name='correction_source', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('corrected_label_id', sa.String(length=64), nullable=True),
    sa.Column('corrected_class', sa.String(length=100), nullable=True),
    sa.Column('corrected_order', sa.String(length=100), nullable=True),
    sa.Column('corrected_family', sa.String(length=100), nullable=True),
    sa.Column('corrected_genus', sa.String(length=100), nullable=True),
    sa.Column('corrected_species', sa.String(length=100), nullable=True),
    sa.Column('corrected_scientific_name', sa.String(length=200), nullable=True),
    sa.Column('corrected_common_name', sa.String(length=200), nullable=True),
    sa.Column('corrected_rank', sa.Enum('class', 'order', 'family', 'genus', 'species', name='corrected_rank', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('suggested_name', sa.String(length=200), nullable=True),
    sa.Column('validated_by', sa.Uuid(), nullable=True),
    sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('validation_notes', sa.Text(), nullable=True),
    sa.Column('validation_history', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=True),
    sa.Column('anon_session_id', sa.Uuid(), nullable=True),
    sa.Column('anon_retain', sa.Boolean(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_classifications_file_sha256_hex')),
    sa.CheckConstraint('(owner_user_id IS NULL) <> (anon_session_id IS NULL)', name=op.f('ck_classifications_owner_xor')),
    sa.CheckConstraint('confidence IS NULL OR confidence BETWEEN 0 AND 1', name=op.f('ck_classifications_confidence_range')),
    sa.ForeignKeyConstraint(['anon_session_id'], ['anon_sessions.id'], name=op.f('fk_classifications_anon_session_id_anon_sessions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['batch_id'], ['classification_batches.id'], name=op.f('fk_classifications_batch_id_classification_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['camera_station_id'], ['camera_stations.id'], name=op.f('fk_classifications_camera_station_id_camera_stations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('fk_classifications_owner_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['repeat_of'], ['classifications.id'], name=op.f('fk_classifications_repeat_of_classifications'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['validated_by'], ['users.id'], name=op.f('fk_classifications_validated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_classifications'))
    )
    op.create_index(op.f('ix_classifications_anon_session_id'), 'classifications', ['anon_session_id'], unique=False)
    op.create_index(op.f('ix_classifications_batch_id'), 'classifications', ['batch_id'], unique=False)
    op.create_index('ix_classifications_camera_captured', 'classifications', ['camera_station_id', 'captured_at'], unique=False)
    op.create_index(op.f('ix_classifications_label_id'), 'classifications', ['label_id'], unique=False)
    op.create_index(op.f('ix_classifications_owner_user_id'), 'classifications', ['owner_user_id'], unique=False)
    op.create_index('ix_classifications_queue', 'classifications', ['status', 'queued_at'], unique=False)
    op.create_index('ix_classifications_sha256', 'classifications', ['file_sha256'], unique=False)
    op.create_index('uq_classifications_camera_sha256_active', 'classifications', ['camera_station_id', 'file_sha256'], unique=True, postgresql_where=sa.text("is_deleted = false AND status IN ('queued', 'processing', 'done')"))

    # Configuración en caliente: retención de datos anónimos activa por defecto (FL-44).
    settings_table = sa.table(
        "system_settings", sa.column("key", sa.String), sa.column("value", postgresql.JSONB)
    )
    op.bulk_insert(settings_table, [{"key": "anon_data_retention", "value": True}])


def downgrade() -> None:
    op.drop_index('uq_classifications_camera_sha256_active', table_name='classifications', postgresql_where=sa.text("is_deleted = false AND status IN ('queued', 'processing', 'done')"))
    op.drop_index('ix_classifications_sha256', table_name='classifications')
    op.drop_index('ix_classifications_queue', table_name='classifications')
    op.drop_index(op.f('ix_classifications_owner_user_id'), table_name='classifications')
    op.drop_index(op.f('ix_classifications_label_id'), table_name='classifications')
    op.drop_index('ix_classifications_camera_captured', table_name='classifications')
    op.drop_index(op.f('ix_classifications_batch_id'), table_name='classifications')
    op.drop_index(op.f('ix_classifications_anon_session_id'), table_name='classifications')
    op.drop_table('classifications')
    op.drop_index(op.f('ix_project_camera_stations_camera_station_id'), table_name='project_camera_stations')
    op.drop_table('project_camera_stations')
    op.drop_index('uq_desktop_imports_camera_package_completed', table_name='desktop_imports', postgresql_where=sa.text("status = 'completed' AND is_deleted = false"))
    op.drop_index(op.f('ix_desktop_imports_owner_user_id'), table_name='desktop_imports')
    op.drop_table('desktop_imports')
    op.drop_index(op.f('ix_classification_batches_owner_user_id'), table_name='classification_batches')
    op.drop_index(op.f('ix_classification_batches_camera_station_id'), table_name='classification_batches')
    op.drop_index(op.f('ix_classification_batches_anon_session_id'), table_name='classification_batches')
    op.drop_table('classification_batches')
    op.drop_index(op.f('ix_projects_owner_user_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_anon_session_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_index('uq_camera_stations_user_code', table_name='camera_stations', postgresql_where=sa.text('is_deleted = false AND owner_user_id IS NOT NULL'))
    op.drop_index('uq_camera_stations_anon_code', table_name='camera_stations', postgresql_where=sa.text('is_deleted = false AND anon_session_id IS NOT NULL'))
    op.drop_index('ix_camera_stations_public', table_name='camera_stations', postgresql_where=sa.text('is_deleted = false'))
    op.drop_index(op.f('ix_camera_stations_owner_user_id'), table_name='camera_stations')
    op.drop_index(op.f('ix_camera_stations_anon_session_id'), table_name='camera_stations')
    op.drop_table('camera_stations')
    op.drop_table('system_settings')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_index(op.f('ix_anon_sessions_expires_at'), table_name='anon_sessions')
    op.drop_table('anon_sessions')
    op.drop_index(op.f('ix_admin_audit_log_created_at'), table_name='admin_audit_log')
    op.drop_index(op.f('ix_admin_audit_log_admin_user_id'), table_name='admin_audit_log')
    op.drop_table('admin_audit_log')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_email_log_created_at'), table_name='email_log')
    op.drop_table('email_log')
    op.drop_table('anon_purge_runs')
