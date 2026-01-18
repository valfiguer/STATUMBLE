from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from time import sleep
from langdetect import detect
import json
import os
import threading
from datetime import datetime
import database as db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bumble-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Inicializar base de datos
db.init_database()
db.migrate_from_files()

# URLs que Bumble usa para obtener datos
DATA_URLS = [
    "SERVER_GET_ENCOUNTERS",
    "SERVER_GET_USER",
    "SERVER_GET_FILTERED_ENCOUNTERS",
    "SERVER_GET_CONNECTIONS",
    "SERVER_GET_MATCHES",
    "SERVER_GET_CONVERSATIONS",
    "SERVER_GET_CITY",
    "SERVER_UPDATE_LOCATION",
    "SERVER_APP_STATS",
    "encounters",
    "beeline",
    "connections",
    "matches",
    "conversations"
]
BUMBLE_URL = "https://bumble.com/app"

# Estado global
monitor_state = {
    'running': False,
    'driver': None,
    'users': [],
    'history': [],
    'start_time': None,
    'autolike_enabled': False,
    'autolike_delay': 3,  # segundos entre likes
    'autolike_count': 0
}


def load_history():
    """Cargar historial de usuarios desde la base de datos"""
    try:
        users = db.get_all_users()
        monitor_state['history'] = users
        log_message(f"Historial cargado: {len(users)} usuarios", 'info')
    except Exception as e:
        log_message(f"Error cargando historial: {str(e)}", 'warning')
        monitor_state['history'] = []


def save_history():
    """Guardar historial - no hace nada porque se guarda automáticamente en la BD"""
    pass  # Los datos se guardan automáticamente al usar db.save_user()


def add_to_history(user_info):
    """Agregar usuario al historial"""
    try:
        db.save_user(user_info)
        # Recargar historial desde la BD
        monitor_state['history'] = db.get_all_users()
        socketio.emit('history_update', {'total': len(monitor_state['history'])})
    except Exception as e:
        log_message(f"Error guardando en historial: {str(e)}", 'error')


