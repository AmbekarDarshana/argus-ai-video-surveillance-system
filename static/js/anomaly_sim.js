function simulateAnomaly() {
    fetch('/anomaly/trigger_process', {method: 'POST'})
        .then(res => res.json())
        .then(data => {
            if (data.status) alert(data.status);
            if (data.error) alert(data.error);
        })
        .catch(err => alert('Error: ' + err));
}
