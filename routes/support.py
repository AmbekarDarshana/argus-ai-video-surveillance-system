from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, jsonify
from models.ticket import create_ticket, get_tickets, update_ticket_reply
from bson import ObjectId
import json

bp = Blueprint('support', __name__)

@bp.route('/support')
def support():
    if 'user' not in session:
        flash('Please login to access support', 'warning')
        return redirect(url_for('auth.login'))
    
    # Get user's tickets
    user_id = session['user']['email']
    tickets = get_tickets(current_app.db, user_id)
    
    return render_template('support.html', tickets=tickets, role=session.get('role'))

@bp.route('/submit_ticket', methods=['POST'])
def submit_ticket():
    if 'user' not in session:
        flash('Please login to submit a ticket', 'warning')
        return redirect(url_for('auth.login'))
    
    try:
        data = dict(request.form)
        data['user_id'] = session['user']['email']
        data['user_name'] = session['user'].get('name', session['user']['email'])
        data['status'] = 'open'
        
        # Create ticket
        ticket = create_ticket(current_app.db, data)
        
        flash('✅ Support ticket submitted successfully! We will respond within 24 hours.', 'success')
        return redirect(url_for('support.support'))
    
    except Exception as e:
        flash(f'❌ Error submitting ticket: {str(e)}', 'danger')
        return redirect(url_for('support.support'))

@bp.route('/tickets')
def tickets():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    role = session.get('role')
    user_id = session['user']['email']
    
    # Admins can see all tickets, users only see their own
    if role == 'admin':
        tickets_list = get_tickets(current_app.db, None)
    else:
        tickets_list = get_tickets(current_app.db, user_id)
    
    return render_template('tickets.html', tickets=tickets_list, role=role)

@bp.route('/ticket/<ticket_id>')
def view_ticket(ticket_id):
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    try:
        ticket = current_app.db.tickets.find_one({'_id': ObjectId(ticket_id)})
        if not ticket:
            flash('❌ Ticket not found', 'danger')
            return redirect(url_for('support.tickets'))
        
        # Check permission
        role = session.get('role')
        user_id = session['user']['email']
        
        if role != 'admin' and ticket['user_id'] != user_id:
            flash('❌ You do not have permission to view this ticket', 'danger')
            return redirect(url_for('support.tickets'))
        
        ticket['_id'] = str(ticket['_id'])
        return render_template('ticket_detail.html', ticket=ticket, role=role)
    
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')
        return redirect(url_for('support.tickets'))

@bp.route('/ticket/<ticket_id>/reply', methods=['POST'])
def reply_ticket(ticket_id):
    if 'user' not in session or session.get('role') != 'admin':
        flash('❌ Admin access required', 'danger')
        return redirect(url_for('support.tickets'))
    
    try:
        reply = request.form.get('reply', '').strip()
        if not reply:
            flash('❌ Reply cannot be empty', 'danger')
            return redirect(url_for('support.view_ticket', ticket_id=ticket_id))
        
        update_ticket_reply(current_app.db, ticket_id, reply)
        flash('✅ Reply submitted successfully', 'success')
        return redirect(url_for('support.view_ticket', ticket_id=ticket_id))
    
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')
        return redirect(url_for('support.tickets'))

@bp.route('/api/tickets')
def api_tickets():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    role = session.get('role')
    user_id = session['user']['email']
    
    if role == 'admin':
        tickets_list = get_tickets(current_app.db, None)
    else:
        tickets_list = get_tickets(current_app.db, user_id)
    
    return jsonify(tickets_list)

@bp.route('/faq')
def faq():
    faqs = [
        {
            'question': 'How does AI anomaly detection work?',
            'answer': 'Our system uses YOLOv8 deep learning model to detect objects (people, vehicles, animals) in real-time, then applies rules to identify suspicious activities.'
        },
        {
            'question': 'What types of anomalies can be detected?',
            'answer': 'We detect: intrusion, loitering, crowding, suspicious objects (weapons), unauthorized vehicles, animal intrusions, and fight detection.'
        },
        {
            'question': 'How long are videos stored?',
            'answer': 'Free tier: 7 days, Professional: 30 days, Enterprise: 90 days. Anomaly screenshots are stored indefinitely.'
        },
        {
            'question': 'Can I use my own camera?',
            'answer': 'Yes! You can connect RTSP cameras or upload video files for processing.'
        },
        {
            'question': 'Is there a mobile app?',
            'answer': 'Currently web-only, but our interface is mobile-responsive. Mobile apps are coming soon.'
        }
    ]
    
    return render_template('faq.html', faqs=faqs, role=session.get('role'))