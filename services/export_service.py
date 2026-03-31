"""Export service for generating reports in PDF and CSV formats."""
import csv
from io import StringIO, BytesIO
from datetime import datetime


def export_anomalies_csv(anomalies, video_map=None):
    """Export anomalies to CSV format.
    
    Args:
        anomalies: list of anomaly documents
        video_map: dict mapping video_id to camera name
    
    Returns:
        CSV string
    """
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'timestamp', 'camera', 'type', 'score', 'objects', 'description', 'status'
    ])
    writer.writeheader()
    
    for a in anomalies:
        ts = a.get('detection_time')
        if isinstance(ts, str):
            ts_str = ts
        else:
            ts_str = ts.isoformat() if ts else ''
        
        writer.writerow({
            'timestamp': ts_str,
            'camera': video_map.get(a.get('video_id'), a.get('video_id', 'N/A')) if video_map else a.get('video_id', 'N/A'),
            'type': a.get('anomaly_type', 'unknown'),
            'score': f"{a.get('anomaly_score', 0):.2f}",
            'objects': ', '.join(a.get('objects_detected', [])) if a.get('objects_detected') else '',
            'description': a.get('description', ''),
            'status': a.get('status', 'pending')
        })
    
    return output.getvalue()


def export_anomalies_pdf(anomalies, video_map=None, title="Anomaly Report"):
    """Export anomalies to PDF format.
    
    Args:
        anomalies: list of anomaly documents
        video_map: dict mapping video_id to camera name
        title: report title
    
    Returns:
        PDF bytes
    """
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib import colors
    except ImportError:
        # Fallback: return CSV in error message
        return f"PDF library not installed. Install: pip install reportlab".encode()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#003366'))
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 0.3 * inch))
    
    # Metadata
    meta = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total Anomalies: {len(anomalies)}"
    elements.append(Paragraph(meta, styles['Normal']))
    elements.append(Spacer(1, 0.2 * inch))
    
    # Table
    data = [['Timestamp', 'Camera', 'Type', 'Score', 'Objects', 'Status']]
    for a in anomalies[:50]:  # limit to first 50 for PDF readability
        ts = a.get('detection_time')
        if isinstance(ts, str):
            ts_str = ts[:19]  # truncate ISO string
        else:
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else ''
        
        data.append([
            ts_str,
            video_map.get(a.get('video_id'), a.get('video_id', '')[:8]+'...') if video_map else a.get('video_id', '')[:8]+'...',
            a.get('anomaly_type', 'unknown'),
            f"{a.get('anomaly_score', 0):.2f}",
            ', '.join(a.get('objects_detected', [])[:2]),  # first 2 objects
            a.get('status', 'pending')
        ])
    
    table = Table(data, colWidths=[1.2*inch, 1.2*inch, 0.8*inch, 0.6*inch, 1.2*inch, 0.8*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
    ]))
    elements.append(table)
    
    doc.build(elements)
    return buffer.getvalue()


def export_analytics_summary(summary_data):
    """Export analytics summary to CSV.
    
    Args:
        summary_data: dict with 'today', 'week', 'total', etc.
    
    Returns:
        CSV string
    """
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=['metric', 'value'])
    writer.writeheader()
    
    for key, value in summary_data.items():
        writer.writerow({'metric': key, 'value': value})
    
    return output.getvalue()
