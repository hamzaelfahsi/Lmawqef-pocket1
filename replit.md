# Lmawqef Pocket - Moroccan Marketplace Platform

## Overview
A full-featured Moroccan marketplace/SaaS platform built with Flask. It allows workers, freelancers, auto-entrepreneurs, and entreprises to offer and find services.

## Architecture
- **Backend**: Python Flask (app.py - single-file application, ~2779 lines)
- **Database**: SQLite via Flask-SQLAlchemy (`instance/lmawqef_ultimate.db`)
- **Templates**: Jinja2 HTML templates in `templates/`
- **Static files**: CSS, JS, and uploads in `static/`

## Key Features
- User authentication (workers, clients, admins)
- Service listings and bookings
- Announcement (annonce) board
- Devis (quotes) system
- Subscription plans (SaaS model)
- Gamification: levels, badges, points
- QR code check-ins
- Messaging system
- Admin panel
- Insurance module
- Featured listings

## Running the App
- **Workflow**: "Start application" runs `python app.py` on port 5000
- The app auto-creates the SQLite database and seeds default data on first run

## Default Admin Credentials
- Username: `admin`
- Password: `admin123`

## Dependencies
- Flask 3.0.0
- Flask-SQLAlchemy 3.1.1
- Flask-Migrate 4.0.5
- Werkzeug 3.0.1
- SQLAlchemy 2.0.23
- qrcode 7.4.2
- Pillow 10.1.0
- python-dotenv 1.0.0
