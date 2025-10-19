from datetime import datetime
from bson import ObjectId
from .. import mongo
from .BankAccount import BankAccount

class Organization:
    def __init__(self, document):
        self._id = document.get('_id')
        self.name = document.get('name')
        self.bank_account_id = document.get('bank_account_id')
        self.created_at = document.get('created_at')
        self.updated_at = document.get('updated_at')

    @staticmethod
    def get_by_user_id(user_id):
        org_data = mongo.db.organizations.find_one({'oconvener_id': user_id})
        return Organization(org_data) if org_data else None

    def add_member(self, member_data):
        """Add a new member to the organization"""
        try:
            # Validate member data
            if not member_data.get('email'):
                return False

            # Check if member already exists
            existing_member = mongo.db.organization_members.find_one({
                'organization_id': self._id,
                'email': member_data['email']
            })
            if existing_member:
                return False

            # Calculate membership fee based on access level
            membership_fee = 0
            if member_data.get('access_level_public'):
                membership_fee += 1000  # Public access fee
            if member_data.get('access_level_private_consume'):
                membership_fee += 100   # Private consumer fee
            # Provider access is free (0)

            # Prepare member document
            member_doc = {
                'organization_id': self._id,
                'email': member_data['email'],
                'username': member_data.get('username', ''),
                'access_level': [
                    member_data.get('access_level_public', False),
                    member_data.get('access_level_private_consume', False),
                    member_data.get('access_level_private_provide', False)
                ],
                'membership_fee': membership_fee,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }

            # Insert member
            result = mongo.db.organization_members.insert_one(member_doc)
            return result.inserted_id is not None

        except Exception as e:
            print(f"Error adding member: {str(e)}")
            return False

    def get_members(self):
        """Get all members of the organization"""
        try:
            members = mongo.db.organization_members.find({'organization_id': self._id})
            return list(members)
        except Exception as e:
            print(f"Error getting members: {str(e)}")
            return []

    def get_bank_account(self):
        """Get the organization's bank account"""
        if not self.bank_account_id:
            return None
        return BankAccount.get_by_id(self.bank_account_id)

    def set_bank_account(self, account_name, account_number, is_default=True):
        """Set or update the organization's bank account"""
        try:
            # Create or update bank account
            bank_account = BankAccount.create(
                organization_id=self._id,
                account_name=account_name,
                account_number=account_number,
                is_default=is_default
            )

            if bank_account:
                # Update organization with bank account reference
                mongo.db.organizations.update_one(
                    {'_id': self._id},
                    {'$set': {
                        'bank_account_id': str(bank_account.account_id),
                        'updated_at': datetime.utcnow()
                    }}
                )
                self.bank_account_id = str(bank_account.account_id)
                return True
            return False

        except Exception as e:
            print(f"Error setting bank account: {str(e)}")
            return False

    def get_member(self, member_id):
        """Get member details including bank account information"""
        try:
            member = mongo.db.organization_members.find_one({
                'organization_id': self._id,
                '_id': ObjectId(member_id)
            })
            
            if member and member.get('bank_account_id'):
                # Get bank account details
                bank_account = BankAccount.get_by_id(member['bank_account_id'])
                if bank_account:
                    member['bank_account'] = bank_account.to_dict()
            
            return member
        except Exception as e:
            print(f"Error getting member: {str(e)}")
            return None

    def update_name(self, new_name: str) -> bool:
        """Update organization name and related records"""
        try:
            old_name = self.name
            
            # 更新组织名称
            result = mongo.db.organizations.update_one(
                {'_id': self._id},
                {'$set': {
                    'name': new_name,
                    'updated_at': datetime.utcnow()
                }}
            )
            
            if result.modified_count > 0:
                self.name = new_name
                
                # 更新服务配置
                from ..datauser.models.service_config import ServiceConfig
                ServiceConfig.update_organization_name(old_name, new_name)
                
                # 更新策略
                from ..datauser.models.policy import Policy
                Policy.update_organization_name(old_name, new_name)
                
                # 更新组织成员记录
                mongo.db.organization_members.update_many(
                    {'organization_id': self._id},
                    {'$set': {'organization_name': new_name}}
                )
                
                return True
            return False
            
        except Exception as e:
            print(f"Error updating organization name: {str(e)}")
            return False 