def log_message(message, msg_type='info'):
    """Enviar mensaje de log a los clientes conectados"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Emojis y prefijos por tipo de log
    log_types = {
        'success': '✅',
        'error': '❌',
        'warning': '⚠️',
        'info': '🔵',
        'debug': '🔍',
        'chrome': '🌐',
        'api': '📡',
        'user': '👤'
    }
    
    emoji = log_types.get(msg_type, '💬')
    formatted_message = f"{emoji} {message}"
    
    # Imprimir en consola del servidor con formato
    print(f"[{timestamp}] {formatted_message}")
    
    socketio.emit('log', {
        'timestamp': timestamp,
        'message': formatted_message,
        'type': msg_type
    })


def update_stats():
    """Actualizar estadísticas en tiempo real"""
    socketio.emit('stats_update', {
        'total': len(monitor_state['users']),
        'elapsed_time': get_elapsed_time()
    })


def get_elapsed_time():
    """Calcular tiempo transcurrido"""
    if monitor_state['start_time']:
        elapsed = datetime.now() - monitor_state['start_time']
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return "00:00:00"


def create_cookies(driver):
    """Crear y guardar cookies"""
    log_message("Esperando inicio de sesión manual en Chrome...", 'chrome')
    log_message("Por favor, inicia sesión en Bumble", 'info')
    
    wait_time = 0
    while not driver.current_url.startswith(BUMBLE_URL) and monitor_state['running']:
        sleep(1)
        wait_time += 1
        if wait_time % 10 == 0:  # Cada 10 segundos
            log_message(f"Esperando... ({wait_time}s)", 'debug')
        
    if monitor_state['running']:
        cookies = driver.get_cookies()
        db.save_cookies(cookies)
        log_message("Sesión guardada exitosamente", 'success')
        log_message(f"{len(cookies)} cookies almacenadas en base de datos", 'debug')


def load_cookies(driver):
    """Cargar cookies guardadas"""
    log_message("Cargando sesión guardada...", 'info')
    cookies = db.load_cookies()
    if cookies:
        for cookie in cookies:
            driver.add_cookie(cookie)
        log_message(f"{len(cookies)} cookies cargadas correctamente", 'success')
    else:
        log_message("No se encontraron cookies guardadas", 'warning')


def get_likes(driver):
    """Obtener información de likes de los logs de performance"""
    try:
        sleep(1)
        logs = driver.get_log("performance")
        response_data = None
        found_urls = []
        processed_count = 0
        
        for log in logs:
            try:
                network_log = json.loads(log["message"])["message"]
                
                # Capturar todas las URLs para debugging
                if "Network.responseReceived" in network_log["method"]:
                    url = network_log["params"]["response"]["url"]
                    response = network_log["params"]["response"]
                    
                    if "bumble.com" in url and "mwebapi" in url:
                        found_urls.append(url)
                        
                        # Verificar que sea JSON y tenga contenido
                        mime_type = response.get("mimeType", "")
                        status = response.get("status", 0)
                        
                        # Solo intentar obtener si es JSON y exitoso
                        if "json" in mime_type.lower() and status == 200:
                            # Verificar si la URL contiene alguna de las palabras clave
                            if any(keyword in url for keyword in DATA_URLS):
                                try:
                                    # Pequeña espera para asegurar que la respuesta esté disponible
                                    sleep(0.5)
                                    
                                    request_id = network_log["params"]["requestId"]
                                    response_body = driver.execute_cdp_cmd(
                                        'Network.getResponseBody', 
                                        {'requestId': request_id}
                                    )
                                    
                                    if response_body and 'body' in response_body:
                                        # Extraer nombre corto de la API
                                        api_name = next((k for k in DATA_URLS if k in url), "API")
                                        log_message(f"Datos capturados de: {api_name}", 'api')
                                        process_response(response_body['body'], url)
                                        processed_count += 1
                                        
                                except Exception as e:
                                    # Solo loguear si es un error relevante
                                    error_msg = str(e)
                                    if "No data found" not in error_msg:
                                        log_message(f"Error obteniendo respuesta: {error_msg[:80]}", 'debug')
                                    continue
            except Exception as e:
                continue
        
        # Logging de URLs encontradas para debugging (solo ocasionalmente)
        if found_urls and len(found_urls) % 20 == 0:  # Cada 20 URLs
            unique_urls = list(set([url.split('/')[-1].split('?')[0] for url in found_urls]))
            log_message(f"{len(unique_urls)} endpoints únicos detectados | {processed_count} procesados", 'debug')
                
    except Exception as e:
        log_message(f"Error obteniendo datos: {str(e)[:100]}", 'error')


def process_response(response_data, url=""):
    """Procesar respuesta de la API de Bumble"""
    try:
        response = json.loads(response_data)
        
        # Intentar diferentes estructuras de respuesta
        results = None
        
        # Estructura 1: encounters
        if 'body' in response and isinstance(response['body'], list) and len(response['body']) > 0:
            body = response['body'][0]
            
            # Client encounters (principal para swipe/feed)
            if 'client_encounters' in body:
                results = body['client_encounters'].get('results', [])
            # Client user list (lista de usuarios, beeline)
            elif 'client_user_list' in body:
                user_list = body['client_user_list']
                if 'section' in user_list:
                    section = user_list['section']
                    if 'users' in section:
                        results = section['users']
                    elif 'items' in section:
                        results = section['items']
                elif 'users' in user_list:
                    results = user_list['users']
            # Encounters directo
            elif 'encounters' in body:
                results = body['encounters']
            # Sections (beeline alternativo)
            elif 'section' in body or 'sections' in body:
                sections = body.get('sections', [body.get('section', {})])
                for section in sections:
                    if isinstance(section, dict):
                        if 'users' in section:
                            results = section['users']
                            break
                        elif 'items' in section:
                            results = section['items']
                            break
            # User list directo
            elif 'users' in body:
                results = body['users']
            # Conversations/Matches
            elif 'results' in body:
                results = body['results']
            # Connections
            elif 'connections' in body:
                connections = body['connections']
                results = []
                for conn in connections:
                    if 'user' in conn:
                        user_data = {
                            'user': conn['user'],
                            'has_user_voted': conn.get('has_conversation', False) or conn.get('is_match', True)
                        }
                        results.append(user_data)
        
        # Estructura 2: directa
        if not results and 'encounters' in response:
            results = response['encounters']
            
        # Estructura 3: beeline
        if not results and 'beeline' in response:
            results = response['beeline']
        
        # Estructura 4: matches
        if not results and 'matches' in response:
            matches = response['matches']
            results = []
            for match in matches:
                if 'user' in match:
                    results.append({'user': match['user'], 'has_user_voted': True})
        
        # Estructura 5: conversations
        if not results and 'conversations' in response:
            conversations = response['conversations']
            results = []
            for conv in conversations:
                if 'person' in conv:
                    results.append({'user': conv['person'], 'has_user_voted': True})
                elif 'user' in conv:
                    results.append({'user': conv['user'], 'has_user_voted': True})
        
        if not results:
            return  # Sin datos relevantes
        
        log_message(f"✅ {len(results)} usuarios encontrados", 'api')
        
        new_users = 0
        for user_data in results:
            try:
                # Extraer información del usuario - manejar diferentes estructuras
                user = user_data.get('user', user_data)
                
                if not user or 'user_id' not in user:
                    continue
                
                user_id = user['user_id']
                
                # Verificar si ya existe
                if any(u['id'] == user_id for u in monitor_state['users']):
                    continue
                
                # Extraer foto
                photo = None
                if 'albums' in user and user['albums']:
                    if 'photos' in user['albums'][0] and user['albums'][0]['photos']:
                        photo_url = user['albums'][0]['photos'][0].get('large_url', '')
                        if photo_url:
                            photo = 'https://' + photo_url[2:] if photo_url.startswith('//') else photo_url
                
                # Extraer intereses de Facebook
                interests = []
                if 'interests' in user and user['interests']:
                    interests = [interest.get('name', '') for interest in user['interests'][:10]]  # Primeros 10
                
                # Extraer campos de perfil (profile_fields)
                profile_data = {
                    'education': '',
                    'height': '',
                    'smoking': '',
                    'drinking': '',
                    'exercise': '',
                    'pets': '',
                    'politics': '',
                    'religion': '',
                    'zodiac': '',
                    'dating_intentions': ''
                }
                
                if 'profile_fields' in user and user['profile_fields']:
                    for field in user['profile_fields']:
                        field_id = field.get('id', '')
                        display_value = field.get('display_value', '')
                        
                        if 'education' in field_id:
                            profile_data['education'] = display_value
                        elif 'height' in field_id:
                            profile_data['height'] = display_value
                        elif 'smoking' in field_id:
                            profile_data['smoking'] = display_value
                        elif 'drinking' in field_id:
                            profile_data['drinking'] = display_value
                        elif 'exercise' in field_id:
                            profile_data['exercise'] = display_value
                        elif 'pets' in field_id:
                            profile_data['pets'] = display_value
                        elif 'politics' in field_id:
                            profile_data['politics'] = display_value
                        elif 'religion' in field_id:
                            profile_data['religion'] = display_value
                        elif 'zodiak' in field_id:
                            profile_data['zodiac'] = display_value
                        elif 'dating_intentions' in field_id:
                            profile_data['dating_intentions'] = display_value
                
                # Extraer ciudad y país
                city = user.get('city', {}).get('name', '') if 'city' in user else ''
                country = user.get('country', {}).get('name', '') if 'country' in user else ''
                
                # Extraer distancia
                distance_short = user.get('distance_short', '')
                
                # Estado online
                online_status = user.get('online_status', 0)
                
                # Verificado
                is_verified = user.get('is_verified', False)
                
                # Instagram conectado
                instagram_connected = False
                if 'albums' in user:
                    for album in user['albums']:
                        if album.get('album_type') == 12 and album.get('external_provider') == 12:
                            instagram_connected = True
                            break
                
                # Spotify
                spotify_track = ''
                if 'spotify_mood_song' in user and user['spotify_mood_song']:
                    track = user['spotify_mood_song']
                    if 'name' in track:
                        spotify_track = f"{track.get('name', '')} - {track.get('artist_name', '')}"
                
                # Determinar si ya votaste (matches y conversaciones cuentan como votado)
                has_voted = user_data.get('has_user_voted', False)
                if not has_voted:
                    # Si viene de connections/matches/conversations, marcar como votado
                    has_voted = 'connections' in url.lower() or 'matches' in url.lower() or 'conversation' in url.lower()
                
                user_info = {
                    'id': user_id,
                    'name': user.get('name', 'Usuario'),
                    'age': user.get('age', 0),
                    'has_voted': has_voted,
                    'photo': photo,
                    'timestamp': datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
                    'interests': interests,
                    'distance_short': distance_short,
                    'online_status': online_status,
                    'is_verified': is_verified,
                    'instagram_connected': instagram_connected,
                    'spotify_track': spotify_track,
                    'city': city,
                    'country': country,
                    **profile_data
                }
                
                # Detectar idioma para nombres en hebreo
                display_name = user_info['name']
                try:
                    if detect(display_name) == 'he':
                        display_name = display_name[::-1]
                except:
                    pass
                
                user_info['display_name'] = display_name
                monitor_state['users'].append(user_info)
                new_users += 1
                
                # Agregar al historial
                add_to_history(user_info)
                
                # Determinar tipo de usuario
                user_type = "Match" if has_voted else "Like Nuevo"
                
                # Registrar actividad en la base de datos
                try:
                    action_type = 'match' if has_voted else 'like_received'
                    details = f"{user_info['age']} años, {city or 'ubicación desconocida'}"
                    if user_info.get('is_verified'):
                        details += ", verificada"
                    db.log_activity(action_type, user_id, display_name, details)
                except:
                    pass
                
                # Log con más información
                location_info = f"{city}" if city else "Ubicación desconocida"
                if distance_short:
                    location_info += f" ({distance_short})"
                
                log_message(f"{display_name}, {user_info['age']} años - {location_info} [{user_type}]", 'user')
                
                # Enviar nuevo usuario a los clientes
                socketio.emit('new_user', user_info)
            
            except Exception as e:
                log_message(f"⚠️ Error procesando usuario: {str(e)}", 'warning')
                continue
        
        if new_users > 0:
            update_stats()
            log_message(f"+{new_users} usuarios nuevos agregados", 'success')
                
    except Exception as e:
        log_message(f"Error procesando respuesta: {str(e)[:80]}", 'error')


def load_existing_data(driver):
    """Cargar likes y matches existentes navegando por las secciones"""
    try:
        log_message("Cargando datos históricos...", 'info')
        
        # Navegar a la página de matches/beeline
        log_message("Navegando a Conexiones...", 'chrome')
        driver.get("https://bumble.com/app/connections")
        sleep(4)
        
        # Capturar datos iniciales
        log_message("Analizando Conexiones...", 'api')
        get_likes(driver)
        sleep(2)
        
        # Scroll para cargar más contenido
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(2)
            get_likes(driver)
        except:
            pass
        
        # Navegar a la sección de likes (beeline)
        try:
            log_message("Navegando a Beeline (personas que te dieron like)...", 'chrome')
            driver.get("https://bumble.com/app/beeline")
            sleep(4)
            log_message("Analizando Beeline...", 'api')
            get_likes(driver)
            sleep(2)
            
            # Scroll en beeline
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                sleep(2)
                get_likes(driver)
            except:
                pass
        except Exception as e:
            log_message(f"No se pudo acceder a Beeline: {str(e)[:50]}", 'warning')
        
        # Volver al feed principal
        log_message("Volviendo al feed principal...", 'chrome')
        driver.get("https://bumble.com/app")
        sleep(3)
        
        log_message(f"Carga histórica completada - {len(monitor_state['users'])} usuarios totales", 'success')
        
    except Exception as e:
        log_message(f"Error cargando datos históricos: {str(e)[:80]}", 'warning')


def monitor_thread():
    """Thread principal de monitoreo"""
    try:
        log_message("=" * 50, 'info')
        log_message("INICIANDO MONITOR DE BUMBLE", 'info')
        log_message("=" * 50, 'info')
        
        log_message("Abriendo navegador Chrome...", 'chrome')
        
        # Configurar Chrome
        chrome_options = Options()
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_experimental_option("detach", True)
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        
        monitor_state['driver'] = webdriver.Chrome(options=chrome_options)
        monitor_state['driver'].get(BUMBLE_URL)
        sleep(2)
        
        # Manejar cookies
        cookies = db.load_cookies()
        if cookies:
            log_message("Sesión guardada encontrada", 'success')
            load_cookies(monitor_state['driver'])
            monitor_state['driver'].refresh()
            sleep(2)
        else:
            log_message("Primera ejecución detectada", 'warning')
            log_message("Inicia sesión manualmente en Chrome", 'warning')
            create_cookies(monitor_state['driver'])
        
        log_message("Monitor activo y funcionando", 'success')
        socketio.emit('status_update', {'status': 'running'})
        
        # Cargar datos históricos primero
        log_message("-" * 50, 'info')
        log_message("FASE 1: Cargando datos históricos", 'info')
        log_message("-" * 50, 'info')
        load_existing_data(monitor_state['driver'])
        
        log_message("-" * 50, 'info')
        log_message("FASE 2: Monitoreo en tiempo real activo", 'info')
        log_message("Navega por Bumble para detectar quién te dio like", 'info')
        log_message("-" * 50, 'info')
        
        initial_page_source = monitor_state['driver'].page_source if monitor_state['driver'] else ''
        check_counter = 0
        autolike_counter = 0
        
        while monitor_state['running']:
            # Verificar que el driver sigue activo
            if not monitor_state['driver']:
                log_message("Driver no disponible, deteniendo...", 'error')
                break
            
            try:
                # Verificar que Chrome sigue abierto
                if not monitor_state['driver'].service.process:
                    log_message("Chrome se cerró, deteniendo monitor...", 'warning')
                    break
            except:
                log_message("Error verificando Chrome, deteniendo...", 'error')
                break
            
            # Actualizar tiempo
            update_stats()
            
            # Verificar logs cada vez
            check_counter += 1
            if check_counter % 2 == 0 and monitor_state['driver']:  # Cada 2 segundos
                try:
                    get_likes(monitor_state['driver'])
                except Exception as e:
                    log_message(f"Error obteniendo datos: {str(e)[:50]}", 'debug')
            
            # Autolike si está activado
            if monitor_state['autolike_enabled'] and monitor_state['driver']:
                autolike_counter += 1
                # Ejecutar autolike según el delay configurado
                if autolike_counter >= monitor_state['autolike_delay']:
                    autolike_counter = 0
                    try:
                        # Sistema de autolike mejorado con múltiples estrategias
                        script = """
                            (function() {
                                let likeBtn = null;
                                let method = '';
                                
                                // ======== ESTRATEGIAS DE DETECCIÓN ========
                                
                                // Estrategia 1: data-qa-role (más confiable en Bumble 2024-2026)
                                likeBtn = document.querySelector('[data-qa-role="encounters-action-like"]');
                                if (likeBtn) method = 'data-qa-role';
                                
                                // Estrategia 2: Clase encounters-action--like
                                if (!likeBtn) {
                                    likeBtn = document.querySelector('.encounters-action--like');
                                    if (likeBtn) method = 'encounters-action-class';
                                }
                                
                                // Estrategia 3: aria-label específico
                                if (!likeBtn) {
                                    const ariaSelectors = [
                                        '[aria-label="Me gusta"]',
                                        '[aria-label="Like"]', 
                                        '[aria-label="Yes"]',
                                        '[aria-label*="like" i]',
                                        '[aria-label*="gusta" i]'
                                    ];
                                    for (let sel of ariaSelectors) {
                                        likeBtn = document.querySelector(sel);
                                        if (likeBtn) {
                                            method = 'aria-label';
                                            break;
                                        }
                                    }
                                }
                                
                                // Estrategia 4: Icono floating-action-yes
                                if (!likeBtn) {
                                    const likeIcon = document.querySelector('[data-qa-icon-name="floating-action-yes"]');
                                    if (likeIcon) {
                                        likeBtn = likeIcon.closest('[role="button"], button, .encounters-action');
                                        if (likeBtn) method = 'floating-action-icon';
                                    }
                                }
                                
                                // Estrategia 5: Contenedor encounters-controls con múltiples botones
                                if (!likeBtn) {
                                    const containers = [
                                        '.encounters-controls__action',
                                        '.encounters-controls',
                                        '.encounters-action-buttons'
                                    ];
                                    for (let cont of containers) {
                                        const actions = document.querySelectorAll(cont + ' [role="button"]');
                                        if (actions.length >= 2) {
                                            // El like suele ser el último o segundo botón
                                            likeBtn = actions[actions.length - 1] || actions[1];
                                            method = 'encounters-controls-container';
                                            break;
                                        }
                                    }
                                }
                                
                                // Estrategia 6: Buscar botones con SVG de corazón o checkmark
                                if (!likeBtn) {
                                    const buttons = document.querySelectorAll('[role="button"], button');
                                    for (let btn of buttons) {
                                        const svg = btn.querySelector('svg');
                                        if (svg) {
                                            const path = svg.innerHTML.toLowerCase();
                                            // Buscar paths típicos de corazón o checkmark
                                            if (path.includes('heart') || path.includes('check') || 
                                                path.includes('m12') || path.includes('like')) {
                                                // Verificar que no sea el de superlike (estrella)
                                                if (!path.includes('star')) {
                                                    likeBtn = btn;
                                                    method = 'svg-heart';
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // Estrategia 7: Color verde característico de Bumble
                                if (!likeBtn) {
                                    const buttons = Array.from(document.querySelectorAll('[role="button"], button'));
                                    for (let btn of buttons) {
                                        const style = window.getComputedStyle(btn);
                                        const bgColor = style.backgroundColor || '';
                                        const color = style.color || '';
                                        // Verde de Bumble: rgb(0, 217, 95) o similar
                                        if (bgColor.includes('0, 217, 95') || color.includes('0, 217, 95') ||
                                            bgColor.includes('0,217,95') || bgColor.includes('rgb(0, 210') ||
                                            bgColor.includes('rgb(76, 217') || bgColor.includes('#00d95f')) {
                                            likeBtn = btn;
                                            method = 'green-color';
                                            break;
                                        }
                                    }
                                }
                                
                                // Estrategia 8: Keyboard shortcut simulation
                                if (!likeBtn) {
                                    // Algunos sitios responden a tecla de flecha derecha o Enter
                                    const encounter = document.querySelector('.encounter, .encounters-story-profile');
                                    if (encounter) {
                                        // Marcar que intentamos keyboard
                                        method = 'keyboard-fallback';
                                    }
                                }
                                
                                // ======== VERIFICACIÓN Y CLIC ========
                                
                                if (likeBtn) {
                                    // Verificar que esté habilitado
                                    const isDisabled = likeBtn.disabled || 
                                                      likeBtn.getAttribute('aria-disabled') === 'true' ||
                                                      likeBtn.getAttribute('tabindex') === '-1' ||
                                                      likeBtn.classList.contains('disabled');
                                    
                                    if (!isDisabled) {
                                        // Simular interacción más natural
                                        likeBtn.focus();
                                        
                                        // Dispatch eventos para mejor compatibilidad
                                        const events = ['mouseenter', 'mouseover', 'mousedown', 'mouseup', 'click'];
                                        events.forEach(eventType => {
                                            const event = new MouseEvent(eventType, {
                                                view: window,
                                                bubbles: true,
                                                cancelable: true
                                            });
                                            likeBtn.dispatchEvent(event);
                                        });
                                        
                                        return JSON.stringify({status: 'clicked', method: method});
                                    }
                                    return JSON.stringify({status: 'disabled', method: method});
                                }
                                
                                // Información de debug
                                const debugInfo = {
                                    hasEncounters: !!document.querySelector('.encounters'),
                                    hasControls: !!document.querySelector('.encounters-controls'),
                                    buttonCount: document.querySelectorAll('[role="button"]').length,
                                    url: window.location.pathname
                                };
                                
                                return JSON.stringify({status: 'not_found', debug: debugInfo});
                            })();
                        """
                        result_str = monitor_state['driver'].execute_script(script)
                        result = json.loads(result_str) if result_str else {'status': 'error'}
                        
                        if result.get('status') == 'clicked':
                            monitor_state['autolike_count'] += 1
                            method_used = result.get('method', 'unknown')
                            log_message(f"✅ Autolike #{monitor_state['autolike_count']} enviado (método: {method_used})", 'success')
                            
                            # Registrar en activity log
                            try:
                                db.log_activity('autolike', None, None, f"Autolike #{monitor_state['autolike_count']} via {method_used}")
                            except:
                                pass
                            
                            socketio.emit('autolike_status', {
                                'enabled': monitor_state['autolike_enabled'],
                                'delay': monitor_state['autolike_delay'],
                                'count': monitor_state['autolike_count']
                            })
                            
                        elif result.get('status') == 'disabled':
                            if autolike_counter % 5 == 0:
                                log_message(f"⏸ Botón encontrado ({result.get('method')}) pero deshabilitado", 'debug')
                                
                        else:
                            # Log debug info cada 10 intentos
                            if autolike_counter % 10 == 0:
                                debug = result.get('debug', {})
                                log_message(f"🔍 Buscando botón... (encounters:{debug.get('hasEncounters')}, buttons:{debug.get('buttonCount')})", 'debug')
                                
                    except Exception as e:
                        log_message(f"Error en autolike: {str(e)[:50]}", 'debug')
            
            # También verificar cambios en la página
            try:
                if monitor_state['driver']:
                    current_page_source = monitor_state['driver'].page_source
                    
                    if current_page_source != initial_page_source:
                        log_message("Cambio en la página detectado, analizando...", 'debug')
                        get_likes(monitor_state['driver'])
                        initial_page_source = current_page_source
            except Exception as e:
                log_message(f"Error leyendo página: {str(e)[:30]}", 'debug')
                
            sleep(1)
            
    except Exception as e:
        log_message(f"Error crítico: {str(e)[:100]}", 'error')
        socketio.emit('status_update', {'status': 'error', 'message': str(e)})
    finally:
        if monitor_state['running']:
            stop_monitoring()


def stop_monitoring():
    """Detener el monitoreo"""
    log_message("=" * 50, 'info')
    log_message("DETENIENDO MONITOR", 'warning')
    log_message("=" * 50, 'info')
    
    monitor_state['running'] = False
    
    if monitor_state['driver']:
        try:
            monitor_state['driver'].quit()
            log_message("Chrome cerrado correctamente", 'success')
        except:
            log_message("Error al cerrar Chrome", 'warning')
        monitor_state['driver'] = None
    
    log_message(f"Sesión finalizada - {len(monitor_state['users'])} usuarios totales", 'info')
    socketio.emit('status_update', {'status': 'stopped'})
    log_message("⏸️ Monitoreo detenido", 'warning')


def enrich_profiles():
    """Enriquecer perfiles con datos completos abriendo cada uno"""
    if not monitor_state['running'] or not monitor_state['driver']:
        log_message("Monitor no está activo", 'error')
        return
    
    driver = monitor_state['driver']
    
    try:
        # Obtener usuarios sin datos completos (sin intereses)
        users_to_enrich = db.get_all_users()
        incomplete_users = [u for u in users_to_enrich if not u.get('interests') or u.get('interests') == '[]']
        
        if not incomplete_users:
            log_message("✅ Todos los usuarios ya tienen datos completos", 'success')
            socketio.emit('enrich_complete', {'completed': 0, 'total': 0})
            return
        
        total = len(incomplete_users)
        log_message(f"🔍 Enriqueciendo {total} perfiles con datos completos...", 'info')
        socketio.emit('enrich_started', {'total': total})
        
        # Navegar a beeline
        log_message("🌐 Navegando a la sección de personas que te dieron like...", 'chrome')
        driver.get("https://bumble.com/app/beeline")
        sleep(3)
        
        completed = 0
        for index, user in enumerate(incomplete_users, 1):
            try:
                user_id = user['id']
                user_name = user.get('name', 'Desconocido')
                
                log_message(f"📂 [{index}/{total}] Abriendo perfil de {user_name}...", 'info')
                socketio.emit('enrich_progress', {
                    'current': index,
                    'total': total,
                    'name': user_name,
                    'completed': completed
                })
                
                # Buscar y hacer clic en la card del usuario
                # Bumble usa article tags para las cards de usuarios
                script = f"""
                    const articles = document.querySelectorAll('article');
                    for (let article of articles) {{
                        if (article.textContent.includes('{user_name}')) {{
                            article.click();
                            return true;
                        }}
                    }}
                    
                    // Alternativa: buscar por cualquier elemento clickeable que contenga el nombre
                    const elements = document.querySelectorAll('[role="button"], button, a');
                    for (let el of elements) {{
                        if (el.textContent.includes('{user_name}')) {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                """
                
                clicked = driver.execute_script(script)
                
                if not clicked:
                    log_message(f"⚠️ No se pudo abrir perfil de {user_name}", 'warning')
                    continue
                
                # Esperar a que se abra el modal y se carguen los datos
                sleep(2)
                
                # Intentar capturar datos del perfil abierto
                # La API devuelve los datos completos al abrir un perfil
                profile_captured = False
                for _ in range(5):  # Intentar durante 5 segundos
                    try:
                        logs = driver.get_log('performance')
                        for entry in logs:
                            try:
                                log_entry = json.loads(entry['message'])
                                message = log_entry.get('message', {})
                                
                                if message.get('method') == 'Network.responseReceived':
                                    response_url = message.get('params', {}).get('response', {}).get('url', '')
                                    
                                    # Buscar llamadas que traigan datos del usuario
                                    if any(keyword in response_url.lower() for keyword in ['user', 'profile', 'encounters']):
                                        request_id = message.get('params', {}).get('requestId')
                                        
                                        try:
                                            response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                            body = json.loads(response_body['body'])
                                            
                                            # Procesar si contiene datos del usuario
                                            if isinstance(body, dict):
                                                # Buscar el usuario en diferentes estructuras
                                                user_data = None
                                                if 'user' in body:
                                                    user_data = body['user']
                                                elif 'profile' in body:
                                                    user_data = body['profile']
                                                elif 'results' in body and body['results']:
                                                    for result in body['results']:
                                                        if result.get('user', {}).get('user_id') == user_id:
                                                            user_data = result.get('user')
                                                            break
                                                
                                                if user_data and user_data.get('user_id') == user_id:
                                                    # Actualizar usuario con datos completos
                                                    process_response(body)
                                                    profile_captured = True
                                                    completed += 1
                                                    log_message(f"✅ Datos de {user_name} actualizados", 'success')
                                                    break
                                        except:
                                            pass
                            except:
                                pass
                    except:
                        pass
                    
                    if profile_captured:
                        break
                    sleep(1)
                
                if not profile_captured:
                    log_message(f"⚠️ No se pudieron capturar datos de {user_name}", 'warning')
                
                # Cerrar el modal (ESC)
                driver.find_element('tag name', 'body').send_keys('\ue00c')  # ESC key
                sleep(1)
                
            except Exception as e:
                log_message(f"❌ Error con {user_name}: {str(e)[:50]}", 'error')
                continue
        
        log_message(f"✅ Enriquecimiento completado: {completed}/{total} perfiles actualizados", 'success')
        socketio.emit('enrich_complete', {'completed': completed, 'total': total})
        
        # Volver al feed principal
        driver.get("https://bumble.com/app")
        sleep(2)
        
    except Exception as e:
        log_message(f"❌ Error en enriquecimiento: {str(e)}", 'error')
        socketio.emit('enrich_error', {'error': str(e)})


@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')


@app.route('/historial')
def historial():
    """Página de historial completo"""
    return render_template('historial.html')


@app.route('/matches')
def matches_page():
    """Página de matches"""
    return render_template('matches.html')


@app.route('/stats')
def stats_page():
    """Página de estadísticas"""
    return render_template('stats.html')


@socketio.on('get_matches')
def handle_get_matches():
    """Obtener matches"""
    matches = db.get_matches()
    emit('matches_data', {'matches': matches})


@socketio.on('get_full_stats')
def handle_get_full_stats():
    """Obtener estadísticas completas"""
    stats = db.get_stats()
    all_users = db.get_all_users()
    
    # Distribución por edad
    age_distribution = {}
    city_distribution = {}
    
    for user in all_users:
        age = user.get('age', 0)
        if age > 0:
            age_distribution[age] = age_distribution.get(age, 0) + 1
        
        city = user.get('city', '')
        if city:
            city_distribution[city] = city_distribution.get(city, 0) + 1
    
    # Actividad reciente
    recent_activity = db.get_activity_log(50)
    
    emit('full_stats', {
        'stats': stats,
        'age_distribution': age_distribution,
        'city_distribution': city_distribution,
        'recent_activity': recent_activity,
        'autolike_count': monitor_state['autolike_count']
    })


@socketio.on('start_monitoring')
def handle_start_monitoring():
    """Iniciar monitoreo"""
    if not monitor_state['running']:
        monitor_state['running'] = True
        monitor_state['start_time'] = datetime.now()
        
        # Cargar historial al iniciar
        load_history()
        
        log_message("🚀 Iniciando sistema de monitoreo...", 'info')
        
        # Iniciar thread de monitoreo
        thread = threading.Thread(target=monitor_thread, daemon=True)
        thread.start()
        
        emit('status_update', {'status': 'starting'})


@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    """Detener monitoreo"""
    stop_monitoring()


@socketio.on('clear_data')
def handle_clear_data():
    """Limpiar datos"""
    monitor_state['users'] = []
    log_message("🗑️ Datos limpiados", 'info')
    emit('data_cleared', broadcast=True)
    update_stats()


@socketio.on('reset_cookies')
def handle_reset_cookies():
    """Resetear cookies"""
    try:
        db.delete_cookies()
        log_message("🔄 Cookies eliminadas. Necesitarás iniciar sesión nuevamente", 'warning')
        emit('cookies_reset', {'success': True})
    except Exception as e:
        log_message(f"⚠️ Error eliminando cookies: {str(e)}", 'error')
        emit('cookies_reset', {'success': False, 'message': 'Error eliminando cookies'})


@socketio.on('get_users')
def handle_get_users():
    """Enviar lista de usuarios actual"""
    emit('users_list', {'users': monitor_state['users']})


@socketio.on('enrich_profiles')
def handle_enrich_profiles():
    """Iniciar enriquecimiento de perfiles"""
    if not monitor_state['running']:
        emit('enrich_error', {'error': 'El monitor debe estar activo'})
        return
    
    # Ejecutar en un hilo separado para no bloquear
    thread = threading.Thread(target=enrich_profiles)
    thread.daemon = True
    thread.start()


@socketio.on('get_history')
def handle_get_history():
    """Enviar historial de usuarios"""
    # Obtener todos los usuarios de la base de datos
    all_users = db.get_all_users()
    
    # Convertir a formato compatible con el frontend
    users_data = []
    for user in all_users:
        user_dict = {
            'id': user.get('id'),
            'name': user.get('name'),
            'age': user.get('age'),
            'photo': user.get('photo'),
            'interests': user.get('interests'),
            'education': user.get('education'),
            'politics': user.get('politics'),
            'religion': user.get('religion'),
            'height': user.get('height'),
            'smoking': user.get('smoking'),
            'drinking': user.get('drinking'),
            'exercise': user.get('exercise'),
            'pets': user.get('pets'),
            'zodiac': user.get('zodiac'),
            'dating_intentions': user.get('dating_intentions'),
            'instagram_connected': user.get('instagram_connected'),
            'spotify_track': user.get('spotify_track'),
            'city': user.get('city'),
            'country': user.get('country'),
            'distance_short': user.get('distance_short'),
            'online_status': user.get('online_status'),
            'is_verified': user.get('is_verified'),
            'detected_at': user.get('detected_at', datetime.now().isoformat())
        }
        users_data.append(user_dict)
    
    # Enviar al frontend
    emit('history_data', {'users': users_data})
    emit('history_list', {'history': monitor_state['history']})


@socketio.on('toggle_autolike')
def handle_toggle_autolike(data):
    """Activar/desactivar autolike"""
    monitor_state['autolike_enabled'] = data.get('enabled', False)
    monitor_state['autolike_delay'] = data.get('delay', 3)
    
    status = "activado" if monitor_state['autolike_enabled'] else "desactivado"
    log_message(f"Autolike {status} (delay: {monitor_state['autolike_delay']}s)", 
                'success' if monitor_state['autolike_enabled'] else 'warning')
    
    emit('autolike_status', {
        'enabled': monitor_state['autolike_enabled'],
        'delay': monitor_state['autolike_delay'],
        'count': monitor_state['autolike_count']
    }, broadcast=True)


@socketio.on('do_autolike')
def handle_do_autolike():
    """Ejecutar un autolike manualmente"""
    if monitor_state['driver']:
        try:
            # Múltiples selectores para encontrar el botón de like
            script = """
                // Intentar múltiples selectores
                let likeBtn = null;
                
                // Selector 1: Por data attribute
                likeBtn = document.querySelector('[data-qa-icon-name="like"]')?.closest('button');
                
                // Selector 2: Por aria-label
                if (!likeBtn) {
                    likeBtn = document.querySelector('button[aria-label*="like" i], button[aria-label*="yes" i]');
                }
                
                // Selector 3: Por clase de Bumble
                if (!likeBtn) {
                    likeBtn = document.querySelector('.encounters-action--like, button.encounters-action');
                }
                
                // Selector 4: Buscar SVG de corazón
                if (!likeBtn) {
                    const heartIcon = Array.from(document.querySelectorAll('svg')).find(svg => {
                        const path = svg.querySelector('path[d*="M12"]');
                        return path !== null;
                    });
                    if (heartIcon) {
                        likeBtn = heartIcon.closest('button');
                    }
                }
                
                if (likeBtn && !likeBtn.disabled && !likeBtn.getAttribute('aria-disabled')) {
                    likeBtn.click();
                    return true;
                }
                return false;
            """
            result = monitor_state['driver'].execute_script(script)
            
            if result:
                monitor_state['autolike_count'] += 1
                log_message(f"Like manual enviado (#{monitor_state['autolike_count']})", 'success')
                emit('autolike_status', {
                    'enabled': monitor_state['autolike_enabled'],
                    'delay': monitor_state['autolike_delay'],
                    'count': monitor_state['autolike_count']
                }, broadcast=True)
            else:
                log_message("No se encontró botón de like en la página actual", 'warning')
        except Exception as e:
            log_message(f"Error en autolike manual: {str(e)[:80]}", 'error')


@socketio.on('connect')
def handle_connect():
    """Cliente conectado"""
    log_message("👋 Cliente conectado", 'info')
    # Cargar historial si no está cargado
    if not monitor_state['history']:
        load_history()
    
    # Si no hay usuarios activos, usar los más recientes del historial
    users_to_send = monitor_state['users'] if monitor_state['users'] else monitor_state['history'][:50]
    
    # Enviar estado actual
    emit('users_list', {'users': users_to_send})
    emit('history_list', {'history': monitor_state['history']})
    emit('status_update', {
        'status': 'running' if monitor_state['running'] else 'stopped'
    })
    emit('autolike_status', {
        'enabled': monitor_state['autolike_enabled'],
        'delay': monitor_state['autolike_delay'],
        'count': monitor_state['autolike_count']
    })
    update_stats()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🐝 BUMBLE LIKES VIEWER - WEB INTERFACE")
    print("="*60)
    print("\n🌐 Abre tu navegador en: http://localhost:5555")
    print("⚠️  Usa Ctrl+C para detener el servidor\n")
    print("="*60 + "\n")
    
    socketio.run(app, debug=False, host='0.0.0.0', port=5555, allow_unsafe_werkzeug=True)
