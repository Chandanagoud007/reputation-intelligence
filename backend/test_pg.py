import psycopg2

conn = psycopg2.connect(
    host='127.0.0.1',
    port=5432,
    user='repuser',
    password='password123',
    database='reputation_db'
)
cursor = conn.cursor()
cursor.execute('SELECT 1')
print('Connected! Result:', cursor.fetchone())
conn.close()