import os
import sqlite3 # We keep this for the local fallback, but Render will use psycopg2
import psycopg2
from flask import Flask, jsonify, request, render_template
from urllib.parse import urlparse

app = Flask(__name__)

# --- Database Connection Logic ---
# It will use the DATABASE_URL from Render's environment variables.
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Connects to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Could not connect to PostgreSQL database: {e}")
        # In a real production app, you'd have more robust error handling here.
        raise e

def init_db():
    """Initializes the PostgreSQL database."""
    print("--- Initializing PostgreSQL database ---")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("Creating tables: cdk_codes and claim_records...")
        # Note: SERIAL is the PostgreSQL equivalent of AUTOINCREMENT
        cur.execute('''
        CREATE TABLE IF NOT EXISTS cdk_codes (
            id SERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            is_claimed BOOLEAN NOT NULL DEFAULT FALSE
        )''')
        cur.execute('''
        CREATE TABLE IF NOT EXISTS claim_records (
            id SERIAL PRIMARY KEY,
            ip_address TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            claimed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Check if codes are already loaded to prevent duplicate inserts on rebuild
        cur.execute("SELECT COUNT(id) FROM cdk_codes")
        count = cur.fetchone()[0]
        
        if count == 0:
            print("No codes found, loading from cdk_list.txt...")
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            cdk_file_path = os.path.join(BASE_DIR, 'cdk_list.txt')
            with open(cdk_file_path, 'r') as f:
                cdks = [line.strip() for line in f if line.strip()]
                # Use psycopg2's 'extras.execute_values' for efficient bulk insert if available,
                # otherwise, loop. A simple loop is fine for one-time setup.
                for cdk in cdks:
                    cur.execute("INSERT INTO cdk_codes (code) VALUES (%s)", (cdk,))
                print(f"Loaded {len(cdks)} CDKs.")
        else:
            print(f"Database already contains {count} codes. Skipping load.")

        conn.commit()
        cur.close()
        conn.close()
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
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(id) FROM cdk_codes WHERE is_claimed = TRUE")
            claimed = cur.fetchone()[0]
            cur.execute("SELECT COUNT(id) FROM cdk_codes")
            total = cur.fetchone()[0]
    return jsonify({'claimed': claimed, 'total': total})

@app.route('/claim', methods=['POST'])
def claim_cdk():
    data = request.get_json()
    user_ip = request.remote_addr
    user_fingerprint = data.get('fingerprint')

    if not user_fingerprint:
        return jsonify({'error': 'Fingerprint is missing.'}), 400

    conn = get_db_connection()
    try:
        # A transaction is automatically started with a cursor
        with conn.cursor() as cur:
            # 1. Check for existing claims
            cur.execute(
                "SELECT id FROM claim_records WHERE ip_address = %s OR fingerprint = %s",
                (user_ip, user_fingerprint)
            )
            if cur.fetchone():
                return jsonify({'error': 'You have already claimed a gift pack.'}), 429

            # 2. Atomically find and lock an unclaimed CDK
            # FOR UPDATE SKIP LOCKED is a robust way to handle concurrency
            cur.execute(
                "SELECT id, code FROM cdk_codes WHERE is_claimed = FALSE ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
            )
            unclaimed_code_row = cur.fetchone()

            if not unclaimed_code_row:
                return jsonify({'error': 'Sorry, all gift packs have been claimed!'}), 404
            
            cdk_id, cdk_code = unclaimed_code_row[0], unclaimed_code_row[1]
            
            # 3. Mark the CDK as claimed (The "核销" step)
            cur.execute("UPDATE cdk_codes SET is_claimed = TRUE WHERE id = %s", (cdk_id,))
            
            # 4. Log the claim
            cur.execute(
                "INSERT INTO claim_records (ip_address, fingerprint) VALUES (%s, %s)",
                (user_ip, user_fingerprint)
            )
            
            # Commit the transaction
            conn.commit()
            
    except Exception as e:
        conn.rollback()
        print(f"Transaction failed: {e}")
        return jsonify({'error': 'A server error occurred.'}), 500
    finally:
        conn.close()

    return jsonify({'success': True, 'cdk': cdk_code})

# This part allows us to run init_db from the command line
if __name__ == '__main__':
    if os.environ.get('INIT_DB'):
        init_db()
    else:
        # Default run command for Gunicorn
        # The 'app' variable is automatically detected by Gunicorn
        pass