def validate_registration(data):
    required = ['name', 'email', 'phone', 'password']
    return all(data.get(f) for f in required) and data['password'] == data.get('confirm_password', '')
