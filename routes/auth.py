from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from datetime import datetime
from models.user import get_user_by_email, verify_password, create_user
from utils.validators import validate_registration

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = dict(request.form)
        data['role'] = 'client'
        if validate_registration(data):
            try:
                create_user(current_app.db, data)
                flash('✅ Registration successful!', 'success')
                return redirect(url_for('auth.login'))
            except Exception as e:
                flash(f'❌ Error: {str(e)}', 'danger')
        else:
            flash('❌ Invalid data', 'danger')
    return render_template('auth/register.html')

import bcrypt 

@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')

        # Check if user exists
        user = current_app.db.users.find_one({'email': email})
        if user:
            flash('Email address already exists', 'danger')
            return redirect(url_for('auth.signup'))

        # Create new user
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()) # Generate Bcrypt hash
        new_user = {
        'email': email,
        'name': name,
        'password': hashed_password.decode('utf-8'), # Save as string
        'role': 'client',
        'created_at': datetime.now() # Make sure you imported standard datetime as discussed before
    }

        current_app.db.users.insert_one(new_user)
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('❌ Please provide both email and password', 'danger')
            return render_template('auth/login.html')
        
        user = get_user_by_email(current_app.db, email)
        
        if user and verify_password(user['password'], password):
            # remember the user's database id so we can enforce owner restrictions
            session['user'] = {
                'email': email,
                'name': user.get('name', email),
                '_id': str(user.get('_id'))
            }
            session['role'] = user['role']
            session.permanent = True
            
            flash(f'✅ Welcome, {user.get("name", email)}!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('❌ Invalid credentials', 'danger')
    
    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    session.clear()
    flash('👋 Logged out!', 'info')
    return redirect(url_for('auth.login'))
