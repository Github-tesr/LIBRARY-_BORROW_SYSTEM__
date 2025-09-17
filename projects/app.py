from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: pandas not available. CSV functionality will be limited.")
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    student_code = db.Column(db.String(20), unique=True, nullable=False)
    borrows = db.relationship('Borrow', backref='student', lazy=True)

class Borrow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    book_name = db.Column(db.String(200), nullable=False)
    borrow_date = db.Column(db.Date, nullable=False)

# Routes
@app.route('/')
def index():
    return redirect(url_for('borrow'))

@app.route('/borrow', methods=['GET', 'POST'])
def borrow():
    if request.method == 'POST':
        student_code = request.form.get('student_code')
        book_name = request.form.get('book_name')
        borrow_date_str = request.form.get('borrow_date')

        # Validation
        student = Student.query.filter_by(student_code=student_code).first()
        if not student:
            flash('Student not found. Please check the student code.', 'error')
            return redirect(url_for('borrow'))

        # Check if book is available
        books_df = pd.read_csv('books.csv')
        book_row = books_df[books_df['BookName'].str.lower() == book_name.lower()]
        if book_row.empty or book_row['Available'].iloc[0] != 'Yes':
            flash('Book is not available for borrowing.', 'error')
            return redirect(url_for('borrow'))

        # Check borrow limit (max 3 books)
        current_borrows = Borrow.query.filter_by(student_id=student.id).count()
        if current_borrows >= 3:
            flash('Student has reached the maximum borrow limit of 3 books.', 'error')
            return redirect(url_for('borrow'))

        # Create borrow record
        try:
            borrow_date = datetime.strptime(borrow_date_str, '%Y-%m-%d').date()
            new_borrow = Borrow(student_id=student.id, book_name=book_name, borrow_date=borrow_date)
            db.session.add(new_borrow)
            db.session.commit()

            # Update book availability in CSV
            books_df.at[book_row.index[0], 'Available'] = 'No'
            books_df.to_csv('books.csv', index=False)

            flash('Book borrowed successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error borrowing book. Please try again.', 'error')

        return redirect(url_for('borrow'))

    # GET request - show form
    students = Student.query.all()
    return render_template('borrow.html', students=students)

@app.route('/records')
def records():
    borrows = db.session.query(Borrow, Student).join(Student).all()
    return render_template('records.html', borrows=borrows)

@app.route('/return_book/<int:borrow_id>', methods=['POST'])
def return_book(borrow_id):
    borrow = Borrow.query.get_or_404(borrow_id)
    book_name = borrow.book_name
    try:
        db.session.delete(borrow)
        db.session.commit()

        # Update book availability back to Yes in CSV
        books_df = pd.read_csv('books.csv')
        book_row = books_df[books_df['BookName'].str.lower() == book_name.lower()]
        if not book_row.empty:
            books_df.at[book_row.index[0], 'Available'] = 'Yes'
            books_df.to_csv('books.csv', index=False)

        flash('Book returned successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error returning book. Please try again.', 'error')
    return redirect(url_for('records'))

@app.route('/api/books')
def get_books():
    try:
        books_df = pd.read_csv('books.csv')
        available_books = books_df[books_df['Available'] == 'Yes']['BookName'].tolist()
        return jsonify({'books': available_books})
    except Exception as e:
        return jsonify({'error': 'Could not load books'}), 500

@app.route('/api/students')
def get_students():
    students = Student.query.all()
    students_data = [{'id': s.id, 'name': s.name, 'department': s.department, 'code': s.student_code} for s in students]
    return jsonify({'students': students_data})

def init_db():
    """Initialize database and import data from CSV"""
    with app.app_context():
        db.create_all()

        # Import students if not already imported
        if Student.query.count() == 0:
            try:
                students_df = pd.read_csv('students.csv')
                for _, row in students_df.iterrows():
                    # Handle different CSV formats
                    name = row.get('SName') or row.get('name', '')
                    department = row.get('SDepartment') or row.get('department', '')
                    code = row.get('SCode') or row.get('code', '')

                    if name and code:  # Only add if we have required fields
                        student = Student(name=name, department=department, student_code=code)
                        db.session.add(student)
                db.session.commit()
                print("Students imported successfully")
            except Exception as e:
                print(f"Error importing students: {e}")
                db.session.rollback()

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
