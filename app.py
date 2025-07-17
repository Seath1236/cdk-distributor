import sqlite3
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'cdk_database.db')

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

@app.route('/')
def index():
    """渲染网站主页"""
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def get_status():
    """获取CDK发放状态"""
    db = get_db()
    claimed = db.execute("SELECT COUNT(*) FROM cdk_codes WHERE is_claimed = 1").fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM cdk_codes").fetchone()[0]
    db.close()
    return jsonify({'claimed': claimed, 'total': total})

@app.route('/claim', methods=['POST'])
def claim_cdk():
    """处理CDK领取请求，会同时检查IP和浏览器指纹"""
    data = request.get_json()
    user_ip = request.remote_addr
    user_fingerprint = data.get('fingerprint')

    if not user_fingerprint:
        return jsonify({'error': 'Fingerprint is missing. Please enable JavaScript.'}), 400

    db = get_db()
    
    # 1. 检查IP或浏览器指纹是否已经领取过
    record = db.execute(
        "SELECT id FROM claim_records WHERE ip_address = ? OR fingerprint = ?",
        (user_ip, user_fingerprint)
    ).fetchone()

    if record:
        db.close()
        return jsonify({'error': 'You have already claimed a gift pack. One per person.'}), 429

    # 2. 使用事务获取一个可用的CDK，防止并发问题
    try:
        with db: # 'with db' 会自动处理事务的开始、提交和回滚
            cursor = db.cursor()
            available_code_row = cursor.execute(
                "SELECT id, code FROM cdk_codes WHERE is_claimed = 0 LIMIT 1"
            ).fetchone()

            if not available_code_row:
                return jsonify({'error': 'Sorry, all gift packs have been claimed!'}), 404
            
            cdk_id, cdk_code = available_code_row['id'], available_code_row['code']

            # 3. 记录本次领取的IP和指纹
            cursor.execute(
                "INSERT INTO claim_records (ip_address, fingerprint) VALUES (?, ?)",
                (user_ip, user_fingerprint)
            )
            claim_id = cursor.lastrowid

            # 4. 标记CDK为已领取
            cursor.execute(
                "UPDATE cdk_codes SET is_claimed = 1, claimed_by_id = ? WHERE id = ?",
                (claim_id, cdk_id)
            )
            
    except sqlite3.Error as e:
        return jsonify({'error': f'A database error occurred: {e}'}), 500
    finally:
        db.close()

    return jsonify({'success': True, 'cdk': cdk_code})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)