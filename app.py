import os
import sqlite3
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# --- Database Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'cdk_database.db')

def get_db():
    """Connect to the application's specific database."""
    db = sqlite3.connect(DATABASE, timeout=10) # Set a timeout
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """
    Initializes the database. This function is called during the build process.
    """
    print("--- Initializing database ---")
    if os.path.exists(DATABASE):
        print("Database file already exists. Skipping initialization.")
        return
    try:
        db = get_db()
        cursor = db.cursor()
        print("Creating tables...")
        cursor.execute('''
        CREATE TABLE cdk_codes (
            id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            is_claimed INTEGER NOT NULL DEFAULT 0
        )''')
        cursor.execute('''
        CREATE TABLE claim_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        print("Tables created.")
        cdk_file_path = os.path.join(BASE_DIR, 'cdk_list.txt')
        print(f"Loading CDKs from {cdk_file_path}...")
        with open(cdk_file_path, 'r') as f:
            cdks = [line.strip() for line in f if line.strip()]
            cursor.executemany("INSERT INTO cdk_codes (code) VALUES (?)", [(c,) for c in cdks])
        db.commit()
        print(f"Successfully loaded {len(cdks)} CDKs.")
        db.close()
        print("--- Database initialization complete ---")
    except Exception as e:
        print(f"\nAn error occurred during database initialization: {e}\n")
        exit(1)


# --- Application Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def get_status():
    """Correctly counts claimed and total CDKs."""
    with get_db() as db:
        claimed = db.execute("SELECT COUNT(id) FROM cdk_codes WHERE is_claimed = 1").fetchone()[0]
        total = db.execute("SELECT COUNT(id) FROM cdk_codes").fetchone()[0]
    return jsonify({'claimed': claimed, 'total': total})

@app.route('/claim', methods=['POST'])
def claim_cdk():
    """
    Handles the CDK claim request with a robust redemption (核销) mechanism.
    """
    data = request.get_json()
    user_ip = request.remote_addr
    user_fingerprint = data.get('fingerprint')

    if not user_fingerprint:
        return jsonify({'error': 'Fingerprint is missing. Please enable JavaScript.'}), 400

    db = get_db()
    # Use a transaction to ensure atomicity (all or nothing)
    try:
        with db:
            # 1. Check if the user has already claimed a key
            record = db.execute(
                "SELECT id FROM claim_records WHERE ip_address = ? OR fingerprint = ?",
                (user_ip, user_fingerprint)
            ).fetchone()
            if record:
                return jsonify({'error': 'You have already claimed a gift pack. One per person.'}), 429

            # 2. Find an unclaimed CDK, lock the row for update, and retrieve it
            # This is the core of the redemption logic
            unclaimed_code_row = db.execute(
                "SELECT id, code FROM cdk_codes WHERE is_claimed = 0 LIMIT 1"
            ).fetchone()

            if not unclaimed_code_row:
                return jsonify({'error': 'Sorry, all gift packs have been claimed!'}), 404
            
            cdk_id, cdk_code = unclaimed_code_row['id'], unclaimed_code_row['code']
            
            # 3. MARK THE CDK AS CLAIMED (The "核销" step)
            db.execute("UPDATE cdk_codes SET is_claimed = 1 WHERE id = ?", (cdk_id,))
            
            # 4. Log the claim record
            db.execute(
                "INSERT INTO claim_records (ip_address, fingerprint) VALUES (?, ?)",
                (user_ip, user_fingerprint)
            )
            
    except sqlite3.Error as e:
        # If any error occurs, the 'with db' block automatically rolls back the transaction
        return jsonify({'error': f'A database error occurred: {e}'}), 500
    finally:
        db.close()

    # 5. Return the successfully claimed code
    return jsonify({'success': True, 'cdk': cdk_code})

# This part allows us to run init_db from the command line during the build
if __name__ == '__main__':
    if os.environ.get('INIT_DB'):
        init_db()
    else:
        # This part is for local testing and not used by Gunicorn on Render
        # You could add init_db() here for easy local setup if needed
        app.run(host='0.0.0.0', port=8080)