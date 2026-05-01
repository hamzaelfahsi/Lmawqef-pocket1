#!/usr/bin/env python3
"""
Lmawqef Pocket ULTIMATE - Moroccan Marketplace Platform
Version ULTIMATE avec toutes les fonctionnalites startup
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timedelta
import os
import json
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'lmawqef-pocket-ultimate-secret-key-2026-v3'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lmawqef_ultimate.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

for subdir in ['profiles', 'services', 'portfolio', 'annonces']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], subdir), exist_ok=True)

db = SQLAlchemy(app)

# ==================== DATABASE MODELS ====================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    worker_subtype = db.Column(db.String(20), nullable=True)
    skills = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    avatar = db.Column(db.String(200), default='default-avatar.png')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    address = db.Column(db.String(300), nullable=True)
    company_name = db.Column(db.String(150), nullable=True)
    rc_number = db.Column(db.String(50), nullable=True)
    ice_number = db.Column(db.String(50), nullable=True)
    # Gamification
    points = db.Column(db.Integer, default=0)
    level_id = db.Column(db.Integer, db.ForeignKey('levels.id'), nullable=True)
    response_time_avg = db.Column(db.Float, default=0)
    completion_rate = db.Column(db.Float, default=100.0)
    featured_until = db.Column(db.DateTime, nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    # Subscription
    subscription_plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=True)
    subscription_start = db.Column(db.DateTime, nullable=True)
    subscription_end = db.Column(db.DateTime, nullable=True)
    subscription_active = db.Column(db.Boolean, default=False)
    # Annonces counters
    free_announces_used = db.Column(db.Integer, default=0)
    announces_month_used = db.Column(db.Integer, default=0)
    announces_month_reset = db.Column(db.DateTime, default=datetime.utcnow)
    # Insurance
    insurance_active = db.Column(db.Boolean, default=False)
    insurance_expires = db.Column(db.DateTime, nullable=True)
    # Relationships
    services = db.relationship('Service', backref='worker', lazy=True, cascade='all, delete-orphan')
    reviews_given = db.relationship('Review', foreign_keys='Review.client_id', backref='client', lazy=True)
    reviews_received = db.relationship('Review', foreign_keys='Review.worker_id', backref='reviewed_worker', lazy=True)
    bookings = db.relationship('Booking', foreign_keys='Booking.client_id', backref='client', lazy=True)
    portfolio_items = db.relationship('PortfolioItem', backref='user', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade='all, delete-orphan')
    annonces = db.relationship('Annonce', backref='author', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='user', lazy=True)
    badges = db.relationship('UserBadge', backref='user', lazy=True, cascade='all, delete-orphan')
    devis_list = db.relationship('Devis', backref='worker_user', lazy=True, cascade='all, delete-orphan')
    commissions = db.relationship('Commission', backref='worker_comm', lazy=True)
    availability_slots = db.relationship('Availability', backref='user_avail', lazy=True, cascade='all, delete-orphan')

    def average_rating(self):
        reviews = Review.query.filter_by(worker_id=self.id).all()
        if not reviews: return 0
        return round(sum(r.rating for r in reviews) / len(reviews), 1)

    def review_count(self):
        return Review.query.filter_by(worker_id=self.id).count()

    def has_active_subscription(self):
        if not self.subscription_active or not self.subscription_end: return False
        return datetime.utcnow() < self.subscription_end

    def get_monthly_annonce_limit(self):
        if self.has_active_subscription() and self.subscription_plan:
            return self.subscription_plan.annonce_limit
        return 0

    def get_announce_price(self):
        config = AppConfig.get()
        if self.has_active_subscription() and self.subscription_plan.price == 0:
            return 0
        return config.annonce_price

    def can_post_free_announce(self):
        config = AppConfig.get()
        return self.free_announces_used < config.free_announces_new_user

    def can_post_monthly_announce(self):
        if self.announces_month_reset < datetime.utcnow() - timedelta(days=30):
            self.announces_month_used = 0
            self.announces_month_reset = datetime.utcnow()
            db.session.commit()
        limit = self.get_monthly_annonce_limit()
        return self.announces_month_used < limit and limit > 0

    def get_level(self):
        if self.level_id:
            return Level.query.get(self.level_id)
        # Auto-assign based on points
        level = Level.query.filter(Level.min_points <= self.points).order_by(Level.min_points.desc()).first()
        if level and self.level_id != level.id:
            self.level_id = level.id
            db.session.commit()
        return level

    def get_badges_list(self):
        return Badge.query.join(UserBadge).filter(UserBadge.user_id == self.id).all()


class Service(db.Model):
    __tablename__ = 'services'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    city = db.Column(db.String(50), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    image = db.Column(db.String(200), default='default-service.jpg')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    address = db.Column(db.String(300), nullable=True)
    views_count = db.Column(db.Integer, default=0)
    is_urgent = db.Column(db.Boolean, default=False)
    urgency_multiplier = db.Column(db.Float, default=1.0)
    bookings = db.relationship('Booking', backref='service', lazy=True, cascade='all, delete-orphan')
    images = db.relationship('ServiceImage', backref='service', lazy=True, cascade='all, delete-orphan')


class ServiceImage(db.Model):
    __tablename__ = 'service_images'
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PortfolioItem(db.Model):
    __tablename__ = 'portfolio_items'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    filename = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    commission_amount = db.Column(db.Float, default=0)
    commission_paid = db.Column(db.Boolean, default=False)
    insurance_used = db.Column(db.Boolean, default=False)
    devis_id = db.Column(db.Integer, db.ForeignKey('devis.id'), nullable=True)


class Commission(db.Model):
    __tablename__ = 'commissions'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    rate_percent = db.Column(db.Float, default=10.0)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


class Devis(db.Model):
    __tablename__ = 'devis'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client_name = db.Column(db.String(100), nullable=False)
    client_email = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    items = db.Column(db.Text, nullable=False)
    total_ht = db.Column(db.Float, nullable=False)
    tva_rate = db.Column(db.Float, default=20.0)
    total_ttc = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=True)
    bookings = db.relationship('Booking', backref='devis_ref', lazy=True)


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    link = db.Column(db.String(300), nullable=True)


class Annonce(db.Model):
    __tablename__ = 'annonces'
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(30), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    price = db.Column(db.Float, nullable=True)
    is_paid = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=True)
    image = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    views_count = db.Column(db.Integer, default=0)


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='MAD')
    type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')
    reference = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)


class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    annonce_limit = db.Column(db.Integer, default=0)
    features = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    target_type = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscribers = db.relationship('User', backref='subscription_plan', lazy=True)


class AppConfig(db.Model):
    __tablename__ = 'app_config'
    id = db.Column(db.Integer, primary_key=True)
    annonce_price = db.Column(db.Float, default=20.0)
    free_announces_new_user = db.Column(db.Integer, default=5)
    annonce_duration_days = db.Column(db.Integer, default=30)
    contact_email = db.Column(db.String(120), default='info@lmawqef.ma')
    contact_phone = db.Column(db.String(20), default='+212 5XX-XXXXXX')
    commission_rate = db.Column(db.Float, default=10.0)
    insurance_price = db.Column(db.Float, default=50.0)
    featured_profile_price = db.Column(db.Float, default=100.0)
    urgency_multiplier = db.Column(db.Float, default=1.5)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def get():
        config = AppConfig.query.first()
        if not config:
            config = AppConfig()
            db.session.add(config)
            db.session.commit()
        return config


class ContactMessage(db.Model):
    __tablename__ = 'contact_messages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)


class AdminRole(db.Model):
    __tablename__ = 'admin_roles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    can_manage_users = db.Column(db.Boolean, default=True)
    can_manage_services = db.Column(db.Boolean, default=True)
    can_manage_bookings = db.Column(db.Boolean, default=True)
    can_manage_annonces = db.Column(db.Boolean, default=True)
    can_manage_subscriptions = db.Column(db.Boolean, default=True)
    can_manage_payments = db.Column(db.Boolean, default=True)
    can_manage_admins = db.Column(db.Boolean, default=False)
    can_edit_config = db.Column(db.Boolean, default=False)
    can_view_analytics = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='admin_role')


# ==================== GAMIFICATION ====================

class Level(db.Model):
    __tablename__ = 'levels'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    min_points = db.Column(db.Integer, nullable=False)
    max_points = db.Column(db.Integer, nullable=True)
    icon = db.Column(db.String(50), default='fa-star')
    color = db.Column(db.String(20), default='#0d9488')
    benefits = db.Column(db.Text, nullable=True)


class Badge(db.Model):
    __tablename__ = 'badges'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(50), default='fa-award')
    color = db.Column(db.String(20), default='#f59e0b')
    condition_type = db.Column(db.String(50), nullable=False)
    condition_value = db.Column(db.Integer, nullable=False)
    points_reward = db.Column(db.Integer, default=0)


class UserBadge(db.Model):
    __tablename__ = 'user_badges'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    badge = db.relationship('Badge', backref='earned_by')


class Availability(db.Model):
    __tablename__ = 'availability'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    is_available = db.Column(db.Boolean, default=True)


# ==================== CATEGORIES & CITIES ====================

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

CATEGORIES = [
    'IT & Technology', 'Construction & Renovation', 'Cleaning & Housekeeping',
    'Transport & Logistics', 'Plumbing & Electrical', 'Carpentry & Woodwork',
    'Painting & Decoration', 'Gardening & Landscaping', 'Automotive & Mechanics',
    'Education & Tutoring', 'Health & Wellness', 'Photography & Events',
    'Legal & Accounting', 'Marketing & Design', 'Urgent Services', 'Other'
]

MOROCCAN_CITIES = [
    'Casablanca', 'Rabat', 'Marrakech', 'Fes', 'Tangier',
    'Agadir', 'Oujda', 'Kenitra', 'Tetouan', 'Safi',
    'El Jadida', 'Nador', 'Khouribga', 'Beni Mellal', 'Mohammedia',
    'Laayoune', 'Dakhla', 'Essaouira', 'Taza', 'Settat',
    'Berrechid', 'Khemisset', 'Ouarzazate', 'Al Hoceima', 'Errachidia'
]

ANNONCE_TYPES = [
    ('recrutement', 'Recrutement de profils'),
    ('demande_service', 'Demande de service'),
    ('offre_service', 'Offre de service')
]

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# ==================== HELPERS ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, folder):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], folder, filename)
        file.save(filepath)
        return f"uploads/{folder}/{filename}"
    return None

def generate_reference():
    return 'LMQ' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

def check_and_award_badges(user):
    """Check all badges and award if conditions met"""
    all_badges = Badge.query.all()
    for badge in all_badges:
        already_has = UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first()
        if already_has:
            continue
        earned = False
        if badge.condition_type == 'bookings_count':
            count = Booking.query.join(Service).filter(Service.worker_id == user.id).count()
            if count >= badge.condition_value:
                earned = True
        elif badge.condition_type == 'reviews_count':
            count = Review.query.filter_by(worker_id=user.id).count()
            if count >= badge.condition_value:
                earned = True
        elif badge.condition_type == 'rating':
            avg = user.average_rating()
            if avg >= badge.condition_value:
                earned = True
        elif badge.condition_type == 'services_count':
            count = Service.query.filter_by(worker_id=user.id).count()
            if count >= badge.condition_value:
                earned = True
        elif badge.condition_type == 'points':
            if user.points >= badge.condition_value:
                earned = True
        elif badge.condition_type == 'response_time':
            if user.response_time_avg > 0 and user.response_time_avg <= badge.condition_value:
                earned = True

        if earned:
            ub = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(ub)
            user.points += badge.points_reward
            db.session.commit()
            # Notify user
            notif = Notification(
                user_id=user.id,
                title=f'Badge debloque: {badge.name}!',
                message=f'Felicitations! Vous avez gagne le badge "{badge.name}" (+{badge.points_reward} points)',
                type='success',
                link='/my-profile'
            )
            db.session.add(notif)
            db.session.commit()

# ==================== DECORATORS ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def worker_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if user.user_type not in ['worker', 'entreprise']:
            flash('Only workers.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user.is_admin:
            flash('Admin required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== CONTEXT PROCESSORS ====================

@app.context_processor
def inject_globals():
    user = None
    unread_notifications = 0
    unread_messages = 0
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        unread_notifications = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
        unread_messages = Message.query.filter_by(receiver_id=session['user_id'], is_read=False).count()
    return {
        'categories': CATEGORIES,
        'cities': MOROCCAN_CITIES,
        'annonce_types': ANNONCE_TYPES,
        'now': datetime.utcnow(),
        'current_user': user,
        'unread_notifications': unread_notifications,
        'unread_messages': unread_messages
    }

# ==================== MAIN ROUTES ====================

@app.route('/')
def index():
    featured_services = Service.query.filter_by(is_active=True).order_by(Service.created_at.desc()).limit(6).all()
    featured_workers = User.query.filter_by(is_featured=True, is_active=True).filter(User.user_type.in_(['worker','entreprise'])).limit(4).all()
    top_workers = User.query.filter(User.user_type.in_(['worker','entreprise'])).all()
    top_workers = sorted(top_workers, key=lambda w: w.average_rating(), reverse=True)[:4]
    urgent_services = Service.query.filter_by(is_urgent=True, is_active=True).limit(3).all()
    stats = {
        'workers': User.query.filter(User.user_type.in_(['worker','entreprise'])).count(),
        'clients': User.query.filter_by(user_type='client').count(),
        'services': Service.query.filter_by(is_active=True).count(),
        'bookings': Booking.query.count(),
        'annonces': Annonce.query.filter_by(is_active=True).count(),
        'entreprises': User.query.filter_by(user_type='entreprise').count()
    }
    return render_template('index.html', featured_services=featured_services, top_workers=top_workers,
                         featured_workers=featured_workers, urgent_services=urgent_services, stats=stats)

@app.route('/services')
def services():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    city = request.args.get('city', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    is_urgent = request.args.get('urgent', '')
    query = Service.query.filter_by(is_active=True)
    if search:
        query = query.filter(db.or_(Service.title.contains(search), Service.description.contains(search)))
    if category: query = query.filter_by(category=category)
    if city: query = query.filter_by(city=city)
    if min_price is not None: query = query.filter(Service.price >= min_price)
    if max_price is not None: query = query.filter(Service.price <= max_price)
    if is_urgent: query = query.filter_by(is_urgent=True)
    services = query.order_by(Service.created_at.desc()).paginate(page=page, per_page=12, error_out=False)
    return render_template('services.html', services=services, search=search, category=category, city=city,
                         min_price=min_price, max_price=max_price, is_urgent=is_urgent)

@app.route('/service/<int:id>')
def service_detail(id):
    service = Service.query.get_or_404(id)
    service.views_count += 1
    db.session.commit()
    reviews = Review.query.filter_by(worker_id=service.worker_id).order_by(Review.created_at.desc()).all()
    related = Service.query.filter(Service.category == service.category, Service.id != service.id).limit(4).all()
    has_booked = False
    if 'user_id' in session:
        has_booked = Booking.query.filter_by(client_id=session['user_id'], service_id=service.id).first() is not None
    return render_template('service_detail.html', service=service, reviews=reviews,
                         related_services=related, has_booked=has_booked)

@app.route('/service/add', methods=['GET', 'POST'])
@login_required
def add_service():
    user = User.query.get(session['user_id'])
    if user.user_type not in ['worker', 'entreprise']:
        flash('Only workers.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category')
        description = request.form.get('description')
        price = request.form.get('price')
        city = request.form.get('city')
        address = request.form.get('address')
        is_urgent = request.form.get('is_urgent') == 'on'
        if not all([title, category, description, price, city]):
            flash('All required.', 'danger')
            return redirect(url_for('add_service'))
        try: price = float(price)
        except ValueError:
            flash('Invalid price.', 'danger')
            return redirect(url_for('add_service'))
        config = AppConfig.get()
        final_price = price * config.urgency_multiplier if is_urgent else price
        service = Service(title=title, category=category, description=description,
                        price=final_price, city=city, worker_id=session['user_id'],
                        address=address, is_urgent=is_urgent)
        db.session.add(service)
        db.session.flush()
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                if file and file.filename:
                    img_path = save_uploaded_file(file, 'services')
                    if img_path:
                        db.session.add(ServiceImage(service_id=service.id, filename=img_path))
        if 'main_image' in request.files:
            file = request.files['main_image']
            if file and file.filename:
                img_path = save_uploaded_file(file, 'services')
                if img_path: service.image = img_path
        db.session.commit()
        flash('Service added!', 'success')
        return redirect(url_for('my_services'))
    return render_template('add_service.html')

@app.route('/service/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_service(id):
    service = Service.query.get_or_404(id)
    if service.worker_id != session['user_id']:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('my_services'))
    if request.method == 'POST':
        service.title = request.form.get('title')
        service.category = request.form.get('category')
        service.description = request.form.get('description')
        service.price = float(request.form.get('price'))
        service.city = request.form.get('city')
        service.address = request.form.get('address')
        service.is_active = request.form.get('is_active') == 'on'
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                if file and file.filename:
                    img_path = save_uploaded_file(file, 'services')
                    if img_path:
                        db.session.add(ServiceImage(service_id=service.id, filename=img_path))
        db.session.commit()
        flash('Updated!', 'success')
        return redirect(url_for('my_services'))
    return render_template('edit_service.html', service=service)

@app.route('/service/delete/<int:id>', methods=['POST'])
@login_required
def delete_service(id):
    service = Service.query.get_or_404(id)
    if service.worker_id != session['user_id']:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('my_services'))
    db.session.delete(service)
    db.session.commit()
    flash('Deleted.', 'success')
    return redirect(url_for('my_services'))

@app.route('/my-services')
@login_required
def my_services():
    user = User.query.get(session['user_id'])
    if user.user_type not in ['worker', 'entreprise']:
        flash('Only workers.', 'danger')
        return redirect(url_for('index'))
    services = Service.query.filter_by(worker_id=session['user_id']).order_by(Service.created_at.desc()).all()
    return render_template('my_services.html', services=services)

@app.route('/book-service/<int:service_id>', methods=['POST'])
@login_required
def book_service(service_id):
    service = Service.query.get_or_404(service_id)
    user = User.query.get(session['user_id'])
    if user.user_type not in ['client']:
        flash('Only clients.', 'danger')
        return redirect(url_for('service_detail', id=service_id))
    message = request.form.get('message')
    insurance = request.form.get('insurance') == 'on'
    if not message:
        flash('Message required.', 'danger')
        return redirect(url_for('service_detail', id=service_id))
    # Commission calculation
    config = AppConfig.get()
    commission = service.price * (config.commission_rate / 100)
    booking = Booking(client_id=session['user_id'], service_id=service_id, message=message,
                     commission_amount=commission, insurance_used=insurance)
    db.session.add(booking)
    db.session.flush()
    db.session.add(Commission(worker_id=service.worker_id, booking_id=booking.id, amount=commission,
                             rate_percent=config.commission_rate))
    # Points for booking
    user.points += 10
    worker = User.query.get(service.worker_id)
    worker.points += 20
    # Notify worker
    notif = Notification(user_id=service.worker_id, title='Nouvelle reservation',
                        message=f'{user.full_name} a reserve "{service.title}"',
                        type='booking', link='/my-bookings')
    db.session.add(notif)
    db.session.commit()
    check_and_award_badges(worker)
    flash('Booking sent!', 'success')
    return redirect(url_for('service_detail', id=service_id))

@app.route('/my-bookings')
@login_required
def my_bookings():
    user = User.query.get(session['user_id'])
    if user.user_type == 'client':
        bookings = Booking.query.filter_by(client_id=session['user_id']).order_by(Booking.created_at.desc()).all()
    else:
        bookings = Booking.query.join(Service).filter(Service.worker_id == session['user_id']).order_by(Booking.created_at.desc()).all()
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/booking/update/<int:id>', methods=['POST'])
@login_required
def update_booking(id):
    booking = Booking.query.get_or_404(id)
    service = Service.query.get(booking.service_id)
    if service.worker_id != session['user_id']:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('my_bookings'))
    status = request.form.get('status')
    if status in ['accepted', 'rejected', 'completed']:
        booking.status = status
        booking.updated_at = datetime.utcnow()
        if status == 'completed':
            commission = Commission.query.filter_by(booking_id=booking.id).first()
            if commission: commission.status = 'due'
            worker = User.query.get(session['user_id'])
            worker.points += 50
            check_and_award_badges(worker)
        notif = Notification(user_id=booking.client_id, title='Reservation mise a jour',
                            message=f'Votre reservation est {status}', type='success', link='/my-bookings')
        db.session.add(notif)
        db.session.commit()
        flash(f'Booking {status}!', 'success')
    return redirect(url_for('my_bookings'))

@app.route('/review/<int:worker_id>', methods=['POST'])
@login_required
def add_review(worker_id):
    user = User.query.get(session['user_id'])
    if user.user_type != 'client':
        flash('Only clients.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment')
    if not rating or not comment or rating < 1 or rating > 5:
        flash('Valid rating required.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    has_booked = Booking.query.join(Service).filter(Booking.client_id == session['user_id'],
                                                    Service.worker_id == worker_id).first()
    if not has_booked:
        flash('Book first.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    existing = Review.query.filter_by(client_id=session['user_id'], worker_id=worker_id).first()
    if existing:
        flash('Already reviewed.', 'danger')
        return redirect(url_for('profile', id=worker_id))
    review = Review(rating=rating, comment=comment, client_id=session['user_id'], worker_id=worker_id)
    db.session.add(review)
    worker = User.query.get(worker_id)
    worker.points += 30
    notif = Notification(user_id=worker_id, title='Nouvel avis',
                        message=f'{user.full_name}: {rating} etoiles', type='success',
                        link=f'/profile/{worker_id}')
    db.session.add(notif)
    db.session.commit()
    check_and_award_badges(worker)
    flash('Review added!', 'success')
    return redirect(url_for('profile', id=worker_id))

@app.route('/profile/<int:id>')
def profile(id):
    user = User.query.get_or_404(id)
    services = Service.query.filter_by(worker_id=id, is_active=True).all() if user.user_type in ['worker','entreprise'] else []
    reviews = Review.query.filter_by(worker_id=id).order_by(Review.created_at.desc()).all()
    portfolio = PortfolioItem.query.filter_by(user_id=id).order_by(PortfolioItem.created_at.desc()).all()
    badges = user.get_badges_list()
    level = user.get_level()
    has_booked = False
    if 'user_id' in session and session['user_id'] != id:
        has_booked = Booking.query.join(Service).filter(Booking.client_id == session['user_id'],
                                                        Service.worker_id == id).first() is not None
    return render_template('profile.html', user=user, services=services, reviews=reviews,
                         portfolio=portfolio, badges=badges, level=level, has_booked=has_booked)

@app.route('/my-profile', methods=['GET', 'POST'])
@login_required
def my_profile():
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        user.full_name = request.form.get('full_name')
        user.phone = request.form.get('phone')
        user.city = request.form.get('city')
        user.description = request.form.get('description')
        user.address = request.form.get('address')
        user.company_name = request.form.get('company_name')
        if user.user_type in ['worker', 'entreprise']:
            user.skills = request.form.get('skills')
            user.rc_number = request.form.get('rc_number')
            user.ice_number = request.form.get('ice_number')
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                img_path = save_uploaded_file(file, 'profiles')
                if img_path: user.avatar = img_path
        if 'portfolio_files' in request.files:
            files = request.files.getlist('portfolio_files')
            for file in files:
                if file and file.filename:
                    img_path = save_uploaded_file(file, 'portfolio')
                    if img_path:
                        db.session.add(PortfolioItem(user_id=user.id,
                            title=request.form.get('portfolio_title', 'Portfolio'), filename=img_path))
        lat = request.form.get('latitude')
        lng = request.form.get('longitude')
        if lat and lng:
            try:
                user.latitude = float(lat)
                user.longitude = float(lng)
            except ValueError: pass
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('my_profile'))
    portfolio = PortfolioItem.query.filter_by(user_id=user.id).order_by(PortfolioItem.created_at.desc()).all()
    badges = user.get_badges_list()
    level = user.get_level()
    availability = Availability.query.filter_by(user_id=user.id).all()
    return render_template('my_profile.html', user=user, portfolio=portfolio, badges=badges,
                         level=level, availability=availability)

@app.route('/portfolio/delete/<int:id>', methods=['POST'])
@login_required
def delete_portfolio(id):
    item = PortfolioItem.query.get_or_404(id)
    if item.user_id != session['user_id']:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('my_profile'))
    db.session.delete(item)
    db.session.commit()
    flash('Removed.', 'success')
    return redirect(url_for('my_profile'))

@app.route('/workers')
def workers():
    page = request.args.get('page', 1, type=int)
    city = request.args.get('city', '')
    skill = request.args.get('skill', '')
    user_type = request.args.get('user_type', '')
    query = User.query.filter(User.user_type.in_(['worker', 'entreprise']), User.is_active == True)
    if city: query = query.filter_by(city=city)
    if skill: query = query.filter(User.skills.contains(skill))
    if user_type: query = query.filter_by(user_type=user_type)
    workers = query.order_by(User.points.desc()).paginate(page=page, per_page=12, error_out=False)
    return render_template('workers.html', workers=workers, city=city, skill=skill, user_type=user_type)

@app.route('/leaderboard')
def leaderboard():
    top_workers = User.query.filter(User.user_type.in_(['worker','entreprise'])).order_by(User.points.desc()).limit(20).all()
    return render_template('leaderboard.html', top_workers=top_workers)

@app.route('/featured')
def featured_profiles():
    featured = User.query.filter_by(is_featured=True, is_active=True).filter(
        User.user_type.in_(['worker','entreprise'])).order_by(User.featured_until.desc()).limit(12).all()
    return render_template('featured.html', featured=featured)

# ==================== AUTH ROUTES ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        city = request.form.get('city')
        user_type = request.form.get('user_type')
        if not all([username, email, password, confirm, full_name, phone, city, user_type]):
            flash('All fields required.', 'danger')
            return redirect(url_for('register'))
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Username exists.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email exists.', 'danger')
            return redirect(url_for('register'))
        user = User(username=username, email=email, password_hash=generate_password_hash(password),
                   full_name=full_name, phone=phone, city=city, user_type=user_type,
                   skills=request.form.get('skills', '') if user_type in ['worker', 'entreprise'] else None,
                   description=request.form.get('description', ''),
                   company_name=request.form.get('company_name', '') if user_type == 'entreprise' else None,
                   rc_number=request.form.get('rc_number', '') if user_type == 'entreprise' else None,
                   ice_number=request.form.get('ice_number', '') if user_type == 'entreprise' else None,
                   worker_subtype=request.form.get('worker_subtype') if user_type == 'worker' else None)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Account deactivated.', 'danger')
                return redirect(url_for('login'))
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_type'] = user.user_type
            flash(f'Welcome back, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            if next_page: return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

# ==================== DASHBOARD ROUTES ====================

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    if user.user_type == 'entreprise':
        return redirect(url_for('dashboard_entreprise'))
    elif user.user_type == 'worker':
        return redirect(url_for('dashboard_worker'))
    else:
        return redirect(url_for('dashboard_client'))

@app.route('/dashboard/worker')
@login_required
def dashboard_worker():
    user = User.query.get(session['user_id'])
    if user.user_type not in ['worker', 'entreprise']:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    total_services = Service.query.filter_by(worker_id=user.id).count()
    active_services = Service.query.filter_by(worker_id=user.id, is_active=True).count()
    total_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id).count()
    pending_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id, Booking.status == 'pending').count()
    completed_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id, Booking.status == 'completed').count()
    avg_rating = user.average_rating()
    total_reviews = user.review_count()
    total_views = db.session.query(db.func.sum(Service.views_count)).filter_by(worker_id=user.id).scalar() or 0
    # Monthly stats
    current_month = datetime.utcnow().month
    monthly_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id,
        db.extract('month', Booking.created_at) == current_month).count()
    # Commission stats
    total_commissions = db.session.query(db.func.sum(Commission.amount)).filter_by(worker_id=user.id).scalar() or 0
    pending_commissions = db.session.query(db.func.sum(Commission.amount)).filter_by(worker_id=user.id, status='pending').scalar() or 0
    # Revenue
    total_revenue = db.session.query(db.func.sum(Booking.commission_amount)).join(Service).filter(
        Service.worker_id == user.id, Booking.status == 'completed').scalar() or 0
    recent_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id).order_by(Booking.created_at.desc()).limit(5).all()
    subscription = user.subscription_plan if user.has_active_subscription() else None
    badges = user.get_badges_list()
    level = user.get_level()
    stats = {
        'total_services': total_services, 'active_services': active_services,
        'total_bookings': total_bookings, 'pending_bookings': pending_bookings,
        'completed_bookings': completed_bookings, 'avg_rating': avg_rating,
        'total_reviews': total_reviews, 'total_views': total_views,
        'monthly_bookings': monthly_bookings, 'total_commissions': total_commissions,
        'pending_commissions': pending_commissions, 'total_revenue': total_revenue,
        'points': user.points
    }
    return render_template('dashboard_worker.html', stats=stats, recent_bookings=recent_bookings,
                         subscription=subscription, user=user, badges=badges, level=level)

@app.route('/dashboard/client')
@login_required
def dashboard_client():
    user = User.query.get(session['user_id'])
    if user.user_type != 'client':
        return redirect(url_for('dashboard'))
    total_bookings = Booking.query.filter_by(client_id=user.id).count()
    pending_bookings = Booking.query.filter_by(client_id=user.id, status='pending').count()
    completed_bookings = Booking.query.filter_by(client_id=user.id, status='completed').count()
    total_reviews = Review.query.filter_by(client_id=user.id).count()
    recent_bookings = Booking.query.filter_by(client_id=user.id).order_by(Booking.created_at.desc()).limit(5).all()
    stats = {'total_bookings': total_bookings, 'pending_bookings': pending_bookings,
             'completed_bookings': completed_bookings, 'total_reviews': total_reviews}
    return render_template('dashboard_client.html', stats=stats, recent_bookings=recent_bookings)

@app.route('/dashboard/entreprise')
@login_required
def dashboard_entreprise():
    user = User.query.get(session['user_id'])
    if user.user_type != 'entreprise':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    total_services = Service.query.filter_by(worker_id=user.id).count()
    total_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id).count()
    pending_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id, Booking.status == 'pending').count()
    avg_rating = user.average_rating()
    recent_bookings = Booking.query.join(Service).filter(Service.worker_id == user.id).order_by(Booking.created_at.desc()).limit(5).all()
    subscription = user.subscription_plan if user.has_active_subscription() else None
    badges = user.get_badges_list()
    level = user.get_level()
    stats = {'total_services': total_services, 'total_bookings': total_bookings,
             'pending_bookings': pending_bookings, 'avg_rating': avg_rating, 'total_reviews': user.review_count()}
    return render_template('dashboard_entreprise.html', stats=stats, recent_bookings=recent_bookings,
                         subscription=subscription, user=user, badges=badges, level=level)

# ==================== CHAT ROUTES ====================

@app.route('/messages')
@login_required
def messages():
    user = User.query.get(session['user_id'])
    sent = Message.query.filter_by(sender_id=user.id).all()
    received = Message.query.filter_by(receiver_id=user.id).all()
    conversation_ids = set()
    for m in sent: conversation_ids.add(m.receiver_id)
    for m in received: conversation_ids.add(m.sender_id)
    conversations = []
    for uid in conversation_ids:
        other = User.query.get(uid)
        if other:
            last_msg = Message.query.filter(
                db.or_(
                    db.and_(Message.sender_id == user.id, Message.receiver_id == uid),
                    db.and_(Message.sender_id == uid, Message.receiver_id == user.id)
                )
            ).order_by(Message.created_at.desc()).first()
            unread = Message.query.filter_by(sender_id=uid, receiver_id=user.id, is_read=False).count()
            conversations.append({'user': other, 'last_message': last_msg, 'unread': unread})
    conversations.sort(key=lambda x: x['last_message'].created_at if x['last_message'] else datetime.min, reverse=True)
    selected_id = request.args.get('with', type=int)
    selected_user = User.query.get(selected_id) if selected_id else None
    messages_list = []
    if selected_user:
        messages_list = Message.query.filter(
            db.or_(
                db.and_(Message.sender_id == user.id, Message.receiver_id == selected_id),
                db.and_(Message.sender_id == selected_id, Message.receiver_id == user.id)
            )
        ).order_by(Message.created_at.asc()).all()
        for msg in messages_list:
            if msg.receiver_id == user.id and not msg.is_read:
                msg.is_read = True
        db.session.commit()
    return render_template('messages.html', conversations=conversations, selected_user=selected_user,
                         messages_list=messages_list)

@app.route('/messages/send', methods=['POST'])
@login_required
def send_message():
    receiver_id = request.form.get('receiver_id', type=int)
    content = request.form.get('content')
    if not receiver_id or not content:
        return jsonify({'success': False, 'error': 'Missing data'})
    receiver = User.query.get(receiver_id)
    if not receiver:
        return jsonify({'success': False, 'error': 'User not found'})
    msg = Message(sender_id=session['user_id'], receiver_id=receiver_id, content=content)
    db.session.add(msg)
    sender = User.query.get(session['user_id'])
    notif = Notification(user_id=receiver_id, title='Nouveau message',
                        message=f'{sender.full_name}: {content[:50]}...',
                        type='message', link='/messages?with=' + str(session['user_id']))
    db.session.add(notif)
    db.session.commit()
    return jsonify({'success': True, 'message': {
        'id': msg.id, 'content': msg.content,
        'created_at': msg.created_at.strftime('%H:%M'), 'is_sender': True
    }})

@app.route('/api/messages/poll')
@login_required
def poll_messages():
    with_id = request.args.get('with', type=int)
    last_id = request.args.get('last_id', 0, type=int)
    if not with_id:
        return jsonify({'messages': []})
    messages = Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == session['user_id'], Message.receiver_id == with_id),
            db.and_(Message.sender_id == with_id, Message.receiver_id == session['user_id'])
        ), Message.id > last_id
    ).order_by(Message.created_at.asc()).all()
    for msg in messages:
        if msg.receiver_id == session['user_id']:
            msg.is_read = True
    db.session.commit()
    return jsonify({'messages': [{
        'id': m.id, 'content': m.content,
        'created_at': m.created_at.strftime('%H:%M'),
        'is_sender': m.sender_id == session['user_id']
    } for m in messages]})

# ==================== NOTIFICATIONS ====================

@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=session['user_id']).order_by(Notification.created_at.desc()).all()
    for n in notifs:
        if not n.is_read:
            n.is_read = True
    db.session.commit()
    return render_template('notifications.html', notifications=notifs)

@app.route('/notification/delete/<int:id>', methods=['POST'])
@login_required
def delete_notification(id):
    notif = Notification.query.get_or_404(id)
    if notif.user_id != session['user_id']:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('notifications'))
    db.session.delete(notif)
    db.session.commit()
    flash('Deleted.', 'success')
    return redirect(url_for('notifications'))

# ==================== DEVIS / QUOTE SYSTEM ====================

@app.route('/devis/create', methods=['GET', 'POST'])
@login_required
def create_devis():
    user = User.query.get(session['user_id'])
    if user.user_type not in ['worker', 'entreprise']:
        flash('Only workers.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        client_name = request.form.get('client_name')
        client_email = request.form.get('client_email')
        title = request.form.get('title')
        description = request.form.get('description')
        items_json = request.form.get('items')
        total_ht = float(request.form.get('total_ht', 0))
        tva_rate = float(request.form.get('tva_rate', 20))
        total_ttc = total_ht * (1 + tva_rate / 100)
        valid_days = int(request.form.get('valid_days', 30))
        devis = Devis(
            worker_id=user.id, client_name=client_name, client_email=client_email,
            title=title, description=description, items=items_json,
            total_ht=total_ht, tva_rate=tva_rate, total_ttc=total_ttc,
            valid_until=datetime.utcnow() + timedelta(days=valid_days)
        )
        db.session.add(devis)
        db.session.commit()
        flash('Devis created!', 'success')
        return redirect(url_for('my_devis'))
    return render_template('create_devis.html')

@app.route('/my-devis')
@login_required
def my_devis():
    user = User.query.get(session['user_id'])
    if user.user_type not in ['worker', 'entreprise']:
        flash('Only workers.', 'danger')
        return redirect(url_for('index'))
    devis_list = Devis.query.filter_by(worker_id=user.id).order_by(Devis.created_at.desc()).all()
    return render_template('my_devis.html', devis_list=devis_list)

@app.route('/devis/<int:id>/pdf')
@login_required
def devis_pdf(id):
    devis = Devis.query.get_or_404(id)
    if devis.worker_id != session['user_id']:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('my_devis'))
    items = json.loads(devis.items) if devis.items else []
    return render_template('devis_pdf.html', devis=devis, items=items)

# ==================== ANNONCES ====================

@app.route('/annonces')
def annonces():
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '')
    category = request.args.get('category', '')
    city = request.args.get('city', '')
    query = Annonce.query.filter_by(is_active=True)
    query = query.filter(Annonce.expires_at > datetime.utcnow()) if True else query
    if type_filter: query = query.filter_by(type=type_filter)
    if category: query = query.filter_by(category=category)
    if city: query = query.filter_by(city=city)
    annonces = query.order_by(Annonce.created_at.desc()).paginate(page=page, per_page=12, error_out=False)
    return render_template('annonces.html', annonces=annonces, type_filter=type_filter,
                         category=category, city=city)

@app.route('/annonce/<int:id>')
def annonce_detail(id):
    annonce = Annonce.query.get_or_404(id)
    annonce.views_count += 1
    db.session.commit()
    return render_template('annonce_detail.html', annonce=annonce)

@app.route('/annonce/add', methods=['GET', 'POST'])
@login_required
def add_annonce():
    user = User.query.get(session['user_id'])
    config = AppConfig.get()
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        type_a = request.form.get('type')
        category = request.form.get('category')
        city = request.form.get('city')
        price = request.form.get('price')
        if not all([title, description, type_a]):
            flash('Required fields missing.', 'danger')
            return redirect(url_for('add_annonce'))
        can_free = user.can_post_free_announce()
        can_monthly = user.can_post_monthly_announce()
        price_float = float(price) if price else None
        announce_price = user.get_announce_price()
        needs_payment = announce_price > 0 and not can_free and not can_monthly
        annonce = Annonce(
            author_id=user.id, title=title, description=description, type=type_a,
            category=category, city=city, price=price_float,
            expires_at=datetime.utcnow() + timedelta(days=config.annonce_duration_days)
        )
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                img_path = save_uploaded_file(file, 'annonces')
                if img_path: annonce.image = img_path
        if not needs_payment:
            annonce.is_paid = True
            if can_free: user.free_announces_used += 1
            elif can_monthly: user.announces_month_used += 1
        db.session.add(annonce)
        db.session.flush()
        if needs_payment:
            db.session.commit()
            return redirect(url_for('payment_annonce', annonce_id=annonce.id))
        db.session.commit()
        user.points += 5
        check_and_award_badges(user)
        flash('Annonce published!', 'success')
        return redirect(url_for('annonces'))
    return render_template('add_annonce.html', user=user, config=config)

@app.route('/payment/annonce/<int:annonce_id>')
@login_required
def payment_annonce(annonce_id):
    annonce = Annonce.query.get_or_404(annonce_id)
    if annonce.author_id != session['user_id']:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('annonces'))
    config = AppConfig.get()
    return render_template('payment.html', annonce=annonce, amount=config.annonce_price, type='annonce')

@app.route('/payment/process', methods=['POST'])
@login_required
def process_payment():
    payment_type = request.form.get('type')
    annonce_id = request.form.get('annonce_id', type=int)
    plan_id = request.form.get('plan_id', type=int)
    insurance = request.form.get('insurance') == 'on'
    user = User.query.get(session['user_id'])
    if payment_type == 'annonce' and annonce_id:
        annonce = Annonce.query.get_or_404(annonce_id)
        config = AppConfig.get()
        amount = config.annonce_price
        ref = generate_reference()
        payment = Payment(user_id=user.id, amount=amount, type='annonce', reference=ref,
                          description=f'Annonce: {annonce.title}')
        db.session.add(payment)
        db.session.flush()
        payment.status = 'completed'
        payment.completed_at = datetime.utcnow()
        annonce.is_paid = True
        annonce.payment_id = payment.id
        db.session.commit()
        flash('Payment successful! Annonce online.', 'success')
        return redirect(url_for('annonce_detail', id=annonce_id))
    elif payment_type == 'abonnement' and plan_id:
        plan = SubscriptionPlan.query.get_or_404(plan_id)
        ref = generate_reference()
        payment = Payment(user_id=user.id, amount=plan.price, type='abonnement', reference=ref,
                          description=f'Abonnement {plan.name}')
        db.session.add(payment)
        db.session.flush()
        payment.status = 'completed'
        payment.completed_at = datetime.utcnow()
        user.subscription_plan_id = plan.id
        user.subscription_active = True
        user.subscription_start = datetime.utcnow()
        user.subscription_end = datetime.utcnow() + timedelta(days=plan.duration_days)
        user.announces_month_used = 0
        user.announces_month_reset = datetime.utcnow()
        db.session.commit()
        flash(f'Abonnement {plan.name} active!', 'success')
        return redirect(url_for('dashboard'))
    elif payment_type == 'featured':
        config = AppConfig.get()
        ref = generate_reference()
        payment = Payment(user_id=user.id, amount=config.featured_profile_price, type='featured', reference=ref,
                          description='Featured profile')
        db.session.add(payment)
        db.session.flush()
        payment.status = 'completed'
        payment.completed_at = datetime.utcnow()
        user.is_featured = True
        user.featured_until = datetime.utcnow() + timedelta(days=30)
        db.session.commit()
        flash('Profile featured for 30 days!', 'success')
        return redirect(url_for('my_profile'))
    elif payment_type == 'insurance':
        config = AppConfig.get()
        ref = generate_reference()
        payment = Payment(user_id=user.id, amount=config.insurance_price, type='insurance', reference=ref,
                          description='Lmawqef Protect')
        db.session.add(payment)
        db.session.flush()
        payment.status = 'completed'
        payment.completed_at = datetime.utcnow()
        user.insurance_active = True
        user.insurance_expires = datetime.utcnow() + timedelta(days=30)
        db.session.commit()
        flash('Insurance activated!', 'success')
        return redirect(url_for('dashboard'))
    flash('Invalid payment.', 'danger')
    return redirect(url_for('index'))

# ==================== SUBSCRIPTIONS ====================

@app.route('/abonnements')
def abonnements():
    user = User.query.get(session['user_id']) if 'user_id' in session else None
    if user:
        if user.user_type == 'entreprise':
            plans = SubscriptionPlan.query.filter_by(target_type='entreprise', is_active=True).all()
        elif user.user_type == 'worker':
            if user.worker_subtype == 'freelance':
                plans = SubscriptionPlan.query.filter(SubscriptionPlan.target_type.in_(['autoentrepreneur','freelance']),
                                                      SubscriptionPlan.is_active == True).all()
            else:
                plans = SubscriptionPlan.query.filter_by(target_type='autoentrepreneur', is_active=True).all()
        else:
            plans = []
    else:
        plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    return render_template('abonnements.html', plans=plans, user=user)

@app.route('/abonnement/subscribe/<int:plan_id>')
@login_required
def subscribe_plan(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    user = User.query.get(session['user_id'])
    if plan.price == 0:
        user.subscription_plan_id = plan.id
        user.subscription_active = True
        user.subscription_start = datetime.utcnow()
        user.subscription_end = datetime.utcnow() + timedelta(days=plan.duration_days)
        db.session.commit()
        flash(f'Abonnement {plan.name} active gratuitement!', 'success')
        return redirect(url_for('dashboard'))
    return redirect(url_for('payment_abonnement', plan_id=plan_id))

@app.route('/payment/abonnement/<int:plan_id>')
@login_required
def payment_abonnement(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    return render_template('payment_abonnement.html', plan=plan)

@app.route('/abonnement/cancel')
@login_required
def cancel_subscription():
    user = User.query.get(session['user_id'])
    user.subscription_active = False
    user.subscription_end = datetime.utcnow()
    db.session.commit()
    flash('Abonnement annule.', 'info')
    return redirect(url_for('dashboard'))

# ==================== FEATURED PROFILE ====================

@app.route('/become-featured')
@login_required
def become_featured():
    user = User.query.get(session['user_id'])
    if user.user_type not in ['worker', 'entreprise']:
        flash('Only workers.', 'danger')
        return redirect(url_for('index'))
    config = AppConfig.get()
    return render_template('become_featured.html', price=config.featured_profile_price)

# ==================== INSURANCE ====================

@app.route('/insurance')
@login_required
def insurance_page():
    user = User.query.get(session['user_id'])
    config = AppConfig.get()
    return render_template('insurance.html', config=config, user=user)

# ==================== URGENCY ====================

@app.route('/urgent-services')
def urgent_services():
    services = Service.query.filter_by(is_urgent=True, is_active=True).order_by(Service.created_at.desc()).all()
    return render_template('urgent_services.html', services=services)

# ==================== AVAILABILITY ====================

@app.route('/availability', methods=['GET', 'POST'])
@login_required
def manage_availability():
    user = User.query.get(session['user_id'])
    if user.user_type not in ['worker', 'entreprise']:
        flash('Only workers.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        Availability.query.filter_by(user_id=user.id).delete()
        for i in range(7):
            start = request.form.get(f'start_{i}')
            end = request.form.get(f'end_{i}')
            avail = request.form.get(f'available_{i}') == 'on'
            if start and end:
                db.session.add(Availability(user_id=user.id, day_of_week=i, start_time=start, end_time=end, is_available=avail))
        db.session.commit()
        flash('Availability updated!', 'success')
        return redirect(url_for('manage_availability'))
    availability = Availability.query.filter_by(user_id=user.id).all()
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return render_template('availability.html', availability=availability, days=days)

# ==================== CHATBOT ====================

@app.route('/api/chatbot', methods=['POST'])
def chatbot_api():
    data = request.get_json()
    message = data.get('message', '').lower()
    responses = {
        'bonjour': 'Bonjour! Comment puis-je vous aider aujourd\'hui?',
        'hello': 'Hello! How can I help you today?',
        'salam': 'Wa alaykoum salam! Comment puis-je vous aider?',
        'service': 'Vous pouvez rechercher des services par categorie, ville ou mot-cle. Utilisez la barre de recherche en haut!',
        'prix': 'Les prix varient selon le service. Chaque worker fixe ses propres tarifs.',
        'paiement': 'Nous acceptons les cartes bancaires (CMI), le paiement mobile (Inwi Money, Orange Money) et le virement bancaire.',
        'abonnement': 'Nos abonnements PRO offrent des annonces illimitees, profil prioritaire et plus de visibilite. Consultez la page Abonnements!',
        'annonce': 'Pour publier une annonce, cliquez sur "Publier une Annonce". La premiere est gratuite, les suivantes coutent 20 MAD.',
        'comment': 'Inscrivez-vous, choisissez votre type de compte (client ou worker), et commencez a utiliser la plateforme!',
        'urgence': 'Pour les services urgents, activez le mode Urgence lors de la creation du service. Le prix sera majore mais vous trouverez un worker plus rapidement.',
    }
    for key, response in responses.items():
        if key in message:
            return jsonify({'response': response, 'success': True})
    return jsonify({'response': 'Je ne comprends pas encore cette question. Essayez: prix, abonnement, comment s\'inscrire ou contactez notre support.', 'success': True})

# ==================== CONTACT & STATIC ====================

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        if not all([name, email, subject, message]):
            flash('All fields required.', 'danger')
            return redirect(url_for('contact'))
        msg = ContactMessage(name=name, email=email, subject=subject, message=message)
        db.session.add(msg)
        db.session.commit()
        flash('Message sent!', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/about')
def about():
    stats = {
        'users': User.query.count(),
        'workers': User.query.filter(User.user_type.in_(['worker','entreprise'])).count(),
        'services': Service.query.filter_by(is_active=True).count(),
        'bookings': Booking.query.count(),
        'annonces': Annonce.query.filter_by(is_active=True).count(),
        'revenue': db.session.query(db.func.sum(Payment.amount)).filter_by(status='completed').scalar() or 0
    }
    return render_template('about.html', stats=stats)

@app.route('/categories')
def categories_page():
    category_counts = {}
    for cat in CATEGORIES:
        category_counts[cat] = Service.query.filter_by(category=cat, is_active=True).count()
    return render_template('categories.html', category_counts=category_counts)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ==================== ADMIN PANEL ====================

@app.route('/admin')
@admin_required
def admin_panel():
    config = AppConfig.get()
    stats = {
        'total_users': User.query.count(),
        'total_workers': User.query.filter_by(user_type='worker').count(),
        'total_entreprises': User.query.filter_by(user_type='entreprise').count(),
        'total_clients': User.query.filter_by(user_type='client').count(),
        'total_services': Service.query.count(),
        'total_bookings': Booking.query.count(),
        'total_reviews': Review.query.count(),
        'total_messages': ContactMessage.query.count(),
        'total_annonces': Annonce.query.count(),
        'total_payments': Payment.query.filter_by(status='completed').count(),
        'revenue': db.session.query(db.func.sum(Payment.amount)).filter_by(status='completed').scalar() or 0,
        'active_subscriptions': User.query.filter_by(subscription_active=True).count(),
        'pending_bookings': Booking.query.filter_by(status='pending').count(),
        'total_commissions': db.session.query(db.func.sum(Commission.amount)).scalar() or 0,
        'points_distributed': db.session.query(db.func.sum(User.points)).scalar() or 0,
        'featured_profiles': User.query.filter_by(is_featured=True).count(),
    }
    # Monthly data for charts
    months = []
    bookings_monthly = []
    revenue_monthly = []
    for i in range(6):
        month_date = datetime.utcnow() - timedelta(days=30*i)
        months.insert(0, month_date.strftime('%b'))
        m_num = month_date.month
        b_count = Booking.query.filter(db.extract('month', Booking.created_at) == m_num).count()
        bookings_monthly.insert(0, b_count)
        r_sum = db.session.query(db.func.sum(Payment.amount)).filter(
            db.extract('month', Payment.created_at) == m_num, Payment.status == 'completed').scalar() or 0
        revenue_monthly.insert(0, round(r_sum, 0))
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_services = Service.query.order_by(Service.created_at.desc()).limit(10).all()
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(10).all()
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(10).all()
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template('admin_panel.html', stats=stats, recent_users=recent_users,
                         recent_services=recent_services, recent_bookings=recent_bookings,
                         recent_payments=recent_payments, messages=messages,
                         months=months, bookings_monthly=bookings_monthly, revenue_monthly=revenue_monthly)

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    # User growth by month
    months = []
    users_monthly = []
    for i in range(12):
        d = datetime.utcnow() - timedelta(days=30*i)
        months.insert(0, d.strftime('%b %Y'))
        count = User.query.filter(db.extract('month', User.created_at) == d.month,
                                   db.extract('year', User.created_at) == d.year).count()
        users_monthly.insert(0, count)
    # Top categories
    cat_data = {}
    for cat in CATEGORIES:
        cat_data[cat] = Service.query.filter_by(category=cat).count()
    # Top cities
    city_data = {}
    for city in MOROCCAN_CITIES[:10]:
        city_data[city] = User.query.filter_by(city=city).count()
    return render_template('admin_analytics.html', months=months, users_monthly=users_monthly,
                         cat_data=cat_data, city_data=city_data)

@app.route('/admin/users')
@admin_required
def admin_users():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    user_type = request.args.get('user_type', '')
    query = User.query
    if search:
        query = query.filter(db.or_(User.username.contains(search), User.email.contains(search),
                                     User.full_name.contains(search)))
    if user_type: query = query.filter_by(user_type=user_type)
    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin_users.html', users=users, search=search, user_type=user_type)

@app.route('/admin/user/<int:id>/toggle-active', methods=['POST'])
@admin_required
def toggle_user_active(id):
    user = User.query.get_or_404(id)
    if user.id == session['user_id']:
        flash('Cannot deactivate yourself.', 'danger')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash(f'User {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(id):
    user = User.query.get_or_404(id)
    if user.id == session['user_id']:
        flash('Cannot remove your own admin.', 'danger')
    else:
        user.is_admin = not user.is_admin
        if user.is_admin:
            role = AdminRole.query.filter_by(user_id=user.id).first()
            if not role:
                db.session.add(AdminRole(user_id=user.id))
        db.session.commit()
        flash('Admin status updated.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:id>/delete', methods=['POST'])
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == session['user_id']:
        flash('Cannot delete yourself.', 'danger')
    else:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/services')
@admin_required
def admin_services():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    query = Service.query
    if search:
        query = query.filter(db.or_(Service.title.contains(search), Service.description.contains(search)))
    services = query.order_by(Service.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin_services.html', services=services, search=search)

@app.route('/admin/services/delete/<int:id>', methods=['POST'])
@admin_required
def admin_delete_service(id):
    service = Service.query.get_or_404(id)
    db.session.delete(service)
    db.session.commit()
    flash('Deleted.', 'success')
    return redirect(url_for('admin_services'))

@app.route('/admin/annonces')
@admin_required
def admin_annonces():
    page = request.args.get('page', 1, type=int)
    annonces = Annonce.query.order_by(Annonce.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin_annonces.html', annonces=annonces)

@app.route('/admin/annonces/delete/<int:id>', methods=['POST'])
@admin_required
def admin_delete_annonce(id):
    annonce = Annonce.query.get_or_404(id)
    db.session.delete(annonce)
    db.session.commit()
    flash('Deleted.', 'success')
    return redirect(url_for('admin_annonces'))

@app.route('/admin/subscriptions')
@admin_required
def admin_subscriptions():
    plans = SubscriptionPlan.query.all()
    active_subs = User.query.filter_by(subscription_active=True).all()
    return render_template('admin_subscriptions.html', plans=plans, active_subs=active_subs)

@app.route('/admin/subscription/plan/add', methods=['POST'])
@admin_required
def add_subscription_plan():
    plan = SubscriptionPlan(
        name=request.form.get('name'), slug=request.form.get('slug'),
        description=request.form.get('description'),
        price=float(request.form.get('price', 0)),
        duration_days=int(request.form.get('duration_days', 30)),
        annonce_limit=int(request.form.get('annonce_limit', 0)),
        features=request.form.get('features'),
        target_type=request.form.get('target_type')
    )
    db.session.add(plan)
    db.session.commit()
    flash('Plan added.', 'success')
    return redirect(url_for('admin_subscriptions'))

@app.route('/admin/subscription/plan/edit/<int:id>', methods=['POST'])
@admin_required
def edit_subscription_plan(id):
    plan = SubscriptionPlan.query.get_or_404(id)
    plan.name = request.form.get('name')
    plan.description = request.form.get('description')
    plan.price = float(request.form.get('price', 0))
    plan.duration_days = int(request.form.get('duration_days', 30))
    plan.annonce_limit = int(request.form.get('annonce_limit', 0))
    plan.features = request.form.get('features')
    plan.target_type = request.form.get('target_type')
    plan.is_active = request.form.get('is_active') == 'on'
    db.session.commit()
    flash('Plan updated.', 'success')
    return redirect(url_for('admin_subscriptions'))

@app.route('/admin/payments')
@admin_required
def admin_payments():
    page = request.args.get('page', 1, type=int)
    payments = Payment.query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    total_revenue = db.session.query(db.func.sum(Payment.amount)).filter_by(status='completed').scalar() or 0
    return render_template('admin_payments.html', payments=payments, total_revenue=total_revenue)

@app.route('/admin/commissions')
@admin_required
def admin_commissions():
    commissions = Commission.query.order_by(Commission.created_at.desc()).all()
    total_pending = db.session.query(db.func.sum(Commission.amount)).filter_by(status='pending').scalar() or 0
    total_due = db.session.query(db.func.sum(Commission.amount)).filter_by(status='due').scalar() or 0
    total_paid = db.session.query(db.func.sum(Commission.amount)).filter_by(status='paid').scalar() or 0
    return render_template('admin_commissions.html', commissions=commissions,
                         total_pending=total_pending, total_due=total_due, total_paid=total_paid)

@app.route('/admin/commission/pay/<int:id>', methods=['POST'])
@admin_required
def pay_commission(id):
    commission = Commission.query.get_or_404(id)
    commission.status = 'paid'
    commission.paid_at = datetime.utcnow()
    db.session.commit()
    flash('Commission paid.', 'success')
    return redirect(url_for('admin_commissions'))

@app.route('/admin/config', methods=['GET', 'POST'])
@admin_required
def admin_config():
    config = AppConfig.get()
    if request.method == 'POST':
        config.annonce_price = float(request.form.get('annonce_price', 20))
        config.free_announces_new_user = int(request.form.get('free_announces_new_user', 5))
        config.annonce_duration_days = int(request.form.get('annonce_duration_days', 30))
        config.commission_rate = float(request.form.get('commission_rate', 10))
        config.insurance_price = float(request.form.get('insurance_price', 50))
        config.featured_profile_price = float(request.form.get('featured_profile_price', 100))
        config.urgency_multiplier = float(request.form.get('urgency_multiplier', 1.5))
        config.contact_email = request.form.get('contact_email')
        config.contact_phone = request.form.get('contact_phone')
        config.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Configuration updated.', 'success')
        return redirect(url_for('admin_config'))
    return render_template('admin_config.html', config=config)

@app.route('/admin/admins')
@admin_required
def admin_admins():
    admins = User.query.filter_by(is_admin=True).all()
    return render_template('admin_admins.html', admins=admins)

@app.route('/admin/admin/<int:id>/permissions', methods=['POST'])
@admin_required
def update_admin_permissions(id):
    role = AdminRole.query.filter_by(user_id=id).first()
    if not role:
        role = AdminRole(user_id=id)
        db.session.add(role)
    role.can_manage_users = request.form.get('can_manage_users') == 'on'
    role.can_manage_services = request.form.get('can_manage_services') == 'on'
    role.can_manage_bookings = request.form.get('can_manage_bookings') == 'on'
    role.can_manage_annonces = request.form.get('can_manage_annonces') == 'on'
    role.can_manage_subscriptions = request.form.get('can_manage_subscriptions') == 'on'
    role.can_manage_payments = request.form.get('can_manage_payments') == 'on'
    role.can_manage_admins = request.form.get('can_manage_admins') == 'on'
    role.can_edit_config = request.form.get('can_edit_config') == 'on'
    role.can_view_analytics = request.form.get('can_view_analytics') == 'on'
    db.session.commit()
    flash('Permissions updated.', 'success')
    return redirect(url_for('admin_admins'))

@app.route('/admin/badges', methods=['GET', 'POST'])
@admin_required
def admin_badges():
    if request.method == 'POST':
        badge = Badge(
            name=request.form.get('name'), slug=request.form.get('slug'),
            description=request.form.get('description'),
            icon=request.form.get('icon', 'fa-award'),
            color=request.form.get('color', '#f59e0b'),
            condition_type=request.form.get('condition_type'),
            condition_value=int(request.form.get('condition_value', 0)),
            points_reward=int(request.form.get('points_reward', 0))
        )
        db.session.add(badge)
        db.session.commit()
        flash('Badge added.', 'success')
    badges = Badge.query.all()
    return render_template('admin_badges.html', badges=badges)

@app.route('/admin/levels', methods=['GET', 'POST'])
@admin_required
def admin_levels():
    if request.method == 'POST':
        level = Level(
            name=request.form.get('name'),
            min_points=int(request.form.get('min_points', 0)),
            max_points=int(request.form.get('max_points')) if request.form.get('max_points') else None,
            icon=request.form.get('icon', 'fa-star'),
            color=request.form.get('color', '#0d9488'),
            benefits=request.form.get('benefits')
        )
        db.session.add(level)
        db.session.commit()
        flash('Level added.', 'success')
    levels = Level.query.order_by(Level.min_points.asc()).all()
    return render_template('admin_levels.html', levels=levels)

# ==================== API ROUTES ====================

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '')
    if not q or len(q) < 2:
        return jsonify({'services': [], 'workers': []})
    services = Service.query.filter(
        db.or_(Service.title.contains(q), Service.description.contains(q)),
        Service.is_active == True
    ).limit(5).all()
    workers = User.query.filter(
        db.or_(User.full_name.contains(q), User.skills.contains(q)),
        User.user_type.in_(['worker', 'entreprise'])
    ).limit(5).all()
    return jsonify({
        'services': [{'id': s.id, 'title': s.title, 'price': s.price, 'city': s.city} for s in services],
        'workers': [{'id': w.id, 'name': w.full_name, 'city': w.city, 'rating': w.average_rating()} for w in workers]
    })


# ==================== AI MATCHING SYSTEM ====================

def calculate_match_score(client, worker, service_category=None, city=None):
    """AI Matching Algorithm - multi-factor scoring"""
    score = 0.0
    factors = {}

    # 1. Rating weight (0-30 points)
    rating = worker.average_rating()
    factors['rating'] = min(rating / 5.0 * 30, 30)
    score += factors['rating']

    # 2. Completion rate weight (0-25 points)
    worker_service_ids = [s.id for s in Service.query.filter_by(worker_id=worker.id).all()]
    total_bookings = Booking.query.filter(Booking.service_id.in_(worker_service_ids)).count() if worker_service_ids else 0
    completed_bookings = Booking.query.filter(Booking.service_id.in_(worker_service_ids), Booking.status=='completed').count() if worker_service_ids else 0
    completion_rate = (completed_bookings / total_bookings * 100) if total_bookings > 0 else 0
    factors['completion'] = min(completion_rate / 100 * 25, 25)
    score += factors['completion']

    # 3. Response time weight (0-20 points)
    avg_response = worker.response_time_avg or 999
    if avg_response <= 1: factors['response'] = 20
    elif avg_response <= 3: factors['response'] = 15
    elif avg_response <= 6: factors['response'] = 10
    elif avg_response <= 12: factors['response'] = 5
    else: factors['response'] = 0
    score += factors['response']

    # 4. Location match (0-15 points)
    if city and worker.city and worker.city.lower() == city.lower():
        factors['location'] = 15
    elif city and worker.city and city.lower() in worker.city.lower():
        factors['location'] = 10
    else:
        factors['location'] = 5
    score += factors['location']

    # 5. Price competitiveness (0-10 points)
    if service_category:
        cat_name = Category.query.get(service_category).name if Category.query.get(service_category) else ''
        avg_price = db.session.query(db.func.avg(Service.price)).filter(
            Service.category == cat_name, Service.is_active == True
        ).scalar() or 0
        worker_services = Service.query.filter_by(worker_id=worker.id, is_active=True).all()
        if worker_services:
            worker_avg = sum(s.price for s in worker_services) / len(worker_services)
            if avg_price > 0:
                diff = abs(worker_avg - avg_price) / avg_price
                factors['price'] = max(0, 10 - diff * 10)
            else:
                factors['price'] = 5
        else:
            factors['price'] = 0
    else:
        factors['price'] = 5
    score += factors['price']

    return round(score, 2), factors

@app.route('/ai-match', methods=['GET', 'POST'])
@login_required
def ai_match():
    if request.method == 'POST':
        category_id = request.form.get('category_id', type=int)
        city = request.form.get('city', '')
        description = request.form.get('description', '')

        # Find all eligible workers
        workers = User.query.filter(
            User.user_type.in_(['worker', 'entreprise', 'auto_entrepreneur', 'freelance']),
            User.is_active == True
        ).all()

        results = []
        for worker in workers:
            score, factors = calculate_match_score(
                client=User.query.get(session['user_id']), worker=worker, 
                service_category=category_id, city=city
            )

            # Boost for verified, featured, insurance
            if worker.is_featured: score += 5
            if worker.insurance_active: score += 3

            # Keyword matching in description
            if description and worker.skills:
                keywords = description.lower().split()
                skill_words = worker.skills.lower().split()
                matches = sum(1 for k in keywords if k in skill_words)
                score += min(matches * 2, 10)

            results.append({
                'worker': worker,
                'score': round(score, 1),
                'factors': factors,
                'rating': worker.average_rating(),
                'reviews': worker.review_count(),
                'completed': Booking.query.filter(Booking.service_id.in_([s.id for s in Service.query.filter_by(worker_id=worker.id).all()]), Booking.status=='completed').count() if Service.query.filter_by(worker_id=worker.id).first() else 0
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        top_results = results[:10]

        # Log the match
        if top_results:
            log = AIMatchLog(
                client_id=session['user_id'],
                category_id=category_id,
                city=city,
                top_worker_id=top_results[0]['worker'].id,
                match_score=top_results[0]['score'],
                factors=json.dumps(top_results[0]['factors'])
            )
            db.session.add(log)
            db.session.commit()

        return render_template('ai_match.html', results=top_results, category_id=category_id, city=city)

    categories = Category.query.all()
    return render_template('ai_match.html', categories=categories, results=None)

@app.route('/api/ai-match/score')
def api_ai_match_score():
    worker_id = request.args.get('worker_id', type=int)
    category_id = request.args.get('category_id', type=int)
    city = request.args.get('city', '')
    if not worker_id:
        return jsonify({'error': 'worker_id required'}), 400
    worker = User.query.get_or_404(worker_id)
    score, factors = calculate_match_score(None, worker, category_id, city)
    return jsonify({'score': score, 'factors': factors})

# ==================== VIDEO CALL (WebRTC / Jitsi) ====================

@app.route('/video-call/<int:booking_id>')
@login_required
def video_call(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.client_id != session['user_id'] and booking.worker_id != session['user_id']:
        flash('Access denied.', 'danger')
        return redirect(url_for('my_bookings'))

    room = VideoCallRoom.query.filter_by(booking_id=booking_id).first()
    if not room:
        room_id = 'lmawqef-' + generate_reference().lower()
        room = VideoCallRoom(booking_id=booking_id, room_id=room_id, provider='jitsi')
        db.session.add(room)
        db.session.commit()

    return render_template('video_call.html', booking=booking, room=room)

@app.route('/api/video-call/<int:booking_id>/start', methods=['POST'])
@login_required
def start_video_call(booking_id):
    room = VideoCallRoom.query.filter_by(booking_id=booking_id).first()
    if room:
        room.started_at = datetime.utcnow()
        room.status = 'active'
        db.session.commit()
    return jsonify({'success': True, 'room_id': room.room_id if room else None})

@app.route('/api/video-call/<int:booking_id>/end', methods=['POST'])
@login_required
def end_video_call(booking_id):
    room = VideoCallRoom.query.filter_by(booking_id=booking_id).first()
    if room and room.started_at:
        room.ended_at = datetime.utcnow()
        room.duration_seconds = int((room.ended_at - room.started_at).total_seconds())
        room.status = 'ended'
        db.session.commit()
    return jsonify({'success': True, 'duration': room.duration_seconds if room else 0})

# ==================== WHATSAPP BUSINESS INTEGRATION ====================

def send_whatsapp_message(phone, template_name, variables=None):
    """Simulate WhatsApp Business API sending"""
    template = WhatsAppTemplate.query.filter_by(slug=template_name, is_active=True).first()
    if not template:
        return {'success': False, 'error': 'Template not found'}

    # In production, this would call the WhatsApp Business API
    # For demo, we log it
    log = WhatsAppLog(
        user_id=session.get('user_id', 0),
        phone=phone,
        template_name=template_name,
        message_type='template',
        content=template.body,
        status='sent',
        sent_at=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()

    return {'success': True, 'message_id': log.id}

@app.route('/whatsapp/send', methods=['POST'])
@login_required
def whatsapp_send():
    phone = request.form.get('phone')
    template = request.form.get('template', 'booking_confirmation')
    if not phone:
        return jsonify({'error': 'Phone required'}), 400
    result = send_whatsapp_message(phone, template)
    return jsonify(result)

@app.route('/admin/whatsapp')
@admin_required
def admin_whatsapp():
    templates = WhatsAppTemplate.query.all()
    logs = WhatsAppLog.query.order_by(WhatsAppLog.created_at.desc()).limit(100).all()
    return render_template('admin_whatsapp.html', templates=templates, logs=logs)

# ==================== QR CODE CHECK-IN ====================

import qrcode
import base64
from io import BytesIO

def generate_qr_code(data):
    """Generate QR code and return base64 PNG"""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D9488", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()

@app.route('/qr-check/<code>')
def qr_check(code):
    qr = QRCodeCheck.query.filter_by(code=code).first()
    if not qr or not qr.is_valid:
        flash('Invalid or expired QR code.', 'danger')
        return redirect(url_for('index'))

    booking = Booking.query.get(qr.booking_id)
    if not booking:
        flash('Booking not found.', 'danger')
        return redirect(url_for('index'))

    if qr.status == 'checked_in':
        flash('Already checked in!', 'info')
    else:
        qr.status = 'checked_in'
        qr.checked_in_at = datetime.utcnow()
        db.session.commit()
        flash('Check-in successful!', 'success')

    return render_template('qr_check.html', qr=qr, booking=booking)

@app.route('/qr-check/generate/<int:booking_id>')
@login_required
def generate_qr_check(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.client_id != session['user_id'] and booking.worker_id != session['user_id']:
        flash('Access denied.', 'danger')
        return redirect(url_for('my_bookings'))

    # Invalidate old QR codes for this booking
    QRCodeCheck.query.filter_by(booking_id=booking_id).update({'is_valid': False})

    code = generate_reference() + '-' + str(booking_id)
    qr_data = url_for('qr_check', code=code, _external=True)
    qr_b64 = generate_qr_code(qr_data)

    qr = QRCodeCheck(
        booking_id=booking_id,
        code=code,
        qr_image_url='data:image/png;base64,' + qr_b64,
        is_valid=True
    )
    db.session.add(qr)
    db.session.commit()

    return render_template('qr_check.html', qr=qr, booking=booking, generated=True)

# ==================== RAMADAN MODE ====================

def get_ramadan_config():
    current_year = datetime.utcnow().year
    config = RamadanConfig.query.filter_by(year=current_year).first()
    if not config:
        # Auto-detect approximate Ramadan dates (simplified)
        config = RamadanConfig(
            year=current_year,
            start_date=datetime(current_year, 3, 1).date(),
            end_date=datetime(current_year, 3, 30).date(),
            is_active=False,
            special_hours_start=None,
            special_hours_end=None,
            discount_percent=10,
            message='Ramadan Mubarak! Special offers during the holy month.'
        )
        db.session.add(config)
        db.session.commit()
    return config

@app.route('/ramadan-toggle', methods=['POST'])
@admin_required
def ramadan_toggle():
    config = get_ramadan_config()
    config.is_active = not config.is_active
    db.session.commit()
    flash(f'Ramadan mode {"activated" if config.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin_config'))

@app.context_processor
def inject_ramadan():
    config = RamadanConfig.query.filter_by(is_active=True).first()
    return {'ramadan_active': config is not None, 'ramadan_config': config}

# ==================== GOOGLE MAPS API PROXY ====================

@app.route('/api/maps/geocode')
def maps_geocode():
    address = request.args.get('address', '')
    if not address:
        return jsonify({'error': 'Address required'}), 400

    # In production, call Google Maps Geocoding API
    # For demo, return mock data or use lat/lng from user profiles
    users = User.query.filter(
        db.or_(User.city.contains(address), User.address.contains(address))
    ).all()

    results = []
    for u in users:
        if u.latitude and u.longitude:
            results.append({
                'id': u.id,
                'name': u.full_name,
                'lat': u.latitude,
                'lng': u.longitude,
                'city': u.city,
                'type': u.user_type
            })

    return jsonify({'results': results})

@app.route('/api/maps/nearby-workers')
def maps_nearby_workers():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', 10, type=float)  # km
    category_id = request.args.get('category_id', type=int)

    if not lat or not lng:
        return jsonify({'error': 'lat and lng required'}), 400

    # Simple distance filter using Haversine formula
    workers = User.query.filter(
        User.user_type.in_(['worker', 'entreprise', 'auto_entrepreneur', 'freelance']),
        User.is_active == True,
        User.latitude != None,
        User.longitude != None
    ).all()

    from math import radians, sin, cos, sqrt, atan2
    def haversine(lat1, lng1, lat2, lng2):
        R = 6371
        dlat = radians(lat2 - lat1)
        dlng = radians(lng2 - lng1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng/2)**2
        return 2 * R * atan2(sqrt(a), sqrt(1-a))

    results = []
    for w in workers:
        dist = haversine(lat, lng, w.latitude, w.longitude)
        if dist <= radius:
            services = Service.query.filter_by(worker_id=w.id, is_active=True)
            if category_id:
                services = services.filter_by(category_id=category_id)
            svc_count = services.count()
            results.append({
                'id': w.id,
                'name': w.full_name,
                'lat': w.latitude,
                'lng': w.longitude,
                'distance_km': round(dist, 2),
                'rating': w.average_rating(),
                'services_count': svc_count
            })

    results.sort(key=lambda x: x['distance_km'])
    return jsonify({'results': results, 'center': {'lat': lat, 'lng': lng}})

# ==================== CHART.JS ANALYTICS API ====================

@app.route('/api/analytics/dashboard')
@login_required
def api_analytics_dashboard():
    user_id = session['user_id']
    user = User.query.get(user_id)

    # Monthly bookings data for Chart.js
    months = []
    bookings_data = []
    revenue_data = []

    for i in range(6):
        month_date = datetime.utcnow() - timedelta(days=30*i)
        month_name = month_date.strftime('%b %Y')
        months.insert(0, month_name)

        start = month_date.replace(day=1, hour=0, minute=0, second=0)
        if i > 0:
            end = (start + timedelta(days=32)).replace(day=1)
        else:
            end = datetime.utcnow()

        if user.user_type in ['worker', 'entreprise']:
            count = Booking.query.filter(
                Booking.worker_id == user_id,
                Booking.created_at >= start,
                Booking.created_at < end
            ).count()
            revenue = db.session.query(db.func.sum(Booking.price)).filter(
                Booking.worker_id == user_id,
                Booking.status == 'completed',
                Booking.created_at >= start,
                Booking.created_at < end
            ).scalar() or 0
        else:
            count = Booking.query.filter(
                Booking.client_id == user_id,
                Booking.created_at >= start,
                Booking.created_at < end
            ).count()
            revenue = 0

        bookings_data.insert(0, count)
        revenue_data.insert(0, round(float(revenue), 2))

    # Rating distribution
    if user.user_type in ['worker', 'entreprise']:
        reviews = Review.query.filter_by(worker_id=user_id).all()
    else:
        reviews = []

    rating_dist = {1:0, 2:0, 3:0, 4:0, 5:0}
    for r in reviews:
        rating_dist[r.rating] = rating_dist.get(r.rating, 0) + 1

    return jsonify({
        'months': months,
        'bookings': bookings_data,
        'revenue': revenue_data,
        'rating_distribution': list(rating_dist.values()),
        'total_views': Service.query.filter_by(worker_id=user_id).with_entities(db.func.sum(Service.views)).scalar() or 0 if user.user_type in ['worker', 'entreprise'] else 0,
        'conversion_rate': round(len(reviews) / max(len(bookings_data), 1) * 100, 1)
    })

@app.route('/api/analytics/admin')
@admin_required
def api_analytics_admin():
    # Platform-wide analytics for admin Chart.js
    months = []
    users_data = []
    bookings_data = []
    revenue_data = []

    for i in range(6):
        month_date = datetime.utcnow() - timedelta(days=30*i)
        month_name = month_date.strftime('%b %Y')
        months.insert(0, month_name)

        start = month_date.replace(day=1, hour=0, minute=0, second=0)
        if i > 0:
            end = (start + timedelta(days=32)).replace(day=1)
        else:
            end = datetime.utcnow()

        u_count = User.query.filter(User.created_at >= start, User.created_at < end).count()
        b_count = Booking.query.filter(Booking.created_at >= start, Booking.created_at < end).count()
        rev = db.session.query(db.func.sum(Payment.amount)).filter(
            Payment.status == 'completed',
            Payment.created_at >= start,
            Payment.created_at < end
        ).scalar() or 0

        users_data.insert(0, u_count)
        bookings_data.insert(0, b_count)
        revenue_data.insert(0, round(float(rev), 2))

    # Category distribution
    cats = Category.query.all()
    cat_labels = [c.name for c in cats]
    cat_counts = [Service.query.filter_by(category_id=c.id, is_active=True).count() for c in cats]

    # City distribution (top 10)
    city_data = db.session.query(User.city, db.func.count(User.id)).group_by(User.city).order_by(db.func.count(User.id).desc()).limit(10).all()

    return jsonify({
        'months': months,
        'new_users': users_data,
        'bookings': bookings_data,
        'revenue': revenue_data,
        'category_labels': cat_labels,
        'category_data': cat_counts,
        'city_labels': [c[0] for c in city_data],
        'city_data': [c[1] for c in city_data],
        'total_users': User.query.count(),
        'total_workers': User.query.filter(User.user_type.in_(['worker', 'entreprise'])).count(),
        'total_bookings': Booking.query.count(),
        'total_revenue': round(float(db.session.query(db.func.sum(Payment.amount)).filter(Payment.status == 'completed').scalar() or 0), 2)
    })

# ==================== SAAS / MULTITENANCY ROUTES ====================

@app.route('/saas/register', methods=['GET', 'POST'])
def saas_register():
    if request.method == 'POST':
        name = request.form.get('name')
        slug = request.form.get('slug')
        contact_email = request.form.get('email')
        contact_phone = request.form.get('phone')
        city = request.form.get('city')
        plan = request.form.get('plan', 'starter')

        if Organization.query.filter_by(slug=slug).first():
            flash('Organization slug already exists.', 'danger')
            return redirect(url_for('saas_register'))

        org = Organization(
            name=name, slug=slug, contact_email=contact_email,
            contact_phone=contact_phone, city=city, plan=plan,
            status='trial',
            trial_ends_at=datetime.utcnow() + timedelta(days=14)
        )
        db.session.add(org)
        db.session.commit()

        # Create owner member
        if 'user_id' in session:
            member = OrganizationMember(
                organization_id=org.id,
                user_id=session['user_id'],
                role='owner'
            )
            db.session.add(member)
            db.session.commit()

        flash('Organization created! 14-day trial started.', 'success')
        return redirect(url_for('saas_dashboard', org_slug=slug))

    saas_plans = SaaSPlan.query.filter_by(is_active=True).order_by(SaaSPlan.display_order.asc()).all()
    return render_template('saas_register.html', plans=saas_plans)

@app.route('/saas/<org_slug>/dashboard')
@login_required
def saas_dashboard(org_slug):
    org = Organization.query.filter_by(slug=org_slug).first_or_404()
    member = OrganizationMember.query.filter_by(organization_id=org.id, user_id=session['user_id']).first()
    if not member:
        flash('You are not a member of this organization.', 'danger')
        return redirect(url_for('index'))

    org_users = db.session.query(User).join(OrganizationMember).filter(
        OrganizationMember.organization_id == org.id
    ).all()
    org_services = Service.query.join(User).join(OrganizationMember).filter(
        OrganizationMember.organization_id == org.id,
        Service.is_active == True
    ).all()

    return render_template('saas_dashboard.html', org=org, member=member, org_users=org_users, org_services=org_services)

@app.route('/admin/saas')
@admin_required
def admin_saas():
    orgs = Organization.query.order_by(Organization.created_at.desc()).all()
    saas_plans = SaaSPlan.query.all()
    return render_template('admin_saas.html', organizations=orgs, saas_plans=saas_plans)

@app.route('/admin/saas/plans', methods=['GET', 'POST'])
@admin_required
def admin_saas_plans():
    if request.method == 'POST':
        plan = SaaSPlan(
            name=request.form.get('name'),
            slug=request.form.get('slug'),
            description=request.form.get('description'),
            price_monthly=float(request.form.get('price_monthly', 0)),
            price_yearly=float(request.form.get('price_yearly', 0)),
            max_users=int(request.form.get('max_users', 5)),
            max_services=int(request.form.get('max_services', 50)),
            max_annonces=int(request.form.get('max_annonces', 100)),
            features=request.form.get('features', '[]'),
            display_order=int(request.form.get('display_order', 0))
        )
        db.session.add(plan)
        db.session.commit()
        flash('SaaS plan added.', 'success')
    plans = SaaSPlan.query.order_by(SaaSPlan.display_order.asc()).all()
    return render_template('admin_saas_plans.html', plans=plans)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


# ==================== SAAS MODELS ====================

class Organization(db.Model):
    __tablename__ = 'organizations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    logo = db.Column(db.String(300), default='default-org-logo.png')
    primary_color = db.Column(db.String(10), default='#0D9488')
    secondary_color = db.Column(db.String(10), default='#F59E0B')
    domain = db.Column(db.String(200), nullable=True)
    contact_email = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(300), nullable=True)
    ice_number = db.Column(db.String(50), nullable=True)
    rc_number = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, suspended, trial
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    plan = db.Column(db.String(30), default='starter')  # starter, growth, enterprise
    max_users = db.Column(db.Integer, default=5)
    max_services = db.Column(db.Integer, default=50)
    billing_email = db.Column(db.String(120), nullable=True)
    stripe_customer_id = db.Column(db.String(100), nullable=True)
    cmi_merchant_id = db.Column(db.String(100), nullable=True)
    # Relationships
    members = db.relationship('OrganizationMember', backref='org', lazy=True, cascade='all, delete-orphan')

    def is_trial_active(self):
        if self.status == 'trial' and self.trial_ends_at:
            return datetime.utcnow() < self.trial_ends_at
        return self.status == 'active'

class OrganizationMember(db.Model):
    __tablename__ = 'organization_members'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(30), default='member')  # owner, admin, member
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class OrganizationSubscription(db.Model):
    __tablename__ = 'organization_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    plan = db.Column(db.String(30), default='starter')
    status = db.Column(db.String(20), default='active')  # active, cancelled, expired
    price_monthly = db.Column(db.Float, default=0)
    current_period_start = db.Column(db.DateTime, default=datetime.utcnow)
    current_period_end = db.Column(db.DateTime, nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(30), default='cmi')  # cmi, stripe, bank_transfer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SaaSPlan(db.Model):
    __tablename__ = 'saas_plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    price_monthly = db.Column(db.Float, default=0)
    price_yearly = db.Column(db.Float, default=0)
    max_users = db.Column(db.Integer, default=5)
    max_services = db.Column(db.Integer, default=50)
    max_annonces = db.Column(db.Integer, default=100)
    features = db.Column(db.Text, default='[]')  # JSON list
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== AI MATCHING MODEL ====================

class AIMatchLog(db.Model):
    __tablename__ = 'ai_match_logs'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    top_worker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    match_score = db.Column(db.Float, default=0)
    factors = db.Column(db.Text, default='{}')  # JSON: rating_weight, distance_weight, price_weight, completion_weight
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    was_booked = db.Column(db.Boolean, default=False)

# ==================== VIDEO CALL MODELS ====================

class VideoCallRoom(db.Model):
    __tablename__ = 'video_call_rooms'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    room_id = db.Column(db.String(100), unique=True, nullable=False)
    provider = db.Column(db.String(30), default='jitsi')  # jitsi, daily, custom
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Integer, default=0)
    recording_url = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), default='created')  # created, active, ended

# ==================== WHATSAPP INTEGRATION ====================

class WhatsAppLog(db.Model):
    __tablename__ = 'whatsapp_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    template_name = db.Column(db.String(100), nullable=True)
    message_type = db.Column(db.String(30), default='text')  # text, template, media
    content = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='pending')  # pending, sent, delivered, read, failed
    wa_message_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    failed_reason = db.Column(db.Text, nullable=True)

class WhatsAppTemplate(db.Model):
    __tablename__ = 'whatsapp_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    language = db.Column(db.String(10), default='fr')
    category = db.Column(db.String(30), default='UTILITY')  # MARKETING, UTILITY, AUTHENTICATION
    body = db.Column(db.Text, nullable=False)
    header_type = db.Column(db.String(20), default='NONE')  # NONE, TEXT, IMAGE, VIDEO
    header_content = db.Column(db.String(300), nullable=True)
    footer = db.Column(db.String(200), nullable=True)
    variables = db.Column(db.Text, default='[]')  # JSON list of variable names
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== QR CODE CHECK-IN ====================

class QRCodeCheck(db.Model):
    __tablename__ = 'qr_code_checks'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    code = db.Column(db.String(200), unique=True, nullable=False)
    qr_image_url = db.Column(db.String(300), nullable=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    checked_in_at = db.Column(db.DateTime, nullable=True)
    checked_in_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    location_lat = db.Column(db.Float, nullable=True)
    location_lng = db.Column(db.Float, nullable=True)
    is_valid = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default='pending')  # pending, checked_in, expired

# ==================== RAMADAN MODE ====================

class RamadanConfig(db.Model):
    __tablename__ = 'ramadan_configs'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    special_hours_start = db.Column(db.Time, nullable=True)  # e.g. 20:00
    special_hours_end = db.Column(db.Time, nullable=True)  # e.g. 02:00
    discount_percent = db.Column(db.Float, default=10)  # 10% off during Ramadan
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RamadanBooking(db.Model):
    __tablename__ = 'ramadan_bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    is_ramadan_period = db.Column(db.Boolean, default=True)
    discount_applied = db.Column(db.Float, default=0)
    adjusted_price = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== GOOGLE MAPS / GEO MODELS ====================

class GeoLocationLog(db.Model):
    __tablename__ = 'geo_location_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float, nullable=True)
    action = db.Column(db.String(50), default='tracking')  # tracking, arrival, departure, check_in
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== INITIALIZATION ====================

def create_default_data():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin', email='admin@lmawqef.ma',
            password_hash=generate_password_hash('admin123'),
            full_name='System Administrator', phone='0600000000',
            city='Rabat', user_type='client', is_admin=True
        )
        db.session.add(admin)
        role = AdminRole(user_id=1, can_manage_users=True, can_manage_services=True,
                        can_manage_bookings=True, can_manage_annonces=True,
                        can_manage_subscriptions=True, can_manage_payments=True,
                        can_manage_admins=True, can_edit_config=True, can_view_analytics=True)
        db.session.add(role)
        db.session.commit()
        print('Admin created: admin / admin123')
    plans = SubscriptionPlan.query.all()
    if not plans:
        default_plans = [
            SubscriptionPlan(name='Entreprise Premium', slug='entreprise-premium',
                           description='For workforce companies', price=500, duration_days=30,
                           annonce_limit=999, features='["Unlimited announces","Featured profile","Priority support","Analytics"]',
                           target_type='entreprise'),
            SubscriptionPlan(name='Entreprise Basic', slug='entreprise-basic',
                           description='Basic plan for companies', price=0, duration_days=30,
                           annonce_limit=50, features='["50 announces/month","Basic support"]',
                           target_type='entreprise'),
            SubscriptionPlan(name='Auto-Entrepreneur Pro', slug='auto-pro',
                           description='For self-employed professionals', price=150, duration_days=30,
                           annonce_limit=100, features='["100 announces/month","Portfolio showcase","Priority listing","Direct messages"]',
                           target_type='autoentrepreneur'),
            SubscriptionPlan(name='Freelance Starter', slug='freelance-starter',
                           description='For freelancers', price=0, duration_days=30,
                           annonce_limit=20, features='["20 announces/month","Basic profile"]',
                           target_type='freelance'),
            SubscriptionPlan(name='Freelance Pro', slug='freelance-pro',
                           description='Pro plan for freelancers', price=100, duration_days=30,
                           annonce_limit=50, features='["50 announces/month","Portfolio","Featured services"]',
                           target_type='freelance')
        ]
        for p in default_plans:
            db.session.add(p)
        db.session.commit()
        print('Subscription plans created')
    config = AppConfig.query.first()
    if not config:
        config = AppConfig()
        db.session.add(config)
        db.session.commit()
        print('App config created')
    # Create default levels
    levels = Level.query.all()
    if not levels:
        default_levels = [
            Level(name='Novice', min_points=0, max_points=99, icon='fa-seedling', color='#84cc16', benefits='Basic profile'),
            Level(name='Apprenti', min_points=100, max_points=499, icon='fa-leaf', color='#22c55e', benefits='Portfolio access'),
            Level(name='Professionnel', min_points=500, max_points=1999, icon='fa-star', color='#0d9488', benefits='Priority listing'),
            Level(name='Expert', min_points=2000, max_points=4999, icon='fa-gem', color='#3b82f6', benefits='Featured services'),
            Level(name='Maitre', min_points=5000, max_points=9999, icon='fa-crown', color='#f59e0b', benefits='Analytics dashboard'),
            Level(name='Legende', min_points=10000, max_points=None, icon='fa-trophy', color='#ef4444', benefits='All premium features')
        ]
        for l in default_levels:
            db.session.add(l)
        db.session.commit()
        print('Levels created')
    # Create default badges
    badges = Badge.query.all()
    if not badges:
        default_badges = [
            Badge(name='Premier Service', slug='first-service', description='Complete your first service',
                  icon='fa-handshake', color='#0d9488', condition_type='bookings_count', condition_value=1, points_reward=50),
            Badge(name='Worker Actif', slug='active-worker', description='Complete 10 services',
                  icon='fa-briefcase', color='#3b82f6', condition_type='bookings_count', condition_value=10, points_reward=200),
            Badge(name='Top Rated', slug='top-rated', description='Achieve 4.5+ average rating',
                  icon='fa-star', color='#f59e0b', condition_type='rating', condition_value=5, points_reward=300),
            Badge(name='Critique Acclame', slug='popular-reviews', description='Receive 25 reviews',
                  icon='fa-comments', color='#8b5cf6', condition_type='reviews_count', condition_value=25, points_reward=250),
            Badge(name='Portfolio Pro', slug='portfolio-pro', description='Add 5 portfolio items',
                  icon='fa-images', color='#ec4899', condition_type='services_count', condition_value=5, points_reward=150),
            Badge(name='Rapidite Flash', slug='flash-response', description='Respond within 1 hour average',
                  icon='fa-bolt', color='#eab308', condition_type='response_time', condition_value=60, points_reward=200),
        ]
        for b in default_badges:
            db.session.add(b)
        db.session.commit()
        print('Badges created')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_default_data()
    app.run(host='0.0.0.0', port=5000, debug=True)
