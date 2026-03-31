from datetime import datetime

def create_payment(db, payment_data):
    payment_data['timestamp'] = datetime.now()
    payment_data['status'] = 'success'
    result = db.payments.insert_one(payment_data)
    payment_data['_id'] = str(result.inserted_id)
    return payment_data

def get_user_subscriptions(db, user_id):
    payments = list(db.payments.find({'user_id': user_id}))
    for p in payments:
        p['_id'] = str(p['_id'])
    return payments
