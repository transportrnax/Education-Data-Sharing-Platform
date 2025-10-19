from datetime import datetime, UTC
from app.extensions import mongo
from app.main.User import User
from bson import ObjectId

class OConvener(User):
    def __init__(self, user_doc: dict, organization_id: str = None, organization_name: str = None):
        user_doc['role'] = User.Roles.O_CONVENER.value

        super().__init__(user_doc)
        self.organization_id = organization_id if organization_id is not None else user_doc.get('organization_id')
        self.organization_name = organization_name if organization_name is not None else user_doc.get('organization_name')
    
    def to_dict(self) -> dict:
        data = {
            "_id": ObjectId(self.user_id) if self.user_id and self.user_id != "-1" else None,
            "email": self.email,
            "username": self.username,
            "role": self.role.value if isinstance(self.role, User.Roles) else self.role,
            "access_level": self.access_level, 
        }
        data['organization_id'] = self.organization_id
        data['organizatoin_name'] = self.organization_name
        
        return data
        
    def __repr__(self):
        org_info = f", Org: {self.organization_name} ({self.organization_id})" if self.organization_id else ""
        return f"<OConvener email: {self.email} id: {self.user_id} {org_info}>"
    
class Workspace:
    def __init__(self, workspace_doc: dict):
        self.name: str = workspace_doc.get('name')
        self.organization_id: str = workspace_doc.get('organization_id')
        self.organization_name: str = workspace_doc.get('organization_name')
        self.created_oconvener: str = workspace_doc.get('created_oconvener')
        self.description: str = workspace_doc.get('description','')
        self.member: list = workspace_doc.get('members')
        self.created_at: datetime = workspace_doc.get('created_time')
        self.updated_at: datetime = datetime.now(UTC)

    def to_dict(self) -> dict[str, any]:
        return {
            "name": self.name,
            "organization_id": self.organization_id,
            "created_oconvener": self.created_oconvener,
            "description": self.description,
            "members": self.member, 
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, any]) -> 'Workspace':
        return cls(data)

    def __repr__(self):
        return f"<Workspace(name='{self.name}', organization_id='{self.organization_id}', id='{str(self._id)}')>"
    