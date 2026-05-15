"""initial schema

Revision ID: ed18375f03a0
Revises:
Create Date: 2026-05-14 20:20:01.815840

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed18375f03a0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('first_name', sa.Text(), nullable=False),
        sa.Column('last_name', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('phone_number', sa.Text(), nullable=True),
        sa.Column('avatar', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('profile_pic', sa.Text(), nullable=True),
        sa.CheckConstraint("role IN ('seeker', 'provider')", name='ck_users_role'),
        sa.UniqueConstraint('email', 'role', name='uq_users_email_role'),
    )

    op.create_table(
        'providers',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('user_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('expertise', sa.Text(), nullable=True),
        sa.Column('phone_number', sa.Text(), nullable=False),
        sa.Column('hourly_rate', sa.Float(), nullable=True),
        sa.Column('access_fee', sa.Float(), nullable=False),
        sa.Column('request_approval_required', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('profile_photo', sa.Text(), nullable=True),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('offered_benefits', sa.Text(), nullable=True),
        sa.Column('verified', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('id_document_path', sa.Text(), nullable=True),
        sa.Column('selfie_path', sa.Text(), nullable=True),
        sa.Column('verification_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('verification_submitted_at', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
    )

    op.create_table(
        'access_requests',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('seeker_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_id', sa.Text(), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('contact_email', sa.Text(), nullable=True),
        sa.Column('contact_phone', sa.Text(), nullable=True),
        sa.Column('released_data', sa.Text(), nullable=True),
        sa.Column('access_fee_status', sa.Text(), nullable=False),
        sa.Column('payment_method', sa.Text(), nullable=True),
        sa.Column('transaction_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'completed')", name='ck_access_requests_status'),
        sa.CheckConstraint("access_fee_status IN ('pending', 'paid', 'refunded')", name='ck_access_requests_fee_status'),
    )

    op.create_table(
        'access_grants',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('seeker_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_id', sa.Text(), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request_id', sa.Text(), sa.ForeignKey('access_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_email', sa.Text(), nullable=False),
        sa.Column('contact_phone', sa.Text(), nullable=True),
        sa.Column('granted_data', sa.Text(), nullable=True),
        sa.Column('granted_at', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked')", name='ck_access_grants_status'),
    )

    op.create_table(
        'messages',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('from_user_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('to_user_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request_id', sa.Text(), sa.ForeignKey('access_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('user_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('related_request_id', sa.Text(), sa.ForeignKey('access_requests.id', ondelete='CASCADE'), nullable=True),
        sa.Column('is_read', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.Text(), nullable=False),
    )

    op.create_table(
        'payments',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('request_id', sa.Text(), sa.ForeignKey('access_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('seeker_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_id', sa.Text(), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tx_ref', sa.Text(), nullable=False, unique=True),
        sa.Column('paychangu_checkout_url', sa.Text(), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.Text(), nullable=False, server_default='MWK'),
        sa.Column('platform_share', sa.Float(), nullable=False, server_default='0'),
        sa.Column('provider_share', sa.Float(), nullable=False, server_default='0'),
        sa.Column('split_percentage', sa.Float(), nullable=False, server_default='50.0'),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('payment_channel', sa.Text(), nullable=True),
        sa.Column('paychangu_reference', sa.Text(), nullable=True),
        sa.Column('paychangu_charge_id', sa.Text(), nullable=True),
        sa.Column('customer_email', sa.Text(), nullable=True),
        sa.Column('customer_name', sa.Text(), nullable=True),
        sa.Column('meta', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'success', 'failed', 'cancelled')", name='ck_payments_status'),
    )

    op.create_table(
        'payouts',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('provider_id', sa.Text(), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('charge_id', sa.Text(), nullable=False, unique=True),
        sa.Column('payout_method', sa.Text(), nullable=False),
        sa.Column('recipient_name', sa.Text(), nullable=False),
        sa.Column('recipient_account', sa.Text(), nullable=False),
        sa.Column('bank_name', sa.Text(), nullable=True),
        sa.Column('bank_uuid', sa.Text(), nullable=True),
        sa.Column('mobile_operator_ref_id', sa.Text(), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.Text(), nullable=False, server_default='MWK'),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('paychangu_ref_id', sa.Text(), nullable=True),
        sa.Column('paychangu_trans_id', sa.Text(), nullable=True),
        sa.Column('paychangu_trace_id', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.CheckConstraint("payout_method IN ('airtel_money', 'tnm_mpamba', 'bank_transfer')", name='ck_payouts_method'),
        sa.CheckConstraint("status IN ('pending', 'processing', 'successful', 'failed', 'cancelled')", name='ck_payouts_status'),
    )

    op.create_table(
        'reviews',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('request_id', sa.Text(), sa.ForeignKey('access_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reviewer_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_id', sa.Text(), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('is_verified_transaction', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_reviews_rating'),
        sa.UniqueConstraint('request_id', 'reviewer_id', name='uq_reviews_request_reviewer'),
    )

    op.create_table(
        'login_attempts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('ip_address', sa.Text(), nullable=True),
        sa.Column('success', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attempted_at', sa.Text(), nullable=False),
    )

    op.create_table(
        'platform_settings',
        sa.Column('key', sa.Text(), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.Column('updated_by', sa.Text(), nullable=True),
    )

    op.create_table(
        'verification_requests',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('provider_id', sa.Text(), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('id_document_path', sa.Text(), nullable=True),
        sa.Column('selfie_path', sa.Text(), nullable=True),
        sa.Column('submitted_at', sa.Text(), nullable=False),
        sa.Column('admin_id', sa.Text(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='ck_verification_requests_status'),
    )

    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('user_id', sa.Text(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.Text(), nullable=False),
        sa.Column('used', sa.Integer(), nullable=False, server_default='0'),
    )

    op.create_index('idx_login_attempts_email', 'login_attempts', ['email', 'attempted_at'])
    op.create_index('idx_reviews_provider', 'reviews', ['provider_id'])
    op.create_index('idx_reviews_request', 'reviews', ['request_id'])
    op.create_index('idx_password_reset_tokens_user', 'password_reset_tokens', ['user_id'])
    op.create_index('idx_password_reset_tokens_hash', 'password_reset_tokens', ['token_hash'])
    op.create_index('idx_verification_requests_provider', 'verification_requests', ['provider_id'])
    op.create_index('idx_verification_requests_status', 'verification_requests', ['status'])

    op.execute(
        """
        INSERT INTO platform_settings (key, value, updated_at, updated_by)
        VALUES ('provider_revenue_share_percentage', '50.0', CURRENT_TIMESTAMP, 'system')
        """
    )


def downgrade():
    op.drop_index('idx_verification_requests_status', table_name='verification_requests')
    op.drop_index('idx_verification_requests_provider', table_name='verification_requests')
    op.drop_index('idx_password_reset_tokens_hash', table_name='password_reset_tokens')
    op.drop_index('idx_password_reset_tokens_user', table_name='password_reset_tokens')
    op.drop_index('idx_reviews_request', table_name='reviews')
    op.drop_index('idx_reviews_provider', table_name='reviews')
    op.drop_index('idx_login_attempts_email', table_name='login_attempts')

    op.drop_table('password_reset_tokens')
    op.drop_table('verification_requests')
    op.drop_table('platform_settings')
    op.drop_table('login_attempts')
    op.drop_table('reviews')
    op.drop_table('payouts')
    op.drop_table('payments')
    op.drop_table('notifications')
    op.drop_table('messages')
    op.drop_table('access_grants')
    op.drop_table('access_requests')
    op.drop_table('providers')
    op.drop_table('users')
