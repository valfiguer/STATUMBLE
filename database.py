import sqlite3
import json
from datetime import datetime
import os

DB_FILE = "bumble_data.db"

def init_database():
    """Inicializar la base de datos con las tablas necesarias"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            age INTEGER NOT NULL,
            has_voted BOOLEAN NOT NULL,
            photo TEXT,
            timestamp TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            distance_short TEXT,
            online_status INTEGER,
            is_verified INTEGER,
            interests TEXT,
            education TEXT,
            height TEXT,
            smoking TEXT,
            drinking TEXT,
            exercise TEXT,
            pets TEXT,
            politics TEXT,
            religion TEXT,
            zodiac TEXT,
            dating_intentions TEXT,
            instagram_connected INTEGER,
            spotify_track TEXT,
            city TEXT,
            country TEXT
        )
    ''')
    
    # Tabla de sesiones (cookies)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cookies TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    # Tabla de configuración
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Tabla de estadísticas de sesión
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            likes_received INTEGER DEFAULT 0,
            likes_sent INTEGER DEFAULT 0,
            matches INTEGER DEFAULT 0,
            profiles_viewed INTEGER DEFAULT 0,
            session_duration INTEGER DEFAULT 0
        )
    ''')
    
    # Tabla de actividad/logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL,
            user_id TEXT,
            user_name TEXT,
            details TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


def save_user(user_info):
    """Guardar o actualizar un usuario en la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Verificar si el usuario ya existe
    cursor.execute('SELECT id, first_seen FROM users WHERE id = ?', (user_info['id'],))
    result = cursor.fetchone()
    
    # Convertir intereses a JSON string si es una lista
    interests = user_info.get('interests', [])
    if isinstance(interests, list):
        interests = json.dumps(interests, ensure_ascii=False)
    
    if result:
        # Actualizar usuario existente
        cursor.execute('''
            UPDATE users 
            SET name = ?, display_name = ?, age = ?, has_voted = ?, 
                photo = ?, timestamp = ?, last_seen = ?,
                distance_short = ?, online_status = ?, is_verified = ?,
                interests = ?, education = ?, height = ?, smoking = ?,
                drinking = ?, exercise = ?, pets = ?, politics = ?,
                religion = ?, zodiac = ?, dating_intentions = ?,
                instagram_connected = ?, spotify_track = ?, city = ?, country = ?
            WHERE id = ?
        ''', (
            user_info['name'],
            user_info['display_name'],
            user_info['age'],
            user_info['has_voted'],
            user_info.get('photo'),
            user_info['timestamp'],
            now,
            user_info.get('distance_short', ''),
            user_info.get('online_status', 0),
            user_info.get('is_verified', 0),
            interests,
            user_info.get('education', ''),
            user_info.get('height', ''),
            user_info.get('smoking', ''),
            user_info.get('drinking', ''),
            user_info.get('exercise', ''),
            user_info.get('pets', ''),
            user_info.get('politics', ''),
            user_info.get('religion', ''),
            user_info.get('zodiac', ''),
            user_info.get('dating_intentions', ''),
            user_info.get('instagram_connected', 0),
            user_info.get('spotify_track', ''),
            user_info.get('city', ''),
            user_info.get('country', ''),
            user_info['id']
        ))
    else:
        # Insertar nuevo usuario
        cursor.execute('''
            INSERT INTO users (id, name, display_name, age, has_voted, photo, timestamp, first_seen, last_seen,
                             distance_short, online_status, is_verified, interests, education, height,
                             smoking, drinking, exercise, pets, politics, religion, zodiac, dating_intentions,
                             instagram_connected, spotify_track, city, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_info['id'],
            user_info['name'],
            user_info['display_name'],
            user_info['age'],
            user_info['has_voted'],
            user_info.get('photo'),
            user_info['timestamp'],
            now,
            now,
            user_info.get('distance_short', ''),
            user_info.get('online_status', 0),
            user_info.get('is_verified', 0),
            interests,
            user_info.get('education', ''),
            user_info.get('height', ''),
            user_info.get('smoking', ''),
            user_info.get('drinking', ''),
            user_info.get('exercise', ''),
            user_info.get('pets', ''),
            user_info.get('politics', ''),
            user_info.get('religion', ''),
            user_info.get('zodiac', ''),
            user_info.get('dating_intentions', ''),
            user_info.get('instagram_connected', 0),
            user_info.get('spotify_track', ''),
            user_info.get('city', ''),
            user_info.get('country', '')
        ))
    
    conn.commit()
    conn.close()


def get_all_users():
    """Obtener todos los usuarios de la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users ORDER BY last_seen DESC')
    rows = cursor.fetchall()
    
    users = []
    for row in rows:
        # Parsear intereses de JSON string
        interests = row[12] if len(row) > 12 else '[]'
        if interests and isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except:
                interests = []
        
        users.append({
            'id': row[0],
            'name': row[1],
            'display_name': row[2],
            'age': row[3],
            'has_voted': row[4],
            'photo': row[5],
            'timestamp': row[6],
            'first_seen': row[7],
            'last_seen': row[8],
            'distance_short': row[9] if len(row) > 9 else '',
            'online_status': row[10] if len(row) > 10 else 0,
            'is_verified': row[11] if len(row) > 11 else 0,
            'interests': interests,
            'education': row[13] if len(row) > 13 else '',
            'height': row[14] if len(row) > 14 else '',
            'smoking': row[15] if len(row) > 15 else '',
            'drinking': row[16] if len(row) > 16 else '',
            'exercise': row[17] if len(row) > 17 else '',
            'pets': row[18] if len(row) > 18 else '',
            'politics': row[19] if len(row) > 19 else '',
            'religion': row[20] if len(row) > 20 else '',
            'zodiac': row[21] if len(row) > 21 else '',
            'dating_intentions': row[22] if len(row) > 22 else '',
            'instagram_connected': row[23] if len(row) > 23 else 0,
            'spotify_track': row[24] if len(row) > 24 else '',
            'city': row[25] if len(row) > 25 else '',
            'country': row[26] if len(row) > 26 else '',
            'detected_at': row[7] if len(row) > 7 else ''  # first_seen como detected_at
        })
    
    conn.close()
    return users


def get_recent_users(limit=50):
    """Obtener los usuarios más recientes"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users ORDER BY last_seen DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    
    users = []
    for row in rows:
        users.append({
            'id': row[0],
            'name': row[1],
            'display_name': row[2],
            'age': row[3],
            'has_voted': bool(row[4]),
            'photo': row[5],
            'timestamp': row[6],
            'first_seen': row[7],
            'last_seen': row[8]
        })
    
    conn.close()
    return users


def save_cookies(cookies):
    """Guardar cookies en la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    cookies_json = json.dumps(cookies)
    
    # Eliminar sesiones antiguas
    cursor.execute('DELETE FROM session')
    
    # Insertar nueva sesión
    cursor.execute('''
        INSERT INTO session (cookies, created_at, updated_at)
        VALUES (?, ?, ?)
    ''', (cookies_json, now, now))
    
    conn.commit()
    conn.close()


def load_cookies():
    """Cargar cookies desde la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT cookies FROM session ORDER BY id DESC LIMIT 1')
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return json.loads(result[0])
    return None


def delete_cookies():
    """Eliminar cookies de la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM session')
    
    conn.commit()
    conn.close()


def get_stats():
    """Obtener estadísticas de la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE has_voted = 0')
    new_likes = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE has_voted = 1')
    matches = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_verified = 1')
    verified = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE instagram_connected = 1')
    with_instagram = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE interests IS NOT NULL AND interests != '[]' AND interests != ''")
    with_interests = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total': total_users,
        'new_likes': new_likes,
        'matches': matches,
        'verified': verified,
        'with_instagram': with_instagram,
        'with_interests': with_interests
    }


def get_matches():
    """Obtener usuarios que son matches (has_voted = True)"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE has_voted = 1 ORDER BY last_seen DESC')
    rows = cursor.fetchall()
    
    users = []
    for row in rows:
        interests = row[12] if len(row) > 12 else '[]'
        if interests and isinstance(interests, str):
            try:
                interests = json.loads(interests)
            except:
                interests = []
        
        users.append({
            'id': row[0],
            'name': row[1],
            'display_name': row[2],
            'age': row[3],
            'has_voted': row[4],
            'photo': row[5],
            'timestamp': row[6],
            'first_seen': row[7],
            'last_seen': row[8],
            'distance_short': row[9] if len(row) > 9 else '',
            'online_status': row[10] if len(row) > 10 else 0,
            'is_verified': row[11] if len(row) > 11 else 0,
            'interests': interests,
            'city': row[25] if len(row) > 25 else '',
            'country': row[26] if len(row) > 26 else ''
        })
    
    conn.close()
    return users


def log_activity(action_type, user_id=None, user_name=None, details=None):
    """Registrar actividad en la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute('''
        INSERT INTO activity_log (timestamp, action_type, user_id, user_name, details)
        VALUES (?, ?, ?, ?, ?)
    ''', (now, action_type, user_id, user_name, details))
    
    conn.commit()
    conn.close()


def get_activity_log(limit=100):
    """Obtener log de actividad reciente"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    
    activities = []
    for row in rows:
        activities.append({
            'id': row[0],
            'timestamp': row[1],
            'action_type': row[2],
            'user_id': row[3],
            'user_name': row[4],
            'details': row[5]
        })
    
    conn.close()
    return activities


def save_daily_stats(likes_received=0, likes_sent=0, matches=0, profiles_viewed=0, session_duration=0):
    """Guardar estadísticas diarias"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Verificar si ya existe registro para hoy
    cursor.execute('SELECT id, likes_received, likes_sent, matches, profiles_viewed, session_duration FROM stats WHERE date = ?', (today,))
    result = cursor.fetchone()
    
    if result:
        # Actualizar registro existente (sumar valores)
        cursor.execute('''
            UPDATE stats SET 
                likes_received = likes_received + ?,
                likes_sent = likes_sent + ?,
                matches = matches + ?,
                profiles_viewed = profiles_viewed + ?,
                session_duration = session_duration + ?
            WHERE date = ?
        ''', (likes_received, likes_sent, matches, profiles_viewed, session_duration, today))
    else:
        # Crear nuevo registro
        cursor.execute('''
            INSERT INTO stats (date, likes_received, likes_sent, matches, profiles_viewed, session_duration)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (today, likes_received, likes_sent, matches, profiles_viewed, session_duration))
    
    conn.commit()
    conn.close()


