import random

def send_otp(phone):
    otp = str(random.randint(100000, 999999))
    print(f"📱 Demo OTP for {phone}: {otp}")
    return otp
