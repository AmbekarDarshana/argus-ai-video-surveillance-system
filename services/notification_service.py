def send_alert(anomaly_data):
    """Display or log alert messages without crashing the stream."""
    # handle both string and dict calls safely
    if isinstance(anomaly_data, dict):
        alert_type = anomaly_data.get("anomaly_type", "unknown")
        alert_msg = f"⚠️ ALERT: {alert_type} detected"
    else:
        # if it's already a string
        alert_msg = f"⚠️ ALERT: {anomaly_data}"

    # You can change this to any logging or notification system
    print(alert_msg)