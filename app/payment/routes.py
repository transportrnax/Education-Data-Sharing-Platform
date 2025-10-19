from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from bson import ObjectId
from datetime import datetime, timezone

from . import payment_bp
from ..models.Payment import Payment
from ..models.BankAccount import BankAccount
from ..models.Organization import Organization
from ..extensions import mongo

# EDBA account details - should be configured in environment variables
EDBA_ACCOUNT_NUMBER = "596117071864958"  # Replace with actual EDBA account number
MEMBERSHIP_FEE = 100.0  # Replace with actual membership fee amount

@payment_bp.route('/bank-accounts', methods=['GET'])
@login_required
def get_bank_accounts():
    """Get all bank accounts for the current organization"""
    try:
        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        accounts = BankAccount.get_all_for_organization(organization._id)
        return jsonify({
            'accounts': [account.to_dict() for account in accounts]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/bank-accounts', methods=['POST'])
@login_required
def create_bank_account():
    """Create a new bank account for the organization"""
    try:
        data = request.get_json()
        required_fields = ['account_name', 'account_number']
        
        # Validate required fields
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        # Create new bank account
        account = BankAccount.create_organization_account(
            organization_id=str(organization._id),
            account_number=data['account_number'],
            account_holder=data['account_name']
        )

        return jsonify({
            'message': 'Bank account created successfully',
            'account': account.to_dict()
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/bank-accounts/<account_id>', methods=['PUT'])
@login_required
def update_bank_account(account_id):
    """Update an existing bank account"""
    try:
        data = request.get_json()
        
        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        # Get account and verify ownership
        account = BankAccount.get_by_id(account_id)
        if not account or str(account.organization_id) != str(organization._id):
            return jsonify({'error': 'Bank account not found or unauthorized'}), 404

        # Update account
        success = account.update(
            account_name=data.get('account_name'),
            account_number=data.get('account_number'),
            is_default=data.get('is_default')
        )

        if success:
            return jsonify({
                'message': 'Bank account updated successfully',
                'account': account.to_dict()
            }), 200
        else:
            return jsonify({'error': 'No changes made'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/bank-accounts/<account_id>', methods=['DELETE'])
@login_required
def delete_bank_account(account_id):
    """Delete a bank account"""
    try:
        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        # Get account and verify ownership
        account = BankAccount.get_by_id(account_id)
        if not account or str(account.organization_id) != str(organization._id):
            return jsonify({'error': 'Bank account not found or unauthorized'}), 404

        # Delete account
        if account.delete():
            return jsonify({'message': 'Bank account deleted successfully'}), 200
        else:
            return jsonify({'error': 'Failed to delete bank account'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/payments', methods=['POST'])
@login_required
def create_payment():
    """Create a new payment record"""
    try:
        data = request.get_json()
        required_fields = ['service_type', 'amount', 'payment_method']
        
        # Validate required fields
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        # Create payment record
        payment = Payment.create(
            user_id=current_user.id,
            organization_id=organization._id,
            amount=float(data['amount']),
            service_type=data['service_type'],
            payment_method=data['payment_method'],
            description=data.get('description', '')
        )

        return jsonify({
            'message': 'Payment created successfully',
            'payment_id': str(payment.payment_id)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/payments', methods=['GET'])
@login_required
def get_payments():
    """Get payment history for the current user or organization"""
    try:
        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        # Get payments for the organization
        payments = Payment.get_by_organization_id(organization._id)
        return jsonify(payments)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/payments/<payment_id>', methods=['PUT'])
@login_required
def update_payment_status(payment_id):
    """Update payment status"""
    try:
        data = request.get_json()
        if 'status' not in data:
            return jsonify({'error': 'Status is required'}), 400

        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        # Get payment and verify ownership
        payment = Payment.get_by_id(payment_id)
        if not payment or str(payment.organization_id) != str(organization._id):
            return jsonify({'error': 'Payment not found or unauthorized'}), 404

        # Update payment status
        payment.update_status(data['status'])
        return jsonify({'message': 'Payment status updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/membership-fee', methods=['POST'])
@login_required
def transfer_membership_fee():
    """Transfer membership fee from organization account to EDBA account"""
    try:
        # Get organization ID from current user
        organization = Organization.get_by_user_id(current_user.id)
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404

        # Get organization's bank account
        org_account = BankAccount.get_organization_account(str(organization._id))
        if not org_account:
            return jsonify({'error': 'Organization bank account not found'}), 404

        # Get EDBA account
        edba_account = BankAccount.get_organization_account(EDBA_ACCOUNT_NUMBER)
        if not edba_account:
            return jsonify({'error': 'EDBA account not found'}), 404

        # Transfer membership fee
        if org_account.transfer_membership_fee(edba_account, MEMBERSHIP_FEE):
            # Create payment record
            payment = Payment.create(
                user_id=current_user.id,
                organization_id=organization._id,
                amount=MEMBERSHIP_FEE,
                service_type='membership_fee',
                payment_method='bank_transfer',
                description='Membership fee payment'
            )

            return jsonify({
                'message': 'Membership fee transferred successfully',
                'payment_id': str(payment.payment_id)
            }), 200
        else:
            return jsonify({'error': 'Failed to transfer membership fee'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

