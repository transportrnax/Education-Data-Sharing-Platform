from datetime import datetime, UTC # Redundant if already imported above
from bson import ObjectId # Redundant if already imported
from ..extensions import mongo # Assuming this is your Flask-PyMongo instance
from app.models.ActivityRecord import ActivityRecord # For logging actions

class UserQuestionService: # (Status constants and __init__, from_document, __repr__ as defined in Data Representation section)
    def raiseQuestion(self):
        if not self.user_account or not self.question:
            print("Error: user_account or question is empty")
            return None

        collection = mongo.db.question
        question_data = {
            "user_account": self.user_account,
            "question": self.question,
            "question_time": self.question_time,
            "status": self.status # Should be STATUS_PENDING by default from __init__
        }
        
        result = collection.insert_one(question_data)
        print(f"Question raised by {self.user_account}. ID: {self._id}")
            
        #ActivityRecord(userAccount=self.user_account, activityName="Help Question Raised", activityTime=self.question_time, details=f"Question ID: {self._id}").addRecord()
        return self._id


    def solveQuestion(self, answer: str, answered_by: str):
        """
        Operation: T-Admin answers a question.
        Updates status, records answer details in DB, and logs.
        """
        if not self._id or not answer or not answered_by:
            print("Error: _id, answer, or answered_by is empty for solveQuestion")
            return False

        collection = self.get_collection()
        now_utc = datetime.now(UTC)

        update_data = {
            "answer": answer,
            "answered_by": answered_by,
            "answered_time": now_utc,
            "status": self.STATUS_ANSWERED
        }
        
        try:
            result = collection.update_one(
                {"_id": self._id},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                # Update instance attributes to reflect the change in data state
                self.answer = answer
                self.answered_by = answered_by
                self.answered_time = now_utc
                self.status = self.STATUS_ANSWERED
                print(f"Question {self._id} answered by {answered_by}.")
                
                # ActivityRecord(
                #     userAccount=answered_by,
                #     activityName="Help Question Answered",
                #     activityTime=now_utc,
                #     details=f"Question ID: {self._id}, Target User: {self.user_account}"
                # ).addRecord()
                return True
            else:
                print(f"Error: Question {self._id} not found for answering or no update made.")
                return False
        except Exception as e:
            print(f"Error updating question {self._id} in DB: {e}")
            return False