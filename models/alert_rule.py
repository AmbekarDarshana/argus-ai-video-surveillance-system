# models/alert_rule.py (create this file)
from bson import ObjectId
from datetime import datetime

def get_alert_rules(db, owner_id=None):
    query = {}
    if owner_id:
        query['owner_id'] = owner_id
    rules = list(db.alert_rules.find(query))
    for r in rules:
        r['_id'] = str(r['_id'])
    return rules

def create_alert_rule(db, rule_data):
    rule_data['created_at'] = datetime.now()
    result = db.alert_rules.insert_one(rule_data)
    rule_data['_id'] = str(result.inserted_id)
    return rule_data

def delete_alert_rule(db, rule_id):
    db.alert_rules.delete_one({'_id': ObjectId(rule_id)})