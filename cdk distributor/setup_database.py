import sqlite3

# 连接或创建数据库文件
conn = sqlite3.connect('cdk_database.db')
cursor = conn.cursor()

# 1. 创建CDK码表
cursor.execute('''
CREATE TABLE IF NOT EXISTS cdk_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    is_claimed INTEGER NOT NULL DEFAULT 0,
    claimed_by_id INTEGER
)
''')

# 2. 创建领取记录表 (存储IP和浏览器指纹)
cursor.execute('''
CREATE TABLE IF NOT EXISTS claim_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# 为常用查询字段创建索引，可以提高查询速度
cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprint ON claim_records (fingerprint)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_address ON claim_records (ip_address)")

# 3. 从 cdk_list.txt 文件加载CDK
try:
    with open('cdk_list.txt', 'r') as f:
        cdks = [line.strip() for line in f if line.strip()]
        # 使用 INSERT OR IGNORE 防止因重复插入而已存在的代码而报错
        cursor.executemany("INSERT OR IGNORE INTO cdk_codes (code) VALUES (?)", [(c,) for c in cdks])
    print(f"成功加载或验证了 {len(cdks)} 个CDK到数据库。")
except FileNotFoundError:
    print("错误: 'cdk_list.txt' 文件未找到。请将它放在同一个目录下。")

# 提交更改并关闭连接
conn.commit()
conn.close()

print("数据库 'cdk_database.db' 已成功初始化。")