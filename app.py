import os
import sqlite3
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# --- Database Configuration ---
# Use an absolute path to ensure the db is found correctly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'cdk_database.db')

def get_db():
    """Connect to the application's specific database."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """
    Initializes the database from scratch.
    This function will create the tables and load the CDK codes from the text file.
    """
    print("--- Initializing database ---")
    if os.path.exists(DATABASE):
        print("Database file already exists. Skipping initialization.")
        return

    try:
        with app.app_context():
            db = get_db()
            cursor = db.cursor()

            print("Creating tables: cdk_codes and claim_records...")
            # 1. Create the table for CDK codes
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cdk_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                is_claimed INTEGER NOT NULL DEFAULT 0,
                claimed_by_id INTEGER
            )
            ''')

            # 2. Create the table for claim records
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS claim_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            print("Tables created successfully.")

            # 3. Load CDKs from cdk_list.txt
            cdk_file_path = os.path.join(BASE_DIR, 'cdk_list.txt')
            print(f"Looking for CDK file at: {cdk_file_path}")
            with open(cdk_file_path, 'r') as f:
                cdks = [line.strip() for line in f if line.strip()]
                cursor.executemany("INSERT OR IGNORE INTO cdk_codes (code) VALUES (?)", [(c,) for c in cdks])
            
            db.commit()
            print(f"Successfully loaded {len(cdks)} CDKs into the database.")
            db.close()
            print("--- Database initialization complete ---")

    except FileNotFoundError:
        print("\nFATAL ERROR: 'cdk_list.txt' not found. Please ensure it is in your GitHub repository.\n")
        # Exit with an error code to fail the build intentionally
        exit(1)
    except Exception as e:
        print(f"\nAn error occurred during database initialization: {e}\n")
        exit(1)


# --- Application Routes ---

@app.route('/')
def index():
    """Renders the main page."""
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def get_status():
    """Gets the current distribution status of CDKs."""
    db = get_db()
    claimed = db.execute("SELECT COUNT(*) FROM cdk_codes WHERE is_claimed = 1").fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM cdk_codes").fetchone()[0]
    db.close()
    return jsonify({'claimed': claimed, 'total': total})

@app.route('/claim', methods=['POST'])
def claim_cdk():
    """Handles the CDK claim request."""
    data = request.get_json()
    user_ip = request.remote_addr
    user_fingerprint = data.get('fingerprint')

    if not user_fingerprint:
        return jsonify({'error': 'Fingerprint is missing. Please enable JavaScript.'}), 400

    db = get_db()
    
    record = db.execute(
        "SELECT id FROM claim_records WHERE ip_address = ? OR fingerprint = ?",
        (user_ip, user_fingerprint)
    ).fetchone()

    if record:
        db.close()
        return jsonify({'error': 'You have already claimed a gift pack. One per person.'}), 429

    try:
        with db:
            cursor = db.cursor()
            available_code_row = cursor.execute(
                "SELECT id, code FROM cdk_codes WHERE is_claimed = 0 LIMIT 1"
            ).fetchone()

            if not available_code_row:
                return jsonify({'error': 'Sorry, all gift packs have been claimed!'}), 404
            
            cdk_id, cdk_code = available_code_row['id'], available_code_row['code']
            
            cursor.execute(
                "INSERT INTO claim_records (ip_address, fingerprint) VALUES (?, ?)",
                (user_ip, user_fingerprint)
            )
            claim_id = cursor.lastrowid
            
            cursor.execute(
                "UPDATE cdk_codes SET is_claimed = 1, claimed_by_id = ? WHERE id = ?",
                (claim_id, cdk_id)
            )
            
    except sqlite3.Error as e:
        return jsonify({'error': f'A database error occurred: {e}'}), 500
    finally:
        db.close()

    return jsonify({'success': True, 'cdk': cdk_code})

# This part allows us to run init_db from the command line during the build
if __name__ == '__main__':
    # Check if an environment variable is set to trigger initialization
    if os.environ.get('INIT_DB'):
        init_db()
    else:
        # This is for local testing, not used by Gunicorn on Render
        app.run(host='0.0.0.0', port=5000)