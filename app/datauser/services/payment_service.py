from ..models.payment import PaymentRecord

def pay_for_download(student_id, org_id, thesis_id):
    PaymentRecord.create(student_id, org_id, 10, 'download', detail={'thesis_id': thesis_id})

def pay_for_record(student_id, org_id, record_id):
    PaymentRecord.create(student_id, org_id, 10, 'record', detail={'record_id': record_id})

def pay_for_identify(student_id, org_id, identify_id):
    PaymentRecord.create(student_id, org_id, 50, 'identify', detail={'identify_id': identify_id}) 