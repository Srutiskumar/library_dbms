from flask import Flask, render_template, request, jsonify,session, redirect, url_for, flash
from db import get_connection
from datetime import date

app = Flask(__name__)
app.secret_key = 'mysecret123'

#Login
@app.route('/login', methods=['POST','GET'])
def login():
    if request.method == 'GET':
        return render_template('dashboard.html')
    
    username = request.form['username']
    password = request.form['password']
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT * FROM Librarians 
    WHERE username = %s AND password = %s
    """
    cursor.execute(query, (username, password))

    result = cursor.fetchone()

    cursor.close()
    conn.close()

    if result:
        session['librarian_id'] = result['librarian_id']
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html')

@app.route("/dashboard")
def dashboard():
    conn = get_connection()
    with conn.cursor() as cursor:
        # Total books
        cursor.execute("SELECT COUNT(*) as total FROM Book_Copies")
        total_books = cursor.fetchone()['total']

        # Available books (status = 'available' in Book_Copies)
        cursor.execute("SELECT COUNT(*) as available FROM Book_Copies WHERE status='available'")
        available_books = cursor.fetchone()['available']

        # Issued books (status = 'issued')
        cursor.execute("SELECT COUNT(*) as issued FROM Book_Copies WHERE status='issued'")
        issued_books = cursor.fetchone()['issued']

        # Overdue books (issued but due_date < today and not returned)
        today_str = date.today().strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) as overdue FROM Issued_Books WHERE return_date IS NULL AND due_date < %s",
            (today_str,)
        )
        overdue_books = cursor.fetchone()['overdue']

        cursor.execute("""SELECT m.name AS member_name, ib.title AS book_title,
        CASE 
            WHEN ib.return_date IS NULL THEN 'Issued'
            ELSE 'Returned'
        END AS action,
        COALESCE(ib.return_date, ib.issue_date) AS date
    FROM Issued_Books ib
    JOIN Members m ON ib.member_id = m.member_id
    ORDER BY date DESC
    LIMIT 5""")

        recent_transactions = cursor.fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        total_books=total_books,
        available_books=available_books,
        issued_books=issued_books,
        overdue_books=overdue_books,
        recent_transactions=recent_transactions
    )


# Home
@app.route('/')
def home():
    return render_template('login.html')

# Add Book 
# GET route to render form
@app.route('/add_book', methods=['GET'])
def add_book():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Categories")
    categories = cursor.fetchall()
    cursor.close()
    return render_template('add_book.html', categories=categories)

# POST route to handle form submission
@app.route('/add_book', methods=['POST'])
def add_book_post():
    title = request.form['title']
    author = request.form['author']
    publisher = request.form.get('publisher')
    location = request.form.get('location')
    total_copies = request.form['total_copies']
    available_copies = total_copies
    category_id = request.form.get('category_id') or None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Books (title, author, publisher, location, total_copies, available_copies, category_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (title, author, publisher, location, total_copies,available_copies, category_id))
    conn.commit()
    cursor.close()

    flash("Book added successfully!", "success")
    return redirect(url_for('add_book'))

#Add member
@app.route('/member')
def members():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Members")
    members = cursor.fetchall()  # use DictCursor to get dicts
    return render_template('members.html', members=members)

# View Books
@app.route('/books')
def view_books():
    conn = get_connection()
    cursor = conn.cursor()

    query = """SELECT bc.copy_id, b.title
    FROM Book_Copies bc
    JOIN Books b ON b.title = bc.title
    WHERE bc.status = 'available';
    """

    cursor.execute(query)
    books = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('books.html', books=books)

# Display the Issue/Return page
@app.route('/issue_return', methods=['GET'])
def issue_return():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get all members
    cursor.execute("SELECT member_id, name FROM Members")
    members = cursor.fetchall()
    
    # Get all available books for issuing
    cursor.execute("""
        SELECT bc.copy_id, b.title 
        FROM Book_Copies bc 
        JOIN Books b ON bc.title = b.title 
        WHERE bc.status = 'available'
    """)
    available_books = cursor.fetchall()
    
    # Optionally, you could also get currently issued books for each member
    cursor.close()
    
    return render_template('issue_return.html', members=members, available_books=available_books)


# Handle issue or return action
@app.route('/issue_return', methods=['POST'])
def issue_return_post():
    member_id = request.form['member_id']
    copy_id = request.form['copy_id']
    action = request.form['action']  # 'issue' or 'return'
    librarian_id = session.get('librarian_id')

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT title FROM Book_Copies WHERE copy_id = %s", (copy_id,))
    book = cursor.fetchone()
    title = book['title']
    
    if action == 'issue':
        # Issue the book
        cursor.execute("""INSERT INTO Issued_books (copy_id,title,member_id,librarian_id,issue_date,due_date)
        VALUES (%s,%s,%s,%s,CURDATE(),DATE_ADD(CURDATE(),INTERVAL 7 DAY))""", (copy_id, title ,member_id,librarian_id))
        msg = "Book issued successfully."
        cursor.execute("UPDATE Book_Copies SET status='issued' WHERE copy_id=%s;", (copy_id,))
    elif action == 'return':
        # Return the book
        cursor.execute("""UPDATE Issued_Books SET return_date = CURDATE() WHERE copy_id = %s ORDER BY issue_date DESC LIMIT 1;""", (copy_id,))
        msg = "Book returned successfully."
        cursor.execute("UPDATE Book_Copies SET status='available'WHERE copy_id=%s;", (copy_id,))
    
    conn.commit()
    cursor.close()
    
    flash(msg)  # optional: show a message
    return redirect(url_for('issue_return'))

@app.route('/reports')
def reports():
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today()

    cursor.execute("""SELECT COUNT(*) FROM Issued_books WHERE DATE(issue_date) = %s""", (today,))
    issued_today = cursor.fetchone()['COUNT(*)']

    cursor.execute("""SELECT COUNT(*) FROM Issued_books WHERE DATE(return_date) = %s""", (today,))
    returned_today = cursor.fetchone()['COUNT(*)']

    cursor.execute("SELECT * FROM daily_report_view")
    daily_report = cursor.fetchall()

    cursor.execute("SELECT * FROM weekly_report_view")
    weekly_report = cursor.fetchall()

    cursor.execute("SELECT * FROM overdue_fines_view")
    overdue_report = cursor.fetchall()

    cursor.execute("SELECT * FROM overdue_30days_view")
    long_overdue_report = cursor.fetchall()

    cursor.close()
    return render_template(
        'report.html',
        issued_today = issued_today,
        returned_today = returned_today,
        daily_report=daily_report,
        weekly_report=weekly_report,
        overdue_report=overdue_report,
        long_overdue_report=long_overdue_report
    )

@app.route('/add_member', methods=['GET'])
def add_member():
    return render_template('add_member.html')

@app.route('/add_member', methods=['POST'])
def add_member_post():
    conn = get_connection()
    cursor = conn.cursor()

    name = request.form['name']
    email = request.form['email']
    phone = request.form['phone']
    address = request.form['address']
    membership_date = request.form['membership_date']

    cursor.execute("INSERT INTO Members (name, email, phone, address, membership_date) VALUES (%s, %s, %s, %s, %s)",
                (name, email, phone, address, membership_date))
    conn.commit()
    cursor.close()

    return redirect(url_for('members'))

@app.route('/profile/<int:member_id>')
def profile(member_id):
    conn = get_connection()
    cursor = conn.cursor()

    # Member details
    cursor.execute("SELECT * FROM Members WHERE member_id = %s", (member_id,))
    member = cursor.fetchone()

    # Borrowed + returned books
    cursor.execute("""
        SELECT ib.title, ib.issue_date, ib.due_date, ib.return_date
        FROM Issued_Books ib
        WHERE ib.member_id = %s
        ORDER BY ib.issue_date DESC
    """, (member_id,))
    transactions = cursor.fetchall()

    # Fines
    cursor.execute("""
        SELECT fine_amount, paid_status
        FROM Fines
        WHERE member_id = %s
    """, (member_id,))
    fines = cursor.fetchall()

    cursor.close()

    return render_template(
        'profile.html',
        member=member,
        transactions=transactions,
        fines=fines
    )

if __name__ == '__main__':
    app.run(debug=True)