def get_daily_stats(days=7):
    """Obtener estadísticas de los últimos N días"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM stats ORDER BY date DESC LIMIT ?', (days,))
    rows = cursor.fetchall()
    
    stats = []
    for row in rows:
        stats.append({
            'date': row[1],
            'likes_received': row[2],
            'likes_sent': row[3],
            'matches': row[4],
            'profiles_viewed': row[5],
            'session_duration': row[6]
        })
    
    conn.close()
    return stats


def clear_all_data():
    """Limpiar todos los datos de la base de datos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM users')
    cursor.execute('DELETE FROM session')
    
    conn.commit()
    conn.close()


# Migrar datos existentes si existen
def migrate_from_files():
    """Migrar datos de archivos pickle/json a la base de datos"""
    import pickle
    
    # Migrar history.json
    if os.path.exists('history.json'):
        try:
            with open('history.json', 'r') as f:
                users = json.load(f)
                for user in users:
                    save_user(user)
            print(f"✅ Migrados {len(users)} usuarios desde history.json")
            # Renombrar archivo para no volver a migrarlo
            os.rename('history.json', 'history.json.old')
        except Exception as e:
            print(f"Error migrando history.json: {e}")
    
    # Migrar cookies.pkl
    if os.path.exists('cookies.pkl'):
        try:
            with open('cookies.pkl', 'rb') as f:
                cookies = pickle.load(f)
                save_cookies(cookies)
            print(f"✅ Migradas {len(cookies)} cookies desde cookies.pkl")
            # Renombrar archivo
            os.rename('cookies.pkl', 'cookies.pkl.old')
        except Exception as e:
            print(f"Error migrando cookies.pkl: {e}")
