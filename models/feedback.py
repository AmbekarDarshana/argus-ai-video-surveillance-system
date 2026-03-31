from datetime import datetime

def add_feedback(db, feedback_data):
    feedback_data['date_submitted'] = datetime.now()
    result = db.feedback.insert_one(feedback_data)
    feedback_data['_id'] = str(result.inserted_id)
    
    if 'anomaly_id' in feedback_data:
        label = feedback_data['label']
        status = 'confirmed' if label == 'true_positive' else 'false_alarm'
        from models.anomaly import update_anomaly_status
        update_anomaly_status(db, feedback_data['anomaly_id'], status)
    return feedback_data

def get_feedback_analytics(db):
    return list(db.feedback.aggregate([{'$group': {'_id': '$label', 'count': {'$sum': 1}}}]))
