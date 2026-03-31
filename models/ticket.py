from bson import ObjectId
from datetime import datetime

def create_ticket(db, ticket_data):
    ticket_data['status'] = 'open'
    ticket_data['created_at'] = datetime.now()
    result = db.tickets.insert_one(ticket_data)
    ticket_data['_id'] = str(result.inserted_id)
    return ticket_data

def update_ticket_reply(db, ticket_id, reply):
    db.tickets.update_one({'_id': ObjectId(ticket_id)}, {'$set': {'reply': reply, 'status': 'replied'}})

def get_tickets(db, user_id=None):
    query = {} if user_id is None else {'user_id': user_id}
    tickets = list(db.tickets.find(query).sort('created_at', -1))
    for t in tickets:
        t['_id'] = str(t['_id'])
    return tickets
