# 🛒 E-Commerce Mini Store

A full-stack e-commerce web application built with Flask, MySQL, and vanilla JavaScript.

## Features

- User Signup/Login with password hashing
- Product listing with search & category filter
- Cart system (database-backed, AJAX-powered — no page reload)
- Place Order & Order History with real-time status badges
- **Admin Control Panel:**
  - Real-time business metrics (Revenue, Orders, Products, Users)
  - Full Product CRUD (Add, Edit, Delete with Image Upload)
  - Order Management & Status Tracking (Pending, Processing, Shipped, Delivered, Cancelled)
- Role-based route protection (`@login_required`, `@admin_required`)
- Flash messages & template inheritance

## Tech Stack

- **Frontend:** HTML, CSS, JavaScript (Fetch API)
- **Backend:** Python, Flask
- **Database:** MySQL

## Setup Instructions

1. Clone the repo: `git clone <repo-url>`
2. Create virtual environment: `python -m venv venv`
3. Activate it: `venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a `.env` file with your DB credentials (see `.env.example`)
6. Import the database schema:
   `mysql -u root -p ecommerce_db < schema.sql`
7. Run: `python app.py`

## Screenshots

(Add screenshots here later)
