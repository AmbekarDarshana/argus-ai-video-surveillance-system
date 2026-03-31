def generate_invoice(payment_data):
    print(f"📄 Invoice: {payment_data['plan']} - ₹{payment_data['amount']}")
    return "Invoice generated"
