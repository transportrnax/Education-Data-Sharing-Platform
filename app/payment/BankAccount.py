from datetime import datetime
from typing import Optional
from bson import ObjectId
from ..extensions import mongo

class BankAccount:
    def __init__(self, account_number: str, account_holder: str, organization_id: str, balance: float = 0.0):
        self._id: Optional[ObjectId] = None
        self.account_number = account_number
        self.account_holder = account_holder
        self.organization_id = organization_id
        self.balance = balance
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.is_active = True

    def to_dict(self) -> dict:
        return {
            "_id": str(self._id) if self._id else None,
            "account_number": self.account_number,
            "account_holder": self.account_holder,
            "organization_id": self.organization_id,
            "balance": self.balance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'BankAccount':
        account = cls(
            account_number=data["account"],
            account_holder=data["name"],
            organization_id=data["organization_id"],
            balance=data["balance"]
        )
        account._id = data.get("_id")
        account.created_at = data.get("created_at", datetime.utcnow())
        account.updated_at = data.get("updated_at", datetime.utcnow())
        account.is_active = data.get("is_active", True)
        return account

    @classmethod
    def get_organization_account(cls, organization_id: str) -> Optional['BankAccount']:
        """Get the bank account for an organization"""
        account_data = mongo.db.BANK_ACCOUNT.find_one({"organization_id": organization_id})
        if account_data:
            return cls.from_dict(account_data)
        return None

    @classmethod
    def create_organization_account(cls, organization_id: str, account_number: str, account_holder: str) -> 'BankAccount':
        """Create a new bank account for an organization"""
        account = cls(
            account_number=account_number,
            account_holder=account_holder,
            organization_id=organization_id
        )
        result = mongo.db.BANK_ACCOUNT.insert_one(account.to_dict())
        account._id = result.inserted_id
        return account

    def deposit(self, amount: float) -> bool:
        if amount <= 0:
            return False
        self.balance += amount
        self.updated_at = datetime.utcnow()
        mongo.db.BANK_ACCOUNT.update_one(
            {"_id": self._id},
            {"$set": {"balance": self.balance, "updated_at": self.updated_at}}
        )
        return True

    def withdraw(self, amount: float) -> bool:
        if amount <= 0 or amount > self.balance:
            return False
        self.balance -= amount
        self.updated_at = datetime.utcnow()
        mongo.db.BANK_ACCOUNT.update_one(
            {"_id": self._id},
            {"$set": {"balance": self.balance, "updated_at": self.updated_at}}
        )
        return True

    def transfer_membership_fee(self, edba_account: '596117071864958', amount: float) -> bool:
        """Transfer membership fee to EDBA account"""
        if not self.withdraw(amount):
            return False
        if not edba_account.deposit(amount):
            # If deposit fails, rollback withdrawal
            self.deposit(amount)
            return False
        return True
