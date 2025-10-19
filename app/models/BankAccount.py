from datetime import datetime
from bson import ObjectId
from .. import mongo

class BankAccount:
    BANK_NAME = "UICBank"  # 唯一的银行名称

    def __init__(self, document):
        self.account_id = document.get('_id')
        self.organization_id = document.get('organization_id')
        self.account_name = document.get('account_name')
        self.account_number = document.get('account_number')
        self.bank_name = self.BANK_NAME  # 固定使用UICBank
        self.bank_branch = document.get('bank_branch')
        self.swift_code = document.get('swift_code')
        self.is_default = document.get('is_default', False)
        self.created_at = document.get('created_at', datetime.utcnow())
        self.updated_at = document.get('updated_at', datetime.utcnow())

    @staticmethod
    def create(organization_id, account_name, account_number, is_default=False):
        # If this is set as default, unset any existing default account
        if is_default:
            mongo.db.bank_accounts.update_many(
                {'organization_id': organization_id, 'is_default': True},
                {'$set': {'is_default': False}}
            )

        account_data = {
            'organization_id': organization_id,
            'account_name': account_name,
            'account_number': account_number,
            'bank_name': BankAccount.BANK_NAME,
            'is_default': is_default,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = mongo.db.bank_accounts.insert_one(account_data)
        account_data['_id'] = result.inserted_id
        return BankAccount(account_data)

    @staticmethod
    def get_by_id(account_id):
        account_data = mongo.db.bank_accounts.find_one({'_id': ObjectId(account_id)})
        return BankAccount(account_data) if account_data else None

    @staticmethod
    def get_all_for_organization(organization_id):
        accounts = mongo.db.bank_accounts.find({'organization_id': organization_id})
        return [BankAccount(account) for account in accounts]

    @staticmethod
    def get_default_account(organization_id):
        account_data = mongo.db.bank_accounts.find_one({
            'organization_id': organization_id,
            'is_default': True
        })
        return BankAccount(account_data) if account_data else None

    def update(self, account_name=None, account_number=None, is_default=None):
        update_data = {
            'updated_at': datetime.utcnow()
        }

        if account_name is not None:
            update_data['account_name'] = account_name
        if account_number is not None:
            update_data['account_number'] = account_number
        if is_default is not None:
            update_data['is_default'] = is_default
            # If setting as default, unset any existing default account
            if is_default:
                mongo.db.bank_accounts.update_many(
                    {
                        'organization_id': self.organization_id,
                        '_id': {'$ne': self.account_id},
                        'is_default': True
                    },
                    {'$set': {'is_default': False}}
                )

        result = mongo.db.bank_accounts.update_one(
            {'_id': self.account_id},
            {'$set': update_data}
        )

        if result.modified_count > 0:
            # Update instance attributes
            for key, value in update_data.items():
                if key != 'updated_at':
                    setattr(self, key, value)
            self.updated_at = update_data['updated_at']
            return True
        return False

    def delete(self):
        result = mongo.db.bank_accounts.delete_one({'_id': self.account_id})
        return result.deleted_count > 0

    def to_dict(self):
        return {
            'account_id': str(self.account_id),
            'organization_id': str(self.organization_id),
            'account_name': self.account_name,
            'account_number': self.account_number,
            'bank_name': self.bank_name,
            'bank_branch': self.bank_branch,
            'swift_code': self.swift_code,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        } 