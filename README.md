# E-Commerce Mini Store

A full-stack e-commerce web application built with Flask, MySQL, and vanilla JavaScript.

## Features

- User Authentication (Signup/Login with secure password hashing)
- Product catalog with search and category filtering
- Dynamic Inventory & Stock Management (real-time stock deduction, low-stock warnings, out-of-stock badges)
- Interactive Shopping Cart (AJAX-powered quantity updates without page reload)
- Multi-step Checkout Flow (shipping address validation, payment selection: COD / UPI)
- Printable Tax Invoices (auto-generated invoices with printable layout)
- Customer Order History with real-time status tracking
- **Admin Control Panel:**
  - Real-time business metrics (Revenue, Orders, Products, Customers)
  - Product Catalog Management (Add, Edit, Delete with image upload and stock control)
  - Customer Order Processing (Status updates: Pending, Processing, Shipped, Delivered, Cancelled)
- Role-based Access Control (`@login_required`, `@admin_required`)
- Jinja2 multi-level template inheritance and clean, responsive UI

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
