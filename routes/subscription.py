from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, jsonify
from models.payment import create_payment, get_user_subscriptions
import json

bp = Blueprint('subscription', __name__)

@bp.route('/subscription')
def subscription():
    if 'user' not in session:
        flash('Please login to view subscriptions', 'warning')
        return redirect(url_for('auth.login'))
    
    # Subscription plans
    plans = [
        {'name': 'Basic', 'price': 499, 'features': ['1 Camera', 'Basic Anomaly Detection', '7-day History']},
        {'name': 'Professional', 'price': 1499, 'features': ['5 Cameras', 'Advanced AI Detection', '30-day History', 'Email Alerts']},
        {'name': 'Enterprise', 'price': 4999, 'features': ['Unlimited Cameras', 'All AI Features', '90-day History', 'Priority Support', 'Custom Models']}
    ]
    
    # Get user's current subscription if any
    user_subscriptions = []
    if 'user' in session:
        user_id = session['user']['email']
        user_subscriptions = get_user_subscriptions(current_app.db, user_id)
    
    return render_template('subscription.html', 
                         plans=plans, 
                         user_subscriptions=user_subscriptions,
                         role=session.get('role'))

@bp.route('/subscribe', methods=['POST'])
def subscribe():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    try:
        data = dict(request.form)
        data['user_id'] = session['user']['email']
        data['user_name'] = session['user']['name']
        
        # Create payment record
        payment = create_payment(current_app.db, data)
        
        flash(f'✅ Successfully subscribed to {data["plan"]} plan!', 'success')
        
        # Update user role if needed
        if data['plan'] == 'Enterprise':
            current_app.db.users.update_one(
                {'email': session['user']['email']},
                {'$set': {'plan': 'enterprise'}}
            )
        
        return redirect(url_for('subscription.subscription'))
    
    except Exception as e:
        flash(f'❌ Error processing subscription: {str(e)}', 'danger')
        return redirect(url_for('subscription.subscription'))

@bp.route('/api/plans')
def get_plans():
    plans = [
        {'id': 1, 'name': 'Basic', 'price': 499, 'duration': 'month'},
        {'id': 2, 'name': 'Professional', 'price': 1499, 'duration': 'month'},
        {'id': 3, 'name': 'Enterprise', 'price': 4999, 'duration': 'month'}
    ]
    return jsonify(plans)

@bp.route('/api/my_subscription')
def my_subscription():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user']['email']
    subscriptions = get_user_subscriptions(current_app.db, user_id)
    
    if subscriptions:
        latest = subscriptions[0] 
        return jsonify({
            'plan': latest.get('plan', 'Basic'),
            'status': latest.get('status', 'active'),
            'since': latest.get('timestamp', ''),
            'amount': latest.get('amount', 0)
        })
    
    return jsonify({'plan': 'Free', 'status': 'inactive'})